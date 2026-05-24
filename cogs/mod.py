"""
cogs/mod.py — Hệ thống mod: ban/kick/mute, warn, auto-mod.
Lệnh prefix + slash cho tất cả.
v3.4.1 — 2026-05-15
"""

import re
import asyncio
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core.data import ADMIN_IDS, load_data, save_data, _uname_plain
from cogs.logger import send_log

# ══════════════════════════════════════════
# DATA HELPERS
# ══════════════════════════════════════════
def _get_mod_data() -> dict:
    data = load_data()
    data.setdefault("mod", {
        "warns": {},          # uid → [{"reason":..., "by":..., "time":...}]
        "warn_actions": {     # số warn → hành động
            "3": "mute_10m",
            "5": "kick",
            "7": "ban",
        },
        "automod": {
            "enabled": False,
            "delete_links": False,
            "delete_invites": False,
            "anti_spam": False,
            "banned_words": [],
            "whitelist_roles": [],  # role ID miễn kiểm tra
            "whitelist_users": [],  # user ID miễn kiểm tra
            "log_violations": True,
        },
        "muted_role_id": 0,
    })
    return data["mod"]

def _save_mod_data(mod: dict):
    data = load_data()
    data["mod"] = mod
    save_data(data)

def _get_warns(user_id: int) -> list:
    return _get_mod_data()["warns"].get(str(user_id), [])

def _add_warn(user_id: int, reason: str, by: str) -> int:
    mod  = _get_mod_data()
    uid  = str(user_id)
    mod["warns"].setdefault(uid, [])
    mod["warns"][uid].append({
        "reason": reason,
        "by":     by,
        "time":   datetime.now(timezone.utc).isoformat(),
    })
    _save_mod_data(mod)
    return len(mod["warns"][uid])

def _clear_warns(user_id: int):
    mod = _get_mod_data()
    mod["warns"].pop(str(user_id), None)
    _save_mod_data(mod)

def _remove_warn(user_id: int, index: int) -> bool:
    mod   = _get_mod_data()
    uid   = str(user_id)
    warns = mod["warns"].get(uid, [])
    if index < 0 or index >= len(warns):
        return False
    warns.pop(index)
    mod["warns"][uid] = warns
    _save_mod_data(mod)
    return True

# ══════════════════════════════════════════
# PARSE THỜI GIAN  (10m, 1h, 2d)
# ══════════════════════════════════════════
def _parse_duration(raw: str) -> timedelta | None:
    m = re.fullmatch(r"(\d+)(s|m|h|d)", raw.strip().lower())
    if not m:
        return None
    val, unit = int(m.group(1)), m.group(2)
    return {"s": timedelta(seconds=val), "m": timedelta(minutes=val),
            "h": timedelta(hours=val),   "d": timedelta(days=val)}[unit]

def _fmt_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    d, r  = divmod(total, 86400)
    h, r  = divmod(r, 3600)
    m, s  = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return " ".join(parts) or "0s"

# ══════════════════════════════════════════
# AUTO-MOD HELPERS
# ══════════════════════════════════════════
_LINK_RE    = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_INVITE_RE  = re.compile(r"discord(?:\.gg|\.com/invite)/\S+", re.IGNORECASE)
_spam_cache: dict[int, list] = {}   # uid → [timestamps]

def _check_spam(user_id: int, threshold: int = 5, window: int = 5) -> bool:
    now  = datetime.now(timezone.utc).timestamp()
    msgs = _spam_cache.setdefault(user_id, [])
    msgs.append(now)
    _spam_cache[user_id] = [t for t in msgs if now - t < window]
    return len(_spam_cache[user_id]) >= threshold

