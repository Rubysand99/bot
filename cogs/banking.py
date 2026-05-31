"""
cogs/banking.py — Tích hợp ngân hàng qua Casso webhook
- Nhận webhook POST từ Casso (Vietinbank + MB Bank)
- Phân loại giao dịch vào/ra, lưu MongoDB
- Ví ảo tích phí 500đ/giao dịch (cả vào lẫn ra)
- Lệnh .stats    — Dashboard tổng thu/chi/số dư ước tính
- Lệnh .txlog    — Lịch sử giao dịch ngân hàng gần đây
- Lệnh .wallet   — Xem số dư ví ảo phí
- Lệnh .bankset  — Cài kênh log ngân hàng
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
WEBHOOK_PORT   = int(os.getenv("BANKING_WEBHOOK_PORT", "8080"))
WEBHOOK_PATH   = "/casso"
CASSO_SECRET   = os.getenv("CASSO_SECRET", "")
BANK_LOG_ENV   = os.getenv("BANK_LOG_CHANNEL_ID", "0")
MAX_TX_HISTORY = 500

FEE_PER_TX = 500  # đ phí mỗi giao dịch (cả vào lẫn ra)

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
        "log_channel":    int(BANK_LOG_ENV) if BANK_LOG_ENV != "0" else 0,
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
    data["banking_txs"] = data["banking_txs"][-MAX_TX_HISTORY:]
    save_data(data)

# ── Ví ảo phí ──────────────────────────────

def get_wallet_balance() -> int:
    """Trả về số dư ví ảo phí (đơn vị: đồng)."""
    return load_data().get("fee_wallet", 0)

def add_wallet_fee(amount: int = FEE_PER_TX):
    """Cộng phí vào ví ảo."""
    data = load_data()
    data["fee_wallet"] = data.get("fee_wallet", 0) + amount
    save_data(data)

def reset_wallet_balance():
    """Reset ví ảo về 0 (dùng khi admin xác nhận đã thu phí)."""
    data = load_data()
    data["fee_wallet"] = 0
    save_data(data)

# ── Misc helpers ───────────────────────────

def fmt_vnd(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{abs(amount):,}đ".replace(",", ".")

def _bank_label(bank_str: str) -> str:
    s = str(bank_str).upper()
    for k, v in BANK_NAMES.items():
        if k in s:
            return v
    return bank_str or "N/A"

def _stats_period(txs: list, since: datetime) -> dict:
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
        # SePay gửi header: Authorization: Apikey <key>
        if CASSO_SECRET:
            auth = request.headers.get("Authorization", "")
            # Chấp nhận cả "Apikey xxx" lẫn raw token (tuỳ cấu hình SePay)
            token = auth.replace("Apikey ", "").strip()
            if token != CASSO_SECRET:
                log.warning("[BANKING] ⚠️ Webhook nhận request sai API key")
                return web.Response(status=401, text="Unauthorized")

        try:
            payload = await request.json()
        except Exception:
            return web.Response(status=400, text="Bad JSON")

        # ── SePay payload format ──────────────────────────────────────
        # {
        #   "id": 1,
        #   "gateway": "MB Bank",
        #   "transactionDate": "2026-05-30 22:00:00",
        #   "accountNumber": "0123456789",
        #   "subAccount": null,
        #   "code": null,
        #   "content": "CHUYEN KHOAN MA DON 12345",
        #   "transferType": "in",          ← "in" hoặc "out"
        #   "transferAmount": 500000,      ← luôn dương
        #   "accumulated": 2500000,
        #   "referenceCode": "FT26001234",
        #   "description": "..."
        # }
        # SePay có thể gửi 1 object hoặc wrap trong "data": [...]
        # ─────────────────────────────────────────────────────────────
        if "data" in payload:
            transactions = payload["data"]
            if not isinstance(transactions, list):
                transactions = [transactions]
        elif "id" in payload:
            # SePay gửi thẳng 1 object
            transactions = [payload]
        else:
            transactions = []

        for tx_raw in transactions:
            await self.cog.process_sepay_tx(tx_raw)

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
    # XỬ LÝ GIAO DỊCH TỪ SEPAY
    # ──────────────────────────────────────

    async def process_sepay_tx(self, raw: dict):
        """
        SePay payload:
          transferType:    "in" | "out"
          transferAmount:  số dương
          transactionDate: "YYYY-MM-DD HH:MM:SS"
          gateway:         tên ngân hàng
          referenceCode:   mã GD
          content:         nội dung CK
          accumulated:     số dư sau GD
        """
        try:
            direction  = raw.get("transferType", "in").lower()
            amount     = abs(int(raw.get("transferAmount", 0)))
            desc       = raw.get("content") or raw.get("description", "")
            bank_name  = raw.get("gateway", "MB Bank")
            tid        = str(raw.get("referenceCode") or raw.get("id", ""))
            when_str   = raw.get("transactionDate", "")
            balance    = raw.get("accumulated")

            try:
                tx_time = datetime.strptime(when_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                tx_time = datetime.now(timezone.utc)

            # Bỏ qua TID trùng
            existing = get_bank_txs()
            if tid and any(t.get("tid") == tid for t in existing):
                log.info(f"[BANKING] ℹ️ Bỏ qua TID trùng: {tid}")
                return

            # Cộng phí 500đ vào ví ảo
            add_wallet_fee(FEE_PER_TX)
            wallet_bal = get_wallet_balance()

            tx = {
                "tid":       tid,
                "direction": direction,
                "amount":    amount,
                "bank":      bank_name,
                "desc":      desc,
                "balance":   balance,
                "time":      tx_time.isoformat(),
                "fee":       FEE_PER_TX,
            }
            append_bank_tx(tx)

            await self._notify_discord(tx, wallet_bal)

        except Exception as e:
            log.error(f"[BANKING] ❌ Lỗi xử lý giao dịch SePay: {e}")

    # ──────────────────────────────────────
    # THÔNG BÁO DISCORD
    # ──────────────────────────────────────

    async def _notify_discord(self, tx: dict, wallet_bal: int):
        cfg   = get_banking_cfg()
        ch_id = cfg.get("log_channel", 0)
        if not ch_id:
            return
        ch = await get_or_fetch_channel(self.bot, ch_id)
        if not ch:
            return

        is_in = tx["direction"] == "in"
        color = 0x57F287 if is_in else 0xED4245
        icon  = "📥" if is_in else "📤"
        label = "Tiền Vào" if is_in else "Tiền Ra"

        embed = discord.Embed(
            title=f"{icon}  {label} — {tx['bank']}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        # Số tiền GD
        embed.add_field(
            name="💵 Số tiền",
            value=f"**{fmt_vnd(tx['amount'])}**",
            inline=True,
        )

        # Số dư tài khoản thật (nếu Casso trả về)
        if tx.get("balance") is not None:
            embed.add_field(
                name="🏦 Số dư TK",
                value=fmt_vnd(int(tx["balance"])),
                inline=True,
            )

        embed.add_field(
            name="🏛️ Ngân hàng",
            value=tx["bank"],
            inline=True,
        )

        # Nội dung chuyển khoản
        if tx.get("desc"):
            embed.add_field(
                name="📝 Nội dung",
                value=tx["desc"][:200],
                inline=False,
            )

        # Ví ảo phí — luôn hiển thị
        embed.add_field(
            name="💼 Ví ảo phí",
            value=(
                f"Phí GD này: **-{fmt_vnd(FEE_PER_TX)}**\n"
                f"Số dư ví: **{fmt_vnd(wallet_bal)}**"
            ),
            inline=False,
        )

        if tx.get("tid"):
            embed.set_footer(text=f"TID: {tx['tid']}  •  {tx['time'][:19]}")

        try:
            await ch.send(embed=embed)
        except Exception as e:
            log.error(f"[BANKING] ❌ Không gửi được Discord: {e}")

    # ──────────────────────────────────────
    # LỆNH .wallet
    # ──────────────────────────────────────

    @commands.command(name="wallet")
    async def wallet_cmd(self, ctx):
        """Xem số dư ví ảo phí giao dịch. Dùng: .wallet"""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

        txs       = get_bank_txs()
        wallet    = get_wallet_balance()
        total_txs = len(txs)

        # Đếm số GD có phí (tất cả GD đã lưu)
        fee_txs = sum(1 for t in txs if t.get("fee", 0) > 0)

        embed = discord.Embed(
            title="💼  Ví Ảo Phí Giao Dịch",
            color=0xF1C40F,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="💰 Số dư hiện tại",
            value=f"**{fmt_vnd(wallet)}**",
            inline=True,
        )
        embed.add_field(
            name="📋 Số GD tính phí",
            value=f"**{fee_txs}** GD",
            inline=True,
        )
        embed.add_field(
            name="💸 Phí mỗi GD",
            value=f"**{fmt_vnd(FEE_PER_TX)}** / GD",
            inline=True,
        )
        embed.add_field(
            name="ℹ️ Ghi chú",
            value=(
                f"Phí **{fmt_vnd(FEE_PER_TX)}** được thu tự động mỗi khi có giao dịch "
                f"vào hoặc ra.\nDùng `.walletreset` để reset về 0 sau khi đã thu phí."
            ),
            inline=False,
        )
        embed.set_footer(text="TuyTam Store  •  Ví ảo chỉ theo dõi, không phải số dư thật")
        await ctx.reply(embed=embed)

    @commands.command(name="walletreset")
    async def walletreset_cmd(self, ctx):
        """Reset ví ảo phí về 0. Dùng: .walletreset"""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

        old_bal = get_wallet_balance()
        reset_wallet_balance()

        embed = discord.Embed(
            title="🔄  Reset Ví Ảo Phí",
            color=0x95A5A6,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="💰 Số dư trước", value=fmt_vnd(old_bal), inline=True)
        embed.add_field(name="💰 Số dư sau",   value=fmt_vnd(0),       inline=True)
        embed.add_field(name="👤 Bởi",         value=ctx.author.mention, inline=True)
        await ctx.reply(embed=embed)

        await send_log(self.bot, "BANKING", "Reset Ví Ảo Phí",
            fields=[
                ("💰 Số dư cũ",  fmt_vnd(old_bal),     True),
                ("👤 Bởi",       ctx.author.mention,   True),
            ],
            user=ctx.author,
        )

    # ──────────────────────────────────────
    # LỆNH .stats
    # ──────────────────────────────────────

    @commands.command(name="stats")
    async def stats_cmd(self, ctx):
        """Dashboard tổng thu/chi ngân hàng."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

        txs = get_bank_txs()
        now = datetime.now(timezone.utc)

        today_s = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_s  = today_s - timedelta(days=now.weekday())
        month_s = today_s.replace(day=1)

        day_s   = _stats_period(txs, today_s)
        week_s2 = _stats_period(txs, week_s)
        mon_s   = _stats_period(txs, month_s)
        all_s   = _stats_period(txs, datetime.min.replace(tzinfo=timezone.utc))

        from core.data import load_data as _ld
        data = _ld()
        spent_map  = data.get("user_total_spent", {})
        top_buyers = sorted(spent_map.items(), key=lambda x: x[1], reverse=True)[:5]

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

        wallet = get_wallet_balance()

        embed = discord.Embed(
            title="📊  Dashboard Ngân Hàng",
            color=0x5865F2,
            timestamp=now,
        )
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
        # Ví ảo tóm tắt trong .stats
        embed.add_field(
            name="💼 Ví ảo phí",
            value=f"**{fmt_vnd(wallet)}** ({len(txs)} GD × {fmt_vnd(FEE_PER_TX)})\nDùng `.wallet` để xem chi tiết",
            inline=False,
        )
        if top_buyers:
            lines  = []
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
            title=f"📜  Lịch Sử Giao Dịch — {limit} GD gần nhất",
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
            cfg   = get_banking_cfg()
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

    @discord.app_commands.command(name="wallet", description="Xem số dư ví ảo phí GD")
    async def slash_wallet(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin mới dùng được.", ephemeral=True)
        await interaction.response.defer()
        ctx_like = type("FakeCtx", (), {
            "author": interaction.user,
            "guild":  interaction.guild,
            "reply":  lambda self2, *a, **kw: interaction.followup.send(*a, **kw),
        })()
        await self.wallet_cmd(ctx_like)


async def setup(bot: commands.Bot):
    await bot.add_cog(BankingCog(bot))
