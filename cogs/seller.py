"""
cogs/seller.py — Seller Subscription System
Quản lý gói thuê kênh bán hàng theo tháng trong server Discord.

Lệnh admin:
  .seller add @user [days]     — Thêm seller mới hoặc gia hạn (mặc định 30 ngày)
  .seller remove @user         — Xoá seller
  .seller list                 — Danh sách tất cả seller
  .seller info @user           — Xem thông tin 1 seller
  .seller panel [@user]        — Gửi embed thông tin seller (giống ảnh mẫu)

Lệnh seller (tự xem):
  .myseller                    — Xem thông tin gói của mình
"""

import discord
from discord.ext import commands, tasks
import datetime
from core.data import ADMIN_IDS, get_or_fetch_channel, send_log

# ── Màu embed ──────────────────────────────────────────────────────────────────
COLOR_OK      = 0x57F287   # xanh lá — còn hạn
COLOR_WARN    = 0xFEE75C   # vàng — sắp hết hạn (≤3 ngày)
COLOR_EXPIRED = 0xED4245   # đỏ — đã hết hạn
COLOR_INFO    = 0x5865F2   # tím


# ── Helper MongoDB ──────────────────────────────────────────────────────────────
async def _get_seller(db, guild_id: int, user_id: int) -> dict | None:
    col = db[f"sellers_{guild_id}"]
    return await col.find_one({"_id": user_id})


async def _upsert_seller(db, guild_id: int, user_id: int, data: dict):
    col = db[f"sellers_{guild_id}"]
    await col.update_one({"_id": user_id}, {"$set": data}, upsert=True)


async def _delete_seller(db, guild_id: int, user_id: int):
    col = db[f"sellers_{guild_id}"]
    await col.delete_one({"_id": user_id})


async def _list_sellers(db, guild_id: int) -> list[dict]:
    col = db[f"sellers_{guild_id}"]
    return await col.find({}).to_list(length=200)


# ── Build embed theo mẫu ảnh ───────────────────────────────────────────────────
def _build_seller_embed(member: discord.Member, doc: dict, guild: discord.Guild) -> discord.Embed:
    expire_dt: datetime.datetime = doc.get("expires_at")
    now = datetime.datetime.utcnow()

    if expire_dt is None:
        color = COLOR_INFO
        status_text = "Không xác định"
        time_left = ""
    elif expire_dt < now:
        color = COLOR_EXPIRED
        status_text = "❌ Đã hết hạn"
        time_left = ""
    else:
        delta = expire_dt - now
        days_left = delta.days
        if days_left <= 3:
            color = COLOR_WARN
            status_text = f"⚠️ Còn {days_left} ngày"
        else:
            color = COLOR_OK
            status_text = f"✅ Còn {days_left} ngày"
        time_left = f"({status_text})"

    # Format ngày hết hạn kiểu Discord timestamp
    expire_ts = int(expire_dt.timestamp()) if expire_dt else None
    expire_str = (
        f"<t:{expire_ts}:F> {time_left}" if expire_ts else "Không xác định"
    )

    embed = discord.Embed(
        title="Chào Mừng Chủ Shop",
        description=f"Chào mừng {member.mention}! Shop của bạn đã sẵn sàng hoạt động.",
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )

    # Ảnh đại diện seller
    embed.set_thumbnail(url=member.display_avatar.url)

    # Nội quy shop
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

    # Thời hạn
    embed.add_field(
        name="⏳ THỜI HẠN SHOP",
        value=f"Hết hạn: {expire_str}",
        inline=False,
    )

    # Info thêm
    joined_at = doc.get("joined_at")
    if joined_at:
        joined_ts = int(joined_at.timestamp())
        embed.add_field(name="📅 Ngày tham gia", value=f"<t:{joined_ts}:D>", inline=True)

    total_days = doc.get("total_days_paid", 0)
    embed.add_field(name="💰 Tổng thời gian đã mua", value=f"{total_days} ngày", inline=True)

    embed.set_footer(text=f"Market Management System | {guild.name}")
    return embed