# ══════════════════════════════════════════
# COG
# ══════════════════════════════════════════
class ModCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_mod(self, member: discord.Member) -> bool:
        if member.id in ADMIN_IDS: return True
        if member.guild_permissions.administrator: return True
        if member.guild_permissions.kick_members: return True
        return False

    async def _get_or_create_muted_role(self, guild: discord.Guild) -> discord.Role:
        mod      = _get_mod_data()
        role_id  = mod.get("muted_role_id", 0)
        role     = guild.get_role(role_id)
        if role:
            return role
        # Tạo role Muted mới
        role = await guild.create_role(name="Muted", reason="Auto-tạo bởi bot mod")
        for channel in guild.channels:
            try:
                await channel.set_permissions(role,
                    send_messages=False, speak=False, add_reactions=False)
            except: pass
        mod["muted_role_id"] = role.id
        _save_mod_data(mod)
        return role

    async def _apply_warn_action(self, guild: discord.Guild, member: discord.Member, count: int):
        mod     = _get_mod_data()
        actions = mod.get("warn_actions", {})
        action  = actions.get(str(count))
        if not action:
            return
        if action.startswith("mute"):
            duration_str = action.split("_")[1] if "_" in action else "10m"
            td   = _parse_duration(duration_str) or timedelta(minutes=10)
            role = await self._get_or_create_muted_role(guild)
            await member.add_roles(role, reason=f"Auto-mute: {count} warns")
            await asyncio.sleep(td.total_seconds())
            await member.remove_roles(role, reason="Hết thời gian mute")
        elif action == "kick":
            try: await member.kick(reason=f"Auto-kick: {count} warns")
            except: pass
        elif action == "ban":
            try: await member.ban(reason=f"Auto-ban: {count} warns", delete_message_days=0)
            except: pass

    # ══════════════════════════════════════
    # BAN
    # ══════════════════════════════════════
    @commands.command(name="ban")
    async def ban_cmd(self, ctx, member: discord.Member = None, *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.ban @user [lý do]`")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.reply("❌ Không thể ban thành viên có role cao hơn bot.")
        try:
            await member.ban(reason=f"{reason} — Bởi {ctx.author}", delete_message_days=0)
        except discord.Forbidden:
            return await ctx.reply("❌ Bot không có quyền ban.")
        embed = discord.Embed(title="🔨 Đã Ban", color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên", value=f"{member} (`{member.id}`)", inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,                      inline=True)
        embed.add_field(name="🛡️ Mod",        value=ctx.author.mention,          inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.reply(embed=embed)
        await send_log(self.bot, "INFO", f"Ban — {member}",
            fields=[("👤 Thành viên", f"{member} (`{member.id}`)", True),
                    ("📝 Lý do", reason, True), ("🛡️ Mod", str(ctx.author), True)],
            user=ctx.author, color=0xED4245)
        try:
            await member.send(embed=discord.Embed(title="🔨 Bạn đã bị ban",
                description=f"**Server:** {ctx.guild.name}\n**Lý do:** {reason}", color=0xED4245))
        except: pass

    @app_commands.command(name="ban", description="Ban thành viên khỏi server")
    @app_commands.describe(member="Thành viên", reason="Lý do ban")
    async def slash_ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Không có lý do"):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        if member.top_role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ Role thành viên này cao hơn bot.")
        try:
            await member.ban(reason=f"{reason} — Bởi {interaction.user}", delete_message_days=0)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Bot không có quyền ban.")
        embed = discord.Embed(title="🔨 Đã Ban", color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên", value=f"{member} (`{member.id}`)", inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,                      inline=True)
        embed.add_field(name="🛡️ Mod",        value=interaction.user.mention,    inline=True)
        await interaction.response.send_message(embed=embed)
        await send_log(self.bot, "INFO", f"Ban — {member}",
            fields=[("👤 Thành viên", f"{member} (`{member.id}`)", True),
                    ("📝 Lý do", reason, True), ("🛡️ Mod", str(interaction.user), True)],
            user=interaction.user, color=0xED4245)

    # ══════════════════════════════════════
    # UNBAN
    # ══════════════════════════════════════
    @commands.command(name="unban")
    async def unban_cmd(self, ctx, user_id: str = None, *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not user_id or not user_id.isdigit():
            return await ctx.reply("❌ Dùng: `.unban <user_id> [lý do]`")
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user, reason=f"{reason} — Bởi {ctx.author}")
            embed = discord.Embed(title="✅ Đã Unban", color=0x57F287, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="👤 User",   value=f"{user} (`{user.id}`)", inline=True)
            embed.add_field(name="📝 Lý do",  value=reason,                  inline=True)
            embed.add_field(name="🛡️ Mod",    value=ctx.author.mention,      inline=True)
            await ctx.reply(embed=embed)
            await send_log(self.bot, "INFO", f"Unban — {user}",
                fields=[("👤 User", f"{user} (`{user.id}`)", True), ("🛡️ Mod", str(ctx.author), True)],
                user=ctx.author, color=0x57F287)
        except discord.NotFound:
            await ctx.reply("❌ User không tìm thấy hoặc chưa bị ban.")

    @app_commands.command(name="unban", description="Unban thành viên")
    @app_commands.describe(user_id="ID của user cần unban", reason="Lý do")
    async def slash_unban(self, interaction: discord.Interaction, user_id: str, reason: str = "Không có lý do"):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        if not user_id.isdigit():
            return await interaction.response.send_message("❌ ID không hợp lệ!")
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=f"{reason} — Bởi {interaction.user}")
            embed = discord.Embed(title="✅ Đã Unban", color=0x57F287)
            embed.add_field(name="👤 User",  value=f"{user} (`{user.id}`)", inline=True)
            embed.add_field(name="📝 Lý do", value=reason,                  inline=True)
            await interaction.response.send_message(embed=embed)
        except discord.NotFound:
            await interaction.response.send_message("❌ User không tìm thấy.")

    # ══════════════════════════════════════
    # KICK
    # ══════════════════════════════════════
    @commands.command(name="kick")
    async def kick_cmd(self, ctx, member: discord.Member = None, *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.kick @user [lý do]`")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.reply("❌ Không thể kick thành viên có role cao hơn bot.")
        try:
            await member.kick(reason=f"{reason} — Bởi {ctx.author}")
        except discord.Forbidden:
            return await ctx.reply("❌ Bot không có quyền kick.")
        embed = discord.Embed(title="👢 Đã Kick", color=0xFEE75C, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên", value=f"{member} (`{member.id}`)", inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,                      inline=True)
        embed.add_field(name="🛡️ Mod",        value=ctx.author.mention,          inline=True)
        await ctx.reply(embed=embed)
        await send_log(self.bot, "INFO", f"Kick — {member}",
            fields=[("👤 Thành viên", f"{member} (`{member.id}`)", True),
                    ("📝 Lý do", reason, True), ("🛡️ Mod", str(ctx.author), True)],
            user=ctx.author, color=0xFEE75C)
        try:
            await member.send(embed=discord.Embed(title="👢 Bạn đã bị kick",
                description=f"**Server:** {ctx.guild.name}\n**Lý do:** {reason}", color=0xFEE75C))
        except: pass

    @app_commands.command(name="kick", description="Kick thành viên khỏi server")
    @app_commands.describe(member="Thành viên", reason="Lý do kick")
    async def slash_kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Không có lý do"):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        try:
            await member.kick(reason=f"{reason} — Bởi {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Bot không có quyền kick.")
        embed = discord.Embed(title="👢 Đã Kick", color=0xFEE75C)
        embed.add_field(name="👤 Thành viên", value=f"{member} (`{member.id}`)", inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,                      inline=True)
        await interaction.response.send_message(embed=embed)
        await send_log(self.bot, "INFO", f"Kick — {member}",
            fields=[("👤 Thành viên", f"{member} (`{member.id}`)", True),
                    ("📝 Lý do", reason, True), ("🛡️ Mod", str(interaction.user), True)],
            user=interaction.user, color=0xFEE75C)

    # ══════════════════════════════════════
    # MUTE / UNMUTE
    # ══════════════════════════════════════
    @commands.command(name="mute")
    async def mute_cmd(self, ctx, member: discord.Member = None, duration: str = "10m", *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.mute @user [thời gian] [lý do]`\nVD: `.mute @user 10m spam`")
        td = _parse_duration(duration)
        if not td:
            return await ctx.reply("❌ Thời gian không hợp lệ! Dùng: `10s`, `5m`, `1h`, `2d`")
        role = await self._get_or_create_muted_role(ctx.guild)
        if role in member.roles:
            return await ctx.reply(f"❌ {member.mention} đã bị mute rồi!")
        await member.add_roles(role, reason=f"{reason} — Bởi {ctx.author}")
        embed = discord.Embed(title="🔇 Đã Mute", color=0x9B59B6, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên", value=member.mention,          inline=True)
        embed.add_field(name="⏱️ Thời gian",  value=_fmt_duration(td),       inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,                  inline=True)
        embed.add_field(name="🛡️ Mod",        value=ctx.author.mention,      inline=True)
        await ctx.reply(embed=embed)
        await send_log(self.bot, "INFO", f"Mute — {member}",
            fields=[("👤", member.mention, True), ("⏱️", _fmt_duration(td), True),
                    ("📝", reason, True), ("🛡️", str(ctx.author), True)],
            user=ctx.author, color=0x9B59B6)
        try:
            await member.send(embed=discord.Embed(title="🔇 Bạn đã bị mute",
                description=f"**Server:** {ctx.guild.name}\n**Thời gian:** {_fmt_duration(td)}\n**Lý do:** {reason}",
                color=0x9B59B6))
        except: pass
        await asyncio.sleep(td.total_seconds())
        if role in member.roles:
            await member.remove_roles(role, reason="Hết thời gian mute")

    @app_commands.command(name="mute", description="Mute thành viên")
    @app_commands.describe(member="Thành viên", duration="Thời gian: 10m, 1h, 2d", reason="Lý do")
    async def slash_mute(self, interaction: discord.Interaction, member: discord.Member, duration: str = "10m", reason: str = "Không có lý do"):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        td = _parse_duration(duration)
        if not td:
            return await interaction.response.send_message("❌ Thời gian không hợp lệ! Dùng: `10s`, `5m`, `1h`, `2d`")
        role = await self._get_or_create_muted_role(interaction.guild)
        if role in member.roles:
            return await interaction.response.send_message(f"❌ {member.mention} đã bị mute rồi!")
        await member.add_roles(role, reason=f"{reason} — Bởi {interaction.user}")
        embed = discord.Embed(title="🔇 Đã Mute", color=0x9B59B6)
        embed.add_field(name="👤 Thành viên", value=member.mention,     inline=True)
        embed.add_field(name="⏱️ Thời gian",  value=_fmt_duration(td),  inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,             inline=True)
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(td.total_seconds())
        if role in member.roles:
            await member.remove_roles(role, reason="Hết thời gian mute")

    @commands.command(name="unmute")
    async def unmute_cmd(self, ctx, member: discord.Member = None):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.unmute @user`")
        mod    = _get_mod_data()
        role   = ctx.guild.get_role(mod.get("muted_role_id", 0))
        if not role or role not in member.roles:
            return await ctx.reply(f"❌ {member.mention} không bị mute.")
        await member.remove_roles(role, reason=f"Unmute bởi {ctx.author}")
        await ctx.reply(f"✅ Đã unmute {member.mention}.")
        await send_log(self.bot, "INFO", f"Unmute — {member}",
            fields=[("👤", member.mention, True), ("🛡️", str(ctx.author), True)],
            user=ctx.author, color=0x57F287)

    @app_commands.command(name="unmute", description="Unmute thành viên")
    @app_commands.describe(member="Thành viên cần unmute")
    async def slash_unmute(self, interaction: discord.Interaction, member: discord.Member):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        mod  = _get_mod_data()
        role = interaction.guild.get_role(mod.get("muted_role_id", 0))
        if not role or role not in member.roles:
            return await interaction.response.send_message(f"❌ {member.mention} không bị mute.")
        await member.remove_roles(role, reason=f"Unmute bởi {interaction.user}")
        await interaction.response.send_message(f"✅ Đã unmute {member.mention}.")

    # ══════════════════════════════════════
    # SLOWMODE / LOCK
    # ══════════════════════════════════════
    @commands.command(name="slowmode", aliases=["slow"])
    async def slowmode_cmd(self, ctx, seconds: int = 0):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        seconds = max(0, min(seconds, 21600))
        await ctx.channel.edit(slowmode_delay=seconds)
        msg = f"⏱️ Slowmode **{seconds}s**" if seconds else "✅ Đã tắt slowmode."
        await ctx.reply(msg)

    @app_commands.command(name="slowmode", description="Cài slowmode cho kênh")
    @app_commands.describe(seconds="Số giây (0 = tắt, tối đa 21600)")
    async def slash_slowmode(self, interaction: discord.Interaction, seconds: int = 0):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        seconds = max(0, min(seconds, 21600))
        await interaction.channel.edit(slowmode_delay=seconds)
        msg = f"⏱️ Slowmode **{seconds}s**" if seconds else "✅ Đã tắt slowmode."
        await interaction.response.send_message(msg)

    @commands.command(name="lock")
    async def lock_cmd(self, ctx, channel: discord.TextChannel = None):
        if not self._is_mod(ctx.author): return await ctx.reply("❌ Bạn không có quyền.")
        ch = channel or ctx.channel
        await ch.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.reply(f"🔒 Đã khóa {ch.mention}.")

    @commands.command(name="unlock")
    async def unlock_cmd(self, ctx, channel: discord.TextChannel = None):
        if not self._is_mod(ctx.author): return await ctx.reply("❌ Bạn không có quyền.")
        ch = channel or ctx.channel
        await ch.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.reply(f"🔓 Đã mở khóa {ch.mention}.")

    @app_commands.command(name="lock", description="Khóa kênh không cho gửi tin nhắn")
    @app_commands.describe(channel="Kênh cần khóa (để trống = kênh hiện tại)")
    async def slash_lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if not self._is_mod(interaction.user): return await interaction.response.send_message("❌ Bạn không có quyền.")
        ch = channel or interaction.channel
        await ch.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message(f"🔒 Đã khóa {ch.mention}.")

    @app_commands.command(name="unlock", description="Mở khóa kênh")
    @app_commands.describe(channel="Kênh cần mở khóa (để trống = kênh hiện tại)")
    async def slash_unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if not self._is_mod(interaction.user): return await interaction.response.send_message("❌ Bạn không có quyền.")
        ch = channel or interaction.channel
        await ch.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message(f"🔓 Đã mở khóa {ch.mention}.")

    # ══════════════════════════════════════
    # WARN SYSTEM
    # ══════════════════════════════════════
    @commands.command(name="warn", aliases=["w"])
    async def warn_cmd(self, ctx, member: discord.Member = None, *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.warn @user [lý do]`")
        count = _add_warn(member.id, reason, str(ctx.author))
        mod   = _get_mod_data()
        actions = mod.get("warn_actions", {})
        next_action = actions.get(str(count + 1), "")
        embed = discord.Embed(title="⚠️ Đã Cảnh Cáo", color=0xFEE75C, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên",  value=member.mention,                     inline=True)
        embed.add_field(name="📝 Lý do",       value=reason,                             inline=True)
        embed.add_field(name="⚠️ Tổng warn",   value=f"**{count}** lần",                 inline=True)
        embed.add_field(name="🛡️ Mod",         value=ctx.author.mention,                 inline=True)
        if next_action:
            embed.add_field(name="⚡ Warn tiếp theo sẽ", value=f"`{next_action}`", inline=True)
        await ctx.reply(embed=embed)
        await send_log(self.bot, "INFO", f"Warn #{count} — {member}",
            fields=[("👤", member.mention, True), ("📝", reason, True),
                    ("⚠️ Tổng", str(count), True), ("🛡️", str(ctx.author), True)],
            user=ctx.author, color=0xFEE75C)
        try:
            await member.send(embed=discord.Embed(title="⚠️ Bạn đã bị cảnh cáo",
                description=f"**Server:** {ctx.guild.name}\n**Lý do:** {reason}\n**Tổng warn:** {count}",
                color=0xFEE75C))
        except: pass
        asyncio.create_task(self._apply_warn_action(ctx.guild, member, count))

    @app_commands.command(name="warn", description="Cảnh cáo thành viên")
    @app_commands.describe(member="Thành viên", reason="Lý do")
    async def slash_warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Không có lý do"):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        count = _add_warn(member.id, reason, str(interaction.user))
        embed = discord.Embed(title="⚠️ Đã Cảnh Cáo", color=0xFEE75C)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,         inline=True)
        embed.add_field(name="⚠️ Tổng warn",  value=f"**{count}**", inline=True)
        await interaction.response.send_message(embed=embed)
        asyncio.create_task(self._apply_warn_action(interaction.guild, member, count))

    @commands.command(name="warns", aliases=["warnlist"])
    async def warns_cmd(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        warns  = _get_warns(target.id)
        embed  = discord.Embed(title=f"⚠️ Warns — {_uname_plain(target)}", color=0xFEE75C, timestamp=datetime.now(timezone.utc))
        if warns:
            for i, w in enumerate(warns):
                t = w.get("time","")[:10]
                embed.add_field(name=f"#{i+1} — {t}", value=f"📝 {w['reason']}\n🛡️ {w['by']}", inline=False)
            embed.set_footer(text=f"Tổng: {len(warns)} warn")
        else:
            embed.description = "✅ Không có warn nào!"
        await ctx.reply(embed=embed)

    @app_commands.command(name="warns", description="Xem danh sách warn của thành viên")
    @app_commands.describe(member="Thành viên (để trống = bản thân)")
    async def slash_warns(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        warns  = _get_warns(target.id)
        embed  = discord.Embed(title=f"⚠️ Warns — {_uname_plain(target)}", color=0xFEE75C)
        if warns:
            for i, w in enumerate(warns):
                embed.add_field(name=f"#{i+1} — {w.get('time','')[:10]}", value=f"📝 {w['reason']}\n🛡️ {w['by']}", inline=False)
            embed.set_footer(text=f"Tổng: {len(warns)} warn")
        else:
            embed.description = "✅ Không có warn nào!"
        await interaction.response.send_message(embed=embed)

    @commands.command(name="clearwarn", aliases=["warnreset"])
    async def clearwarn_cmd(self, ctx, member: discord.Member = None, index: str = None):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.clearwarn @user` (xoá tất cả) hoặc `.clearwarn @user 2` (xoá warn #2)")
        if index:
            if not index.isdigit():
                return await ctx.reply("❌ Index phải là số!")
            ok = _remove_warn(member.id, int(index) - 1)
            if not ok:
                return await ctx.reply(f"❌ Không tìm thấy warn #{index}.")
            await ctx.reply(f"✅ Đã xoá warn #{index} của {member.mention}.")
        else:
            _clear_warns(member.id)
            await ctx.reply(f"✅ Đã xoá toàn bộ warn của {member.mention}.")

    @app_commands.command(name="clearwarn", description="Xoá warn của thành viên (mod)")
    @app_commands.describe(member="Thành viên", index="Số thứ tự warn cần xoá (để trống = xoá tất cả)")
    async def slash_clearwarn(self, interaction: discord.Interaction, member: discord.Member, index: int = None):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        if index:
            ok = _remove_warn(member.id, index - 1)
            if not ok:
                return await interaction.response.send_message(f"❌ Không tìm thấy warn #{index}.")
            await interaction.response.send_message(f"✅ Đã xoá warn #{index} của {member.mention}.")
        else:
            _clear_warns(member.id)
            await interaction.response.send_message(f"✅ Đã xoá toàn bộ warn của {member.mention}.")

    # ══════════════════════════════════════
    # AUTO-MOD CONFIG
    # ══════════════════════════════════════
    @commands.group(name="automod", aliases=["am"], invoke_without_command=True)
    async def automod_group(self, ctx):
        if not self._is_mod(ctx.author): return
        mod = _get_mod_data()
        am  = mod.get("automod", {})
        embed = discord.Embed(title="🛡️ Cài Đặt Auto-Mod", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        def status(v): return "✅ Bật" if v else "❌ Tắt"
        embed.add_field(name="🛡️ Auto-mod",      value=status(am.get("enabled")),       inline=True)
        embed.add_field(name="🔗 Xoá link",      value=status(am.get("delete_links")),  inline=True)
        embed.add_field(name="📨 Xoá invite",    value=status(am.get("delete_invites")),inline=True)
        embed.add_field(name="🚫 Anti-spam",     value=status(am.get("anti_spam")),     inline=True)
        words = am.get("banned_words", [])
        embed.add_field(name="🚷 Từ cấm",        value=f"`{len(words)}` từ" if words else "Chưa có", inline=True)
        wl_roles = am.get("whitelist_roles", [])
        wl_users = am.get("whitelist_users", [])
        embed.add_field(name="🛡️ Whitelist",     value=f"`{len(wl_roles)}` role, `{len(wl_users)}` user", inline=True)
        embed.add_field(name="💡 Lệnh",          value=(
            "`.automod on/off` — Bật/tắt\n"
            "`.automod links on/off` — Xoá link\n"
            "`.automod invites on/off` — Xoá invite\n"
            "`.automod spam on/off` — Anti-spam\n"
            "`.automod addword/delword <từ>` — Từ cấm\n"
            "`.automod addrole/delrole @role` — Whitelist role\n"
            "`.automod adduser/deluser @user` — Whitelist user\n"
            "`.automod whitelist` — Xem danh sách whitelist"
        ), inline=False)
        await ctx.reply(embed=embed)

    @automod_group.command(name="on")
    async def am_on(self, ctx):
        if not self._is_mod(ctx.author): return
        mod = _get_mod_data(); mod["automod"]["enabled"] = True; _save_mod_data(mod)
        await ctx.reply("✅ Đã **bật** auto-mod.")

    @automod_group.command(name="off")
    async def am_off(self, ctx):
        if not self._is_mod(ctx.author): return
        mod = _get_mod_data(); mod["automod"]["enabled"] = False; _save_mod_data(mod)
        await ctx.reply("✅ Đã **tắt** auto-mod.")

    @automod_group.command(name="links")
    async def am_links(self, ctx, toggle: str = "on"):
        if not self._is_mod(ctx.author): return
        val = toggle.lower() == "on"
        mod = _get_mod_data(); mod["automod"]["delete_links"] = val; _save_mod_data(mod)
        await ctx.reply(f"{'✅ Bật' if val else '❌ Tắt'} xoá link.")

    @automod_group.command(name="invites")
    async def am_invites(self, ctx, toggle: str = "on"):
        if not self._is_mod(ctx.author): return
        val = toggle.lower() == "on"
        mod = _get_mod_data(); mod["automod"]["delete_invites"] = val; _save_mod_data(mod)
        await ctx.reply(f"{'✅ Bật' if val else '❌ Tắt'} xoá invite.")

    @automod_group.command(name="spam")
    async def am_spam(self, ctx, toggle: str = "on"):
        if not self._is_mod(ctx.author): return
        val = toggle.lower() == "on"
        mod = _get_mod_data(); mod["automod"]["anti_spam"] = val; _save_mod_data(mod)
        await ctx.reply(f"{'✅ Bật' if val else '❌ Tắt'} anti-spam.")

    @automod_group.command(name="addword")
    async def am_addword(self, ctx, *, word: str = None):
        if not self._is_mod(ctx.author): return
        if not word: return await ctx.reply("❌ Dùng: `.automod addword <từ>`")
        mod = _get_mod_data()
        words = mod["automod"].setdefault("banned_words", [])
        word  = word.lower().strip()
        if word in words: return await ctx.reply(f"❌ `{word}` đã có trong danh sách.")
        words.append(word); _save_mod_data(mod)
        await ctx.reply(f"✅ Đã thêm từ cấm: `{word}` (tổng: {len(words)} từ)")

    @automod_group.command(name="delword")
    async def am_delword(self, ctx, *, word: str = None):
        if not self._is_mod(ctx.author): return
        if not word: return await ctx.reply("❌ Dùng: `.automod delword <từ>`")
        mod   = _get_mod_data()
        words = mod["automod"].get("banned_words", [])
        word  = word.lower().strip()
        if word not in words: return await ctx.reply(f"❌ `{word}` không có trong danh sách.")
        words.remove(word); _save_mod_data(mod)
        await ctx.reply(f"✅ Đã xoá từ cấm: `{word}` (còn: {len(words)} từ)")

    @automod_group.command(name="words")
    async def am_words(self, ctx):
        if not self._is_mod(ctx.author): return
        words = _get_mod_data()["automod"].get("banned_words", [])
        if not words: return await ctx.reply("Chưa có từ cấm nào.")
        await ctx.reply(f"🚷 **Danh sách từ cấm ({len(words)}):**\n" + ", ".join(f"`{w}`" for w in words))

    # ══════════════════════════════════════
    # AUTOMOD WHITELIST
    # ══════════════════════════════════════
    @automod_group.command(name="addrole")
    async def am_addrole(self, ctx, role: discord.Role = None):
        """Thêm role vào whitelist — bỏ qua auto-mod"""
        if not self._is_mod(ctx.author): return
        if not role: return await ctx.reply("❌ Dùng: `.automod addrole @role`")
        mod = _get_mod_data()
        wl  = mod["automod"].setdefault("whitelist_roles", [])
        if role.id in wl: return await ctx.reply(f"❌ {role.mention} đã có trong whitelist rồi.")
        wl.append(role.id); _save_mod_data(mod)
        embed = discord.Embed(title="✅ Đã Thêm Whitelist Role", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏷️ Role",   value=role.mention,           inline=True)
        embed.add_field(name="📋 Tổng",   value=f"{len(wl)} role",      inline=True)
        embed.set_footer(text="Role này sẽ không bị kiểm tra bởi auto-mod")
        await ctx.reply(embed=embed)

    @automod_group.command(name="delrole")
    async def am_delrole(self, ctx, role: discord.Role = None):
        """Xoá role khỏi whitelist"""
        if not self._is_mod(ctx.author): return
        if not role: return await ctx.reply("❌ Dùng: `.automod delrole @role`")
        mod = _get_mod_data()
        wl  = mod["automod"].get("whitelist_roles", [])
        if role.id not in wl: return await ctx.reply(f"❌ {role.mention} không có trong whitelist.")
        wl.remove(role.id); _save_mod_data(mod)
        embed = discord.Embed(title="🗑️ Đã Xoá Whitelist Role", color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏷️ Role", value=role.mention, inline=True)
        await ctx.reply(embed=embed)

    @automod_group.command(name="adduser")
    async def am_adduser(self, ctx, member: discord.Member = None):
        """Thêm user vào whitelist — bỏ qua auto-mod"""
        if not self._is_mod(ctx.author): return
        if not member: return await ctx.reply("❌ Dùng: `.automod adduser @user`")
        mod = _get_mod_data()
        wu  = mod["automod"].setdefault("whitelist_users", [])
        if member.id in wu: return await ctx.reply(f"❌ {member.mention} đã có trong whitelist rồi.")
        wu.append(member.id); _save_mod_data(mod)
        embed = discord.Embed(title="✅ Đã Thêm Whitelist User", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 User",  value=member.mention,           inline=True)
        embed.add_field(name="📋 Tổng", value=f"{len(wu)} user",         inline=True)
        embed.set_footer(text="User này sẽ không bị kiểm tra bởi auto-mod")
        await ctx.reply(embed=embed)

    @automod_group.command(name="deluser")
    async def am_deluser(self, ctx, member: discord.Member = None):
        """Xoá user khỏi whitelist"""
        if not self._is_mod(ctx.author): return
        if not member: return await ctx.reply("❌ Dùng: `.automod deluser @user`")
        mod = _get_mod_data()
        wu  = mod["automod"].get("whitelist_users", [])
        if member.id not in wu: return await ctx.reply(f"❌ {member.mention} không có trong whitelist.")
        wu.remove(member.id); _save_mod_data(mod)
        embed = discord.Embed(title="🗑️ Đã Xoá Whitelist User", color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 User", value=member.mention, inline=True)
        await ctx.reply(embed=embed)

    @automod_group.command(name="whitelist")
    async def am_whitelist(self, ctx):
        """Xem danh sách whitelist role và user"""
        if not self._is_mod(ctx.author): return
        mod = _get_mod_data()
        am  = mod.get("automod", {})
        wl_roles = am.get("whitelist_roles", [])
        wl_users = am.get("whitelist_users", [])
        embed = discord.Embed(title="🛡️ Whitelist Auto-Mod", color=0x5865F2, timestamp=datetime.now(timezone.utc))

        if wl_roles:
            lines = []
            for rid in wl_roles:
                role = ctx.guild.get_role(rid)
                lines.append(role.mention if role else f"`ID:{rid}` *(đã xoá)*")
            embed.add_field(name=f"🏷️ Roles ({len(wl_roles)})", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="🏷️ Roles", value="*(Chưa có)*", inline=False)

        if wl_users:
            lines = []
            for uid in wl_users:
                member = ctx.guild.get_member(uid)
                lines.append(member.mention if member else f"`ID:{uid}` *(không tìm thấy)*")
            embed.add_field(name=f"👤 Users ({len(wl_users)})", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="👤 Users", value="*(Chưa có)*", inline=False)

        embed.add_field(
            name="💡 Lệnh",
            value=(
                "`.automod addrole @role` — Thêm role\n"
                "`.automod delrole @role` — Xoá role\n"
                "`.automod adduser @user` — Thêm user\n"
                "`.automod deluser @user` — Xoá user"
            ),
            inline=False
        )
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════
    # AUTO-MOD EVENT
    # ══════════════════════════════════════
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        mod = _get_mod_data()
        am  = mod.get("automod", {})
        if not am.get("enabled"):
            return

        # Bỏ qua whitelist roles và users
        whitelist_roles = am.get("whitelist_roles", [])
        whitelist_users = am.get("whitelist_users", [])
        if isinstance(message.author, discord.Member):
            if message.author.id in whitelist_users:
                return
            if any(r.id in whitelist_roles for r in message.author.roles):
                return
            if self._is_mod(message.author):
                return

        deleted = False
        reason  = None

        # Kiểm tra từ cấm
        content_lower = message.content.lower()
        for word in am.get("banned_words", []):
            if word in content_lower:
                reason = f"Từ cấm: `{word}`"; break

        # Kiểm tra link
        if not reason and am.get("delete_links") and _LINK_RE.search(message.content):
            reason = "Không được phép gửi link"

        # Kiểm tra invite Discord
        if not reason and am.get("delete_invites") and _INVITE_RE.search(message.content):
            reason = "Không được phép gửi link invite Discord"

        if reason:
            try:
                await message.delete()
                deleted = True
            except: pass
            try:
                warn_embed = discord.Embed(
                    title="🛡️ Auto-Mod",
                    description=f"{message.author.mention} tin nhắn của bạn đã bị xoá.\n**Lý do:** {reason}",
                    color=0xED4245, timestamp=datetime.now(timezone.utc)
                )
                warn_embed.set_footer(text="TuyTam Store • Auto-Mod")
                notif = await message.channel.send(embed=warn_embed)
                await asyncio.sleep(5)
                await notif.delete()
            except: pass
            if am.get("log_violations"):
                await send_log(self.bot, "INFO", f"Auto-Mod — {message.author}",
                    fields=[("👤 User",  message.author.mention,          True),
                            ("📝 Lý do", reason,                          True),
                            ("📌 Kênh",  message.channel.mention,         True),
                            ("💬 Nội dung", f"`{message.content[:200]}`", False)],
                    user=message.author, color=0xED4245)
            return

        # Anti-spam
        if am.get("anti_spam") and _check_spam(message.author.id):
            try: await message.delete()
            except: pass
            try:
                notif = await message.channel.send(
                    f"🚫 {message.author.mention} bạn đang gửi tin nhắn quá nhanh!", delete_after=5)
            except: pass
            if am.get("log_violations"):
                await send_log(self.bot, "INFO", f"Anti-Spam — {message.author}",
                    fields=[("👤", message.author.mention, True), ("📌", message.channel.mention, True)],
                    user=message.author, color=0xFEE75C)


async def setup(bot):
    await bot.add_cog(ModCog(bot))
