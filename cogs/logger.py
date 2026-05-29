"""
cogs/logger.py — Hệ thống log đa kênh.
Mọi cog gọi: await send_log(bot, "TICKET_CREATE", "Tạo ticket", ...)
Mỗi nhóm event được route vào kênh riêng, cài qua .setlog <nhóm> #kênh

Nhóm kênh:
  ticket   → TICKET_CREATE, TICKET_CLOSE, TICKET_DONE, TICKET_CLAIM
  balance  → BALANCE_IN, BALANCE_OUT, BALANCE_SET, BALANCE_RESET
  mod      → MOD_BAN, MOD_KICK, MOD_MUTE, MOD_WARN
  giveaway → GIVEAWAY_START, GIVEAWAY_END, GIVEAWAY_REROLL
  member   → MEMBER_JOIN, MEMBER_LEAVE
  role     → ROLE_ADD, ROLE_REMOVE
  ai       → AI_USED
  admin    → CMD_USED, SLASH_USED, SETTINGS
  general  → INFO, ERROR, INVITE, RATING (fallback)
"""

from datetime import datetime, timezone
import discord
from discord.ext import commands
from core.data import ADMIN_IDS, get_cfg_log_rudy, get_log_channels, get_log_channel_by_group, set_log_channel_db

LOG_ICONS = {
    "TICKET_CREATE":   ("🎫", 0x57F287),
    "TICKET_CLOSE":    ("🔒", 0xED4245),
    "TICKET_DONE":     ("✅", 0x57F287),
    "TICKET_CLAIM":    ("🙋", 0x5865F2),
    "BALANCE_IN":      ("📥", 0x57F287),
    "BALANCE_OUT":     ("📤", 0xED4245),
    "BALANCE_SET":     ("⚙️",  0xFEE75C),
    "BALANCE_RESET":   ("🔄", 0x99AAB5),
    "MOD_BAN":         ("🔨", 0xED4245),
    "MOD_KICK":        ("👢", 0xE67E22),
    "MOD_MUTE":        ("🔇", 0xF0A500),
    "MOD_WARN":        ("⚠️",  0xFEE75C),
    "GIVEAWAY_START":  ("🎉", 0xF1C40F),
    "GIVEAWAY_END":    ("🏆", 0xF1C40F),
    "GIVEAWAY_REROLL": ("🔄", 0xF1C40F),
    "MEMBER_JOIN":     ("📥", 0x57F287),
    "MEMBER_LEAVE":    ("📤", 0xED4245),
    "ROLE_ADD":        ("🏷️", 0x57F287),
    "ROLE_REMOVE":     ("🏷️", 0xED4245),
    "CMD_USED":        ("⌨️",  0x5865F2),
    "SLASH_USED":      ("🔧", 0x5865F2),
    "INVITE":          ("📨", 0x9B59B6),
    "RATING":          ("⭐", 0xF1C40F),
    "AI_USED":         ("🤖", 0x1ABC9C),
    "SETTINGS":        ("⚙️",  0xFEE75C),
    "ERROR":           ("❌", 0xED4245),
    "INFO":            ("ℹ️",  0x5865F2),
}

# Map event_type → nhóm kênh
LOG_ROUTES: dict[str, str] = {
    "TICKET_CREATE":   "ticket",
    "TICKET_CLOSE":    "ticket",
    "TICKET_DONE":     "ticket",
    "TICKET_CLAIM":    "ticket",
    "BALANCE_IN":      "balance",
    "BALANCE_OUT":     "balance",
    "BALANCE_SET":     "balance",
    "BALANCE_RESET":   "balance",
    "MOD_BAN":         "mod",
    "MOD_KICK":        "mod",
    "MOD_MUTE":        "mod",
    "MOD_WARN":        "mod",
    "GIVEAWAY_START":  "giveaway",
    "GIVEAWAY_END":    "giveaway",
    "GIVEAWAY_REROLL": "giveaway",
    "MEMBER_JOIN":     "member",
    "MEMBER_LEAVE":    "member",
    "ROLE_ADD":        "role",
    "ROLE_REMOVE":     "role",
    "AI_USED":         "ai",
    "CMD_USED":        "admin",
    "SLASH_USED":      "admin",
    "SETTINGS":        "admin",
    "INVITE":          "general",
    "RATING":          "general",
    "ERROR":           "general",
    "INFO":            "general",
}

# Tên hiển thị cho từng nhóm
LOG_GROUP_LABELS: dict[str, str] = {
    "ticket":   "🎫 Ticket",
    "balance":  "💰 Balance",
    "mod":      "🛡️ Mod",
    "giveaway": "🎉 Giveaway",
    "member":   "👥 Member",
    "role":     "🏷️ Role",
    "ai":       "🤖 AI",
    "admin":    "⌨️ Admin",
    "general":  "📋 General",
}

