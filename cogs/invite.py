"""
cogs/invite.py — Invite tracking (đơn giản: total mời − rời server = net).
v7.0.0 — BỎ HOÀN TOÀN verify/IP fake-detection (xem CHANGELOG.md để biết lý do
và tin nhắn chat lúc tách — file này trước đó đã bị lệch với AI_CONTEXT.md một
thời gian, giờ mới đồng bộ lại):
  - _member_inviters populate NGAY lúc join, không còn chờ verify.
  - Model đếm invite rút gọn: chỉ còn {total, left}, net = max(0, total - left).
  - Đã xoá: role Unverify/Verify tự tạo (_ensure_roles), .verify, .checkip,
    .ipstats, .backfillip, .testip; giới hạn "1 IP = 1 suất" + .gwverify bên
    cogs/giveaway.py cũng bỏ theo (xem giveaway.py).
  - Monthly leaderboard reset: invite_counts_YYYY_MM (tháng hiện tại)
  - All-time total: invite_counts_all (cộng dồn mãi mãi, không bao giờ reset)
  - .invite: hiển thị cả tháng này + tổng all-time
  - .invitetop: leaderboard tháng này, có flag alltime để xem tổng
  - .resetinvite: chỉ reset tháng hiện tại, all-time KHÔNG bị ảnh hưởng
"""

import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from cogs.logger import send_log
from core.data import (
    ADMIN_IDS, load_data, save_data, _uname, _uname_plain,
    get_member_inviters, save_member_inviters,
    set_current_guild, get_or_fetch_channel,
    get_cfg_welcome_channel,
)


_invite_cache:    dict[int, dict[str, int]] = {}
_member_inviters: dict[int, dict]           = {}   # member_id → {inviter_id, guild_id}


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

_DEFAULT_COUNTS = {"total": 0, "left": 0}

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

def _calc_net(c: dict) -> tuple[int, int, int]:
    """Tính (total, left, net) từ dict counts — net = max(0, total - left)."""
    total = c.get("total", 0)
    left  = c.get("left",  0)
    net   = max(0, total - left)
    return total, left, net

def _get_net_invites(inviter_id: int, month_key = None) -> tuple[int, int, int]:
    """Trả về (total, left, net) của tháng chỉ định."""
    counts = _get_invite_counts(month_key)
    uid = str(inviter_id)
    c = counts.get(uid, dict(_DEFAULT_COUNTS))
    return _calc_net(c)

def _get_net_invites_alltime(inviter_id: int) -> tuple[int, int, int]:
    """Trả về (total, left, net) tổng all-time."""
    alltime = _get_alltime_counts()
    uid = str(inviter_id)
    c = alltime.get(uid, dict(_DEFAULT_COUNTS))
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
# COG
# ══════════════════════════════════════════

class InviteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        global _member_inviters
        _member_inviters = {int(k): v for k, v in get_member_inviters().items()}

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Khi bot vào server mới — log lại để admin biết."""
        await send_log(self.bot, "INFO", f"Bot vừa vào server mới: {guild.name}",
            fields=[
                ("🆔 ID",      str(guild.id),                                   True),
                ("👑 Owner",   str(guild.owner) if guild.owner else "?",        True),
                ("👥 Members", str(guild.member_count),                         True),
            ],
            guild_id=guild.id,
        )

    @commands.command(name="serverlist", aliases=["servers", "guildlist"])
    async def serverlist_cmd(self, ctx):
        """Admin xem danh sách server bot đang hoạt động."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")

        guilds = self.bot.guilds
        if not guilds:
            return await ctx.reply("❌ Bot chưa vào server nào.")

        from core.data import is_guild_authorized
        n_auth = sum(1 for g in guilds if is_guild_authorized(g.id))

        embed = discord.Embed(
            title     = f"🌐 Bot đang ở {len(guilds)} server ({n_auth} đã ủy quyền)",
            color     = 0x5865F2,
            timestamp = datetime.now(timezone.utc),
        )

        for g in sorted(guilds, key=lambda x: x.member_count, reverse=True):
            bots    = sum(1 for m in g.members if m.bot)
            humans  = g.member_count - bots
            owner   = str(g.owner) if g.owner else f"ID:{g.owner_id}"
            auth_tag = "✅ Đã ủy quyền" if is_guild_authorized(g.id) else "🔒 CHƯA ủy quyền — `.as {}`".format(g.id)
            embed.add_field(
                name  = f"{g.name}",
                value = (
                    f"🆔 `{g.id}`\n"
                    f"{auth_tag}\n"
                    f"👑 {owner}\n"
                    f"👥 {humans} người · 🤖 {bots} bot\n"
                    f"📅 <t:{int(g.created_at.timestamp())}:D>"
                ),
                inline = True,
            )

        embed.set_footer(text=f"TuyTam Bot  •  {len(guilds)} servers  •  .as <id> để bật/tắt ủy quyền")
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

        total_m, left_m, net_m = _get_net_invites(target.id)
        total_a, left_a, net_a = _get_net_invites_alltime(target.id)

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
            name  = "👤 Thành viên",
            value = f"🗓️ Tài khoản: **{acc_age_str}** tuổi",
            inline = False,
        )
        embed.add_field(
            name  = f"📅 Tháng {now.month}/{now.year}",
            value = f"✅ Net: **{net_m}**\n📊 Tổng mời: **{total_m}** | 🚪 Đã rời: **{left_m}**",
            inline = False,
        )
        embed.add_field(
            name  = "🏆 All-time (tổng cộng)",
            value = f"✅ Net: **{net_a}**\n📊 Tổng mời: **{total_a}** | 🚪 Đã rời: **{left_a}**",
            inline = False,
        )
        embed.set_footer(text="Net = Tổng mời − Đã rời  •  TuyTam Store")
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
            total, left, net = _calc_net(c)
            board.append((int(uid_str), net, total, left))
        board.sort(key=lambda x: x[1], reverse=True)

        if not board:
            return await ctx.reply(f"❌ Chưa có dữ liệu invite nào ({title_label}).")

        server_total_net = sum(x[1] for x in board)
        board = board[:top]

        def _name(uid):
            m = ctx.guild.get_member(uid)
            return _uname_plain(m) if m else f"ID:{uid}"

        embed = discord.Embed(
            title       = f"🏆 Bảng xếp hạng Invite — {title_label}",
            description = f"👥 **{len(counts)}** người có invite  •  📈 Tổng net server: **{server_total_net}**",
            color       = 0xF1C40F,
            timestamp   = now,
        )

        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, net, total, left) in enumerate(board[:3]):
            embed.add_field(
                name=f"{medals[i]} {_name(uid)} — {net} net",
                value=f"🚪 {left} rời  •  Σ {total} tổng",
                inline=False,
            )

        if len(board) > 3:
            rest_lines = [
                f"`{i+4}.` **{_name(uid)}** — **{net}** net (`{total}` tổng, `{left}` rời)"
                for i, (uid, net, total, left) in enumerate(board[3:])
            ]
            embed.add_field(name=f"📄 Hạng 4–{len(board)}", value="\n".join(rest_lines)[:1024], inline=False)

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

    # FIX: trước đây WELCOME_GUILDS hardcode {950363132679831642: 1276087208150827070} —
    # guild_id đó KHÔNG PHẢI TuyTam Community (LEGACY_MAIN_GUILD_ID thật =
    # 1464407860640219189) nên tính năng này thực ra đã im lặng không chạy ở TuyTam từ
    # trước. Giờ dùng get_cfg_welcome_channel() (per-guild, cấu hình qua `.st` → nút
    # "👋 Welcome Channel") — server nào muốn bật thì admin tự chọn kênh.
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # FIX: listener này chạy trên 1 Task RIÊNG do discord.py tự dispatch, KHÔNG
        # thừa hưởng guild context set ở on_message/before_invoke. Thiếu dòng này khiến
        # _add_invite()/load_data()/save_data() bên dưới lưu dữ liệu KHÔNG thành công
        # (đã xác nhận qua log lỗi thực tế: "load_data() được gọi mà KHÔNG có guild context").
        set_current_guild(member.guild.id)

        # AUTH_GATE — server chưa được admin ủy quyền qua .as → bỏ qua (xem bot.py + AI_CONTEXT.md)
        from core.data import is_guild_authorized
        if not is_guild_authorized(member.guild.id):
            return

        # Welcome ping (xóa sau 10s)
        ch_id = get_cfg_welcome_channel()
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

        # Ghi nhận invite NGAY lúc join — không còn chờ verify (verify đã bỏ hoàn toàn)
        if inviter_id and inviter_id != member.id:
            _member_inviters[member.id] = {"inviter_id": inviter_id, "guild_id": member.guild.id}
            save_member_inviters(_member_inviters)
            _add_invite(inviter_id, "total", 1)

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

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # FIX: cùng lý do với on_member_join — listener chạy Task riêng, phải tự set
        # guild context trước khi đụng vào cache_invites()/_add_invite()/save_*().
        set_current_guild(member.guild.id)

        # AUTH_GATE — server chưa được admin ủy quyền qua .as → bỏ qua (xem bot.py + AI_CONTEXT.md)
        from core.data import is_guild_authorized
        if not is_guild_authorized(member.guild.id):
            return

        await cache_invites(member.guild)

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
                guild_id=member.guild.id,
            )

    # ── Slash commands ──

    @discord.app_commands.command(name="invite", description="Xem thống kê invite của thành viên")
    @discord.app_commands.describe(member="Thành viên (để trống = bản thân)")
    async def slash_invite(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        now    = datetime.now(timezone.utc)

        total_m, left_m, net_m = _get_net_invites(target.id)
        total_a, left_a, net_a = _get_net_invites_alltime(target.id)

        embed = discord.Embed(
            title     = f"📨 Invite của {_uname(target)}",
            color     = 0x5865F2,
            timestamp = now,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name  = f"📅 Tháng {now.month}/{now.year}",
            value = f"✅ Net: **{net_m}**\n📊 Tổng mời: **{total_m}** | 🚪 Đã rời: **{left_m}**",
            inline = False,
        )
        embed.add_field(
            name  = "🏆 All-time",
            value = f"✅ Net: **{net_a}**\n📊 Tổng mời: **{total_a}** | 🚪 Đã rời: **{left_a}**",
            inline = False,
        )
        embed.set_footer(text="Net = Tổng mời − Đã rời")
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
            total, left, net = _calc_net(c)
            board.append((int(uid_str), net, total, left))
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
