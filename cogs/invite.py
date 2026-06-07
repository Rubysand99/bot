"""
cogs/invite.py — Invite tracking + IP-based fake detection + verify system.
v5.0.0:
  - Xoá auto-kick
  - Fake = IP trùng inviter hoặc member khác trong server (qua verify web)
  - Bot DM link verify khi member join, timeout 10 phút
  - Log đầy đủ: INVITE_JOIN, INVITE_VERIFY, INVITE_FAKE, INVITE_LEFT
  - Giữ toàn bộ lệnh prefix + slash cũ
"""

import asyncio
import time as _time
from datetime import datetime, timezone

import discord
from discord.ext import commands

from cogs.logger import send_log
from core.data import (
    ADMIN_IDS, load_data, save_data, _uname, _uname_plain,
    get_member_inviters, save_member_inviters,
    get_pending_joins, save_pending_joins,
    get_ip_records, save_ip_records,
)
from verify_server import (
    create_token, build_verify_url, VERIFY_CALLBACKS,
)


# ══════════════════════════════════════════
# IN-MEMORY STATE
# ══════════════════════════════════════════

_invite_cache:    dict[int, dict[str, int]] = {}
_pending_joins:   dict[int, dict]           = {}   # member_id → {inviter_id, guild_id, joined_at}
_member_inviters: dict[int, dict]           = {}   # member_id → {inviter_id, guild_id}
_ip_records:      dict[str, list[int]]      = {}   # ip → [user_id, ...]  (persist MongoDB)


# ══════════════════════════════════════════
# INVITE COUNTS HELPERS
# ══════════════════════════════════════════

def _get_invite_counts() -> dict:
    return load_data().get("invite_counts", {})

def _save_invite_counts(counts: dict):
    data = load_data()
    data["invite_counts"] = counts
    save_data(data)

def _add_invite(inviter_id: int, field: str, amount: int = 1):
    counts = _get_invite_counts()
    uid    = str(inviter_id)
    if uid not in counts:
        counts[uid] = {"total": 0, "fake": 0, "left": 0}
    counts[uid][field] = counts[uid].get(field, 0) + amount
    _save_invite_counts(counts)

def _get_net_invites(inviter_id: int) -> tuple[int, int, int, int]:
    counts = _get_invite_counts()
    uid    = str(inviter_id)
    c      = counts.get(uid, {"total": 0, "fake": 0, "left": 0})
    total  = c.get("total", 0)
    fake   = c.get("fake",  0)
    left   = c.get("left",  0)
    net    = max(0, total - fake - left)
    return total, fake, left, net


# ══════════════════════════════════════════
# CACHE INVITE UTILS
# ══════════════════════════════════════════

async def cache_invites(guild: discord.Guild):
    try:
        invites = await guild.invites()
        _invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
    except (discord.Forbidden, discord.HTTPException):
        pass


# ══════════════════════════════════════════
# IP FAKE CHECK
# ══════════════════════════════════════════

def _check_ip_collision(user_id: int, ip: str, inviter_id: int | None) -> tuple[bool, str]:
    """
    Kiểm tra IP có trùng với:
      - inviter → fake chắc chắn
      - member khác trong server đã verify → fake nghi ngờ
    Trả về (is_fake: bool, reason: str)
    """
    users_on_ip = _ip_records.get(ip, [])

    # Trùng với inviter
    if inviter_id and inviter_id in users_on_ip:
        return True, f"IP trùng với inviter (ID:{inviter_id})"

    # Trùng với member khác đã verify (không tính bản thân)
    others = [uid for uid in users_on_ip if uid != user_id]
    if others:
        return True, f"IP trùng với {len(others)} thành viên khác ({', '.join(f'ID:{u}' for u in others[:3])})"

    return False, ""

def _register_ip(user_id: int, ip: str):
    """Lưu mapping ip → user_id."""
    if ip not in _ip_records:
        _ip_records[ip] = []
    if user_id not in _ip_records[ip]:
        _ip_records[ip].append(user_id)
    save_ip_records(_ip_records)


# ══════════════════════════════════════════
# COG
# ══════════════════════════════════════════

class InviteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        global _pending_joins, _member_inviters, _ip_records
        _pending_joins   = {int(k): v for k, v in get_pending_joins().items()}
        _member_inviters = {int(k): v for k, v in get_member_inviters().items()}
        _ip_records      = get_ip_records()

    # ── Lệnh prefix ──

    @commands.command(name="invite", aliases=["inv", "invites", "i"])
    async def invite_cmd(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        total, fake, left, net = _get_net_invites(target.id)
        embed = discord.Embed(
            title     = f"📨 Invite của {_uname(target)}",
            color     = 0x5865F2,
            timestamp = datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="✅ Net (thực tế)", value=f"**{net}** người",  inline=True)
        embed.add_field(name="📊 Tổng",          value=f"**{total}** lần",  inline=True)
        embed.add_field(name="⚠️ Fake",          value=f"**{fake}** người", inline=True)
        embed.add_field(name="🚪 Đã rời",        value=f"**{left}** người", inline=True)
        embed.set_footer(text="Net = Tổng − Fake − Đã rời  •  TuyTam Store")
        await ctx.reply(embed=embed)

    @commands.command(name="invitetop", aliases=["invtop"])
    async def invitetop_cmd(self, ctx, top: int = 10):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")
        top    = max(1, min(top, 25))
        counts = _get_invite_counts()
        board  = []
        for uid_str, c in counts.items():
            total = c.get("total", 0)
            fake  = c.get("fake",  0)
            left  = c.get("left",  0)
            net   = max(0, total - fake - left)
            board.append((int(uid_str), net, total, fake, left))
        board.sort(key=lambda x: x[1], reverse=True)
        board = board[:top]
        if not board:
            return await ctx.reply("❌ Chưa có dữ liệu invite nào.")
        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (uid, net, total, fake, left) in enumerate(board):
            icon   = medals[i] if i < 3 else f"`{i+1}.`"
            m      = ctx.guild.get_member(uid)
            name   = _uname(m) if m else f"ID:{uid}"
            lines.append(f"{icon} **{name}** — **{net}** net (`{total}` tổng, `{fake}` fake, `{left}` rời)")
        embed = discord.Embed(
            title       = f"🏆 Bảng xếp hạng Invite — Top {top}",
            description = "\n".join(lines),
            color       = 0xF1C40F,
            timestamp   = datetime.now(timezone.utc),
        )
        embed.set_footer(text="TuyTam Store  •  Net = Tổng − Fake − Đã rời")
        await ctx.reply(embed=embed)

    @commands.command(name="resetinvite", aliases=["resetinv"])
    async def resetinvite_cmd(self, ctx, *, arg: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        if arg and arg.strip().lower() == "all" and not ctx.message.mentions:
            _save_invite_counts({})
            await ctx.reply("✅ Đã reset toàn bộ invite của server.")
            await send_log(self.bot, "INVITE", "Reset toàn bộ invite server",
                fields=[("👤 Admin", str(ctx.author), True)])
            return

        member = None
        if ctx.message.mentions:
            member = ctx.message.mentions[0]
        elif arg:
            try:
                member = await commands.MemberConverter().convert(ctx, arg.strip())
            except commands.BadArgument:
                return await ctx.reply(
                    f"❌ Không tìm thấy thành viên `{arg.strip()}`.\n"
                    "Dùng: `.resetinvite @user` hoặc `.resetinvite all`"
                )

        if member:
            counts = _get_invite_counts()
            counts.pop(str(member.id), None)
            _save_invite_counts(counts)
            await ctx.reply(f"✅ Đã reset invite của **{_uname(member)}**.")
            await send_log(self.bot, "INVITE", f"Reset invite — {member}",
                fields=[
                    ("👤 Admin",  str(ctx.author), True),
                    ("🎯 Target", str(member),     True),
                ])
        else:
            await ctx.reply("❌ Dùng:\n`.resetinvite @user` — reset 1 người\n`.resetinvite all` — reset toàn bộ")

    # ── Events ──

    WELCOME_GUILDS = {
        950363132679831642: 1276087208150827070,
    }

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Welcome ping (xóa sau 10s)
        ch_id = self.WELCOME_GUILDS.get(member.guild.id)
        if ch_id:
            channel = member.guild.get_channel(ch_id)
            if channel:
                try:
                    msg = await channel.send(member.mention)
                    await asyncio.sleep(10)
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    pass

        # Xác định inviter qua cache
        try:
            old_cache   = _invite_cache.get(member.guild.id, {})
            new_invites = await member.guild.invites()
            new_cache   = {inv.code: inv.uses for inv in new_invites}
            inviter_id  = None
            invite_code = None
            for inv in new_invites:
                if inv.uses > old_cache.get(inv.code, 0):
                    if inv.inviter:
                        inviter_id  = inv.inviter.id
                        invite_code = inv.code
                    break
            _invite_cache[member.guild.id] = new_cache
        except (discord.Forbidden, discord.HTTPException):
            inviter_id  = None
            invite_code = None

        # Lưu pending
        if inviter_id and inviter_id != member.id:
            _pending_joins[member.id] = {
                "inviter_id":  inviter_id,
                "guild_id":    member.guild.id,
                "joined_at":   _time.time(),
                "invite_code": invite_code,
            }
            save_pending_joins(_pending_joins)
            _add_invite(inviter_id, "total", 1)

        # Log member join
        inviter_member = member.guild.get_member(inviter_id) if inviter_id else None
        await send_log(self.bot, "INVITE_JOIN", f"Thành viên mới tham gia",
            fields=[
                ("👤 Thành viên",  f"{member} (`{member.id}`)",        True),
                ("📨 Được mời bởi", str(inviter_member) if inviter_member else (f"ID:{inviter_id}" if inviter_id else "Không rõ"), True),
                ("🔗 Invite code", f"`{invite_code}`" if invite_code else "Không rõ", True),
                ("📅 Tạo acc",     f"<t:{int(member.created_at.timestamp())}:R>", True),
            ],
        )

        # Gửi DM link verify
        if inviter_id and inviter_id != member.id:
            await self._send_verify_dm(member, inviter_id)

    async def _send_verify_dm(self, member: discord.Member, inviter_id: int):
        """Gửi DM link verify, đăng ký callback xử lý kết quả."""
        token = create_token(member.id, member.guild.id, inviter_id, ttl=600)
        url   = build_verify_url(token)

        async def _on_verify(result: dict):
            await self._handle_verify_result(member, result)

        VERIFY_CALLBACKS[token] = _on_verify

        try:
            embed = discord.Embed(
                title       = "🔐 Xác minh thành viên — TuyTam Store",
                description = (
                    f"Xin chào **{member.display_name}**!\n\n"
                    "Để hoàn tất tham gia server, vui lòng xác minh bằng cách nhấn nút bên dưới.\n\n"
                    "⏱️ Link có hiệu lực trong **10 phút**.\n"
                    "⚠️ Tắt VPN/Proxy trước khi verify."
                ),
                color       = 0x5865F2,
            )
            embed.add_field(name="🔗 Link xác minh", value=f"[Nhấn vào đây để xác minh]({url})", inline=False)
            embed.set_footer(text="TuyTam Store  •  Xác minh bảo vệ cộng đồng")
            await member.send(embed=embed)
        except discord.Forbidden:
            # User tắt DM — log warning
            await send_log(self.bot, "INVITE_VERIFY", "Không thể gửi DM verify",
                fields=[
                    ("👤 Thành viên", f"{member} (`{member.id}`)", True),
                    ("⚠️ Lý do",      "User đã tắt DM",           True),
                ],
            )
            # Xóa callback vì sẽ không bao giờ được gọi
            VERIFY_CALLBACKS.pop(token, None)

        # Timeout 10 phút — nếu không verify thì xóa callback
        async def _timeout():
            await asyncio.sleep(600)
            if VERIFY_CALLBACKS.pop(token, None):
                await send_log(self.bot, "INVITE_VERIFY", "Hết hạn verify (không nhấn link)",
                    fields=[
                        ("👤 Thành viên", f"{member} (`{member.id}`)", True),
                        ("⏱️ Trạng thái", "Timeout 10 phút",           True),
                    ],
                )

        asyncio.create_task(_timeout())

    async def _handle_verify_result(self, member: discord.Member, result: dict):
        """Xử lý kết quả sau khi user click verify link."""
        user_id    = result["user_id"]
        inviter_id = result["inviter_id"]
        ip         = result["ip"]
        is_vpn     = result["is_vpn"]
        country    = result["country"]
        isp        = result["isp"]

        # VPN log (server đã hiển thị warning, chỉ log)
        if is_vpn:
            await send_log(self.bot, "INVITE_VERIFY", "Verify — phát hiện VPN/Proxy",
                fields=[
                    ("👤 Thành viên", f"{member} (`{user_id}`)",     True),
                    ("🌐 IP",         f"||`{ip}`||",                 True),
                    ("📡 ISP",        isp,                           True),
                    ("🌍 Quốc gia",   country,                       True),
                    ("⚠️ VPN",        "✅ Phát hiện",                True),
                ],
            )
            # Không tính fake chỉ vì dùng VPN — chờ họ re-verify

        # Check IP collision
        is_fake, fake_reason = _check_ip_collision(user_id, ip, inviter_id)

        # Lưu IP mapping
        _register_ip(user_id, ip)

        # Xác nhận member hợp lệ
        _pending_joins.pop(user_id, None)
        save_pending_joins(_pending_joins)
        _member_inviters[user_id] = {"inviter_id": inviter_id, "guild_id": result["guild_id"]}
        save_member_inviters(_member_inviters)

        if is_fake:
            # Đánh dấu fake
            _add_invite(inviter_id, "fake", 1)
            inviter_member = member.guild.get_member(inviter_id) if member.guild else None
            await send_log(self.bot, "INVITE_FAKE", "⚠️ Fake invite phát hiện qua IP",
                fields=[
                    ("👤 Member (fake)",  f"{member} (`{user_id}`)",                                         True),
                    ("📨 Inviter",        str(inviter_member) if inviter_member else f"ID:{inviter_id}",      True),
                    ("🌐 IP",             f"||`{ip}`||",                                                      True),
                    ("🔍 Lý do",          fake_reason,                                                        False),
                    ("📡 ISP",            isp,                                                                True),
                    ("🌍 Quốc gia",       country,                                                            True),
                ],
            )
        else:
            # Verify sạch
            await send_log(self.bot, "INVITE_VERIFY", "Verify thành công",
                fields=[
                    ("👤 Thành viên", f"{member} (`{user_id}`)", True),
                    ("🌐 IP",         f"||`{ip}`||",             True),
                    ("🌍 Quốc gia",   country,                   True),
                    ("📡 ISP",        isp,                       True),
                    ("✅ Trạng thái", "Hợp lệ",                  True),
                ],
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await cache_invites(member.guild)

        if member.id in _pending_joins:
            _pending_joins.pop(member.id, None)
            save_pending_joins(_pending_joins)
            return

        inv_info = _member_inviters.pop(member.id, None)
        if inv_info:
            _add_invite(inv_info["inviter_id"], "left", 1)
            save_member_inviters(_member_inviters)

            inviter_m = member.guild.get_member(inv_info["inviter_id"])
            await send_log(self.bot, "INVITE_LEFT", "Thành viên rời server",
                fields=[
                    ("👤 Thành viên", f"{member} (`{member.id}`)",                                              True),
                    ("📨 Được mời bởi", str(inviter_m) if inviter_m else f"ID:{inv_info['inviter_id']}",        True),
                ],
            )

    # ── Slash commands ──

    @discord.app_commands.command(name="invite", description="Xem thống kê invite của thành viên")
    @discord.app_commands.describe(member="Thành viên (để trống = bản thân)")
    async def slash_invite(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        total, fake, left, net = _get_net_invites(target.id)
        embed = discord.Embed(
            title     = f"📨 Invite của {_uname(target)}",
            color     = 0x5865F2,
            timestamp = datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="✅ Net",     value=f"**{net}**",   inline=True)
        embed.add_field(name="📊 Tổng",   value=f"**{total}**", inline=True)
        embed.add_field(name="⚠️ Fake",   value=f"**{fake}**",  inline=True)
        embed.add_field(name="🚪 Đã rời", value=f"**{left}**",  inline=True)
        embed.set_footer(text="Net = Tổng − Fake − Đã rời")
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="invitetop", description="Bảng xếp hạng invite (admin)")
    @discord.app_commands.describe(top="Số người top (mặc định 10)")
    async def slash_invitetop(self, interaction: discord.Interaction, top: int = 10):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        top    = max(1, min(top, 25))
        counts = _get_invite_counts()
        board  = []
        for uid_str, c in counts.items():
            net = max(0, c.get("total", 0) - c.get("fake", 0) - c.get("left", 0))
            board.append((int(uid_str), net, c.get("total", 0), c.get("fake", 0), c.get("left", 0)))
        board.sort(key=lambda x: x[1], reverse=True)
        board = board[:top]
        if not board:
            return await interaction.response.send_message("❌ Chưa có dữ liệu invite.", ephemeral=True)
        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (uid, net, *_) in enumerate(board):
            icon = medals[i] if i < 3 else f"`{i+1}.`"
            m    = interaction.guild.get_member(uid) if interaction.guild else None
            name = _uname(m) if m else f"ID:{uid}"
            lines.append(f"{icon} **{name}** — **{net}** net")
        embed = discord.Embed(
            title       = f"🏆 Top {top} Invite",
            description = "\n".join(lines),
            color       = 0xF1C40F,
        )
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="resetinvite", description="Reset invite của thành viên (admin)")
    @discord.app_commands.describe(member="Thành viên cần reset (để trống = reset tất cả)")
    async def slash_resetinvite(self, interaction: discord.Interaction, member: discord.Member = None):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        if member:
            counts = _get_invite_counts()
            counts.pop(str(member.id), None)
            _save_invite_counts(counts)
            await interaction.response.send_message(f"✅ Đã reset invite của {member}.", ephemeral=True)
        else:
            _save_invite_counts({})
            await interaction.response.send_message("✅ Đã reset toàn bộ invite server.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteCog(bot))
