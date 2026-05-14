"""
cogs/logger.py — Hệ thống log tập trung.
Mọi cog gọi: await send_log(bot, "TICKET", "Tạo ticket", ..., color=...)
Kênh log được cài qua .settings → cfg_log_channel
"""

from datetime import datetime, timezone
import discord
from discord.ext import commands
from core.data import get_cfg_log_channel

# ══════════════════════════════════════════
# ICON MAP
# ══════════════════════════════════════════
LOG_ICONS = {
    "TICKET_CREATE":   ("🎫", 0x57F287),
    "TICKET_CLOSE":    ("🔒", 0xED4245),
    "TICKET_DONE":     ("✅", 0x57F287),
    "TICKET_CLAIM":    ("🙋", 0x5865F2),
    "BALANCE_IN":      ("📥", 0x57F287),
    "BALANCE_OUT":     ("📤", 0xED4245),
    "BALANCE_SET":     ("⚙️",  0xFEE75C),
    "BALANCE_RESET":   ("🔄", 0x99AAB5),
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
    Gửi log vào kênh log.
    fields: list of (name, value, inline?)
    """
    ch_id = get_cfg_log_channel()
    if not ch_id:
        return
    channel = bot.get_channel(ch_id)
    if not channel:
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

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[LOG] ❌ Không gửi được log {event_type}: {e}")


# ══════════════════════════════════════════
# COG — log member join/leave tự động
# ══════════════════════════════════════════
class LoggerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
