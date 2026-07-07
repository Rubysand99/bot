"""
cogs/seller.py — Seller Subscription System
Lưu data vào bot_data document (load_data/save_data) — giống các module khác.

Lệnh admin:
  .seller add @user [days]     — Thêm mới hoặc gia hạn (mặc định 30 ngày)
  .seller remove @user         — Xoá seller
  .seller list                 — Danh sách tất cả seller
  .seller panel [@user]        — Gửi embed thông tin seller

Lệnh seller:
  .myseller                    — Xem thông tin gói của mình
"""

import datetime
import discord
from discord.ext import commands, tasks

from core.data import (
    ADMIN_IDS, load_data, save_data, set_current_guild,
    wait_data_cache_ready,
)
from cogs.logger import send_log

COLOR_OK      = 0x57F287
COLOR_WARN    = 0xFEE75C
COLOR_EXPIRED = 0xED4245
COLOR_INFO    = 0x5865F2

# ── Helpers data (lưu vào bot_data["seller_subs"]) ─────────────────────────────

def _get_all(guild_id: int) -> dict:
    """Trả về dict {str(user_id): doc} cho guild."""
    return load_data().get("seller_subs", {}).get(str(guild_id), {})

def _get_one(guild_id: int, user_id: int) -> dict | None:
    return _get_all(guild_id).get(str(user_id))

def _save_one(guild_id: int, user_id: int, doc: dict):
    data = load_data()
    subs = data.setdefault("seller_subs", {})
    guild_subs = subs.setdefault(str(guild_id), {})
    guild_subs[str(user_id)] = doc
    save_data(data)

def _delete_one(guild_id: int, user_id: int):
    data = load_data()
    subs = data.get("seller_subs", {})
    guild_subs = subs.get(str(guild_id), {})
    guild_subs.pop(str(user_id), None)
    save_data(data)

def is_active_seller(guild_id: int, user_id: int) -> bool:
    """Trả về True nếu user có subscription còn hạn."""
    doc = _get_one(guild_id, user_id)
    if not doc:
        return False
    expires_str = doc.get("expires_at")
    if not expires_str:
        return False
    try:
        expires_at = datetime.datetime.fromisoformat(expires_str)
        return expires_at > datetime.datetime.now(datetime.timezone.utc)
    except Exception:
        return False

# ── Build embed ─────────────────────────────────────────────────────────────────

