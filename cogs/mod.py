"""
cogs/mod.py — Hệ thống mod: ban/kick/timeout, warn, purge, auto-mod.
v4.0.0 — 2026-05-30
Thay đổi:
- Mute → Discord native Timeout (không mất khi restart)
- .xoa [số] — xoá hàng loạt tin nhắn
- .modlog @user — lịch sử hành động mod
- .tempban @user <time> — ban tạm thời
- Anti-spam ảnh/attachment lặp lại
- Caps lock filter
- Warn cooldown (tránh spam warn)
"""

import re
import asyncio
import hashlib
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
        "warns": {},
        "warn_actions": {
            "3": "timeout_10m",
            "5": "kick",
            "7": "ban",
        },
        "mod_log": [],          # lịch sử hành động mod
        "automod": {
            "enabled":        False,
            "delete_links":   False,
            "delete_invites": False,
            "anti_spam":      False,
            "anti_image_spam":False,
            "caps_filter":    False,
            "caps_threshold": 70,   # % chữ hoa để bị xoá (mặc định 70%)
            "caps_min_len":   10,   # độ dài tối thiểu để kiểm tra caps
            "banned_words":   [],
            "whitelist_roles":[],
            "whitelist_users":[],
            "log_violations": True,
        },
    })
    return data["mod"]

def _save_mod_data(mod: dict):
    data = load_data()
    data["mod"] = mod
    save_data(data)

def _get_warns(user_id: int) -> list:
    return _get_mod_data()["warns"].get(str(user_id), [])

def _add_warn(user_id: int, reason: str, by: str) -> int:
    mod = _get_mod_data()
    uid = str(user_id)
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

def _add_mod_log(action: str, target_id: int, target_str: str, by_str: str, reason: str, extra: str = ""):
    mod = _get_mod_data()
    mod.setdefault("mod_log", [])
    mod["mod_log"].append({
        "action":     action,
        "target_id":  target_id,
        "target":     target_str,
        "by":         by_str,
        "reason":     reason,
        "extra":      extra,
        "time":       datetime.now(timezone.utc).isoformat(),
    })
    mod["mod_log"] = mod["mod_log"][-1000:]   # giữ 1000 record
    _save_mod_data(mod)

def _get_mod_log(user_id: int) -> list:
    return [e for e in _get_mod_data().get("mod_log", []) if e.get("target_id") == user_id]

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
_LINK_RE   = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_INVITE_RE = re.compile(r"discord(?:\.gg|\.com/invite)/\S+", re.IGNORECASE)

# Anti text-spam: uid → [timestamps]
_spam_cache: dict[int, list] = {}

# Anti image-spam: uid → [(hash_or_name, timestamp)]
_image_cache: dict[int, list] = {}

# Warn cooldown: (mod_id, target_id) → last warn timestamp
_warn_cooldown: dict[tuple, float] = {}
WARN_COOLDOWN_SECS = 60

def _check_spam(user_id: int, threshold: int = 5, window: int = 5) -> bool:
    now  = datetime.now(timezone.utc).timestamp()
    msgs = _spam_cache.setdefault(user_id, [])
    msgs.append(now)
    _spam_cache[user_id] = [t for t in msgs if now - t < window]
    return len(_spam_cache[user_id]) >= threshold

def _check_image_spam(user_id: int, message: discord.Message,
                      threshold: int = 4, window: int = 10) -> bool:
    """
    Phát hiện spam ảnh/sticker/attachment.
    - Đếm số lần gửi ảnh trong `window` giây
    - Nếu >= threshold → spam
    """
    now     = datetime.now(timezone.utc).timestamp()
    entries = _image_cache.setdefault(user_id, [])

    # Lấy "dấu hiệu" của ảnh: sticker ID hoặc tên file attachment
    identifiers = []
    for att in message.attachments:
        # Hash tên file để nhận dạng ảnh giống nhau
        identifiers.append(att.filename.lower())
    for sticker in message.stickers:
        identifiers.append(f"sticker_{sticker.id}")
    # Không có ảnh → bỏ qua
    if not identifiers:
        return False

    for ident in identifiers:
        entries.append((ident, now))

    # Dọn entry cũ
    _image_cache[user_id] = [(i, t) for i, t in entries if now - t < window]

    # Đếm tổng số ảnh trong window (không phân biệt có giống nhau không)
    total_in_window = len(_image_cache[user_id])
    return total_in_window >= threshold

def _check_warn_cooldown(mod_id: int, target_id: int) -> float:
    """Trả về số giây còn lại nếu đang cooldown, 0 nếu OK."""
    key  = (mod_id, target_id)
    last = _warn_cooldown.get(key, 0)
    remaining = WARN_COOLDOWN_SECS - (datetime.now(timezone.utc).timestamp() - last)
    return max(0.0, remaining)

def _set_warn_cooldown(mod_id: int, target_id: int):
    _warn_cooldown[(mod_id, target_id)] = datetime.now(timezone.utc).timestamp()