# Lưu channel ID theo nhóm: đọc/ghi thẳng vào MongoDB qua core.data

def set_log_channel(group: str, channel_id: int):
    """Cài kênh log cho một nhóm — lưu vào MongoDB."""
    set_log_channel_db(group, channel_id)


def get_log_channel(group: str) -> int | None:
    """Lấy channel ID của nhóm log từ MongoDB cache."""
    return get_log_channel_by_group(group)


def get_all_log_channels() -> dict[str, int]:
    return get_log_channels()

# ══════════════════════════════════════════
# SEND LOG
# ══════════════════════════════════════════
async def send_log(
    bot: discord.Client,
    event_type: str,
    title: str,
    fields: list[tuple] = None,
    description: str = None,
    user: discord.Member | discord.User = None,
    color: int = None,
    footer: str = None,
):
    """
    Gửi log vào kênh tương ứng với nhóm của event_type.
    Fallback về kênh log_rudy nếu nhóm chưa được cài.
    fields: list of (name, value, inline?)
    """
    if bot is None:
        return

    icon, default_color = LOG_ICONS.get(event_type, ("📋", 0x5865F2))
    embed = discord.Embed(
        title=f"{icon}  {title}",
        color=color or default_color,
        timestamp=datetime.now(timezone.utc),
    )
    if description:
        embed.description = description
    if user:
        embed.set_author(
            name=str(user),
            icon_url=user.display_avatar.url if hasattr(user, "display_avatar") else None,
        )
    if fields:
        for f in fields:
            name   = f[0]
            value  = f[1]
            inline = f[2] if len(f) > 2 else True
            embed.add_field(name=name, value=value, inline=inline)
    embed.add_field(name="🕐 Thời gian", value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", inline=False)
    embed.set_footer(text=footer or f"TuyTam Store  •  {event_type}")

    # Xác định kênh đích
    group   = LOG_ROUTES.get(event_type, "general")
    ch_id   = get_log_channel(group) or get_cfg_log_rudy()
    if not ch_id:
        print(f"[LOG] ⚠️ Không có kênh log cho nhóm '{group}' ({event_type}), bỏ qua.")
        return
    channel = bot.get_channel(ch_id)
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[LOG] ❌ Không gửi được log {event_type} → #{channel.name}: {e}")


# ══════════════════════════════════════════
# COG — log member join/leave tự động
# ══════════════════════════════════════════
class LoggerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── LỆNH CÀI KÊNH LOG ──
    @commands.command(name="setlog")
    async def set_log(self, ctx, group: str = None, channel: discord.TextChannel = None):
        """Cài kênh log cho từng nhóm. Dùng: .setlog <nhóm> #kênh"""
        if ctx.author.id not in ADMIN_IDS:
            return
        if not group or not channel:
            # Hiện danh sách nhóm + kênh hiện tại
            embed = discord.Embed(
                title="⚙️ Cài Đặt Kênh Log",
                description="Dùng `.setlog <nhóm> #kênh` để cài\n\n**Nhóm hiện tại:**",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )
            for grp, label in LOG_GROUP_LABELS.items():
                ch_id = get_log_channel(grp)
                ch_mention = f"<#{ch_id}>" if ch_id else "*(chưa cài)*"
                embed.add_field(name=label, value=ch_mention, inline=True)
            embed.add_field(
                name="📋 Nhóm hợp lệ",
                value=" | ".join(f"`{g}`" for g in LOG_GROUP_LABELS),
                inline=False,
            )
            return await ctx.reply(embed=embed)

        group = group.lower()
        if group not in LOG_GROUP_LABELS:
            valid = ", ".join(f"`{g}`" for g in LOG_GROUP_LABELS)
            return await ctx.reply(f"❌ Nhóm `{group}` không hợp lệ.\nNhóm hợp lệ: {valid}")

        set_log_channel(group, channel.id)
        label = LOG_GROUP_LABELS[group]
        await ctx.reply(f"✅ Đã cài kênh log **{label}** → {channel.mention}")
        await send_log(
            self.bot, "SETTINGS", f"Cài kênh log {label}",
            fields=[
                ("👤 Admin",  f"{ctx.author.mention}", True),
                ("📌 Kênh",   channel.mention,         True),
                ("🗂️ Nhóm",   label,                   True),
            ],
            user=ctx.author,
        )

    @commands.command(name="setuplog")
    async def setup_log(self, ctx):
        """Tự động tạo toàn bộ kênh log và bỏ vào danh mục cố định."""
        if ctx.author.id not in ADMIN_IDS:
            return

        CATEGORY_ID = 1486967303802191912
        category = ctx.guild.get_channel(CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            return await ctx.reply("❌ Không tìm thấy danh mục. Kiểm tra lại ID.")

        # Tên kênh cho từng nhóm
        CHANNEL_NAMES = {
            "ticket":   "log-ticket",
            "balance":  "log-balance",
            "mod":      "log-mod",
            "giveaway": "log-giveaway",
            "member":   "log-member",
            "role":     "log-role",
            "ai":       "log-ai",
            "admin":    "log-admin",
            "general":  "log-general",
        }

        # Chỉ bot và admin mới xem được kênh log
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            ctx.guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
            ctx.author:             discord.PermissionOverwrite(view_channel=True),
        }

        msg = await ctx.reply("⏳ Đang tạo kênh log...")
        results = []

        for group, ch_name in CHANNEL_NAMES.items():
            # Kiểm tra kênh đã tồn tại trong category chưa
            existing = discord.utils.get(category.channels, name=ch_name)
            if existing:
                set_log_channel(group, existing.id)
                results.append(f"⏭️ {existing.mention} *(đã tồn tại)*")
                continue
            try:
                ch = await ctx.guild.create_text_channel(
                    ch_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"Auto setup log bởi {ctx.author}",
                )
                set_log_channel(group, ch.id)
                results.append(f"✅ {ch.mention}")
            except Exception as e:
                results.append(f"❌ `{ch_name}`: {e}")

        embed = discord.Embed(
            title="✅ Setup Log Hoàn Tất",
            description="\n".join(results),
            color=0x57F287,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Danh mục: {category.name} • Bởi {ctx.author}")
        await msg.edit(content=None, embed=embed)


    @commands.command(name="loginfo")
    async def log_info(self, ctx):
        """Xem toàn bộ kênh log đang được cài."""
        if ctx.author.id not in ADMIN_IDS:
            return
        embed = discord.Embed(
            title="📋 Kênh Log Hiện Tại",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        any_set = False
        for grp, label in LOG_GROUP_LABELS.items():
            ch_id = get_log_channel(grp)
            if ch_id:
                embed.add_field(name=label, value=f"<#{ch_id}>", inline=True)
                any_set = True
            else:
                embed.add_field(name=label, value="*(chưa cài)*", inline=True)

        fallback_id = get_cfg_log_rudy()
        fallback    = f"<#{fallback_id}>" if fallback_id else "*(chưa cài)*"
        embed.add_field(name="🔁 Fallback (log_rudy)", value=fallback, inline=False)
        embed.set_footer(text="Kênh chưa cài sẽ fallback về log_rudy")
        await ctx.reply(embed=embed)

    # ── LISTENERS ──
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await send_log(
            self.bot, "MEMBER_JOIN", "Thành Viên Tham Gia",
            fields=[
                ("👤 Thành viên", f"{member.mention} (`{member.id}`)", True),
                ("📅 Tạo acc",    f"<t:{int(member.created_at.timestamp())}:D>", True),
                ("👥 Tổng member", str(member.guild.member_count), True),
            ],
            user=member,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        await send_log(
            self.bot, "MEMBER_LEAVE", "Thành Viên Rời Server",
            fields=[
                ("👤 Thành viên", f"{member} (`{member.id}`)", True),
                ("🏷️ Roles",      " ".join(roles[-5:]) if roles else "Không có", True),
                ("👥 Tổng member", str(member.guild.member_count), True),
            ],
            user=member,
        )

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if ctx.author.bot:
            return
        if ctx.command is None:
            return
        await send_log(
            self.bot, "CMD_USED", f"Lệnh: .{ctx.command}",
            fields=[
                ("👤 Người dùng", f"{ctx.author.mention} (`{ctx.author.id}`)", True),
                ("📝 Lệnh đầy đủ", f"`{ctx.message.content[:200]}`",           True),
                ("📌 Kênh",        ctx.channel.mention,                        True),
            ],
            user=ctx.author,
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.application_command:
            return
        cmd_name = getattr(interaction.command, "name", "unknown")
        opts = ""
        if interaction.data and interaction.data.get("options"):
            opts = " ".join(
                f'{o["name"]}={o.get("value","")}'
                for o in interaction.data["options"]
            )
        await send_log(
            self.bot, "SLASH_USED", f"Slash: /{cmd_name}",
            fields=[
                ("👤 Người dùng", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                ("🔧 Options",    f"`{opts}`" if opts else "*(không có)*",                True),
                ("📌 Kênh",       interaction.channel.mention if interaction.channel else "N/A", True),
            ],
            user=interaction.user,
        )


async def setup(bot):
    await bot.add_cog(LoggerCog(bot))