def _build_embed(member: discord.Member, doc: dict, guild: discord.Guild) -> discord.Embed:
    now = datetime.datetime.now(datetime.timezone.utc)

    expire_str_raw = doc.get("expires_at")
    if expire_str_raw:
        expire_dt = datetime.datetime.fromisoformat(expire_str_raw)
        expire_ts = int(expire_dt.timestamp())
        if expire_dt < now:
            color = COLOR_EXPIRED
            time_left = "❌ Đã hết hạn"
        else:
            delta = expire_dt - now
            days_left = delta.days
            if days_left <= 3:
                color = COLOR_WARN
                time_left = f"⚠️ Còn {days_left} ngày"
            else:
                color = COLOR_OK
                time_left = f"✅ Còn {days_left} ngày"
        expire_display = f"<t:{expire_ts}:F> ({time_left})"
    else:
        color = COLOR_INFO
        expire_display = "Không xác định"

    embed = discord.Embed(
        title="Chào Mừng Chủ Shop",
        description=f"Chào mừng {member.mention}! Shop của bạn đã sẵn sàng hoạt động.",
        color=color,
        timestamp=now,
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(
        name="📋 NỘI QUY SHOP",
        value=(
            "**Nghiêm cấm lừa đảo** — Vi phạm sẽ bị ban vĩnh viễn và báo cáo.\n"
            "**Không spam** — Cấm gửi tin nhắn rác, quảng cáo ngoài kênh shop.\n"
            "**Không hoàn tiền (Chargeback)** — Mọi giao dịch là cuối cùng.\n"
            "**Giao dịch qua trung gian** — Khuyến khích sử dụng admin làm trung gian."
        ),
        inline=False,
    )

    embed.add_field(
        name="⏳ THỜI HẠN SHOP",
        value=f"Hết hạn: {expire_display}",
        inline=False,
    )

    joined_str = doc.get("joined_at")
    if joined_str:
        joined_ts = int(datetime.datetime.fromisoformat(joined_str).timestamp())
        embed.add_field(name="📅 Ngày tham gia", value=f"<t:{joined_ts}:D>", inline=True)

    total_days = doc.get("total_days_paid", 0)
    embed.add_field(name="💰 Tổng ngày đã mua", value=f"{total_days} ngày", inline=True)

    embed.set_footer(text=f"Market Management System | {guild.name}")
    return embed


# ── Cog ─────────────────────────────────────────────────────────────────────────

class SellerCog(commands.Cog, name="Seller"):
    def __init__(self, bot):
        self.bot = bot
        self.check_expiry_loop.start()

    def cog_unload(self):
        self.check_expiry_loop.cancel()

    # Auto check hết hạn mỗi giờ
    @tasks.loop(hours=1)
    async def check_expiry_loop(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        warn_threshold = now + datetime.timedelta(days=3)

        for guild in self.bot.guilds:
            set_current_guild(guild.id)  # task nền không có context tự nhiên như lệnh/nút bấm
            subs = _get_all(guild.id)
            for uid_str, doc in subs.items():
                expires_str = doc.get("expires_at")
                if not expires_str:
                    continue
                expires_at = datetime.datetime.fromisoformat(expires_str)
                uid = int(uid_str)

                if expires_at < now and not doc.get("notified_expire"):
                    member = guild.get_member(uid)
                    name = member.display_name if member else f"ID:{uid}"
                    await send_log(self.bot, "INFO", "🔴 Seller hết hạn",
                        fields=[("Seller", name, True),
                                ("Hết hạn", f"<t:{int(expires_at.timestamp())}:R>", True)],
                        guild_id=guild.id)
                    doc["notified_expire"] = True
                    _save_one(guild.id, uid, doc)

                elif now < expires_at < warn_threshold and not doc.get("notified_warn"):
                    member = guild.get_member(uid)
                    name = member.display_name if member else f"ID:{uid}"
                    await send_log(self.bot, "INFO", "⚠️ Seller sắp hết hạn",
                        fields=[("Seller", name, True),
                                ("Hết hạn", f"<t:{int(expires_at.timestamp())}:R>", True)],
                        guild_id=guild.id)
                    doc["notified_warn"] = True
                    _save_one(guild.id, uid, doc)

    @check_expiry_loop.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()
        # FIX: init_data_cache() (chạy trong on_ready) hoàn tất ĐỘC LẬP và muộn hơn
        # wait_until_ready() ~2-3s → nếu không chờ thêm, vòng lặp đầu chạy khi
        # _data_cache chưa nạp xong → "Guild X chưa có trong cache".
        await wait_data_cache_ready()

    # ── .seller ──────────────────────────────────────────────────────────────────

    @commands.group(name="seller", invoke_without_command=True)
    async def seller_group(self, ctx):
        if ctx.author.id not in ADMIN_IDS:
            return
        await ctx.send("❓ Dùng: `.seller add/remove/list/panel`", delete_after=10)

    @seller_group.command(name="add")
    async def seller_add(self, ctx, member: discord.Member, days: int = 30):
        if ctx.author.id not in ADMIN_IDS:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        doc = _get_one(ctx.guild.id, member.id)

        if doc and doc.get("expires_at"):
            old_expire = datetime.datetime.fromisoformat(doc["expires_at"])
            if old_expire > now:
                new_expire = old_expire + datetime.timedelta(days=days)
                action = "gia hạn"
            else:
                new_expire = now + datetime.timedelta(days=days)
                action = "gia hạn (hết hạn rồi)"
        else:
            new_expire = now + datetime.timedelta(days=days)
            action = "thêm mới"

        total_days = (doc.get("total_days_paid", 0) if doc else 0) + days
        joined_at = doc.get("joined_at") if doc else now.isoformat()

        new_doc = {
            "username":        str(member),
            "expires_at":      new_expire.isoformat(),
            "total_days_paid": total_days,
            "joined_at":       joined_at,
            "notified_warn":   False,
            "notified_expire": False,
        }
        _save_one(ctx.guild.id, member.id, new_doc)

        embed = discord.Embed(title=f"✅ Seller {action}", color=COLOR_OK, timestamp=now)
        embed.add_field(name="Seller",      value=member.mention, inline=True)
        embed.add_field(name="Thêm (ngày)", value=str(days),      inline=True)
        embed.add_field(name="Hết hạn mới",
                        value=f"<t:{int(new_expire.timestamp())}:F>", inline=False)
        embed.set_footer(text=f"Bởi {ctx.author.display_name}")
        await ctx.reply(embed=embed)

        await send_log(self.bot, "INFO", f"Seller {action}",
            fields=[("Seller", f"{member} ({member.id})", False),
                    ("Ngày thêm", str(days), True),
                    ("Hết hạn", f"<t:{int(new_expire.timestamp())}:F>", True),
                    ("Admin", str(ctx.author), True)],
            guild_id=ctx.guild.id)

    @seller_group.command(name="remove")
    async def seller_remove(self, ctx, member: discord.Member):
        if ctx.author.id not in ADMIN_IDS:
            return
        if not _get_one(ctx.guild.id, member.id):
            return await ctx.send(f"❌ {member.mention} không phải seller.", delete_after=8)

        _delete_one(ctx.guild.id, member.id)
        await ctx.send(f"🗑️ Đã xoá seller {member.mention}.")
        await send_log(self.bot, "INFO", "Seller bị xoá",
            fields=[("Seller", f"{member} ({member.id})", True),
                    ("Admin", str(ctx.author), True)],
            guild_id=ctx.guild.id)

    @seller_group.command(name="list")
    async def seller_list(self, ctx):
        if ctx.author.id not in ADMIN_IDS:
            return

        subs = _get_all(ctx.guild.id)
        if not subs:
            return await ctx.send("📭 Chưa có seller nào.", delete_after=8)

        now = datetime.datetime.now(datetime.timezone.utc)
        lines = []
        for uid_str, doc in subs.items():
            member = ctx.guild.get_member(int(uid_str))
            name = member.mention if member else f"`{doc.get('username', uid_str)}`"
            expires_str = doc.get("expires_at")
            if not expires_str:
                status = "❓"; expire_display = "N/A"
            else:
                expire_dt = datetime.datetime.fromisoformat(expires_str)
                expire_display = f"<t:{int(expire_dt.timestamp())}:d>"
                if expire_dt < now:
                    status = "🔴"
                elif expire_dt - now <= datetime.timedelta(days=3):
                    status = "🟡"
                else:
                    status = "🟢"
            lines.append((expire_dt if expires_str else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
                          f"{status} {name} — hết hạn {expire_display}"))

        lines.sort(key=lambda x: x[0])
        text_lines = [t for _, t in lines]

        # Gửi theo chunk 20 dòng
        chunks = [text_lines[i:i+20] for i in range(0, len(text_lines), 20)]
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"📋 Danh sách Seller ({len(subs)}) — Trang {i+1}/{len(chunks)}",
                description="\n".join(chunk),
                color=COLOR_INFO,
                timestamp=now,
            )
            embed.set_footer(text="🟢 Còn hạn  🟡 Sắp hết (≤3 ngày)  🔴 Hết hạn")
            await ctx.send(embed=embed)

    @seller_group.command(name="panel")
    async def seller_panel(self, ctx, member: discord.Member = None):
        if ctx.author.id not in ADMIN_IDS:
            return
        await self._send_panel(ctx, member or ctx.author)

    # ── .myseller ────────────────────────────────────────────────────────────────

    @commands.command(name="myseller")
    async def my_seller(self, ctx):
        await self._send_panel(ctx, ctx.author)

    # ── Helper ───────────────────────────────────────────────────────────────────

    async def _send_panel(self, ctx, member: discord.Member):
        doc = _get_one(ctx.guild.id, member.id)
        if not doc:
            return await ctx.send(
                f"❌ {member.mention} chưa được đăng ký làm seller.", delete_after=10)
        await ctx.send(embed=_build_embed(member, doc, ctx.guild))


async def setup(bot):
    await bot.add_cog(SellerCog(bot))
