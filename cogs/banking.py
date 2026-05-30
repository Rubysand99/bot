"""
cogs/banking.py — Tích hợp ngân hàng qua Casso webhook
- Nhận webhook POST từ Casso (Vietinbank + MB Bank)
- Phân loại giao dịch vào/ra, lưu MongoDB
- Lệnh .stats  — Dashboard tổng thu/chi/số dư ước tính
- Lệnh .txlog  — Lịch sử giao dịch ngân hàng gần đây
- Lệnh .bankset — Cài kênh log ngân hàng
"""

import os
import asyncio
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from aiohttp import web

import discord
from discord.ext import commands

from core.data import (
    ADMIN_IDS, load_data, save_data, can_use_dangerous_cmd,
    get_or_fetch_channel, _uname_plain,
)
from cogs.logger import send_log

log = logging.getLogger("banking")

# ══════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════
WEBHOOK_PORT      = int(os.getenv("BANKING_WEBHOOK_PORT", "8080"))
WEBHOOK_PATH      = "/casso"
CASSO_SECRET      = os.getenv("CASSO_SECRET", "")   # Casso → Security token
BANK_LOG_ENV      = os.getenv("BANK_LOG_CHANNEL_ID", "0")
MAX_TX_HISTORY    = 500

BANK_NAMES = {
    "970415": "Vietinbank",
    "970422": "MB Bank",
    "MB":     "MB Bank",
    "VTB":    "Vietinbank",
}

# ══════════════════════════════════════════
# DATA HELPERS
# ══════════════════════════════════════════

def get_banking_cfg() -> dict:
    return load_data().get("banking_cfg", {
        "log_channel": int(BANK_LOG_ENV) if BANK_LOG_ENV != "0" else 0,
        "notify_channel": 0,
    })

def save_banking_cfg(cfg: dict):
    data = load_data()
    data["banking_cfg"] = cfg
    save_data(data)

def get_bank_txs() -> list:
    return load_data().get("banking_txs", [])

def append_bank_tx(tx: dict):
    data = load_data()
    data.setdefault("banking_txs", [])
    data["banking_txs"].append(tx)
    data["banking_txs"] = data["banking_txs"][-MAX_TX_HISTORY:]  # giữ 500 giao dịch gần nhất
    save_data(data)