def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters) * 100

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

    # ══════════════════════════════════════
    # BAN / UNBAN
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
        _add_mod_log("ban", member.id, str(member), str(ctx.author), reason)
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
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if member.top_role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ Role thành viên này cao hơn bot.", ephemeral=True)
        try:
            await member.ban(reason=f"{reason} — Bởi {interaction.user}", delete_message_days=0)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Bot không có quyền ban.", ephemeral=True)
        _add_mod_log("ban", member.id, str(member), str(interaction.user), reason)
        embed = discord.Embed(title="🔨 Đã Ban", color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên", value=f"{member} (`{member.id}`)", inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,                      inline=True)
        embed.add_field(name="🛡️ Mod",        value=interaction.user.mention,    inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await send_log(self.bot, "INFO", f"Ban — {member}",
            fields=[("👤 Thành viên", f"{member} (`{member.id}`)", True),
                    ("📝 Lý do", reason, True), ("🛡️ Mod", str(interaction.user), True)],
            user=interaction.user, color=0xED4245)

    @commands.command(name="unban")
    async def unban_cmd(self, ctx, user_id: str = None, *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not user_id or not user_id.isdigit():
            return await ctx.reply("❌ Dùng: `.unban <user_id> [lý do]`")
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user, reason=f"{reason} — Bởi {ctx.author}")
            _add_mod_log("unban", user.id, str(user), str(ctx.author), reason)
            embed = discord.Embed(title="✅ Đã Unban", color=0x57F287, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="👤 User",  value=f"{user} (`{user.id}`)", inline=True)
            embed.add_field(name="📝 Lý do", value=reason,                  inline=True)
            embed.add_field(name="🛡️ Mod",   value=ctx.author.mention,      inline=True)
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
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if not user_id.isdigit():
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=f"{reason} — Bởi {interaction.user}")
            _add_mod_log("unban", user.id, str(user), str(interaction.user), reason)
            embed = discord.Embed(title="✅ Đã Unban", color=0x57F287)
            embed.add_field(name="👤 User",  value=f"{user} (`{user.id}`)", inline=True)
            embed.add_field(name="📝 Lý do", value=reason,                  inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("❌ User không tìm thấy.", ephemeral=True)

    # ══════════════════════════════════════
    # TEMPBAN — ban tạm thời
    # ══════════════════════════════════════
    @commands.command(name="tempban", aliases=["tban"])
    async def tempban_cmd(self, ctx, member: discord.Member = None, duration: str = "1d", *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.tempban @user <thời gian> [lý do]`\nVD: `.tempban @user 2d spam`")
        td = _parse_duration(duration)
        if not td:
            return await ctx.reply("❌ Thời gian không hợp lệ! Dùng: `10m`, `1h`, `2d`")
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.reply("❌ Không thể ban thành viên có role cao hơn bot.")
        try:
            await member.ban(reason=f"[TempBan {_fmt_duration(td)}] {reason} — Bởi {ctx.author}", delete_message_days=0)
        except discord.Forbidden:
            return await ctx.reply("❌ Bot không có quyền ban.")

        _add_mod_log("tempban", member.id, str(member), str(ctx.author), reason, _fmt_duration(td))
        embed = discord.Embed(title="⏱️ Đã TempBan", color=0xE67E22, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên", value=f"{member} (`{member.id}`)", inline=True)
        embed.add_field(name="⏱️ Thời gian",  value=_fmt_duration(td),           inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,                      inline=True)
        embed.add_field(name="🛡️ Mod",        value=ctx.author.mention,          inline=True)
        await ctx.reply(embed=embed)
        await send_log(self.bot, "INFO", f"TempBan — {member}",
            fields=[("👤", f"{member} (`{member.id}`)", True), ("⏱️", _fmt_duration(td), True),
                    ("📝", reason, True), ("🛡️", str(ctx.author), True)],
            user=ctx.author, color=0xE67E22)
        try:
            await member.send(embed=discord.Embed(title="⏱️ Bạn đã bị ban tạm thời",
                description=f"**Server:** {ctx.guild.name}\n**Thời gian:** {_fmt_duration(td)}\n**Lý do:** {reason}",
                color=0xE67E22))
        except: pass

        # Tự động unban sau thời gian
        async def _auto_unban(guild=ctx.guild, uid=member.id, delay=td.total_seconds()):
            await asyncio.sleep(delay)
            try:
                user = await self.bot.fetch_user(uid)
                await guild.unban(user, reason="TempBan hết hạn — tự động unban")
                await send_log(self.bot, "INFO", f"TempBan hết hạn — {user}",
                    fields=[("👤", f"{user} (`{uid}`)", True), ("⏱️", "Hết hạn tự động", True)],
                    color=0x57F287)
            except Exception:
                pass
        asyncio.create_task(_auto_unban())

    @app_commands.command(name="tempban", description="Ban tạm thời, tự unban sau thời gian")
    @app_commands.describe(member="Thành viên", duration="Thời gian: 10m, 1h, 2d", reason="Lý do")
    async def slash_tempban(self, interaction: discord.Interaction, member: discord.Member, duration: str = "1d", reason: str = "Không có lý do"):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        td = _parse_duration(duration)
        if not td:
            return await interaction.response.send_message("❌ Thời gian không hợp lệ!", ephemeral=True)
        try:
            await member.ban(reason=f"[TempBan {_fmt_duration(td)}] {reason}", delete_message_days=0)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Bot không có quyền ban.", ephemeral=True)
        _add_mod_log("tempban", member.id, str(member), str(interaction.user), reason, _fmt_duration(td))
        embed = discord.Embed(title="⏱️ Đã TempBan", color=0xE67E22)
        embed.add_field(name="👤 Thành viên", value=member.mention,    inline=True)
        embed.add_field(name="⏱️ Thời gian",  value=_fmt_duration(td), inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,            inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        async def _auto_unban(guild=interaction.guild, uid=member.id, delay=td.total_seconds()):
            await asyncio.sleep(delay)
            try:
                user = await self.bot.fetch_user(uid)
                await guild.unban(user, reason="TempBan hết hạn")
            except Exception:
                pass
        asyncio.create_task(_auto_unban())

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
        _add_mod_log("kick", member.id, str(member), str(ctx.author), reason)
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
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            await member.kick(reason=f"{reason} — Bởi {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Bot không có quyền kick.", ephemeral=True)
        _add_mod_log("kick", member.id, str(member), str(interaction.user), reason)
        embed = discord.Embed(title="👢 Đã Kick", color=0xFEE75C)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,         inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ══════════════════════════════════════
    # TIMEOUT (thay Mute — dùng Discord native)
    # ══════════════════════════════════════
    @commands.command(name="timeout", aliases=["mute", "to"])
    async def timeout_cmd(self, ctx, member: discord.Member = None, duration: str = "10m", *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.timeout @user [thời gian] [lý do]`\nVD: `.timeout @user 10m spam`")
        td = _parse_duration(duration)
        if not td:
            return await ctx.reply("❌ Thời gian không hợp lệ! Dùng: `10s`, `5m`, `1h`, `2d`")
        if td.total_seconds() > 28 * 86400:
            return await ctx.reply("❌ Discord timeout tối đa 28 ngày.")
        try:
            until = datetime.now(timezone.utc) + td
            await member.timeout(until, reason=f"{reason} — Bởi {ctx.author}")
        except discord.Forbidden:
            return await ctx.reply("❌ Bot không có quyền timeout.")
        _add_mod_log("timeout", member.id, str(member), str(ctx.author), reason, _fmt_duration(td))
        embed = discord.Embed(title="🔇 Đã Timeout", color=0x9B59B6, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên", value=member.mention,          inline=True)
        embed.add_field(name="⏱️ Thời gian",  value=_fmt_duration(td),       inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,                  inline=True)
        embed.add_field(name="🛡️ Mod",        value=ctx.author.mention,      inline=True)
        embed.set_footer(text="⚡ Discord native timeout — tự hết hạn, không cần role Muted")
        await ctx.reply(embed=embed)
        await send_log(self.bot, "INFO", f"Timeout — {member}",
            fields=[("👤", member.mention, True), ("⏱️", _fmt_duration(td), True),
                    ("📝", reason, True), ("🛡️", str(ctx.author), True)],
            user=ctx.author, color=0x9B59B6)
        try:
            await member.send(embed=discord.Embed(title="🔇 Bạn đã bị timeout",
                description=f"**Server:** {ctx.guild.name}\n**Thời gian:** {_fmt_duration(td)}\n**Lý do:** {reason}",
                color=0x9B59B6))
        except: pass

    @app_commands.command(name="timeout", description="Timeout thành viên (Discord native, tự hết hạn)")
    @app_commands.describe(member="Thành viên", duration="Thời gian: 10m, 1h, 2d (tối đa 28d)", reason="Lý do")
    async def slash_timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str = "10m", reason: str = "Không có lý do"):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        td = _parse_duration(duration)
        if not td:
            return await interaction.response.send_message("❌ Thời gian không hợp lệ!", ephemeral=True)
        if td.total_seconds() > 28 * 86400:
            return await interaction.response.send_message("❌ Tối đa 28 ngày.", ephemeral=True)
        try:
            await member.timeout(datetime.now(timezone.utc) + td, reason=f"{reason} — Bởi {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Bot không có quyền timeout.", ephemeral=True)
        _add_mod_log("timeout", member.id, str(member), str(interaction.user), reason, _fmt_duration(td))
        embed = discord.Embed(title="🔇 Đã Timeout", color=0x9B59B6)
        embed.add_field(name="👤", value=member.mention,    inline=True)
        embed.add_field(name="⏱️", value=_fmt_duration(td), inline=True)
        embed.add_field(name="📝", value=reason,            inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="untimeout", aliases=["unmute", "uto"])
    async def untimeout_cmd(self, ctx, member: discord.Member = None):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.untimeout @user`")
        try:
            await member.timeout(None, reason=f"Gỡ timeout bởi {ctx.author}")
        except discord.Forbidden:
            return await ctx.reply("❌ Bot không có quyền.")
        _add_mod_log("untimeout", member.id, str(member), str(ctx.author), "Gỡ timeout thủ công")
        await ctx.reply(f"✅ Đã gỡ timeout cho {member.mention}.")
        await send_log(self.bot, "INFO", f"Untimeout — {member}",
            fields=[("👤", member.mention, True), ("🛡️", str(ctx.author), True)],
            user=ctx.author, color=0x57F287)

    @app_commands.command(name="untimeout", description="Gỡ timeout thành viên")
    async def slash_untimeout(self, interaction: discord.Interaction, member: discord.Member):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            await member.timeout(None, reason=f"Gỡ timeout bởi {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Bot không có quyền.", ephemeral=True)
        _add_mod_log("untimeout", member.id, str(member), str(interaction.user), "Gỡ timeout thủ công")
        await interaction.response.send_message(f"✅ Đã gỡ timeout cho {member.mention}.", ephemeral=True)

    # ══════════════════════════════════════
    # SLOWMODE / LOCK
    # ══════════════════════════════════════
    @commands.command(name="slowmode", aliases=["slow"])
    async def slowmode_cmd(self, ctx, seconds: int = 0):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        seconds = max(0, min(seconds, 21600))
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.reply(f"⏱️ Slowmode **{seconds}s**" if seconds else "✅ Đã tắt slowmode.")

    @app_commands.command(name="slowmode", description="Cài slowmode cho kênh")
    @app_commands.describe(seconds="Số giây (0 = tắt, tối đa 21600)")
    async def slash_slowmode(self, interaction: discord.Interaction, seconds: int = 0):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        seconds = max(0, min(seconds, 21600))
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"⏱️ Slowmode **{seconds}s**" if seconds else "✅ Đã tắt slowmode.", ephemeral=True)

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

    @app_commands.command(name="lock", description="Khóa kênh")
    @app_commands.describe(channel="Kênh cần khóa (để trống = kênh hiện tại)")
    async def slash_lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if not self._is_mod(interaction.user): return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        ch = channel or interaction.channel
        await ch.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message(f"🔒 Đã khóa {ch.mention}.", ephemeral=True)

    @app_commands.command(name="unlock", description="Mở khóa kênh")
    @app_commands.describe(channel="Kênh cần mở khóa (để trống = kênh hiện tại)")
    async def slash_unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if not self._is_mod(interaction.user): return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        ch = channel or interaction.channel
        await ch.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message(f"🔓 Đã mở khóa {ch.mention}.", ephemeral=True)

    # ══════════════════════════════════════
    # .XOA — xoá hàng loạt tin nhắn
    # ══════════════════════════════════════
    @commands.command(name="del", aliases=["xoa", "purge", "clear"])
    async def xoa_cmd(self, ctx, amount: int = None, member: discord.Member = None):
        """
        .xoa [số] [@user]
        Xoá [số] tin nhắn gần nhất trong kênh.
        Nếu có @user thì chỉ xoá tin của người đó.
        Mặc định 10, tối đa 100.
        """
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if amount is None:
            return await ctx.reply(
                "❌ Dùng: `.xoa <số> [@user]`\n"
                "VD: `.xoa 20` — xoá 20 tin gần nhất\n"
                "VD: `.xoa 10 @user` — xoá 10 tin của @user"
            )
        amount = max(1, min(amount, 100))

        try:
            await ctx.message.delete()
        except: pass

        if member:
            # Lọc theo member — cần fetch nhiều hơn rồi lọc
            deleted = await ctx.channel.purge(
                limit=amount * 5,
                check=lambda m: m.author == member,
                before=ctx.message,
            )
            deleted = deleted[:amount]
        else:
            deleted = await ctx.channel.purge(limit=amount, before=ctx.message)

        count = len(deleted)
        suffix = f" của {member.mention}" if member else ""
        notif  = await ctx.channel.send(
            f"🗑️ Đã xoá **{count}** tin nhắn{suffix}.", delete_after=4
        )
        await send_log(self.bot, "INFO", "Xoá Tin Nhắn Hàng Loạt",
            fields=[
                ("🗑️ Số lượng", str(count),          True),
                ("📌 Kênh",     ctx.channel.mention,  True),
                ("🛡️ Mod",      ctx.author.mention,   True),
                ("👤 Lọc user", member.mention if member else "Tất cả", True),
            ],
            user=ctx.author, color=0x99AAB5)

    @app_commands.command(name="xoa", description="Xoá hàng loạt tin nhắn trong kênh")
    @app_commands.describe(amount="Số lượng (tối đa 100)", member="Chỉ xoá tin của user này (tuỳ chọn)")
    async def slash_xoa(self, interaction: discord.Interaction, amount: int = 10, member: discord.Member = None):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        amount = max(1, min(amount, 100))
        await interaction.response.defer(ephemeral=True)
        if member:
            deleted = await interaction.channel.purge(
                limit=amount * 5,
                check=lambda m: m.author == member,
            )
            deleted = deleted[:amount]
        else:
            deleted = await interaction.channel.purge(limit=amount)
        count  = len(deleted)
        suffix = f" của {member.mention}" if member else ""
        await interaction.followup.send(f"🗑️ Đã xoá **{count}** tin nhắn{suffix}.", ephemeral=True)
        await send_log(self.bot, "INFO", "Xoá Tin Nhắn Hàng Loạt",
            fields=[("🗑️ Số lượng", str(count), True), ("📌 Kênh", interaction.channel.mention, True),
                    ("🛡️ Mod", interaction.user.mention, True)],
            user=interaction.user, color=0x99AAB5)

    # ══════════════════════════════════════
    # WARN SYSTEM  (có cooldown)
    # ══════════════════════════════════════
    async def _apply_warn_action(self, guild: discord.Guild, member: discord.Member, count: int):
        mod     = _get_mod_data()
        actions = mod.get("warn_actions", {})
        action  = actions.get(str(count))
        if not action:
            return
        if action.startswith("timeout"):
            duration_str = action.split("_")[1] if "_" in action else "10m"
            td   = _parse_duration(duration_str) or timedelta(minutes=10)
            try:
                await member.timeout(datetime.now(timezone.utc) + td,
                                     reason=f"Auto-timeout: {count} warns")
            except Exception: pass
        elif action == "kick":
            try: await member.kick(reason=f"Auto-kick: {count} warns")
            except: pass
        elif action == "ban":
            try: await member.ban(reason=f"Auto-ban: {count} warns", delete_message_days=0)
            except: pass

    @commands.command(name="warn", aliases=["w"])
    async def warn_cmd(self, ctx, member: discord.Member = None, *, reason: str = "Không có lý do"):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.warn @user [lý do]`")

        # Cooldown check
        remaining = _check_warn_cooldown(ctx.author.id, member.id)
        if remaining > 0:
            return await ctx.reply(
                f"⏳ Bạn vừa warn {member.mention} rồi. Chờ **{remaining:.0f}s** nữa."
            )

        count = _add_warn(member.id, reason, str(ctx.author))
        _set_warn_cooldown(ctx.author.id, member.id)
        _add_mod_log("warn", member.id, str(member), str(ctx.author), reason, f"warn #{count}")

        mod     = _get_mod_data()
        actions = mod.get("warn_actions", {})
        next_action = actions.get(str(count + 1), "")

        embed = discord.Embed(title="⚠️ Đã Cảnh Cáo", color=0xFEE75C, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Thành viên",  value=member.mention,   inline=True)
        embed.add_field(name="📝 Lý do",       value=reason,           inline=True)
        embed.add_field(name="⚠️ Tổng warn",   value=f"**{count}**",   inline=True)
        embed.add_field(name="🛡️ Mod",         value=ctx.author.mention, inline=True)
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
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        remaining = _check_warn_cooldown(interaction.user.id, member.id)
        if remaining > 0:
            return await interaction.response.send_message(
                f"⏳ Chờ **{remaining:.0f}s** nữa mới warn lại.", ephemeral=True)
        count = _add_warn(member.id, reason, str(interaction.user))
        _set_warn_cooldown(interaction.user.id, member.id)
        _add_mod_log("warn", member.id, str(member), str(interaction.user), reason, f"warn #{count}")
        embed = discord.Embed(title="⚠️ Đã Cảnh Cáo", color=0xFEE75C)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="📝 Lý do",      value=reason,         inline=True)
        embed.add_field(name="⚠️ Tổng warn",  value=f"**{count}**", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        asyncio.create_task(self._apply_warn_action(interaction.guild, member, count))

    @commands.command(name="warns", aliases=["warnlist"])
    async def warns_cmd(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        warns  = _get_warns(target.id)
        embed  = discord.Embed(title=f"⚠️ Warns — {_uname_plain(target)}", color=0xFEE75C,
                               timestamp=datetime.now(timezone.utc))
        if warns:
            for i, w in enumerate(warns):
                embed.add_field(name=f"#{i+1} — {w.get('time','')[:10]}",
                                value=f"📝 {w['reason']}\n🛡️ {w['by']}", inline=False)
            embed.set_footer(text=f"Tổng: {len(warns)} warn")
        else:
            embed.description = "✅ Không có warn nào!"
        await ctx.reply(embed=embed)

    @app_commands.command(name="warns", description="Xem danh sách warn")
    @app_commands.describe(member="Thành viên (để trống = bản thân)")
    async def slash_warns(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        warns  = _get_warns(target.id)
        embed  = discord.Embed(title=f"⚠️ Warns — {_uname_plain(target)}", color=0xFEE75C)
        if warns:
            for i, w in enumerate(warns):
                embed.add_field(name=f"#{i+1} — {w.get('time','')[:10]}",
                                value=f"📝 {w['reason']}\n🛡️ {w['by']}", inline=False)
            embed.set_footer(text=f"Tổng: {len(warns)} warn")
        else:
            embed.description = "✅ Không có warn nào!"
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="clearwarn", aliases=["warnreset"])
    async def clearwarn_cmd(self, ctx, member: discord.Member = None, index: str = None):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.clearwarn @user` hoặc `.clearwarn @user 2`")
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

    @app_commands.command(name="clearwarn", description="Xoá warn của thành viên")
    @app_commands.describe(member="Thành viên", index="Số thứ tự warn (để trống = xoá tất cả)")
    async def slash_clearwarn(self, interaction: discord.Interaction, member: discord.Member, index: int = None):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if index:
            ok = _remove_warn(member.id, index - 1)
            if not ok:
                return await interaction.response.send_message(f"❌ Không tìm thấy warn #{index}.", ephemeral=True)
            await interaction.response.send_message(f"✅ Đã xoá warn #{index} của {member.mention}.", ephemeral=True)
        else:
            _clear_warns(member.id)
            await interaction.response.send_message(f"✅ Đã xoá toàn bộ warn của {member.mention}.", ephemeral=True)

    # ══════════════════════════════════════
    # MODLOG — lịch sử hành động mod
    # ══════════════════════════════════════
    @commands.command(name="modlog", aliases=["ml"])
    async def modlog_cmd(self, ctx, member: discord.Member = None):
        if not self._is_mod(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")
        if not member:
            return await ctx.reply("❌ Dùng: `.modlog @user`")

        logs = _get_mod_log(member.id)
        embed = discord.Embed(
            title=f"📋 Lịch Sử Mod — {_uname_plain(member)}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        if not logs:
            embed.description = "✅ Chưa có hành động mod nào với thành viên này."
        else:
            ACTION_ICONS = {
                "ban": "🔨", "unban": "✅", "kick": "👢",
                "timeout": "🔇", "untimeout": "🔊",
                "tempban": "⏱️", "warn": "⚠️",
            }
            for entry in reversed(logs[-15:]):   # 15 gần nhất
                icon   = ACTION_ICONS.get(entry["action"], "📌")
                title  = f"{icon} {entry['action'].upper()} — {entry['time'][:10]}"
                value  = f"📝 {entry['reason']}"
                if entry.get("extra"):
                    value += f"\n⏱️ {entry['extra']}"
                value += f"\n🛡️ {entry['by']}"
                embed.add_field(name=title, value=value, inline=False)
            embed.set_footer(text=f"Tổng {len(logs)} hành động  •  Hiển thị 15 gần nhất")

        await ctx.reply(embed=embed)

    @app_commands.command(name="modlog", description="Xem lịch sử mod của thành viên")
    @app_commands.describe(member="Thành viên cần tra cứu")
    async def slash_modlog(self, interaction: discord.Interaction, member: discord.Member):
        if not self._is_mod(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        logs  = _get_mod_log(member.id)
        embed = discord.Embed(title=f"📋 Lịch Sử Mod — {_uname_plain(member)}", color=0x5865F2)
        if not logs:
            embed.description = "✅ Chưa có hành động mod nào."
        else:
            ACTION_ICONS = {"ban":"🔨","unban":"✅","kick":"👢","timeout":"🔇",
                            "untimeout":"🔊","tempban":"⏱️","warn":"⚠️"}
            for entry in reversed(logs[-10:]):
                icon  = ACTION_ICONS.get(entry["action"], "📌")
                value = f"📝 {entry['reason']}"
                if entry.get("extra"): value += f"\n⏱️ {entry['extra']}"
                value += f"\n🛡️ {entry['by']}"
                embed.add_field(name=f"{icon} {entry['action'].upper()} — {entry['time'][:10]}",
                                value=value, inline=False)
            embed.set_footer(text=f"Tổng {len(logs)} hành động")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ══════════════════════════════════════
    # AUTO-MOD CONFIG
    # ══════════════════════════════════════
    @commands.group(name="automod", aliases=["am"], invoke_without_command=True)
    async def automod_group(self, ctx):
        if not self._is_mod(ctx.author): return
        mod = _get_mod_data()
        am  = mod.get("automod", {})
        def st(v): return "✅ Bật" if v else "❌ Tắt"
        embed = discord.Embed(title="🛡️ Cài Đặt Auto-Mod", color=0x5865F2,
                              timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🛡️ Auto-mod",       value=st(am.get("enabled")),         inline=True)
        embed.add_field(name="🔗 Xoá link",       value=st(am.get("delete_links")),    inline=True)
        embed.add_field(name="📨 Xoá invite",     value=st(am.get("delete_invites")),  inline=True)
        embed.add_field(name="🚫 Anti-spam",      value=st(am.get("anti_spam")),       inline=True)
        embed.add_field(name="🖼️ Anti-spam ảnh",  value=st(am.get("anti_image_spam")), inline=True)
        embed.add_field(name="🔠 Caps filter",    value=st(am.get("caps_filter")) +
                        f" ({am.get('caps_threshold', 70)}% / min {am.get('caps_min_len', 10)} ký tự)", inline=True)
        words = am.get("banned_words", [])
        embed.add_field(name="🚷 Từ cấm",         value=f"`{len(words)}` từ" if words else "Chưa có", inline=True)
        wl_roles = am.get("whitelist_roles", [])
        wl_users = am.get("whitelist_users", [])
        embed.add_field(name="🛡️ Whitelist",      value=f"`{len(wl_roles)}` role, `{len(wl_users)}` user", inline=True)
        embed.add_field(name="💡 Lệnh", value=(
            "`.automod on/off` — Bật/tắt\n"
            "`.automod links on/off` — Xoá link\n"
            "`.automod invites on/off` — Xoá invite\n"
            "`.automod spam on/off` — Anti-spam text\n"
            "`.automod imagespam on/off` — Anti-spam ảnh\n"
            "`.automod caps on/off [%] [min_len]` — Caps filter\n"
            "`.automod addword/delword <từ>` — Từ cấm\n"
            "`.automod addrole/delrole @role` — Whitelist role\n"
            "`.automod adduser/deluser @user` — Whitelist user"
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
        await ctx.reply(f"{'✅ Bật' if val else '❌ Tắt'} anti-spam text.")

    @automod_group.command(name="imagespam")
    async def am_imagespam(self, ctx, toggle: str = "on"):
        """Bật/tắt anti-spam ảnh. VD: .automod imagespam on"""
        if not self._is_mod(ctx.author): return
        val = toggle.lower() == "on"
        mod = _get_mod_data(); mod["automod"]["anti_image_spam"] = val; _save_mod_data(mod)
        await ctx.reply(
            f"{'✅ Bật' if val else '❌ Tắt'} anti-spam ảnh.\n"
            f"🖼️ Bot sẽ {'xoá và timeout 5m nếu user gửi 4+ ảnh trong 10 giây.' if val else 'không kiểm tra ảnh nữa.'}"
        )

    @automod_group.command(name="caps")
    async def am_caps(self, ctx, toggle: str = "on", threshold: int = 70, min_len: int = 10):
        """
        Bật/tắt caps filter.
        .automod caps on [% chữ hoa] [độ dài tối thiểu]
        VD: .automod caps on 80 15
        """
        if not self._is_mod(ctx.author): return
        val = toggle.lower() == "on"
        mod = _get_mod_data()
        mod["automod"]["caps_filter"]    = val
        mod["automod"]["caps_threshold"] = max(50, min(threshold, 100))
        mod["automod"]["caps_min_len"]   = max(5,  min(min_len, 50))
        _save_mod_data(mod)
        if val:
            await ctx.reply(
                f"✅ Bật caps filter — xoá tin nhắn có **≥{threshold}%** chữ hoa "
                f"và ít nhất **{min_len}** ký tự."
            )
        else:
            await ctx.reply("❌ Tắt caps filter.")

    @automod_group.command(name="addword")
    async def am_addword(self, ctx, *, word: str = None):
        if not self._is_mod(ctx.author): return
        if not word: return await ctx.reply("❌ Dùng: `.automod addword <từ>`")
        mod   = _get_mod_data()
        words = mod["automod"].setdefault("banned_words", [])
        word  = word.lower().strip()
        if word in words: return await ctx.reply(f"❌ `{word}` đã có rồi.")
        words.append(word); _save_mod_data(mod)
        await ctx.reply(f"✅ Thêm từ cấm: `{word}` (tổng: {len(words)} từ)")

    @automod_group.command(name="delword")
    async def am_delword(self, ctx, *, word: str = None):
        if not self._is_mod(ctx.author): return
        if not word: return await ctx.reply("❌ Dùng: `.automod delword <từ>`")
        mod   = _get_mod_data()
        words = mod["automod"].get("banned_words", [])
        word  = word.lower().strip()
        if word not in words: return await ctx.reply(f"❌ `{word}` không có trong danh sách.")
        words.remove(word); _save_mod_data(mod)
        await ctx.reply(f"✅ Xoá từ cấm: `{word}` (còn: {len(words)} từ)")

    @automod_group.command(name="words")
    async def am_words(self, ctx):
        if not self._is_mod(ctx.author): return
        words = _get_mod_data()["automod"].get("banned_words", [])
        if not words: return await ctx.reply("Chưa có từ cấm nào.")
        await ctx.reply(f"🚷 **Từ cấm ({len(words)}):**\n" + ", ".join(f"`{w}`" for w in words))

    @automod_group.command(name="addrole")
    async def am_addrole(self, ctx, role: discord.Role = None):
        if not self._is_mod(ctx.author): return
        if not role: return await ctx.reply("❌ Dùng: `.automod addrole @role`")
        mod = _get_mod_data()
        wl  = mod["automod"].setdefault("whitelist_roles", [])
        if role.id in wl: return await ctx.reply(f"❌ {role.mention} đã có rồi.")
        wl.append(role.id); _save_mod_data(mod)
        await ctx.reply(f"✅ Thêm whitelist role: {role.mention}")

    @automod_group.command(name="delrole")
    async def am_delrole(self, ctx, role: discord.Role = None):
        if not self._is_mod(ctx.author): return
        if not role: return await ctx.reply("❌ Dùng: `.automod delrole @role`")
        mod = _get_mod_data()
        wl  = mod["automod"].get("whitelist_roles", [])
        if role.id not in wl: return await ctx.reply(f"❌ {role.mention} không có trong whitelist.")
        wl.remove(role.id); _save_mod_data(mod)
        await ctx.reply(f"✅ Xoá whitelist role: {role.mention}")

    @automod_group.command(name="adduser")
    async def am_adduser(self, ctx, member: discord.Member = None):
        if not self._is_mod(ctx.author): return
        if not member: return await ctx.reply("❌ Dùng: `.automod adduser @user`")
        mod = _get_mod_data()
        wu  = mod["automod"].setdefault("whitelist_users", [])
        if member.id in wu: return await ctx.reply(f"❌ {member.mention} đã có rồi.")
        wu.append(member.id); _save_mod_data(mod)
        await ctx.reply(f"✅ Thêm whitelist user: {member.mention}")

    @automod_group.command(name="deluser")
    async def am_deluser(self, ctx, member: discord.Member = None):
        if not self._is_mod(ctx.author): return
        if not member: return await ctx.reply("❌ Dùng: `.automod deluser @user`")
        mod = _get_mod_data()
        wu  = mod["automod"].get("whitelist_users", [])
        if member.id not in wu: return await ctx.reply(f"❌ {member.mention} không có trong whitelist.")
        wu.remove(member.id); _save_mod_data(mod)
        await ctx.reply(f"✅ Xoá whitelist user: {member.mention}")

    @automod_group.command(name="whitelist")
    async def am_whitelist(self, ctx):
        if not self._is_mod(ctx.author): return
        mod      = _get_mod_data()
        am       = mod.get("automod", {})
        wl_roles = am.get("whitelist_roles", [])
        wl_users = am.get("whitelist_users", [])
        embed    = discord.Embed(title="🛡️ Whitelist Auto-Mod", color=0x5865F2,
                                 timestamp=datetime.now(timezone.utc))
        if wl_roles:
            lines = [ctx.guild.get_role(r).mention if ctx.guild.get_role(r) else f"`ID:{r}`" for r in wl_roles]
            embed.add_field(name=f"🏷️ Roles ({len(wl_roles)})", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="🏷️ Roles", value="*(Chưa có)*", inline=False)
        if wl_users:
            lines = [ctx.guild.get_member(u).mention if ctx.guild.get_member(u) else f"`ID:{u}`" for u in wl_users]
            embed.add_field(name=f"👤 Users ({len(wl_users)})", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="👤 Users", value="*(Chưa có)*", inline=False)
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

        # Bỏ qua whitelist
        wl_roles = am.get("whitelist_roles", [])
        wl_users = am.get("whitelist_users", [])
        if isinstance(message.author, discord.Member):
            if message.author.id in wl_users:
                return
            if any(r.id in wl_roles for r in message.author.roles):
                return
            if self._is_mod(message.author):
                return

        reason = None

        # 1. Từ cấm
        content_lower = message.content.lower()
        for word in am.get("banned_words", []):
            if word in content_lower:
                reason = f"Từ cấm: `{word}`"
                break

        # 2. Link
        if not reason and am.get("delete_links") and _LINK_RE.search(message.content):
            reason = "Không được phép gửi link"

        # 3. Invite Discord
        if not reason and am.get("delete_invites") and _INVITE_RE.search(message.content):
            reason = "Không được phép gửi link invite Discord"

        # 4. Caps filter
        if not reason and am.get("caps_filter"):
            threshold = am.get("caps_threshold", 70)
            min_len   = am.get("caps_min_len", 10)
            clean     = message.content.strip()
            if len(clean) >= min_len and _caps_ratio(clean) >= threshold:
                reason = f"Tin nhắn quá nhiều chữ hoa ({_caps_ratio(clean):.0f}%)"

        if reason:
            try:
                await message.delete()
            except: pass
            try:
                warn_embed = discord.Embed(
                    title="🛡️ Auto-Mod",
                    description=f"{message.author.mention} tin nhắn của bạn đã bị xoá.\n**Lý do:** {reason}",
                    color=0xED4245, timestamp=datetime.now(timezone.utc),
                )
                warn_embed.set_footer(text="TuyTam Store • Auto-Mod")
                notif = await message.channel.send(embed=warn_embed)
                await asyncio.sleep(5)
                await notif.delete()
            except: pass
            if am.get("log_violations"):
                await send_log(self.bot, "INFO", f"Auto-Mod — {message.author}",
                    fields=[("👤 User",    message.author.mention,          True),
                            ("📝 Lý do",   reason,                          True),
                            ("📌 Kênh",    message.channel.mention,         True),
                            ("💬 Nội dung", f"`{message.content[:200]}`",   False)],
                    user=message.author, color=0xED4245)
            return

        # 5. Anti-spam text
        if am.get("anti_spam") and _check_spam(message.author.id):
            try: await message.delete()
            except: pass
            try:
                await message.channel.send(
                    f"🚫 {message.author.mention} bạn đang gửi tin nhắn quá nhanh!", delete_after=5)
            except: pass
            if am.get("log_violations"):
                await send_log(self.bot, "INFO", f"Anti-Spam Text — {message.author}",
                    fields=[("👤", message.author.mention, True), ("📌", message.channel.mention, True)],
                    user=message.author, color=0xFEE75C)
            return

        # 6. Anti-spam ảnh
        if am.get("anti_image_spam") and (message.attachments or message.stickers):
            if _check_image_spam(message.author.id, message):
                try: await message.delete()
                except: pass
                try:
                    notif = await message.channel.send(
                        embed=discord.Embed(
                            title="🖼️ Anti-Spam Ảnh",
                            description=(
                                f"{message.author.mention} bạn đang gửi ảnh/sticker quá nhiều!\n"
                                f"⏱️ Bạn sẽ bị timeout **5 phút**."
                            ),
                            color=0xE67E22,
                            timestamp=datetime.now(timezone.utc),
                        )
                    )
                    await asyncio.sleep(6)
                    await notif.delete()
                except: pass
                # Tự động timeout 5 phút
                try:
                    if isinstance(message.author, discord.Member):
                        await message.author.timeout(
                            datetime.now(timezone.utc) + timedelta(minutes=5),
                            reason="Auto-Mod: spam ảnh/sticker"
                        )
                except: pass
                if am.get("log_violations"):
                    await send_log(self.bot, "INFO", f"Anti-Spam Ảnh — {message.author}",
                        fields=[
                            ("👤", message.author.mention,  True),
                            ("📌", message.channel.mention, True),
                            ("⏱️ Timeout", "5 phút",        True),
                        ],
                        user=message.author, color=0xE67E22)


async def setup(bot):
    await bot.add_cog(ModCog(bot))
