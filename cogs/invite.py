"""
cogs/invite.py — Invite tracking + IP-based fake detection + verify system.
v6.1.0:
  - Monthly leaderboard reset: invite_counts_YYYY_MM (tháng hiện tại)
  - All-time total: invite_counts_all (cộng dồn mãi mãi, không bao giờ reset)
  - Cuối tháng / đầu tháng mới → tự snapshot + reset tháng hiện tại
  - .invite: hiển thị cả tháng này + tổng all-time
  - .invitetop: leaderboard tháng này, có flag --alltime để xem tổng
  - .resetinvite: chỉ reset tháng hiện tại, all-time KHÔNG bị ảnh hưởng
"""

import asyncio
import time as _time
from datetime import datetime, timezone

import discord
from discord.ext import commands

from cogs.logger import send_log
from core.data import (
    ADMIN_IDS, load_data, save_data, _uname,
    load_global_data, save_global_data,
    get_member_inviters, save_member_inviters,
    get_pending_joins, save_pending_joins,
    get_ip_records,
    atomic_register_ip, get_ip_users_mongo,
    set_current_guild, get_or_fetch_channel,
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
# FIX: dùng load_global_data()/save_global_data() thay vì load_data()/save_data() —
# IP không thuộc về guild nào cụ thể (giống _ip_records/_tempbans), dùng nhầm hàm theo-guild
# trước đây khiến dữ liệu bị tách lẻ sai theo guild hiện tại thay vì dùng chung.
def _get_shared_ip() -> dict:
    return load_global_data().get("_shared_ip", {})

def _save_shared_ip(data: dict):
    d = load_global_data()
    d["_shared_ip"] = data
    save_global_data(d)

def get_primary_user_for_ip(ip: str) -> int | None:
    """Trả về user_id đầu tiên verify trên IP này (được phép join giveaway)."""
    return _get_shared_ip().get(ip)

def register_primary_ip(ip: str, user_id: int):
    """Đăng ký user đầu tiên trên IP — chỉ ghi nếu chưa có."""
    d = _get_shared_ip()
    if ip not in d:
        d[ip] = user_id
        _save_shared_ip(d)


# vpn_users: user_id (str) → {ip, country, isp, ts}
# lưu trong MongoDB qua key "_vpn_users" trong main doc
async def _register_vpn(user_id: int, ip: str, country: str, isp: str):
    """Đánh dấu user đã verify bằng VPN/Proxy — ghi atomic vào MongoDB."""
    from core.data import _get_mongo
    col, _ = _get_mongo()
    try:
        await col.update_one(
            {"_id": "main"},
            {"$set": {
                f"_vpn_users.{user_id}": {
                    "ip":      ip,
                    "country": country,
                    "isp":     isp,
                    "ts":      datetime.now(timezone.utc).isoformat(),
                }
            }},
            upsert=True,
        )
    except Exception as e:
        print(f"[INVITE] ⚠️ Không lưu được _vpn_users: {e}")


# ══════════════════════════════════════════
# INVITE COUNTS HELPERS — MONTHLY + ALL-TIME
# ══════════════════════════════════════════

def _month_key(dt: datetime | None = None) -> str:
    """Trả về key tháng hiện tại: 'invite_counts_YYYY_MM'."""
    dt = dt or datetime.now(timezone.utc)
    return f"invite_counts_{dt.year}_{dt.month:02d}"

def _get_invite_counts(month_key: str | None = None) -> dict:
    """Lấy invite counts của tháng (mặc định tháng hiện tại)."""
    key = month_key or _month_key()
    return load_data().get(key, {})

def _save_invite_counts(counts: dict, month_key: str | None = None):
    """Lưu invite counts của tháng (mặc định tháng hiện tại)."""
    key = month_key or _month_key()
    data = load_data()
    data[key] = counts
    save_data(data)

def _get_alltime_counts() -> dict:
    """Lấy invite counts all-time (cộng dồn mãi mãi)."""
    return load_data().get("invite_counts_all", {})

def _save_alltime_counts(counts: dict):
    """Lưu invite counts all-time."""
    data = load_data()
    data["invite_counts_all"] = counts
    save_data(data)

_DEFAULT_COUNTS = {"total": 0, "unverify": 0, "verify": 0, "fake": 0, "left": 0}

def _add_invite(inviter_id: int, field: str, amount: int = 1):
    """Ghi invite vào tháng hiện tại VÀ all-time."""
    uid = str(inviter_id)

    # ── Tháng hiện tại ──
    counts = _get_invite_counts()
    if uid not in counts:
        counts[uid] = dict(_DEFAULT_COUNTS)
    counts[uid][field] = counts[uid].get(field, 0) + amount
    _save_invite_counts(counts)

    # ── All-time ──
    alltime = _get_alltime_counts()
    if uid not in alltime:
        alltime[uid] = dict(_DEFAULT_COUNTS)
    alltime[uid][field] = alltime[uid].get(field, 0) + amount
    _save_alltime_counts(alltime)

def _calc_net(c: dict) -> tuple[int, int, int, int, int, int]:
    """Tính (total, unverify, verify, fake, left, net) từ dict counts."""
    total    = c.get("total",    0)
    unverify = c.get("unverify", 0)
    verify   = c.get("verify",   0)
    fake     = c.get("fake",     0)
    left     = c.get("left",     0)
    net      = max(0, verify - fake - left)
    return total, unverify, verify, fake, left, net

def _get_net_invites(inviter_id: int, month_key = None) -> tuple[int, int, int, int, int, int]:
    """Trả về (total, unverify, verify, fake, left, net) của tháng chỉ định."""
    counts = _get_invite_counts(month_key)
    uid = str(inviter_id)
    c = counts.get(uid, {"total": 0, "unverify": 0, "verify": 0, "fake": 0, "left": 0})
    return _calc_net(c)

def _get_net_invites_alltime(inviter_id: int) -> tuple[int, int, int, int, int, int]:
    """Trả về (total, unverify, verify, fake, left, net) tổng all-time."""
    alltime = _get_alltime_counts()
    uid = str(inviter_id)
    c = alltime.get(uid, {"total": 0, "unverify": 0, "verify": 0, "fake": 0, "left": 0})
    return _calc_net(c)

def _check_and_rotate_month():
    """
    Kiểm tra xem tháng DB đang lưu có khác tháng hiện tại không.
    Nếu có → tháng cũ đã được snapshot vào all-time rồi (qua _add_invite),
    nên chỉ cần ghi nhận tháng hiện tại trong metadata.
    Không cần làm gì thêm vì _add_invite luôn ghi đồng thời vào tháng + all-time.
    """
    pass  # Rotation tự nhiên qua _month_key() thay đổi mỗi tháng


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
            guild_id=guild.id,
        )

    async def _ensure_roles(self, guild: discord.Guild):
        """Tự tạo role UNVERIFY / VERIFY nếu chưa có, set permission Unverify.
        Hoạt động đúng trên đa server — lưu role ID vào _guild_roles."""

        # ── UNVERIFY ──
        _unverify_created = False
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
                _unverify_created = True
                print(f"[INVITE] ✅ Đã tạo role Unverify ({unverify.id}) tại {guild.name}")
            except discord.Forbidden:
                print(f"[INVITE] ❌ Không có quyền tạo role tại {guild.name}")
                return

        _guild_roles.setdefault(guild.id, {})["unverify"] = unverify.id

        # ── VERIFY ──
        _verify_created = False
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
                _verify_created = True
                print(f"[INVITE] ✅ Đã tạo role Verify ({verify.id}) tại {guild.name}")
            except discord.Forbidden:
                print(f"[INVITE] ❌ Không có quyền tạo role tại {guild.name}")
                return

        _guild_roles.setdefault(guild.id, {})["verify"] = verify.id

        # ── Xóa overwrite của Verify / Unverify trên tất cả kênh về mặc định ──
        roles_to_reset = []
        if _unverify_created:
            roles_to_reset.append(unverify)
        if _verify_created:
            roles_to_reset.append(verify)

        if roles_to_reset:
            for channel in guild.channels:
                for role in roles_to_reset:
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
            await send_log(self.bot, "INVITE_VERIFY", "Force verify bởi admin",
                fields=[
                    ("👤 Member",  f"{member} (`{member.id}`)", True),
                    ("⚙️ Admin",   str(ctx.author),             True),
                    ("📌 Method",  "Force (không qua link)",    True),
                ],
                guild_id=guild.id,
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
                guild_id=ctx.guild.id,
            )
        except discord.HTTPException as e:
            await ctx.reply(f"❌ Không rời được: `{e}`")


    @commands.command(name="invite", aliases=["inv"])
    async def invite_cmd(self, ctx, member: discord.Member = None):
        """Xem thống kê invite của 1 thành viên (tháng này + all-time)."""
        target = member or ctx.author
        now    = datetime.now(timezone.utc)

        total_m, unverify_m, verify_m, fake_m, left_m, net_m = _get_net_invites(target.id)
        total_a, unverify_a, verify_a, fake_a, left_a, net_a = _get_net_invites_alltime(target.id)

        # ── Kiểm tra trạng thái verify ──
        verify_role   = ctx.guild.get_role(_get_verify_role_id(ctx.guild.id))   if ctx.guild else None
        unverify_role = ctx.guild.get_role(_get_unverify_role_id(ctx.guild.id)) if ctx.guild else None
        is_verified   = verify_role   and verify_role   in target.roles
        is_unverified = unverify_role and unverify_role in target.roles

        if is_verified:
            verify_status = "✅ Đã xác minh"
        elif is_unverified:
            verify_status = "⏳ Chưa xác minh"
        else:
            verify_status = "❓ Không rõ"

        # Tuổi tài khoản
        acc_age_days = (now - target.created_at).days
        acc_age_str  = f"{acc_age_days} ngày" if acc_age_days < 30 else f"{acc_age_days // 30} tháng {acc_age_days % 30} ngày"

        embed = discord.Embed(
            title     = f"📨 Invite của {_uname(target)}",
            color     = 0x5865F2,
            timestamp = now,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(
            name  = "👤 Trạng thái",
            value = (
                f"{verify_status}\n"
                f"🗓️ Tài khoản: **{acc_age_str}** tuổi"
            ),
            inline = False,
        )
        embed.add_field(
            name  = f"📅 Tháng {now.month}/{now.year}",
            value = (
                f"✅ Net: **{net_m}**\n"
                f"📊 Tổng: **{total_m}** | ⏳ Chưa verify: **{unverify_m}** | 🟢 Verify: **{verify_m}** | ⚠️ Fake: **{fake_m}** | 🚪 Rời: **{left_m}**"
            ),
            inline = False,
        )
        embed.add_field(
            name  = "🏆 All-time (tổng cộng)",
            value = (
                f"✅ Net: **{net_a}**\n"
                f"📊 Tổng: **{total_a}** | ⏳ Chưa verify: **{unverify_a}** | 🟢 Verify: **{verify_a}** | ⚠️ Fake: **{fake_a}** | 🚪 Rời: **{left_a}**"
            ),
            inline = False,
        )
        embed.set_footer(text="Net = Verify − Fake − Đã rời  •  TuyTam Store")
        await ctx.reply(embed=embed)

    @commands.command(name="invitetop", aliases=["invtop"])
    async def invitetop_cmd(self, ctx, *args):
        """
        .invitetop [top] [MM/YYYY] [alltime]
        Leaderboard invite. Mặc định = tháng hiện tại.
        Ví dụ:
          .invitetop              → top 10 tháng này
          .invitetop 20           → top 20 tháng này
          .invitetop 06/2026      → top 10 tháng 6/2026
          .invitetop 20 06/2026   → top 20 tháng 6/2026
          .invitetop alltime      → top 10 all-time
          .invitetop 20 alltime   → top 20 all-time
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        import re as _re

        top                = 10
        alltime            = False
        month_key_override = None
        month_label        = None

        for a in args:
            if a.lower() == "alltime":
                alltime = True
            elif _re.match(r"^\d{1,2}/\d{4}$", a):
                # Format MM/YYYY
                try:
                    m_part, y_part = a.split("/")
                    m_int, y_int = int(m_part), int(y_part)
                    if not (1 <= m_int <= 12):
                        return await ctx.reply("❌ Tháng phải từ 01–12.")
                    month_key_override = f"invite_counts_{y_int}_{m_int:02d}"
                    month_label        = f"Tháng {m_int}/{y_int}"
                except ValueError:
                    return await ctx.reply("❌ Format tháng: `MM/YYYY` (ví dụ: `06/2026`)")
            else:
                try:
                    top = max(1, min(int(a), 25))
                except ValueError:
                    return await ctx.reply(
                        "❌ Dùng: `.invitetop [số] [MM/YYYY] [alltime]`\n"
                        "Ví dụ: `.invitetop 20 06/2026` hoặc `.invitetop alltime`"
                    )

        now = datetime.now(timezone.utc)

        if alltime:
            counts      = _get_alltime_counts()
            title_label = "All-time"
        elif month_key_override:
            counts      = _get_invite_counts(month_key_override)
            title_label = month_label
        else:
            counts      = _get_invite_counts()
            title_label = f"Tháng {now.month}/{now.year}"

        board = []
        for uid_str, c in counts.items():
            total, unverify, verify, fake, left, net = _calc_net(c)
            board.append((int(uid_str), net, total, fake, left))
        board.sort(key=lambda x: x[1], reverse=True)
        board = board[:top]

        if not board:
            return await ctx.reply(f"❌ Chưa có dữ liệu invite nào ({title_label}).")

        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (uid, net, total, fake, left) in enumerate(board):
            icon   = medals[i] if i < 3 else f"`{i+1}.`"
            m      = ctx.guild.get_member(uid)
            name   = _uname(m) if m else f"ID:{uid}"
            lines.append(f"{icon} **{name}** — **{net}** net (`{total}` tổng, `{fake}` fake, `{left}` rời)")

        embed = discord.Embed(
            title       = f"🏆 Bảng xếp hạng Invite — {title_label} — Top {top}",
            description = "\n".join(lines),
            color       = 0xF1C40F,
            timestamp   = now,
        )
        embed.set_footer(text="TuyTam Store  •  .invitetop [số] [MM/YYYY] [alltime]")
        await ctx.reply(embed=embed)

    @commands.command(name="resetinvite", aliases=["resetinv"])
    async def resetinvite_cmd(self, ctx, *, arg: str = None):
        """
        Reset invite tháng hiện tại (all-time KHÔNG bị ảnh hưởng).
        .resetinvite all    → reset cả server tháng này
        .resetinvite @user  → reset 1 người tháng này
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        now         = datetime.now(timezone.utc)
        month_label = f"Tháng {now.month}/{now.year}"

        member = ctx.message.mentions[0] if ctx.message.mentions else None
        arg_clean = (arg or "").strip()

        if arg_clean.lower() == "all" and not member:
            _save_invite_counts({})
            await ctx.reply(
                f"✅ Đã reset toàn bộ invite **{month_label}** của server.\n"
                f"*(Invite all-time vẫn được giữ nguyên)*"
            )
            await send_log(self.bot, "INVITE", f"Reset toàn bộ invite server ({month_label})",
                fields=[
                    ("👤 Admin", str(ctx.author), True),
                    ("📅 Tháng", month_label,     True),
                ],
                guild_id=ctx.guild.id)
            return

        if not member and arg_clean:
            try:
                member = await commands.MemberConverter().convert(ctx, arg_clean)
            except commands.BadArgument:
                return await ctx.reply(
                    f"❌ Không tìm thấy thành viên `{arg_clean}`.\n"
                    "Dùng: `.resetinvite @user` hoặc `.resetinvite all`\n"
                    "Reset all-time: `.resetinvites [@user]`"
                )

        if member:
            counts = _get_invite_counts()
            counts.pop(str(member.id), None)
            _save_invite_counts(counts)
            await ctx.reply(
                f"✅ Đã reset invite **{month_label}** của **{_uname(member)}**.\n"
                f"*(Invite all-time vẫn được giữ nguyên)*"
            )
            await send_log(self.bot, "INVITE", f"Reset invite {month_label} — {member}",
                fields=[
                    ("👤 Admin",  str(ctx.author), True),
                    ("🎯 Target", str(member),     True),
                    ("📅 Tháng",  month_label,     True),
                ],
                guild_id=ctx.guild.id)
        else:
            await ctx.reply(
                "❌ Dùng:\n"
                "`.resetinvite @user` — reset 1 người (tháng này)\n"
                "`.resetinvite all` — reset toàn bộ (tháng này)\n\n"
                "⚠️ Lệnh này chỉ reset tháng hiện tại. Dùng `.resetinvites` để reset all-time."
            )

    @commands.command(name="resetinvites")
    async def resetinvites_cmd(self, ctx, *, arg: str = None):
        """
        Reset invite ALL-TIME (hỏi lại trước khi thực hiện).
        .resetinvites        → reset all-time toàn server
        .resetinvites @user  → reset all-time 1 người
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        member = ctx.message.mentions[0] if ctx.message.mentions else None
        arg_clean = (arg or "").strip()

        if not member and arg_clean:
            try:
                member = await commands.MemberConverter().convert(ctx, arg_clean)
            except commands.BadArgument:
                return await ctx.reply(
                    f"❌ Không tìm thấy thành viên `{arg_clean}`.\n"
                    "Dùng: `.resetinvites @user` hoặc `.resetinvites` (toàn server)"
                )

        if member:
            confirm_text = (
                f"⚠️ **Xác nhận reset ALL-TIME**\n\n"
                f"Bạn sắp xóa vĩnh viễn toàn bộ lịch sử invite của **{_uname(member)}**.\n"
                f"Hành động này **không thể hoàn tác**!\n\n"
                f"Bấm ✅ để xác nhận hoặc ❌ để huỷ."
            )
        else:
            confirm_text = (
                "⚠️ **Xác nhận reset ALL-TIME**\n\n"
                "Bạn sắp xóa vĩnh viễn toàn bộ lịch sử invite all-time của **toàn bộ server**.\n"
                "Hành động này **không thể hoàn tác**!\n\n"
                "Bấm ✅ để xác nhận hoặc ❌ để huỷ."
            )

        class ConfirmView(discord.ui.View):
            def __init__(self_v):
                super().__init__(timeout=30)
                self_v.confirmed = False

            @discord.ui.button(label="✅ Xác nhận reset", style=discord.ButtonStyle.danger)
            async def confirm_btn(self_v, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("❌ Không phải lệnh của bạn.", ephemeral=True)
                self_v.confirmed = True
                self_v.stop()
                await interaction.response.defer()

            @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.secondary)
            async def cancel_btn(self_v, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("❌ Không phải lệnh của bạn.", ephemeral=True)
                self_v.stop()
                await interaction.response.edit_message(content="❌ Đã huỷ reset all-time.", view=None)

        view = ConfirmView()
        confirm_msg = await ctx.reply(confirm_text, view=view)
        await view.wait()

        if not view.confirmed:
            return  # cancel_btn đã edit message, hoặc timeout tự hết

        now         = datetime.now(timezone.utc)
        month_label = f"Tháng {now.month}/{now.year}"

        if member:
            alltime = _get_alltime_counts()
            alltime.pop(str(member.id), None)
            _save_alltime_counts(alltime)
            await confirm_msg.edit(
                content=(
                    f"✅ Đã reset **ALL-TIME** invite của **{_uname(member)}**.\n"
                    f"*(Invite {month_label} vẫn được giữ nguyên)*"
                ),
                view=None,
            )
            await send_log(self.bot, "INVITE", f"Reset all-time invite — {member}",
                fields=[
                    ("👤 Admin",  str(ctx.author), True),
                    ("🎯 Target", str(member),     True),
                    ("🗂️ Scope",  "All-time",      True),
                ],
                guild_id=ctx.guild.id)
        else:
            _save_alltime_counts({})
            await confirm_msg.edit(
                content=(
                    f"✅ Đã reset **ALL-TIME** toàn bộ invite server.\n"
                    f"*(Invite {month_label} vẫn được giữ nguyên)*"
                ),
                view=None,
            )
            await send_log(self.bot, "INVITE", "Reset all-time toàn bộ server",
                fields=[
                    ("👤 Admin", str(ctx.author), True),
                    ("🗂️ Scope", "All-time",      True),
                ],
                guild_id=ctx.guild.id)

    # ── Events ──

    WELCOME_GUILDS = {
        950363132679831642: 1276087208150827070,
    }

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # FIX: listener này chạy trên 1 Task RIÊNG do discord.py tự dispatch, KHÔNG
        # thừa hưởng guild context set ở on_message/before_invoke. Thiếu dòng này khiến
        # _add_invite()/load_data()/save_data() bên dưới lưu dữ liệu KHÔNG thành công
        # (đã xác nhận qua log lỗi thực tế: "load_data() được gọi mà KHÔNG có guild context").
        set_current_guild(member.guild.id)

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
            _add_invite(inviter_id, "total",    1)   # +1 total ngay khi join
            _add_invite(inviter_id, "unverify", 1)   # +1 unverify, sẽ -1 khi verify xong

        # Log member join
        inviter_member = member.guild.get_member(inviter_id) if inviter_id else None
        await send_log(self.bot, "INVITE_JOIN", "Thành viên mới tham gia",
            fields=[
                ("👤 Thành viên",  f"{member} (`{member.id}`)",        True),
                ("📨 Được mời bởi", str(inviter_member) if inviter_member else (f"ID:{inviter_id}" if inviter_id else "Không rõ"), True),
                ("🔗 Invite code", f"`{invite_code}`" if invite_code else "Không rõ", True),
                ("📅 Tạo acc",     f"<t:{int(member.created_at.timestamp())}:R>", True),
            ],
            guild_id=member.guild.id,
        )

        # Gửi DM link verify
        await self._send_verify_dm(member, inviter_id)

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
            await send_log(self.bot, "INVITE_VERIFY", "Không thể gửi DM verify",
                fields=[
                    ("👤 Thành viên", f"{member} (`{member.id}`)", True),
                    ("⚠️ Lý do",      "User đã tắt DM",           True),
                ],
                guild_id=member.guild.id,
            )
            VERIFY_CALLBACKS.pop(token, None)

        async def _timeout():
            await asyncio.sleep(600)
            if VERIFY_CALLBACKS.pop(token, None):
                await send_log(self.bot, "INVITE_VERIFY", "Hết hạn verify (không nhấn link)",
                    fields=[
                        ("👤 Thành viên", f"{member} (`{member.id}`)", True),
                        ("⏱️ Trạng thái", "Timeout 10 phút",           True),
                    ],
                    guild_id=member.guild.id,
                )

        asyncio.create_task(_timeout())

    async def _handle_verify_result(self, member: discord.Member, result: dict):
        """Xử lý kết quả sau khi user click verify link."""
        # FIX: hàm này được gọi từ VERIFY_CALLBACKS, do verify_server.py (HTTP request
        # riêng biệt, hoàn toàn KHÔNG cùng Task với on_message/before_invoke) trigger —
        # nên contextvar guild_id CHƯA từng được set. Thiếu dòng này khiến mọi
        # _add_invite()/load_data()/save_data() bên dưới chạy không có guild context
        # → invite count KHÔNG được lưu (xem log lỗi thực tế đã gặp).
        set_current_guild(member.guild.id)

        user_id    = result["user_id"]
        inviter_id = result["inviter_id"]
        ip         = result["ip"]
        is_vpn     = result["is_vpn"]
        country    = result["country"]
        isp        = result["isp"]

        # VPN log
        if is_vpn:
            await _register_vpn(user_id, ip, country, isp)
            await send_log(self.bot, "INVITE_VERIFY", "Verify — phát hiện VPN/Proxy",
                fields=[
                    ("👤 Thành viên", f"{member} (`{user_id}`)",     True),
                    ("🌐 IP",         f"||`{ip}`||",                 True),
                    ("📡 ISP",        isp,                           True),
                    ("🌍 Quốc gia",   country,                       True),
                    ("⚠️ VPN",        "✅ Phát hiện",                True),
                ],
                guild_id=member.guild.id,
            )

        # ── Kiểm tra tuổi tài khoản (phải tạo ít nhất 1 ngày trước) ──
        acc_age_seconds = (datetime.now(timezone.utc) - member.created_at).total_seconds()
        is_new_account  = acc_age_seconds < 86400  # < 24 giờ

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

        # ── Xác định tính hợp lệ của invite ──
        # Invite chỉ được đếm khi: verify thành công + không IP trùng + acc >= 1 ngày
        # (logic thực tế xử lý theo từng nhánh is_new_account/is_fake bên dưới)

        if is_new_account:
            # Đánh dấu fake (tài khoản mới < 1 ngày): -1 unverify, +1 fake
            if inviter_id:
                _add_invite(inviter_id, "unverify", -1)
                _add_invite(inviter_id, "fake",     1)
            new_acc_reason = f"Tài khoản tạo {int(acc_age_seconds // 3600)} giờ trước (< 24h)"
            inviter_member = member.guild.get_member(inviter_id) if member.guild and inviter_id else None
            try:
                notice = (
                    "⚠️ **Thông báo từ TuyTam Store**\n\n"
                    "Tài khoản của bạn đã verify thành công. Tuy nhiên, tài khoản của bạn được tạo "
                    "**chưa đến 1 ngày** nên bị xem là tài khoản mới và **không được tính vào invite** của người mời.\n\n"
                    "Bạn vẫn có thể sử dụng server bình thường."
                )
                await member.send(notice)
            except discord.Forbidden:
                pass
            await send_log(self.bot, "INVITE_FAKE", "⚠️ Tài khoản mới < 1 ngày — invite không được tính",
                fields=[
                    ("👤 Member",       f"{member} (`{user_id}`)",                                          True),
                    ("📨 Inviter",       str(inviter_member) if inviter_member else (f"ID:{inviter_id}" if inviter_id else "Không rõ"), True),
                    ("🌐 IP",            f"||`{ip}`||",                                                     True),
                    ("🔍 Lý do",         new_acc_reason,                                                    False),
                    ("🎯 Invite tính?",  "❌ Không tính",                                                   True),
                    ("📡 ISP",           isp,                                                                True),
                    ("🌍 Quốc gia",      country,                                                            True),
                ],
                guild_id=member.guild.id,
            )
        elif is_fake:
            # Đánh dấu fake nhưng vẫn cho vào — đã gán VERIFY ở trên
            # -1 unverify, +1 fake
            if inviter_id:
                _add_invite(inviter_id, "unverify", -1)
                _add_invite(inviter_id, "fake",     1)
            inviter_member = member.guild.get_member(inviter_id) if member.guild and inviter_id else None

            shared_users = _ip_records.get(ip.replace(".", "_"), [])
            primary_id   = get_primary_user_for_ip(ip)
            is_primary   = (primary_id == user_id)

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
                    primary_m    = guild.get_member(primary_id) if guild and primary_id else None
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
                    ("📨 Inviter",   str(inviter_member) if inviter_member else (f"ID:{inviter_id}" if inviter_id else "Không rõ"), True),
                    ("🌐 IP",        f"||`{ip}`||",                                                      True),
                    ("🔍 Lý do",     fake_reason,                                                        False),
                    ("🎯 Giveaway",  "✅ Được phép" if is_primary else "❌ Bị chặn",                    True),
                    ("📡 ISP",       isp,                                                                True),
                    ("🌍 Quốc gia",  country,                                                            True),
                ],
                guild_id=member.guild.id,
            )
        else:
            # ── Hợp lệ hoàn toàn: -1 unverify, +1 verify ──
            if inviter_id:
                _add_invite(inviter_id, "unverify", -1)
                _add_invite(inviter_id, "verify",   1)
            await send_log(self.bot, "INVITE_VERIFY", "✅ Verify thành công",
                fields=[
                    ("👤 Thành viên", f"{member} (`{user_id}`)", True),
                    ("🌐 IP",         f"||`{ip}`||",             True),
                    ("🌍 Quốc gia",   country,                   True),
                    ("📡 ISP",        isp,                       True),
                    ("✅ Trạng thái", "Hợp lệ",                  True),
                ],
                guild_id=member.guild.id,
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # FIX: cùng lý do với on_member_join — listener chạy Task riêng, phải tự set
        # guild context trước khi đụng vào cache_invites()/_add_invite()/save_*().
        set_current_guild(member.guild.id)

        await cache_invites(member.guild)

        if member.id in _pending_joins:
            # Rời khi chưa verify → -1 unverify, +1 left
            inv = _pending_joins.pop(member.id, None)
            save_pending_joins(_pending_joins)
            if inv and inv.get("inviter_id"):
                _add_invite(inv["inviter_id"], "unverify", -1)
                _add_invite(inv["inviter_id"], "left",      1)
            return

        inv_info = _member_inviters.pop(member.id, None)
        if inv_info:
            # Rời sau khi đã verify → -1 verify, +1 left
            _add_invite(inv_info["inviter_id"], "verify", -1)
            _add_invite(inv_info["inviter_id"], "left",    1)
            save_member_inviters(_member_inviters)

            inviter_m = member.guild.get_member(inv_info["inviter_id"])
            await send_log(self.bot, "INVITE_LEFT", "Thành viên rời server",
                fields=[
                    ("👤 Thành viên", f"{member} (`{member.id}`)",                                              True),
                    ("📨 Được mời bởi", str(inviter_m) if inviter_m else f"ID:{inv_info['inviter_id']}",        True),
                ],
                guild_id=member.guild.id,
            )

    @commands.command(name="backfillip")
    async def backfillip_cmd(self, ctx, limit: int = 2000):
        """
        Admin: đọc lại lịch sử kênh log general, parse IP từ INVITE_VERIFY/INVITE_FAKE
        (backfill _ip_records, _shared_ip) và parse luôn log "phát hiện VPN/Proxy"
        (backfill _vpn_users) trong cùng 1 lượt quét.
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        import re
        from core.data import _get_mongo

        from cogs.logger import get_log_channel
        ch_id = get_log_channel("invite")
        if not ch_id:
            return await ctx.reply("❌ Chưa cài kênh log `invite`. Dùng `.setlog` trước.")

        log_channel = await get_or_fetch_channel(self.bot, ch_id)
        if not log_channel:
            return await ctx.reply(f"❌ Không tìm được kênh log `{ch_id}`.")

        status_msg = await ctx.reply(f"⏳ Đang quét {limit} message trong {log_channel.mention}...")

        re_user = re.compile(r"\(`(\d{10,20})`\)")
        re_ip   = re.compile(r"\|\|`([\d\.]+)`\|\|")
        re_isp  = re.compile(r"\*\*📡 ISP:\*\*\s*([^·\n]+)")
        re_geo  = re.compile(r"\*\*🌍 Quốc gia:\*\*\s*([^·\n]+)")

        found_ip   = 0
        added_ip   = 0
        skipped_ip = 0
        found_vpn   = 0
        added_vpn   = 0
        skipped_vpn = 0

        col, _ = _get_mongo()

        async for msg in log_channel.history(limit=limit, oldest_first=False):
            content = msg.content
            if "[INVITE_VERIFY]" not in content and "[INVITE_FAKE]" not in content:
                continue

            m_user = re_user.search(content)
            m_ip   = re_ip.search(content)
            if not m_user or not m_ip:
                continue

            user_id = int(m_user.group(1))
            ip      = m_ip.group(1)

            # ── Backfill IP record ──
            found_ip += 1
            ip_key = ip.replace(".", "_")

            result = await col.update_one(
                {"_id": "main"},
                {"$addToSet": {f"_ip_records.{ip_key}": user_id}},
                upsert=True,
            )
            if result.modified_count > 0:
                added_ip += 1
            else:
                skipped_ip += 1

            await col.update_one(
                {"_id": "main", f"_shared_ip.{ip}": {"$exists": False}},
                {"$set": {f"_shared_ip.{ip}": user_id}},
            )

            # ── Backfill VPN record (nếu log này là log phát hiện VPN) ──
            if "phát hiện VPN/Proxy" in content:
                found_vpn += 1
                m_isp = re_isp.search(content)
                m_geo = re_geo.search(content)
                isp     = m_isp.group(1).strip() if m_isp else "?"
                country = m_geo.group(1).strip() if m_geo else "?"

                vpn_result = await col.update_one(
                    {"_id": "main", f"_vpn_users.{user_id}": {"$exists": False}},
                    {"$set": {f"_vpn_users.{user_id}": {
                        "ip": ip, "isp": isp, "country": country,
                        "ts": msg.created_at.isoformat(),
                    }}},
                )
                if vpn_result.modified_count > 0:
                    added_vpn += 1
                else:
                    skipped_vpn += 1

        doc = await col.find_one({"_id": "main"}, {"_ip_records": 1})
        global _ip_records
        _ip_records = (doc or {}).get("_ip_records", {})

        await status_msg.edit(content=(
            f"✅ **Backfill hoàn tất**\n"
            f"› Quét: **{limit}** message\n\n"
            f"**🌐 IP:**\n"
            f"› Tìm thấy INVITE_VERIFY/FAKE: **{found_ip}**\n"
            f"› Ghi mới vào DB: **{added_ip}** cặp (ip, user)\n"
            f"› Đã có sẵn (bỏ qua): **{skipped_ip}**\n\n"
            f"**🛡️ VPN:**\n"
            f"› Tìm thấy log VPN: **{found_vpn}**\n"
            f"› Ghi mới vào DB: **{added_vpn}** tài khoản\n"
            f"› Đã có sẵn (bỏ qua): **{skipped_vpn}**\n\n"
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

        from core.data import _get_mongo
        col, _ = _get_mongo()
        try:
            doc = await col.find_one({"_id": "main"}, {"_ip_records": 1, "_shared_ip": 1})
        except Exception as e:
            return await ctx.reply(f"❌ Lỗi đọc MongoDB: `{e}`")

        ip_records_raw  = (doc or {}).get("_ip_records", {})
        shared_ip_raw   = (doc or {}).get("_shared_ip", {})

        found = []
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

        from core.data import _get_mongo
        col, _ = _get_mongo()
        try:
            doc = await col.find_one({"_id": "main"}, {"_ip_records": 1, "_shared_ip": 1, "_vpn_users": 1})
        except Exception as e:
            return await ctx.reply(f"❌ Lỗi đọc MongoDB: `{e}`")

        ip_records_raw = (doc or {}).get("_ip_records", {})
        shared_ip_raw  = (doc or {}).get("_shared_ip", {})
        vpn_users_raw  = (doc or {}).get("_vpn_users", {})

        dupes = {
            key.replace("_", "."): uids
            for key, uids in ip_records_raw.items()
            if len(uids) >= 2
        }

        embeds = []

        if dupes:
            sorted_dupes = sorted(dupes.items(), key=lambda x: len(x[1]), reverse=True)

            PAGE_SIZE = 5
            pages     = [sorted_dupes[i:i+PAGE_SIZE] for i in range(0, len(sorted_dupes), PAGE_SIZE)]
            total_ips = len(sorted_dupes)
            total_acc = sum(len(uids) for uids in dupes.values())

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
                    ip_key_dot   = ip_display
                    ip_key_under = ip_display.replace(".", "_")
                    primary_id   = shared_ip_raw.get(ip_key_dot) or shared_ip_raw.get(ip_key_under)
                    if primary_id is None and uids:
                        primary_id = uids[0]
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

        # ── Danh sách tài khoản dùng VPN/Proxy ──
        if vpn_users_raw:
            vpn_items = sorted(vpn_users_raw.items(), key=lambda x: x[1].get("ts", ""), reverse=True)
            VPN_PAGE_SIZE = 10
            vpn_pages = [vpn_items[i:i+VPN_PAGE_SIZE] for i in range(0, len(vpn_items), VPN_PAGE_SIZE)]

            for page_idx, page in enumerate(vpn_pages):
                vembed = discord.Embed(
                    title     = f"🛡️ Tài khoản dùng VPN/Proxy — {len(vpn_items)} tài khoản",
                    color     = 0xF39C12,
                    timestamp = datetime.now(timezone.utc),
                )
                if len(vpn_pages) > 1:
                    vembed.set_author(name=f"Trang {page_idx+1}/{len(vpn_pages)}")
                vembed.set_footer(text="TuyTam Store  •  Chỉ admin thấy")

                lines = []
                for uid_str, info in page:
                    uid  = int(uid_str)
                    m    = ctx.guild.get_member(uid) if ctx.guild else None
                    name = str(m) if m else f"ID:{uid}"
                    lines.append(
                        f"`{uid}` **{name}** — ||`{info.get('ip','?')}`|| "
                        f"({info.get('isp','?')}, {info.get('country','?')})"
                    )
                vembed.description = "\n".join(lines) or "*(trống)*"
                embeds.append(vembed)

        if not embeds:
            return await ctx.reply("✅ Không có IP nào dùng chung, và không có tài khoản VPN nào được ghi nhận.")

        for e in embeds:
            await ctx.send(embed=e)

    @commands.command(name="testip")
    async def testip_cmd(self, ctx):
        """Admin: thêm data test — 1 IP giả có 2 acc."""
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
            await col.update_one(
                {"_id": "main"},
                {"$set": {f"_ip_records.{TEST_IP_KEY}": [ACC1_ID, ACC2_ID]}},
                upsert=True,
            )
            await col.update_one(
                {"_id": "main"},
                {"$set": {f"_shared_ip.{TEST_IP}": ACC1_ID}},
                upsert=True,
            )
        except Exception as e:
            return await ctx.reply(f"❌ Lỗi MongoDB: `{e}`")

        global _ip_records
        _ip_records = get_ip_records()

        await send_log(self.bot, "INVITE_VERIFY", "✅ Verify thành công",
            fields=[
                ("👤 Thành viên", f"{ACC1_NAME} (`{ACC1_ID}`)", True),
                ("🌐 IP",         f"||`{TEST_IP}`||",           True),
                ("📡 ISP",        "Test ISP",                   True),
                ("🌍 Quốc gia",   "Vietnam",                    True),
            ],
            guild_id=ctx.guild.id,
        )

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
            guild_id=ctx.guild.id,
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
        now    = datetime.now(timezone.utc)

        total_m, unverify_m, verify_m, fake_m, left_m, net_m = _get_net_invites(target.id)
        total_a, unverify_a, verify_a, fake_a, left_a, net_a = _get_net_invites_alltime(target.id)

        embed = discord.Embed(
            title     = f"📨 Invite của {_uname(target)}",
            color     = 0x5865F2,
            timestamp = now,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name  = f"📅 Tháng {now.month}/{now.year}",
            value = (
                f"✅ Net: **{net_m}**\n"
                f"📊 Tổng: **{total_m}** | ⏳ Chưa verify: **{unverify_m}** | 🟢 Verify: **{verify_m}** | ⚠️ Fake: **{fake_m}** | 🚪 Rời: **{left_m}**"
            ),
            inline = False,
        )
        embed.add_field(
            name  = "🏆 All-time",
            value = (
                f"✅ Net: **{net_a}**\n"
                f"📊 Tổng: **{total_a}** | ⏳ Chưa verify: **{unverify_a}** | 🟢 Verify: **{verify_a}** | ⚠️ Fake: **{fake_a}** | 🚪 Rời: **{left_a}**"
            ),
            inline = False,
        )
        embed.set_footer(text="Net = Verify − Fake − Đã rời")
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="invitetop", description="Bảng xếp hạng invite tháng này (admin)")
    @discord.app_commands.describe(top="Số người top (mặc định 10)")
    async def slash_invitetop(self, interaction: discord.Interaction, top: int = 10):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        top    = max(1, min(top, 25))
        now    = datetime.now(timezone.utc)
        counts = _get_invite_counts()
        board  = []
        for uid_str, c in counts.items():
            total, unverify, verify, fake, left, net = _calc_net(c)
            board.append((int(uid_str), net, total, fake, left))
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
            title       = f"🏆 Top {top} Invite — Tháng {now.month}/{now.year}",
            description = "\n".join(lines),
            color       = 0xF1C40F,
        )
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="resetinvite", description="Reset invite tháng này của thành viên (admin)")
    @discord.app_commands.describe(member="Thành viên cần reset (để trống = reset tất cả tháng này)")
    async def slash_resetinvite(self, interaction: discord.Interaction, member: discord.Member = None):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        now = datetime.now(timezone.utc)
        month_label = f"Tháng {now.month}/{now.year}"
        if member:
            counts = _get_invite_counts()
            counts.pop(str(member.id), None)
            _save_invite_counts(counts)
            await interaction.response.send_message(
                f"✅ Đã reset invite {month_label} của {member}.\n*(All-time vẫn giữ nguyên)*",
                ephemeral=True,
            )
        else:
            _save_invite_counts({})
            await interaction.response.send_message(
                f"✅ Đã reset toàn bộ invite {month_label} của server.\n*(All-time vẫn giữ nguyên)*",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteCog(bot))
