"""
cogs/logger.py — LoggerCog: lệnh cấu hình log (.setlog/.setuplog/.testlog/.loginfo/.baocao)
+ listener tự động (member join/leave/update, command/interaction usage) + daily report.

Hàm send_log() thuần + bảng LOG_ICONS/LOG_ROUTES/LOG_GROUP_LABELS đã CHUYỂN sang
shared/logger.py (dùng chung mọi bot) — file này chỉ còn phần Cog thật (có state, task
nền, listener), import lại phần dùng chung ở khối dưới.

⚠️ daily_report_task() bên dưới đọc get_ticket_history() (domain ticket) VÀ
load_giveaways_data() (domain giveaway) — coupling CỐ Ý chấp nhận ở Phase 1, xem
AI_CONTEXT_SHARED.md mục "Coupling đã biết".
"""

from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands, tasks

from shared.logger import (
    LOG_ICONS, LOG_ROUTES, LOG_GROUP_LABELS, send_log, get_log_channel,
)
from core.data import is_admin
from core.data import (
    ADMIN_IDS, get_cfg_log_rudy, get_log_channels, get_log_channel_by_group,
    set_log_channel_db, get_or_fetch_channel,
    load_giveaways_data, fmt_amount,
    load_data, set_current_guild, wait_data_cache_ready,
)


def set_log_channel(group: str, channel_id: int):
    """Cài kênh log cho một nhóm — lưu vào MongoDB."""
    set_log_channel_db(group, channel_id)


def get_all_log_channels() -> dict[str, int]:
    return get_log_channels()