# ── Cog ────────────────────────────────────────────────────────────────────────
class SellerCog(commands.Cog, name="Seller"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_expiry_loop.start()

    def cog_unload(self):
        self.check_expiry_loop.cancel()

    @property
    def db(self):
        return self.bot.db  # Motor async client từ bot.py

    # ── Auto check hết hạn mỗi giờ ─────────────────────────────────────────────
    @tasks.loop(hours=1)
    async def check_expiry_loop(self):
        """Tự động log khi seller sắp hết hạn (3 ngày) hoặc đã hết hạn."""
        now = datetime.datetime.utcnow()
        warn_threshold = now + datetime.timedelta(days=3)

        for guild in self.bot.guilds:
            sellers = await _list_sellers(self.db, guild.id)
            for doc in sellers:
                expires_at = doc.get("expires_at")
                if not expires_at:
                    continue
                uid = doc["_id"]
                notified_expire = doc.get("notified_expire", False)
                notified_warn   = doc.get("notified_warn", False)

                if expires_at < now and not notified_expire:
                    # Đã hết hạn — chưa thông báo
                    member = guild.get_member(uid)
                    name = member.display_name if member else f"ID:{uid}"
                    await send_log(
                        self.bot, "TICKET",
                        "🔴 Seller hết hạn",
                        fields=[
                            ("Seller", name, True),
                            ("Hết hạn", f"<t:{int(expires_at.timestamp())}:R>", True),
                        ]
                    )
                    await _upsert_seller(self.db, guild.id, uid, {"notified_expire": True})

                elif expires_at < warn_threshold and expires_at > now and not notified_warn:
                    # Sắp hết hạn
                    member = guild.get_member(uid)
                    name = member.display_name if member else f"ID:{uid}"
                    await send_log(
                        self.bot, "TICKET",
                        "⚠️ Seller sắp hết hạn",
                        fields=[
                            ("Seller", name, True),
                            ("Hết hạn", f"<t:{int(expires_at.timestamp())}:R>", True),
                        ]
                    )
                    await _upsert_seller(self.db, guild.id, uid, {"notified_warn": True})

    @check_expiry_loop.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Group lệnh .seller ──────────────────────────────────────────────────────
    @commands.group(name="seller", invoke_without_command=True)
    async def seller_group(self, ctx: commands.Context):
        if ctx.author.id not in ADMIN_IDS:
            return
        await ctx.send(
            "❓ Dùng: `.seller add/remove/list/info/panel`",
            delete_after=10
        )

    # .seller add @user [days]
    @seller_group.command(name="add")
    async def seller_add(self, ctx: commands.Context, member: discord.Member, days: int = 30):
        if ctx.author.id not in ADMIN_IDS:
            return

        now = datetime.datetime.utcnow()
        doc = await _get_seller(self.db, ctx.guild.id, member.id)

        if doc and doc.get("expires_at") and doc["expires_at"] > now:
            # Gia hạn từ ngày hiện tại của họ
            new_expire = doc["expires_at"] + datetime.timedelta(days=days)
            action = "gia hạn"
        else:
            # Thêm mới hoặc hết hạn rồi → tính từ bây giờ
            new_expire = now + datetime.timedelta(days=days)
            action = "thêm mới"

        total_days = (doc.get("total_days_paid", 0) if doc else 0) + days

        await _upsert_seller(self.db, ctx.guild.id, member.id, {
            "username": str(member),
            "expires_at": new_expire,
            "total_days_paid": total_days,
            "joined_at": doc.get("joined_at", now) if doc else now,
            "notified_warn": False,
            "notified_expire": False,
        })

        embed = discord.Embed(
            title=f"✅ Seller {action}",
            color=COLOR_OK,
            timestamp=now,
        )
        embed.add_field(name="Seller", value=member.mention, inline=True)
        embed.add_field(name="Thêm (ngày)", value=str(days), inline=True)
        embed.add_field(
            name="Hết hạn mới",
            value=f"<t:{int(new_expire.timestamp())}:F>",
            inline=False,
        )
        embed.set_footer(text=f"By {ctx.author.display_name}")
        await ctx.send(embed=embed)

        await send_log(
            self.bot, "TICKET",
            f"Seller {action}",
            fields=[
                ("Seller", f"{member} ({member.id})", False),
                ("Ngày thêm", str(days), True),
                ("Hết hạn", f"<t:{int(new_expire.timestamp())}:F>", True),
                ("Admin", str(ctx.author), True),
            ]
        )

    # .seller remove @user
    @seller_group.command(name="remove")
    async def seller_remove(self, ctx: commands.Context, member: discord.Member):
        if ctx.author.id not in ADMIN_IDS:
            return

        doc = await _get_seller(self.db, ctx.guild.id, member.id)
        if not doc:
            await ctx.send(f"❌ {member.mention} không phải seller.", delete_after=8)
            return

        await _delete_seller(self.db, ctx.guild.id, member.id)
        await ctx.send(f"🗑️ Đã xoá seller {member.mention}.")
        await send_log(
            self.bot, "TICKET",
            "Seller bị xoá",
            fields=[
                ("Seller", f"{member} ({member.id})", True),
                ("Admin", str(ctx.author), True),
            ]
        )

    # .seller list
    @seller_group.command(name="list")
    async def seller_list(self, ctx: commands.Context):
        if ctx.author.id not in ADMIN_IDS:
            return

        docs = await _list_sellers(self.db, ctx.guild.id)
        if not docs:
            await ctx.send("📭 Chưa có seller nào.", delete_after=8)
            return

        now = datetime.datetime.utcnow()
        lines = []
        for doc in sorted(docs, key=lambda d: d.get("expires_at", datetime.datetime.min)):
            uid = doc["_id"]
            expires_at = doc.get("expires_at")
            member = ctx.guild.get_member(uid)
            name = member.mention if member else f"`{doc.get('username', uid)}`"

            if not expires_at:
                status = "❓"
            elif expires_at < now:
                status = "🔴"
            elif expires_at - now <= datetime.timedelta(days=3):
                status = "🟡"
            else:
                status = "🟢"

            expire_str = f"<t:{int(expires_at.timestamp())}:d>" if expires_at else "N/A"
            lines.append(f"{status} {name} — hết hạn {expire_str}")

        # Tách thành nhiều embed nếu quá dài
        chunks = []
        chunk = []
        for line in lines:
            chunk.append(line)
            if len(chunk) == 20:
                chunks.append(chunk)
                chunk = []
        if chunk:
            chunks.append(chunk)

        for i, ch in enumerate(chunks):
            embed = discord.Embed(
                title=f"📋 Danh sách Seller ({len(docs)}) — Trang {i+1}/{len(chunks)}",
                description="\n".join(ch),
                color=COLOR_INFO,
                timestamp=now,
            )
            embed.set_footer(text="🟢 Còn hạn  🟡 Sắp hết  🔴 Hết hạn")
            await ctx.send(embed=embed)

    # .seller info @user
    @seller_group.command(name="info")
    async def seller_info(self, ctx: commands.Context, member: discord.Member):
        if ctx.author.id not in ADMIN_IDS:
            return
        await self._send_seller_panel(ctx, member)

    # .seller panel [@user]
    @seller_group.command(name="panel")
    async def seller_panel(self, ctx: commands.Context, member: discord.Member = None):
        if ctx.author.id not in ADMIN_IDS:
            return
        target = member or ctx.author
        await self._send_seller_panel(ctx, target)

    # ── .myseller (self) ────────────────────────────────────────────────────────
    @commands.command(name="myseller")
    async def my_seller(self, ctx: commands.Context):
        await self._send_seller_panel(ctx, ctx.author)

    # ── Helper send panel ───────────────────────────────────────────────────────
    async def _send_seller_panel(self, ctx: commands.Context, member: discord.Member):
        doc = await _get_seller(self.db, ctx.guild.id, member.id)
        if not doc:
            await ctx.send(
                f"❌ {member.mention} chưa được đăng ký làm seller.",
                delete_after=10
            )
            return

        embed = _build_seller_embed(member, doc, ctx.guild)
        await ctx.send(embed=embed)


# ── Setup ───────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(SellerCog(bot))