def fmt_vnd(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{abs(amount):,}đ".replace(",", ".")

def _bank_label(bank_str: str) -> str:
    """Trả về tên ngân hàng dễ đọc từ bin hoặc bankCode."""
    s = str(bank_str).upper()
    for k, v in BANK_NAMES.items():
        if k in s:
            return v
    return bank_str or "N/A"

def _stats_period(txs: list, since: datetime) -> dict:
    """Tính tổng thu/chi trong khoảng thời gian."""
    total_in = total_out = 0
    for tx in txs:
        try:
            tx_time = datetime.fromisoformat(tx["time"])
            if tx_time.tzinfo is None:
                tx_time = tx_time.replace(tzinfo=timezone.utc)
            if tx_time < since:
                continue
        except Exception:
            continue
        if tx["direction"] == "in":
            total_in += tx["amount"]
        else:
            total_out += tx["amount"]
    return {"in": total_in, "out": total_out, "net": total_in - total_out}

# ══════════════════════════════════════════
# WEBHOOK SERVER (aiohttp)
# ══════════════════════════════════════════

class CassoWebhookServer:
    def __init__(self, cog: "BankingCog"):
        self.cog  = cog
        self.app  = web.Application()
        self.app.router.add_post(WEBHOOK_PATH, self.handle)
        self._runner = None

    async def start(self):
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", WEBHOOK_PORT)
        await site.start()
        log.info(f"[BANKING] ✅ Webhook server chạy trên port {WEBHOOK_PORT}{WEBHOOK_PATH}")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    async def handle(self, request: web.Request) -> web.Response:
        # ── Xác thực secret token từ Casso ──
        if CASSO_SECRET:
            token = request.headers.get("Secure-Token", "")
            if token != CASSO_SECRET:
                log.warning("[BANKING] ⚠️ Webhook nhận request sai secret token")
                return web.Response(status=401, text="Unauthorized")

        try:
            payload = await request.json()
        except Exception:
            return web.Response(status=400, text="Bad JSON")

        # ── Casso gửi list giao dịch trong "data" ──
        transactions = payload.get("data", [])
        if not isinstance(transactions, list):
            transactions = [transactions]

        for tx_raw in transactions:
            await self.cog.process_casso_tx(tx_raw)

        return web.Response(status=200, text="OK")


# ══════════════════════════════════════════
# BANKING COG
# ══════════════════════════════════════════

class BankingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot    = bot
        self.server = CassoWebhookServer(self)
        self._task  = None

    async def cog_load(self):
        self._task = asyncio.create_task(self.server.start())
        log.info("[BANKING] ✅ BankingCog loaded")

    async def cog_unload(self):
        await self.server.stop()
        if self._task:
            self._task.cancel()

    # ──────────────────────────────────────
    # XỬ LÝ GIAO DỊCH TỪ CASSO
    # ──────────────────────────────────────

    async def process_casso_tx(self, raw: dict):
        """
        Casso payload mẫu:
        {
          "id": 123456,
          "tid": "FT24001234567",
          "description": "CHUYEN KHOAN TU NGUYEN VAN A MA DON 12345",
          "amount": 500000,
          "cusum_balance": 2500000,
          "when": "2026-05-30 08:00:00",
          "bank_sub_acc_id": "0123456789",
          "subAccId": "VTB_0123456789",
          "bankName": "VietinBank",
          "bankAbbreviation": "VTB",
          "virtualAccount": "",
          "virtualAccountName": ""
        }
        amount > 0 → tiền vào, amount < 0 → tiền ra
        """
        try:
            amount_raw = int(raw.get("amount", 0))
            direction  = "in" if amount_raw >= 0 else "out"
            amount     = abs(amount_raw)
            desc       = raw.get("description", "")
            bank_name  = raw.get("bankName") or raw.get("bankAbbreviation") or _bank_label(raw.get("subAccId", ""))
            tid        = str(raw.get("tid") or raw.get("id", ""))
            when_str   = raw.get("when", "")
            balance    = raw.get("cusum_balance")

            # Parse thời gian
            try:
                tx_time = datetime.strptime(when_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                tx_time = datetime.now(timezone.utc)

            # Kiểm tra trùng TID
            existing = get_bank_txs()
            if tid and any(t.get("tid") == tid for t in existing):
                log.info(f"[BANKING] ℹ️ Bỏ qua TID trùng: {tid}")
                return

            # Lưu giao dịch
            tx = {
                "tid":       tid,
                "direction": direction,
                "amount":    amount,
                "bank":      bank_name,
                "desc":      desc,
                "balance":   balance,
                "time":      tx_time.isoformat(),
            }
            append_bank_tx(tx)

            # Gửi Discord embed
            await self._notify_discord(tx)

        except Exception as e:
            log.error(f"[BANKING] ❌ Lỗi xử lý giao dịch: {e}")

    async def _notify_discord(self, tx: dict):
        cfg = get_banking_cfg()
        ch_id = cfg.get("log_channel", 0)
        if not ch_id:
            return
        ch = await get_or_fetch_channel(self.bot, ch_id)
        if not ch:
            return

        is_in  = tx["direction"] == "in"
        color  = 0x57F287 if is_in else 0xED4245
        icon   = "📥" if is_in else "📤"
        title  = f"{icon}  Tiền {'Vào' if is_in else 'Ra'} — {tx['bank']}"

        embed = discord.Embed(title=title, color=color,
                              timestamp=datetime.now(timezone.utc))
        embed.add_field(name="💵 Số tiền",
                        value=f"**{fmt_vnd(tx['amount'])}**", inline=True)
        if tx.get("balance") is not None:
            embed.add_field(name="🏦 Số dư TK",
                            value=fmt_vnd(int(tx["balance"])), inline=True)
        embed.add_field(name="🏛️ Ngân hàng",
                        value=tx["bank"], inline=True)
        if tx.get("desc"):
            embed.add_field(name="📝 Nội dung",
                            value=tx["desc"][:200], inline=False)
        if tx.get("tid"):
            embed.set_footer(text=f"TID: {tx['tid']}  •  {tx['time'][:19]}")

        try:
            await ch.send(embed=embed)
        except Exception as e:
            log.error(f"[BANKING] ❌ Không gửi được Discord: {e}")

    # ──────────────────────────────────────
    # LỆNH .stats
    # ──────────────────────────────────────

    @commands.command(name="stats")
    async def stats_cmd(self, ctx):
        """Dashboard tổng thu/chi ngân hàng (Vietinbank + MB Bank)."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

        txs = get_bank_txs()
        now = datetime.now(timezone.utc)

        today_s  = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_s   = today_s - timedelta(days=now.weekday())
        month_s  = today_s.replace(day=1)

        day_s   = _stats_period(txs, today_s)
        week_s2 = _stats_period(txs, week_s)
        mon_s   = _stats_period(txs, month_s)
        all_s   = _stats_period(txs, datetime.min.replace(tzinfo=timezone.utc))

        # Top buyer (dựa theo người chuyển khoản — từ description)
        # (mô tả đơn giản: dùng dữ liệu user_total_spent từ ticket system)
        from core.data import load_data as _ld
        data = _ld()
        spent_map = data.get("user_total_spent", {})
        top_buyers = sorted(spent_map.items(), key=lambda x: x[1], reverse=True)[:5]

        # Tách giao dịch theo ngân hàng
        vtb_in = vtb_out = mb_in = mb_out = 0
        for tx in txs:
            bank = tx.get("bank", "")
            amt  = tx["amount"]
            if "Vietin" in bank or "VTB" in bank:
                if tx["direction"] == "in":  vtb_in  += amt
                else:                        vtb_out += amt
            elif "MB" in bank:
                if tx["direction"] == "in":  mb_in  += amt
                else:                        mb_out += amt

        embed = discord.Embed(
            title="📊  Dashboard Ngân Hàng",
            color=0x5865F2,
            timestamp=now,
        )

        # Thu/chi theo kỳ
        embed.add_field(
            name="📅 Hôm nay",
            value=f"📥 {fmt_vnd(day_s['in'])}\n📤 {fmt_vnd(day_s['out'])}\n💰 {fmt_vnd(day_s['net'])}",
            inline=True,
        )
        embed.add_field(
            name="📆 Tuần này",
            value=f"📥 {fmt_vnd(week_s2['in'])}\n📤 {fmt_vnd(week_s2['out'])}\n💰 {fmt_vnd(week_s2['net'])}",
            inline=True,
        )
        embed.add_field(
            name="🗓️ Tháng này",
            value=f"📥 {fmt_vnd(mon_s['in'])}\n📤 {fmt_vnd(mon_s['out'])}\n💰 {fmt_vnd(mon_s['net'])}",
            inline=True,
        )

        # Tổng toàn thời gian
        embed.add_field(
            name="🏦 Tổng tất cả",
            value=(
                f"📥 Tổng vào: **{fmt_vnd(all_s['in'])}**\n"
                f"📤 Tổng ra:  **{fmt_vnd(all_s['out'])}**\n"
                f"💰 Số dư ước tính: **{fmt_vnd(all_s['net'])}**\n"
                f"🔢 Tổng GD: **{len(txs)}** lần"
            ),
            inline=False,
        )

        # Tách theo ngân hàng
        embed.add_field(
            name="🏛️ Vietinbank",
            value=f"📥 {fmt_vnd(vtb_in)}\n📤 {fmt_vnd(vtb_out)}",
            inline=True,
        )
        embed.add_field(
            name="🏛️ MB Bank",
            value=f"📥 {fmt_vnd(mb_in)}\n📤 {fmt_vnd(mb_out)}",
            inline=True,
        )

        # Top buyer
        if top_buyers:
            lines = []
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, (uid_str, spent) in enumerate(top_buyers):
                member = ctx.guild.get_member(int(uid_str))
                name   = _uname_plain(member) if member else f"<@{uid_str}>"
                lines.append(f"{medals[i]} **{name}** — {fmt_vnd(spent)}")
            embed.add_field(
                name="👥 Top Buyer (theo ticket)",
                value="\n".join(lines),
                inline=False,
            )

        # 3 GD gần nhất
        recent = txs[-3:][::-1]
        if recent:
            lines = []
            for tx in recent:
                icon = "📥" if tx["direction"] == "in" else "📤"
                lines.append(f"{icon} **{fmt_vnd(tx['amount'])}** — {tx['bank']} — `{tx['time'][:10]}`")
            embed.add_field(name="🕐 Giao dịch gần nhất", value="\n".join(lines), inline=False)

        embed.set_footer(text="TuyTam Store  •  Dùng .txlog để xem lịch sử chi tiết")
        await ctx.reply(embed=embed)

    # ──────────────────────────────────────
    # LỆNH .txlog
    # ──────────────────────────────────────

    @commands.command(name="txlog")
    async def txlog_cmd(self, ctx, limit: int = 10):
        """Xem lịch sử giao dịch ngân hàng. Mặc định 10 GD gần nhất."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

        limit = max(1, min(limit, 25))
        txs   = get_bank_txs()
        if not txs:
            return await ctx.reply("📭 Chưa có giao dịch ngân hàng nào được ghi nhận.")

        recent = txs[-limit:][::-1]
        embed  = discord.Embed(
            title=f"📜  Lịch Sử Giao Dịch Ngân Hàng — {limit} GD gần nhất",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        lines = []
        for tx in recent:
            icon = "📥" if tx["direction"] == "in" else "📤"
            ts   = tx["time"][:16].replace("T", " ")
            desc = f" • {tx['desc'][:40]}" if tx.get("desc") else ""
            lines.append(
                f"{icon} **{fmt_vnd(tx['amount'])}** [{tx['bank']}] `{ts}`{desc}"
            )
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Tổng {len(txs)} GD được lưu  •  Dùng .txlog <số> để xem nhiều hơn")
        await ctx.reply(embed=embed)

    # ──────────────────────────────────────
    # LỆNH .bankset
    # ──────────────────────────────────────

    @commands.command(name="bankset")
    async def bankset_cmd(self, ctx, channel: discord.TextChannel = None):
        """Cài kênh log giao dịch ngân hàng. Dùng: .bankset #kênh"""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
        if channel is None:
            cfg = get_banking_cfg()
            ch_id = cfg.get("log_channel", 0)
            mention = f"<#{ch_id}>" if ch_id else "Chưa cài"
            return await ctx.reply(f"📌 Kênh log ngân hàng hiện tại: {mention}\n💡 Dùng `.bankset #kênh` để đổi.")

        cfg = get_banking_cfg()
        cfg["log_channel"] = channel.id
        save_banking_cfg(cfg)
        await ctx.reply(f"✅ Đã cài kênh log ngân hàng: {channel.mention}")
        await send_log(self.bot, "BANKING_CFG", "Cài Kênh Log Ngân Hàng",
            fields=[("📌 Kênh", channel.mention, True), ("👤 Bởi", ctx.author.mention, True)],
            user=ctx.author)

    # ──────────────────────────────────────
    # SLASH COMMANDS
    # ──────────────────────────────────────

    @discord.app_commands.command(name="stats", description="Dashboard thu/chi ngân hàng")
    async def slash_stats(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin mới dùng được.", ephemeral=True)
        # Giả lập ctx để tái dùng logic
        await interaction.response.defer()
        ctx_like = type("FakeCtx", (), {
            "author": interaction.user,
            "guild":  interaction.guild,
            "reply":  lambda self2, *a, **kw: interaction.followup.send(*a, **kw),
        })()
        await self.stats_cmd(ctx_like)

    @discord.app_commands.command(name="txlog", description="Lịch sử giao dịch ngân hàng")
    @discord.app_commands.describe(limit="Số GD muốn xem (mặc định 10, tối đa 25)")
    async def slash_txlog(self, interaction: discord.Interaction, limit: int = 10):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin mới dùng được.", ephemeral=True)
        await interaction.response.defer()
        ctx_like = type("FakeCtx", (), {
            "author": interaction.user,
            "guild":  interaction.guild,
            "reply":  lambda self2, *a, **kw: interaction.followup.send(*a, **kw),
        })()
        await self.txlog_cmd(ctx_like, limit)


async def setup(bot: commands.Bot):
    await bot.add_cog(BankingCog(bot))