# ══════════════════════════════════════════
# COG — log member join/leave tự động
# ══════════════════════════════════════════
class LoggerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_report_date: dict[int, str] = {}  # {guild_id: "YYYY-MM-DD"} — tránh gửi 2 lần
        self.daily_report_task.start()

    def cog_unload(self):
        self.daily_report_task.cancel()

    # ══════════════════════════════════════════
    # BÁO CÁO HÀNG NGÀY 8H SÁNG — cho TỪNG GUILD
    # ══════════════════════════════════════════
    @tasks.loop(hours=1)
    async def daily_report_task(self):
        """Kiểm tra mỗi giờ, khi đúng 8h sáng UTC+7 (= 01:00 UTC) thì gửi báo cáo,
        lặp riêng cho từng guild (mỗi server có ticket_history/kênh log riêng)."""
        now = datetime.now(timezone.utc)
        # UTC+7 = UTC + 7h → 8h sáng UTC+7 = 01:00 UTC
        if now.hour != 1:
            return
        today_str = now.strftime("%Y-%m-%d")

        from core.data import set_current_guild, save_cfg, cleanup_resolved_sold_price
        for guild in self.bot.guilds:
            set_current_guild(guild.id)  # task nền không có context tự nhiên như lệnh/nút bấm
            cleanup_resolved_sold_price()  # dọn resolved_sold_price cũ hơn 7 ngày (v4.11.5)

            if self._last_report_date.get(guild.id) == today_str:
                continue
            # Check MongoDB phòng bot restart trong giờ 01:xx gửi lại
            data = load_data()
            if data.get("_daily_report_date") == today_str:
                self._last_report_date[guild.id] = today_str
                continue
            save_cfg("_daily_report_date", today_str)
            self._last_report_date[guild.id] = today_str
            await self._send_daily_report(guild)

    @daily_report_task.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()
        # FIX: xem giải thích ở seller.py: before_check — tránh chạy trước khi
        # _data_cache nạp xong (init_data_cache() hoàn tất muộn hơn wait_until_ready()).
        await wait_data_cache_ready()

    async def _send_daily_report(self, guild: discord.Guild):
        """Build và gửi embed báo cáo 24h qua vào kênh general log.
        Báo cáo này vẫn dùng embed vì cần layout đẹp để đọc tổng kết."""
        now       = datetime.now(timezone.utc)
        since     = now - timedelta(hours=24)
        date_label = now.strftime("%d/%m/%Y")

        # ── Ticket: đơn hoàn thành trong 24h qua ──
        from core.data import get_ticket_history
        ticket_history = get_ticket_history()
        day_recs = []
        for t in ticket_history:
            try:
                dt = datetime.fromisoformat(t.get("closed_at", ""))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= since:
                    day_recs.append(t)
            except Exception:
                pass
        ticket_count  = len(day_recs)
        ticket_amount = sum(t.get("amount", 0) for t in day_recs)

        # ── Giveaway: kết thúc trong 24h qua ──
        # [FIX v4.11.4] load_giveaways_data() trả về giveaway của MỌI guild
        # (cache không tách theo guild, chỉ tách theo message_id) — phải tự lọc
        # theo guild hiện tại qua channel_id, nếu không report của 2 guild sẽ
        # cùng hiện một con số gộp.
        gw_data    = load_giveaways_data()
        gw_of_guild = []
        for gw in gw_data.values():
            ch = self.bot.get_channel(gw.get("channel_id"))
            if ch is not None and ch.guild.id == guild.id:
                gw_of_guild.append(gw)
        gw_running = sum(1 for gw in gw_of_guild if not gw.get("ended"))
        gw_ended   = 0
        for gw in gw_of_guild:
            end_time = gw.get("end_time", 0)
            if gw.get("ended") and end_time:
                try:
                    end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc)
                    if end_dt >= since:
                        gw_ended += 1
                except Exception:
                    pass

        # ── Top buyer 24h qua ──
        buyer_totals: dict = {}
        for t in day_recs:
            uid = t.get("user_id")
            if uid:
                buyer_totals[uid] = buyer_totals.get(uid, 0) + t.get("amount", 0)
        top3 = sorted(buyer_totals.items(), key=lambda x: x[1], reverse=True)[:3]

        # ── Build embed (báo cáo tổng hợp dùng embed) ──
        embed = discord.Embed(
            title=f"📊  Báo Cáo 24h — {date_label}",
            color=0x5865F2,
            timestamp=now,
        )

        # Ticket
        embed.add_field(
            name="🎫 Ticket",
            value=(
                f"✅ Hoàn thành: **{ticket_count}** đơn\n"
                f"💰 Doanh thu: **{fmt_amount(ticket_amount)}**"
            ),
            inline=True,
        )

        # Giveaway
        embed.add_field(
            name="🎉 Giveaway",
            value=(
                f"🟢 Đang chạy: **{gw_running}**\n"
                f"🏁 Kết thúc 24h: **{gw_ended}**"
            ),
            inline=True,
        )

        # Top buyer
        if top3:
            medals    = ["🥇", "🥈", "🥉"]
            top_lines = [
                f"{medals[i]} ID:{uid} — **{fmt_amount(amt)}**"
                for i, (uid, amt) in enumerate(top3)
            ]
            embed.add_field(
                name="🏆 Top Buyer 24h",
                value="\n".join(top_lines),
                inline=False,
            )

        embed.set_footer(text="TuyTam Store  •  Báo cáo tự động lúc 8:00 SA")

        # Gửi vào kênh general log
        ch_id   = get_log_channel("general") or get_cfg_log_rudy()
        if not ch_id:
            return
        channel = await get_or_fetch_channel(self.bot, ch_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception as e:
                print(f"[DAILY_REPORT] ❌ Lỗi gửi báo cáo: {e}")

    @commands.command(name="baocao", aliases=["report"])
    async def manual_report(self, ctx):
        """Admin gọi thủ công báo cáo ngay lập tức."""
        if not is_admin(ctx.author):
            return
        await self._send_daily_report(ctx.guild)
        await ctx.message.add_reaction("✅")

    # ── LỆNH CÀI KÊNH LOG ──
    @commands.command(name="setlog")
    async def set_log(self, ctx, group: str = None, channel: discord.TextChannel = None):
        """Cài kênh log cho từng nhóm. Dùng: .setlog <nhóm> #kênh"""
        if not is_admin(ctx.author):
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
                ("👤 Admin",  f"{ctx.author}", True),
                ("📌 Kênh",   channel.mention,         True),
                ("🗂️ Nhóm",   label,                   True),
            ],
            user=ctx.author,
            guild_id=ctx.guild.id,
        )

    @commands.command(name="setuplog")
    async def setup_log(self, ctx, category_id: int = None):
        """Tự động tạo toàn bộ kênh log và bỏ vào danh mục cố định.\nDùng: .setuplog [category_id]"""
        if not is_admin(ctx.author):
            return

        DEFAULT_CATEGORY_ID = 1486967303802191912
        CATEGORY_ID = category_id or DEFAULT_CATEGORY_ID
        category = ctx.guild.get_channel(CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            return await ctx.reply("❌ Không tìm thấy danh mục. Kiểm tra lại ID.")

        # Tên kênh cho từng nhóm
        CHANNEL_NAMES = {
            "ticket":   "log-ticket",
            "mod":      "log-mod",
            "giveaway": "log-giveaway",
            "member":   "log-member",
            "role":     "log-role",
            "ai":       "log-ai",
            "admin":    "log-admin",
            "invite":   "log-invite",
            "general":  "log-general",
            "shop":     "log-shop",
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
            # Kiểm tra kênh đã tồn tại — so sánh sau khi strip font Unicode
            from cogs.admin_views import _strip_unicode_font
            existing = discord.utils.find(
                lambda ch, n=ch_name: _strip_unicode_font(ch.name) == n,
                ctx.guild.text_channels,
            )
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


    @commands.command(name="testlog", aliases=["logtest"])
    async def test_log(self, ctx, group: str = None):
        """Gửi log test vào từng kênh để kiểm tra hoạt động.
        Dùng: .testlog          → test tất cả nhóm
              .testlog <nhóm>   → test 1 nhóm cụ thể
        """
        if not is_admin(ctx.author):
            return

        # Map nhóm → event đại diện để test
        GROUP_TEST_EVENTS = {
            "ticket":   ("TICKET_CREATE",   "Test — Ticket tạo"),
            "mod":      ("MOD_WARN",        "Test — Cảnh cáo"),
            "giveaway": ("GIVEAWAY_START",  "Test — Giveaway bắt đầu"),
            "member":   ("MEMBER_JOIN",     "Test — Thành viên tham gia"),
            "role":     ("ROLE_ADD",        "Test — Thêm role"),
            "ai":       ("AI_USED",         "Test — AI sử dụng"),
            "admin":    ("CMD_USED",        "Test — Lệnh admin"),
            "invite":   ("INVITE_JOIN",     "Test — Thành viên tham gia (invite)"),
            "general":  ("INFO",            "Test — Thông tin chung"),
            "shop":     ("SHOP_QR_SHOWN",  "Test — QR thanh toán"),
        }

        # Chọn nhóm cần test
        if group:
            group = group.lower()
            if group not in GROUP_TEST_EVENTS:
                valid = ", ".join(f"`{g}`" for g in GROUP_TEST_EVENTS)
                return await ctx.reply(f"❌ Nhóm `{group}` không hợp lệ.\nNhóm hợp lệ: {valid}")
            groups_to_test = {group: GROUP_TEST_EVENTS[group]}
        else:
            groups_to_test = GROUP_TEST_EVENTS

        fallback_id = get_cfg_log_rudy()
        status_lines = []

        for grp, (event_type, title) in groups_to_test.items():
            ch_id     = get_log_channel(grp)
            label     = LOG_GROUP_LABELS[grp]
            using_fallback = False

            if not ch_id:
                if fallback_id:
                    ch_id = fallback_id
                    using_fallback = True
                else:
                    status_lines.append(f"⚠️ **{label}** — Chưa cài kênh, không có fallback")
                    continue

            channel = await get_or_fetch_channel(self.bot, ch_id)
            if not channel:
                status_lines.append(f"❌ **{label}** — Không tìm được kênh `{ch_id}`")
                continue

            try:
                await send_log(
                    self.bot,
                    event_type,
                    title,
                    fields=[
                        ("🧪 Loại test",   label,                    True),
                        ("👤 Bởi",         str(ctx.author),            True),
                        ("📌 Kênh test",   channel.mention,           True),
                    ],
                    description=(
                        f"Log test từ `.testlog` — kênh `{channel.name}` hoạt động bình thường ✅"
                        + (f" ⚠️ Dùng fallback vì `{grp}` chưa cài riêng." if using_fallback else "")
                    ),
                    user=ctx.author,
                    guild_id=ctx.guild.id,
                )
                tag = " *(fallback)*" if using_fallback else ""
                status_lines.append(f"✅ **{label}** → {channel.mention}{tag}")
            except Exception as e:
                status_lines.append(f"❌ **{label}** → `{channel.name}`: {e}")

        # Gửi bảng kết quả
        embed = discord.Embed(
            title="🧪 Kết Quả Test Log",
            description="\n".join(status_lines),
            color=0x57F287 if all(l.startswith("✅") for l in status_lines) else 0xFEE75C,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="💡 Ghi chú",
            value=(
                "✅ = log gửi thành công\n"
                "⚠️ = chưa cài kênh riêng, dùng fallback log_rudy\n"
                "❌ = lỗi, kiểm tra quyền bot trong kênh đó"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  .setlog <nhóm> #kênh để cài kênh")
        await ctx.reply(embed=embed)

    @commands.command(name="loginfo")
    async def log_info(self, ctx):
        """Xem toàn bộ kênh log đang được cài."""
        if not is_admin(ctx.author):
            return
        embed = discord.Embed(
            title="📋 Kênh Log Hiện Tại",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        for grp, label in LOG_GROUP_LABELS.items():
            ch_id = get_log_channel(grp)
            if ch_id:
                embed.add_field(name=label, value=f"<#{ch_id}>", inline=True)
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
                ("👤 Thành viên", f"{member} (`{member.id}`)", True),
                ("📅 Tạo acc",    f"<t:{int(member.created_at.timestamp())}:D>", True),
                ("👥 Tổng member", str(member.guild.member_count), True),
            ],
            user=member,
            guild_id=member.guild.id,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        roles = [r.name for r in member.roles if r.name != "@everyone"]
        await send_log(
            self.bot, "MEMBER_LEAVE", "Thành Viên Rời Server",
            fields=[
                ("👤 Thành viên", f"{member} (`{member.id}`)", True),
                ("🏷️ Roles",      " ".join(roles[-5:]) if roles else "Không có", True),
                ("👥 Tổng member", str(member.guild.member_count), True),
            ],
            user=member,
            guild_id=member.guild.id,
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        added   = [r for r in after.roles  if r not in before.roles and r.name != "@everyone"]
        removed = [r for r in before.roles if r not in after.roles  and r.name != "@everyone"]
        for role in added:
            await send_log(
                self.bot, "ROLE_ADD", "Thêm Role",
                fields=[
                    ("👤 Thành viên", f"{after} (`{after.id}`)", True),
                    ("🏷️ Role",       role.name,                         True),
                ],
                user=after,
                guild_id=after.guild.id,
            )
        for role in removed:
            await send_log(
                self.bot, "ROLE_REMOVE", "Xoá Role",
                fields=[
                    ("👤 Thành viên", f"{after} (`{after.id}`)", True),
                    ("🏷️ Role",       role.name,                         True),
                ],
                user=after,
                guild_id=after.guild.id,
            )

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if ctx.author.bot:
            return
        if ctx.command is None:
            return
        if ctx.guild is None:
            return  # Lệnh gõ trong DM — không có guild để tra kênh log
        await send_log(
            self.bot, "CMD_USED", f"Lệnh: .{ctx.command}",
            fields=[
                ("👤 Người dùng", f"{ctx.author} (`{ctx.author.id}`)", True),
                ("📝 Lệnh đầy đủ", f"`{ctx.message.content[:200]}`",           True),
                ("📌 Kênh",        ctx.channel.mention,                        True),
            ],
            user=ctx.author,
            guild_id=ctx.guild.id,
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.application_command:
            return
        if interaction.guild_id is None:
            return  # Slash command trong DM — không có guild để tra kênh log
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
                ("👤 Người dùng", f"{interaction.user} (`{interaction.user.id}`)", True),
                ("🔧 Options",    f"`{opts}`" if opts else "*(không có)*",                True),
                ("📌 Kênh",       getattr(interaction.channel, "mention", "N/A"), True),
            ],
            user=interaction.user,
            guild_id=interaction.guild_id,
        )


async def setup(bot):
    await bot.add_cog(LoggerCog(bot))
