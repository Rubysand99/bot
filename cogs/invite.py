"""
cogs/invite.py — Invite tracking + IP-based fake detection + verify system.
v6.0.0:
  - Role UNVERIFY (gán khi join, không xem được kênh nào) + VERIFY (gán sau khi verify xong)
  - Nếu trùng IP: vẫn cho phép verify + gán VERIFY, nhưng lưu data shared_ip
    → Chỉ 1 tài khoản trên cùng IP được tham gia giveaway (tài khoản join trước)
    → Bot gửi ephemeral thông báo khi user bị chặn tham gia giveaway
  - Member không verify sẽ giữ nguyên role Unverify (không auto-kick)
  - Lệnh .checkip <@user|id> để admin xem tài khoản chung IP
  - Log đầy đủ: INVITE_JOIN, INVITE_VERIFY, INVITE_FAKE, INVITE_LEFT
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
    atomic_register_ip, get_ip_users_mongo,
)
from verify_server import (
    create_token, build_verify_url, VERIFY_CALLBACKS,
)

# ── Role IDs (fallback defaults, sẽ được cập nhật động khi _ensure_roles chạy) ──
UNVERIFY_ROLE_ID = 0  # sẽ được set động bởi _ensure_roles
VERIFY_ROLE_ID   = 0  # sẽ được set động bởi _ensure_roles

# ── Các role được gán khi verify thành công (ngoài role Verify tự tạo) ──
MEMBER_ROLE_IDS = [
    1500512964065755288,  # ping Stock
    1500513085096726528,  # ping Notification
    1464411190808805540,  # Member
    1500512893139943455,  # ping media
]


# ── Per-guild role ID cache ──
# {guild_id: {"verify": role_id, "unverify": role_id}}
_guild_roles: dict[int, dict[str, int]] = {}

def _get_verify_role_id(guild_id: int) -> int:
    return _guild_roles.get(guild_id, {}).get("verify", VERIFY_ROLE_ID)

def _get_unverify_role_id(guild_id: int) -> int:
    return _guild_roles.get(guild_id, {}).get("unverify", UNVERIFY_ROLE_ID)



_invite_cache:    dict[int, dict[str, int]] = {}
_pending_joins:   dict[int, dict]           = {}   # member_id → {inviter_id, guild_id, joined_at}
_member_inviters: dict[int, dict]           = {}   # member_id → {inviter_id, guild_id}
_ip_records:      dict[str, list[int]]      = {}   # ip → [user_id, ...]  (persist MongoDB)

# shared_ip: ip → first_verified_user_id (tài khoản đầu tiên verify trên IP đó được ưu tiên giveaway)
# lưu trong MongoDB qua key "_shared_ip" trong main doc
def _get_shared_ip() -> dict:
    return load_data().get("_shared_ip", {})

def _save_shared_ip(data: dict):
    d = load_data()
    d["_shared_ip"] = data
    save_data(d)

def get_primary_user_for_ip(ip: str) -> int | None:
    """Trả về user_id đầu tiên verify trên IP này (được phép join giveaway)."""
    return _get_shared_ip().get(ip)

def register_primary_ip(ip: str, user_id: int):
    """Đăng ký user đầu tiên trên IP — chỉ ghi nếu chưa có."""
    d = _get_shared_ip()
    if ip not in d:
        d[ip] = user_id
        _save_shared_ip(d)


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

async def _check_ip_collision(user_id: int, ip: str, inviter_id: int | None) -> tuple[bool, str]:
    """
    Đọc trực tiếp từ MongoDB (không qua cache) để tránh race condition.
    Trả về (is_fake: bool, reason: str)
    """
    users_on_ip = await get_ip_users_mongo(ip)

    if inviter_id and inviter_id in users_on_ip:
        return True, f"IP trùng với inviter (ID:{inviter_id})"

    others = [uid for uid in users_on_ip if uid != user_id]
    if others:
        return True, f"IP trùng với {len(others)} thành viên khác ({', '.join(f'ID:{u}' for u in others[:3])})"

    return False, ""

async def _register_ip(user_id: int, ip: str) -> list[int]:
    """
    Atomic $addToSet vào MongoDB — tránh race condition.
    Trả về list user_ids hiện tại trên IP đó.
    """
    users = await atomic_register_ip(ip, user_id)
    # Sync in-memory cache
    ip_key = ip.replace(".", "_")
    _ip_records[ip_key] = users
    return users


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

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._ensure_roles(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Khi bot vào server mới → tự tạo role và set permission."""
        await self._ensure_roles(guild)
        await send_log(self.bot, "INFO", f"Bot vừa vào server mới: {guild.name}",
            fields=[
                ("🆔 ID",      str(guild.id),                                   True),
                ("👑 Owner",   str(guild.owner) if guild.owner else "?",        True),
                ("👥 Members", str(guild.member_count),                         True),
            ],
        )

    async def _ensure_roles(self, guild: discord.Guild):
        """Tự tạo role UNVERIFY / VERIFY nếu chưa có, set permission Unverify.
        Hoạt động đúng trên đa server — lưu role ID vào _guild_roles."""

        # ── UNVERIFY ──
        unverify = guild.get_role(_get_unverify_role_id(guild.id))
        if not unverify:
            unverify = discord.utils.get(guild.roles, name="Unverify")
        if not unverify:
            try:
                unverify = await guild.create_role(
                    name   = "Unverify",
                    color  = discord.Color.dark_gray(),
                    reason = "Auto-create bởi TuyTam Bot — role chờ verify",
                )
                print(f"[INVITE] ✅ Đã tạo role Unverify ({unverify.id}) tại {guild.name}")
            except discord.Forbidden:
                print(f"[INVITE] ❌ Không có quyền tạo role tại {guild.name}")
                return

        _guild_roles.setdefault(guild.id, {})["unverify"] = unverify.id

        # ── VERIFY ──
        verify = guild.get_role(_get_verify_role_id(guild.id))
        if not verify:
            verify = discord.utils.get(guild.roles, name="Verify")
        if not verify:
            try:
                verify = await guild.create_role(
                    name   = "Verify",
                    color  = discord.Color.green(),
                    reason = "Auto-create bởi TuyTam Bot — role sau khi verify",
                )
                print(f"[INVITE] ✅ Đã tạo role Verify ({verify.id}) tại {guild.name}")
            except discord.Forbidden:
                print(f"[INVITE] ❌ Không có quyền tạo role tại {guild.name}")
                return

        _guild_roles.setdefault(guild.id, {})["verify"] = verify.id

        # ── Xóa overwrite của Verify / Unverify trên tất cả kênh về mặc định ──
        for channel in guild.channels:
            for role in (verify, unverify):
                try:
                    ow = channel.overwrites_for(role)
                    if not ow.is_empty():
                        await channel.set_permissions(role, overwrite=None,
                                                      reason="Reset overwrite Verify/Unverify về mặc định")
                except (discord.Forbidden, discord.HTTPException):
                    pass

        print(f"[INVITE] ✅ Roles OK tại {guild.name} — Verify:{verify.id} Unverify:{unverify.id}")

    @commands.command(name="verify")
    async def verify_cmd(self, ctx, target_id: str = None):
        """
        Member tự gõ .verify → nhận link xác minh qua DM.
        Admin gõ .verify <user_id> → verify cưỡng bức (không cần link), gán role ngay.
        """
        guild = ctx.guild

        # ── ADMIN FORCE VERIFY ──
        if target_id:
            if ctx.author.id not in ADMIN_IDS:
                return await ctx.reply("❌ Chỉ admin mới có thể verify cho người khác.")

            # Resolve member
            member = None
            try:
                uid = int(target_id.strip("<@!>"))
                member = guild.get_member(uid) or await guild.fetch_member(uid)
            except (ValueError, discord.NotFound, discord.HTTPException):
                pass

            if not member:
                return await ctx.reply(f"❌ Không tìm thấy member `{target_id}` trong server.")

            verify_role   = guild.get_role(_get_verify_role_id(guild.id))
            unverify_role = guild.get_role(_get_unverify_role_id(guild.id))

            if verify_role and verify_role in member.roles:
                return await ctx.reply(f"✅ {member.mention} đã được verify rồi.")

            try:
                roles_to_add = []
                if verify_role:
                    roles_to_add.append(verify_role)
                for rid in MEMBER_ROLE_IDS:
                    role = guild.get_role(rid)
                    if role and role not in member.roles:
                        roles_to_add.append(role)
                if roles_to_add:
                    await member.add_roles(*roles_to_add, reason=f"Force verify bởi {ctx.author}")
                if unverify_role and unverify_role in member.roles:
                    await member.remove_roles(unverify_role, reason=f"Force verify bởi {ctx.author}")
            except (discord.Forbidden, discord.HTTPException) as e:
                return await ctx.reply(f"❌ Không gán được role: `{e}`")

            # Lưu vào member_inviters để tracking
            inv_info = _member_inviters.get(member.id, {})
            if not inv_info:
                _member_inviters[member.id] = {"inviter_id": None, "guild_id": guild.id}
                save_member_inviters(_member_inviters)

            await ctx.reply(f"✅ Đã verify **{member}** thành công.")
            await send_log(self.bot, "INVITE_VERIFY", f"Force verify bởi admin",
                fields=[
                    ("👤 Member",  f"{member} (`{member.id}`)", True),
                    ("⚙️ Admin",   str(ctx.author),             True),
                    ("📌 Method",  "Force (không qua link)",    True),
                ],
            )
            return

        # ── MEMBER TỰ VERIFY ──
        member = ctx.author

        verify_role = guild.get_role(_get_verify_role_id(guild.id)) if guild else None
        if verify_role and verify_role in member.roles:
            return await ctx.reply("✅ Bạn đã được xác minh rồi!")

        # Gán Unverify nếu chưa có (member cũ)
        unverify_role = guild.get_role(_get_unverify_role_id(guild.id)) if guild else None
        if unverify_role and unverify_role not in member.roles:
            try:
                await member.add_roles(unverify_role, reason="Chờ verify")
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Lấy inviter nếu có
        inv_info   = _member_inviters.get(member.id, {})
        inviter_id = inv_info.get("inviter_id")

        await self._send_verify_dm(member, inviter_id)

        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            await member.send("📨 Link verify đã được gửi vào DM của bạn!")
        except discord.Forbidden:
            await ctx.send(f"{member.mention} Vui lòng bật DM để nhận link verify.", delete_after=10)

    @commands.command(name="serverlist", aliases=["servers", "guildlist"])
    async def serverlist_cmd(self, ctx):
        """Admin xem danh sách server bot đang hoạt động."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        guilds = self.bot.guilds
        if not guilds:
            return await ctx.reply("❌ Bot chưa vào server nào.")

        embed = discord.Embed(
            title     = f"🌐 Bot đang ở {len(guilds)} server",
            color     = 0x5865F2,
            timestamp = datetime.now(timezone.utc),
        )

        for g in sorted(guilds, key=lambda x: x.member_count, reverse=True):
            bots    = sum(1 for m in g.members if m.bot)
            humans  = g.member_count - bots
            owner   = str(g.owner) if g.owner else f"ID:{g.owner_id}"
            embed.add_field(
                name  = f"{g.name}",
                value = (
                    f"🆔 `{g.id}`\n"
                    f"👑 {owner}\n"
                    f"👥 {humans} người · 🤖 {bots} bot\n"
                    f"📅 <t:{int(g.created_at.timestamp())}:D>"
                ),
                inline = True,
            )

        embed.set_footer(text=f"TuyTam Bot  •  {len(guilds)} servers")
        await ctx.reply(embed=embed)

    @commands.command(name="leaveguild", aliases=["leaveserver"])
    async def leaveguild_cmd(self, ctx, guild_id: str = None):
        """Admin kick bot ra khỏi server. Dùng: .leaveguild <guild_id>"""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        if not guild_id:
            return await ctx.reply(
                "❌ Dùng: `.leaveguild <guild_id>`\n"
                "Xem danh sách server: `.serverlist`"
            )

        try:
            gid = int(guild_id.strip())
        except ValueError:
            return await ctx.reply("❌ Guild ID không hợp lệ.")

        guild = self.bot.get_guild(gid)
        if not guild:
            return await ctx.reply(f"❌ Không tìm thấy server `{gid}`.")

        name = guild.name
        try:
            await guild.leave()
            await ctx.reply(f"✅ Bot đã rời khỏi **{name}** (`{gid}`).")
            await send_log(self.bot, "INFO", f"Bot rời server: {name}",
                fields=[
                    ("🆔 Guild ID", str(gid),         True),
                    ("⚙️ Admin",    str(ctx.author),   True),
                ],
            )
        except discord.HTTPException as e:
            await ctx.reply(f"❌ Không rời được: `{e}`")


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

        # Gán role UNVERIFY ngay khi join
        unverify_role = member.guild.get_role(_get_unverify_role_id(member.guild.id))
        if unverify_role:
            try:
                await member.add_roles(unverify_role, reason="Chưa verify")
            except (discord.Forbidden, discord.HTTPException):
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
        await self._send_verify_dm(member, inviter_id)

        # Auto-kick sau 24h đã bị tắt — member giữ nguyên role Unverify nếu không verify

    async def _send_verify_dm(self, member: discord.Member, inviter_id: int | None):
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

        # VPN log
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

        # Check IP collision — đọc thẳng MongoDB trước khi ghi
        is_fake, fake_reason = await _check_ip_collision(user_id, ip, inviter_id)

        # Lưu IP mapping — atomic $addToSet, tránh race condition
        await _register_ip(user_id, ip)

        # Đăng ký primary user cho IP này (user đầu tiên verify = được join giveaway)
        register_primary_ip(ip, user_id)

        # Xác nhận member hợp lệ — xóa pending
        _pending_joins.pop(user_id, None)
        save_pending_joins(_pending_joins)
        _member_inviters[user_id] = {"inviter_id": inviter_id, "guild_id": result["guild_id"]}
        save_member_inviters(_member_inviters)

        # Gán role VERIFY + các role member, xóa UNVERIFY
        guild = self.bot.get_guild(member.guild.id)
        if guild:
            m = guild.get_member(user_id)
            if m:
                verify_role   = guild.get_role(_get_verify_role_id(guild.id))
                unverify_role = guild.get_role(_get_unverify_role_id(guild.id))
                roles_to_add = []
                if verify_role and verify_role not in m.roles:
                    roles_to_add.append(verify_role)
                for rid in MEMBER_ROLE_IDS:
                    role = guild.get_role(rid)
                    if role and role not in m.roles:
                        roles_to_add.append(role)
                try:
                    if roles_to_add:
                        await m.add_roles(*roles_to_add, reason="Đã verify")
                    if unverify_role and unverify_role in m.roles:
                        await m.remove_roles(unverify_role, reason="Đã verify")
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"[INVITE] ⚠️ Không gán được role verify: {e}")

        if is_fake:
            # Đánh dấu fake nhưng vẫn cho vào — đã gán VERIFY ở trên
            _add_invite(inviter_id, "fake", 1)
            inviter_member = member.guild.get_member(inviter_id) if member.guild else None

            # Lấy danh sách tài khoản cùng IP
            shared_users = _ip_records.get(ip, [])
            primary_id   = get_primary_user_for_ip(ip)
            is_primary   = (primary_id == user_id)

            # DM thông báo cho user bị ảnh hưởng
            try:
                if is_primary:
                    notice = (
                        f"⚠️ **Thông báo từ TuyTam Store**\n\n"
                        f"Tài khoản của bạn đã verify thành công. Tuy nhiên, chúng tôi phát hiện "
                        f"có **{len(shared_users) - 1}** tài khoản khác đang dùng chung địa chỉ IP với bạn.\n\n"
                        f"Bạn vẫn có thể tham gia giveaway bình thường vì bạn là tài khoản **đầu tiên** xác minh trên IP này.\n"
                        f"Các tài khoản còn lại sẽ **không thể** tham gia giveaway."
                    )
                else:
                    primary_m = guild.get_member(primary_id) if guild and primary_id else None
                    primary_name = str(primary_m) if primary_m else f"ID:{primary_id}"
                    notice = (
                        f"⚠️ **Thông báo từ TuyTam Store**\n\n"
                        f"Tài khoản của bạn đã verify thành công. Tuy nhiên, địa chỉ IP của bạn **trùng** "
                        f"với tài khoản `{primary_name}` đã xác minh trước đó.\n\n"
                        f"Do chính sách chống gian lận, **mỗi địa chỉ IP chỉ được phép 1 tài khoản tham gia giveaway**. "
                        f"Vì vậy, bạn sẽ **không thể bấm tham gia giveaway** trên server này.\n\n"
                        f"Nếu bạn cho rằng đây là nhầm lẫn (dùng chung mạng gia đình, trường học...), "
                        f"vui lòng liên hệ admin để được hỗ trợ."
                    )
                await member.send(notice)
            except discord.Forbidden:
                pass

            await send_log(self.bot, "INVITE_FAKE", "⚠️ IP trùng — đã verify nhưng bị hạn chế giveaway",
                fields=[
                    ("👤 Member",    f"{member} (`{user_id}`)",                                         True),
                    ("📨 Inviter",   str(inviter_member) if inviter_member else f"ID:{inviter_id}",      True),
                    ("🌐 IP",        f"||`{ip}`||",                                                      True),
                    ("🔍 Lý do",     fake_reason,                                                        False),
                    ("🎯 Giveaway",  "✅ Được phép" if is_primary else "❌ Bị chặn",                    True),
                    ("📡 ISP",       isp,                                                                True),
                    ("🌍 Quốc gia",  country,                                                            True),
                ],
            )
        else:
            await send_log(self.bot, "INVITE_VERIFY", "✅ Verify thành công",
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

    @commands.command(name="backfillip")
    async def backfillip_cmd(self, ctx, limit: int = 2000):
        """
        Admin: đọc lại lịch sử kênh log general, parse IP từ INVITE_VERIFY/INVITE_FAKE,
        rồi backfill vào MongoDB _ip_records.
        Dùng: .backfillip        → quét 2000 message gần nhất
              .backfillip 5000   → quét 5000 message
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        import re
        from core.data import _get_mongo

        # Lấy kênh log general
        from cogs.logger import get_log_channel
        ch_id = get_log_channel("general")
        if not ch_id:
            return await ctx.reply("❌ Chưa cài kênh log `general`. Dùng `.setlog` trước.")

        log_channel = self.bot.get_channel(ch_id) or await self.bot.fetch_channel(ch_id)
        if not log_channel:
            return await ctx.reply(f"❌ Không tìm được kênh log `{ch_id}`.")

        status_msg = await ctx.reply(f"⏳ Đang quét {limit} message trong {log_channel.mention}...")

        # Regex parse user_id và IP từ plain text log
        # Format thực: chip020408 (`1259747159092367364`)  ·  **🌐 IP:** ||`14.228.52.58`||
        re_user2 = re.compile(r"\(`(\d{10,20})`\)")  # match (`<id>`) bất kỳ chỗ nào
        re_ip    = re.compile(r"\|\|`([\d\.]+)`\|\|")

        found   = 0   # message INVITE_VERIFY/FAKE dùng được
        added   = 0   # cặp (ip, user_id) mới được ghi
        skipped = 0   # đã có trong records rồi

        col, _ = _get_mongo()

        async for msg in log_channel.history(limit=limit, oldest_first=False):
            content = msg.content
            if "[INVITE_VERIFY]" not in content and "[INVITE_FAKE]" not in content:
                continue

            # Parse user_id
            m_user = re_user2.search(content)
            if not m_user:
                continue
            try:
                user_id = int(m_user.group(1))
            except ValueError:
                continue

            # Parse IP
            m_ip = re_ip.search(content)
            if not m_ip:
                continue
            ip = m_ip.group(1)

            found += 1
            ip_key = ip.replace(".", "_")

            # Kiểm tra đã có chưa — dùng $addToSet (atomic, idempotent)
            result = await col.update_one(
                {"_id": "main"},
                {"$addToSet": {f"_ip_records.{ip_key}": user_id}},
                upsert=True,
            )
            if result.modified_count > 0:
                added += 1
            else:
                skipped += 1

            # Đăng ký primary IP nếu chưa có
            await col.update_one(
                {"_id": "main", f"_shared_ip.{ip}": {"$exists": False}},
                {"$set": {f"_shared_ip.{ip}": user_id}},
            )

        # Sync lại in-memory cache
        doc = await col.find_one({"_id": "main"}, {"_ip_records": 1})
        global _ip_records
        _ip_records = (doc or {}).get("_ip_records", {})

        await status_msg.edit(content=(
            f"✅ **Backfill hoàn tất**\n"
            f"› Quét: **{limit}** message\n"
            f"› Tìm thấy INVITE_VERIFY/FAKE: **{found}**\n"
            f"› Ghi mới vào DB: **{added}** cặp (ip, user)\n"
            f"› Đã có sẵn (bỏ qua): **{skipped}**\n\n"
            f"Dùng `.ipstats` để xem kết quả."
        ))

    @commands.command(name="checkip")
    async def checkip_cmd(self, ctx, *, arg: str = None):
        """Admin xem tài khoản chung IP với 1 user."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        target_id = None
        if ctx.message.mentions:
            target_id = ctx.message.mentions[0].id
        elif arg:
            try:
                target_id = int(arg.strip())
            except ValueError:
                return await ctx.reply("❌ Dùng: `.checkip @user` hoặc `.checkip <user_id>`")

        if not target_id:
            return await ctx.reply("❌ Dùng: `.checkip @user` hoặc `.checkip <user_id>`")

        # Đọc thẳng từ MongoDB — tránh cache stale
        from core.data import _get_mongo
        col, _ = _get_mongo()
        try:
            doc = await col.find_one({"_id": "main"}, {"_ip_records": 1, "_shared_ip": 1})
        except Exception as e:
            return await ctx.reply(f"❌ Lỗi đọc MongoDB: `{e}`")

        ip_records_raw  = (doc or {}).get("_ip_records", {})  # key dạng "1_2_3_4"
        shared_ip_raw   = (doc or {}).get("_shared_ip", {})   # key dạng "1.2.3.4"

        # Tìm tất cả key IP có target_id
        found = []  # list of (ip_display, users)
        for key, users in ip_records_raw.items():
            if target_id in users:
                ip_display = key.replace("_", ".")
                found.append((ip_display, users))

        if not found:
            return await ctx.reply(f"❌ Không có dữ liệu IP cho user `{target_id}`. Có thể chưa verify.")

        embed = discord.Embed(
            title     = f"🔍 Kiểm tra IP — ID:{target_id}",
            color     = 0xE74C3C,
            timestamp = datetime.now(timezone.utc),
        )
        embed.set_footer(text="TuyTam Store  •  Chỉ admin thấy")

        for ip_display, users_on_ip in found:
            primary_id = shared_ip_raw.get(ip_display)
            lines = []
            for uid in users_on_ip:
                m         = ctx.guild.get_member(uid) if ctx.guild else None
                name      = str(m) if m else f"ID:{uid}"
                is_target = "← target" if uid == target_id else ""
                is_prim   = "✅ giveaway OK" if uid == primary_id else "❌ blocked giveaway"
                lines.append(f"`{uid}` **{name}** — {is_prim} {is_target}")

            embed.add_field(
                name   = f"🌐 IP: ||`{ip_display}`|| ({len(users_on_ip)} tài khoản)",
                value  = "\n".join(lines) or "*(trống)*",
                inline = False,
            )

        await ctx.reply(embed=embed)

    @commands.command(name="ipstats")
    async def ipstats_cmd(self, ctx):
        """Admin xem danh sách IP có từ 2 tài khoản trở lên."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        # Đọc thẳng từ MongoDB
        from core.data import _get_mongo
        col, _ = _get_mongo()
        try:
            doc = await col.find_one({"_id": "main"}, {"_ip_records": 1, "_shared_ip": 1})
        except Exception as e:
            return await ctx.reply(f"❌ Lỗi đọc MongoDB: `{e}`")

        ip_records_raw = (doc or {}).get("_ip_records", {})  # key dạng "1_2_3_4"
        shared_ip_raw  = (doc or {}).get("_shared_ip", {})   # key dạng "1.2.3.4"

        # Lọc IP có ≥ 2 acc, convert key về dạng hiển thị
        dupes = {
            key.replace("_", "."): uids
            for key, uids in ip_records_raw.items()
            if len(uids) >= 2
        }
        if not dupes:
            return await ctx.reply("✅ Không có IP nào dùng chung từ 2 tài khoản trở lên.")

        sorted_dupes = sorted(dupes.items(), key=lambda x: len(x[1]), reverse=True)

        PAGE_SIZE = 5
        pages     = [sorted_dupes[i:i+PAGE_SIZE] for i in range(0, len(sorted_dupes), PAGE_SIZE)]
        total_ips = len(sorted_dupes)
        total_acc = sum(len(uids) for uids in dupes.values())

        embeds = []
        for page_idx, page in enumerate(pages):
            embed = discord.Embed(
                title     = f"🌐 IP dùng chung — {total_ips} IP · {total_acc} tài khoản",
                color     = 0xE74C3C,
                timestamp = datetime.now(timezone.utc),
            )
            if len(pages) > 1:
                embed.set_author(name=f"Trang {page_idx+1}/{len(pages)}")
            embed.set_footer(text="TuyTam Store  •  Chỉ admin thấy")

            for ip_display, uids in page:
                primary_id = shared_ip_raw.get(ip_display)
                lines = []
                for uid in uids:
                    m        = ctx.guild.get_member(uid) if ctx.guild else None
                    name     = str(m) if m else f"ID:{uid}"
                    is_prim  = "✅" if uid == primary_id else "❌"
                    lines.append(f"{is_prim} `{uid}` {name}")
                embed.add_field(
                    name   = f"||`{ip_display}`|| — {len(uids)} acc",
                    value  = "\n".join(lines),
                    inline = False,
                )
            embeds.append(embed)

        for e in embeds:
            await ctx.send(embed=e)

    @commands.command(name="testip")
    async def testip_cmd(self, ctx):
        """Admin: thêm data test — 1 IP giả có 2 acc, gửi log INVITE_VERIFY + INVITE_FAKE."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        from core.data import _get_mongo

        TEST_IP      = "192.168.99.99"
        TEST_IP_KEY  = TEST_IP.replace(".", "_")
        ACC1_ID      = 111111111111111111
        ACC2_ID      = 222222222222222222
        ACC1_NAME    = "TestAcc1#0001"
        ACC2_NAME    = "TestAcc2#0002"

        col, _ = _get_mongo()
        try:
            # Ghi _ip_records: ip → [acc1, acc2]
            await col.update_one(
                {"_id": "main"},
                {"$set": {f"_ip_records.{TEST_IP_KEY}": [ACC1_ID, ACC2_ID]}},
                upsert=True,
            )
            # Ghi _shared_ip: ip → acc1 (acc đầu tiên verify)
            await col.update_one(
                {"_id": "main"},
                {"$set": {f"_shared_ip.{TEST_IP}": ACC1_ID}},
                upsert=True,
            )
        except Exception as e:
            return await ctx.reply(f"❌ Lỗi MongoDB: `{e}`")

        # Reload cache
        global _ip_records
        _ip_records = get_ip_records()

        # Gửi log INVITE_VERIFY (acc1 — verify thành công bình thường)
        await send_log(self.bot, "INVITE_VERIFY", "✅ Verify thành công",
            fields=[
                ("👤 Thành viên", f"{ACC1_NAME} (`{ACC1_ID}`)", True),
                ("🌐 IP",         f"||`{TEST_IP}`||",           True),
                ("📡 ISP",        "Test ISP",                   True),
                ("🌍 Quốc gia",   "Vietnam",                    True),
            ],
        )

        # Gửi log INVITE_FAKE (acc2 — trùng IP, bị chặn giveaway)
        await send_log(self.bot, "INVITE_FAKE", "⚠️ IP trùng — đã verify nhưng bị hạn chế giveaway",
            fields=[
                ("👤 Member",   f"{ACC2_NAME} (`{ACC2_ID}`)",                     True),
                ("📨 Inviter",  "TestInviter#0000",                                True),
                ("🌐 IP",       f"||`{TEST_IP}`||",                                True),
                ("🔍 Lý do",    f"IP trùng với `{ACC1_NAME}` (đã verify trước)",   False),
                ("🎯 Giveaway", "❌ Bị chặn",                                      True),
                ("📡 ISP",      "Test ISP",                                        True),
                ("🌍 Quốc gia", "Vietnam",                                         True),
            ],
        )

        await ctx.reply(
            f"✅ **Test data đã được thêm!**\n"
            f"• IP: `{TEST_IP}`\n"
            f"• Acc 1 (✅ giveaway): `{ACC1_ID}` — {ACC1_NAME}\n"
            f"• Acc 2 (❌ bị chặn): `{ACC2_ID}` — {ACC2_NAME}\n"
            f"• Log INVITE_VERIFY + INVITE_FAKE đã gửi.\n"
            f"Gõ `.ipstats` để xem kết quả."
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
