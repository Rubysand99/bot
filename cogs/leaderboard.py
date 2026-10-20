"""
cogs/leaderboard.py — Bảng xếp hạng TOP 10 chi tiêu: có nút bấm + tự cập nhật.

Ý tưởng lấy từ mẫu bảng xếp hạng của bot khác (Cookie Store), tự viết lại:
  • Embed "TOP 10 CHI TIÊU": dòng Top 1 nổi bật, danh sách #01–#10, tổng quan, giờ cập nhật.
  • Nút 🔍 "Thứ hạng của tôi"  → trả lời RIÊNG (ephemeral): hạng, số tiền đã chi, cần chi thêm
                                 bao nhiêu để lên hạng / vào Top 10.
  • Nút 🔄 "Làm mới"           → cập nhật lại bảng ngay (có cooldown chống spam).
  • Bảng TỰ CẬP NHẬT mỗi AUTO_UPDATE_HOURS giờ: `.bxhpanel [#kênh]` tạo, `.bxhpanel off` tắt.

Nguồn dữ liệu: `user_total_spent` của guild (tự cộng dồn mỗi khi `.done` / `.donecash`) —
module này KHÔNG ghi vào dữ liệu chi tiêu, chỉ ĐỌC. Chỉ ghi duy nhất khoá `leaderboard_panel`
({channel_id, message_id}) để nhớ bảng tự cập nhật qua restart.

Tên người chơi hiển thị bằng TÊN (display name), không dùng `<@id>`:
  - `<@id>` trong embed hiện nguyên mã thô với người chưa có trong cache của client;
  - không bao giờ ping ai khi cập nhật bảng.

Tách code sang bot khác: file này chỉ phụ thuộc core.data (load_data/save_data,
GuildContextView, set_current_guild...) — copy kèm các import đó là chạy được.
"""

import logging
import re
import time
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.data import is_admin
from core.data import (
    ADMIN_IDS,
    GuildContextView,
    get_or_fetch_channel,
    is_guild_authorized,
    is_guild_loaded,
    load_data,
    reset_current_guild,
    save_data,
    set_current_guild,
    wait_data_cache_ready,
)

log = logging.getLogger("leaderboard")

TOP_N = 10
AUTO_UPDATE_HOURS = 5          # chu kỳ tự cập nhật bảng (panel)
REFRESH_COOLDOWN = 20          # giây — cooldown nút "Làm mới" trên mỗi message
COLOR_BOARD = 0xF1C40F
COLOR_ME = 0x5865F2
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

# RAM: tránh gọi API lặp lại / hạn chế spam nút
_name_cache: dict[int, str] = {}
_refresh_last: dict[int, float] = {}                  # message_id → monotonic lần làm mới gần nhất
_last_update: dict[tuple[int, int], float] = {}       # (guild_id, message_id) → epoch lần cập nhật gần nhất


# ══════════════════════════════════════════════════════════════════
# LOGIC THUẦN (không đụng Discord — dễ test)
# ══════════════════════════════════════════════════════════════════
def fmt_vnd(amount: int) -> str:
    """21120000 → '21.120.000đ' (đủ chữ số, khác fmt_amount() rút gọn kiểu '21.12tr')."""
    return f"{int(amount):,}".replace(",", ".") + "đ"


def clean_name(name: str, limit: int = 24) -> str:
    """Chặn markdown/mention lọt vào embed qua tên hiển thị."""
    name = (name or "").replace("@", "@\u200b")
    name = re.sub(r"([*_`~|>\\])", r"\\\1", name).replace("\n", " ").strip()
    return (name[:limit - 1] + "…") if len(name) > limit else (name or "Ẩn danh")


def build_ranking(spent: dict) -> list[tuple[int, int, int]]:
    """[(rank, user_id, amount)] giảm dần theo amount. Đồng hạng cùng số hạng (1, 2, 2, 4...).
    Bỏ qua amount <= 0 và dữ liệu hỏng."""
    rows = []
    for uid, amt in (spent or {}).items():
        try:
            u, a = int(uid), int(amt)
        except (TypeError, ValueError):
            continue
        if a > 0:
            rows.append((u, a))
    rows.sort(key=lambda r: (-r[1], r[0]))
    out, prev_amt, prev_rank = [], None, 0
    for i, (u, a) in enumerate(rows, 1):
        rank = prev_rank if a == prev_amt else i
        out.append((rank, u, a))
        prev_amt, prev_rank = a, rank
    return out


def my_rank_info(ranking: list, user_id: int) -> dict:
    """Thông tin 'Thứ hạng của tôi'. Không tiết lộ chi tiêu người ngoài Top 10: chỉ trả
    `above` (người ngay trên) khi người đó nằm trong Top 10 (đã công khai trên bảng)."""
    total = len(ranking)
    tenth = ranking[TOP_N - 1][2] if total >= TOP_N else 0
    idx = next((i for i, (_, u, _) in enumerate(ranking) if u == user_id), None)
    if idx is None:
        return {"found": False, "total": total, "slots_left": max(0, TOP_N - total), "tenth_amount": tenth}

    rank, _, amount = ranking[idx]
    above = next(((r, u, a) for r, u, a in reversed(ranking[:idx]) if a > amount), None)
    below = next(((r, u, a) for r, u, a in ranking[idx + 1:] if a < amount), None)
    return {
        "found": True, "rank": rank, "amount": amount, "total": total,
        "above_rank": above[0] if above else None,
        "above_uid": above[1] if above and above[0] <= TOP_N else None,   # chỉ lộ danh tính nếu đã công khai
        "gap_above": (above[2] - amount) if above else None,
        "below_rank": below[0] if below else None,
        "below_uid": below[1] if below and below[0] <= TOP_N else None,
        "gap_below": (amount - below[2]) if below else None,
        "gap_top10": (tenth - amount) if rank > TOP_N else None,
    }


def build_board_embed(guild_name: str, icon_url: str | None, ranking: list, names: dict,
                      total_buyers: int, total_spent: int, now_ts: int) -> discord.Embed:
    top = ranking[:TOP_N]
    lines: list[str] = []
    if top:
        r1, u1, a1 = top[0]
        lines.append(f"👑 **Top 1:** **{names.get(u1, '—')}** đã chi tiêu **{fmt_vnd(a1)}**")
        lines.append("")
        for rank, uid, amount in top:
            icon = MEDALS.get(rank, "▫️")
            lines.append(f"{icon} `#{rank:02d}` **{names.get(uid, '—')}** · {fmt_vnd(amount)}")
    else:
        lines.append("📭 Chưa có ai chi tiêu trong server này.\nMua hàng xong là tên bạn sẽ lên bảng!")

    lines.append("")
    lines.append("💡 Bấm **Thứ Hạng Của Tôi** để xem vị trí & khoảng cách lên hạng!")
    lines.append(f"🔄 Cập nhật <t:{now_ts}:R>")

    embed = discord.Embed(
        title=f"🏆 BẢNG XẾP HẠNG TOP {TOP_N} CHI TIÊU",
        description="\n".join(lines),
        color=COLOR_BOARD,
        timestamp=datetime.fromtimestamp(now_ts, tz=timezone.utc),
    )
    embed.add_field(name="👥 Người mua", value=f"**{total_buyers}**", inline=True)
    embed.add_field(name="💰 Tổng chi tiêu", value=f"**{fmt_vnd(total_spent)}**", inline=True)
    if icon_url:
        embed.set_thumbnail(url=icon_url)
    embed.set_footer(text=f"Tự động cập nhật mỗi {AUTO_UPDATE_HOURS} giờ • {guild_name}")
    return embed


def build_my_rank_embed(display_name: str, info: dict, names: dict) -> discord.Embed:
    embed = discord.Embed(title="🔍 Thứ hạng của bạn", color=COLOR_ME)
    embed.set_author(name=clean_name(display_name, 40))

    if not info["found"]:
        embed.description = "Bạn chưa có đơn nào được tính vào bảng xếp hạng."
        if info["slots_left"] > 0:
            embed.add_field(
                name="🎯 Vào Top 10",
                value=f"Top 10 còn **{info['slots_left']}** chỗ trống — mua đơn đầu tiên là có tên ngay!",
                inline=False)
        else:
            embed.add_field(
                name="🎯 Vào Top 10",
                value=f"Cần chi **hơn {fmt_vnd(info['tenth_amount'])}** để chen vào Top 10.",
                inline=False)
        embed.set_footer(text=f"Hiện có {info['total']} người trên bảng")
        return embed

    embed.add_field(name="🏅 Hạng", value=f"**#{info['rank']}** / {info['total']}", inline=True)
    embed.add_field(name="💰 Đã chi", value=f"**{fmt_vnd(info['amount'])}**", inline=True)

    if info["gap_above"] is None:
        text = "👑 Bạn đang **dẫn đầu** — chưa ai vượt qua được bạn!"
        if info["gap_below"] is not None and info["below_uid"] is not None:
            text += f"\nHơn **{names.get(info['below_uid'], 'người sau')}** (#{info['below_rank']}) **{fmt_vnd(info['gap_below'])}**."
    else:
        who = f" ({names[info['above_uid']]})" if info["above_uid"] in names else ""
        text = (f"⬆️ Lên hạng **#{info['above_rank']}**{who}: cần chi thêm "
                f"**hơn {fmt_vnd(info['gap_above'])}**.")
        if info["gap_top10"] is not None:
            text += (f"\n🎯 Vào Top 10: cần chi thêm **hơn {fmt_vnd(info['gap_top10'])}**."
                     if info["gap_top10"] > 0 else "\n🎯 Bằng điểm Top 10 — chỉ cần chi thêm một chút là vào!")
    embed.add_field(name="📈 Khoảng cách", value=text, inline=False)
    return embed


# ══════════════════════════════════════════════════════════════════
# KEO NỐI DISCORD
# ══════════════════════════════════════════════════════════════════
async def resolve_names(bot, guild, uids: list[int]) -> dict[int, str]:
    """uid → tên hiển thị (member trong server → cache RAM → fetch_user → '…1234')."""
    out: dict[int, str] = {}
    for uid in uids:
        member = guild.get_member(uid)
        if member is not None:
            name = member.display_name
        elif uid in _name_cache:
            name = _name_cache[uid]
        else:
            try:
                user = bot.get_user(uid) or await bot.fetch_user(uid)
                name = getattr(user, "global_name", None) or user.name
            except Exception:
                name = f"Người dùng …{str(uid)[-4:]}"
        if len(_name_cache) > 1000:
            _name_cache.clear()
        _name_cache[uid] = name
        out[uid] = clean_name(name)
    return out


async def build_guild_embed(bot, guild) -> discord.Embed:
    """Dựng embed bảng xếp hạng cho guild. YÊU CẦU: guild context đã được set (command/View/loop)."""
    spent = load_data().get("user_total_spent", {})
    ranking = build_ranking(spent)
    names = await resolve_names(bot, guild, [u for _, u, _ in ranking[:TOP_N]])
    icon = guild.icon.url if getattr(guild, "icon", None) else None
    total_spent = sum(a for _, _, a in ranking)
    return build_board_embed(guild.name, icon, ranking, names, len(ranking), total_spent, int(time.time()))


async def handle_my_rank(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    ranking = build_ranking(load_data().get("user_total_spent", {}))
    info = my_rank_info(ranking, interaction.user.id)
    uids = [u for u in (info.get("above_uid"), info.get("below_uid")) if u]
    names = await resolve_names(interaction.client, interaction.guild, uids)
    await interaction.followup.send(embed=build_my_rank_embed(interaction.user.display_name, info, names),
                                    ephemeral=True)


async def handle_refresh(interaction: discord.Interaction) -> None:
    msg_id = interaction.message.id
    now = time.monotonic()
    wait = REFRESH_COOLDOWN - (now - _refresh_last.get(msg_id, -REFRESH_COOLDOWN))
    if wait > 0:
        return await interaction.response.send_message(
            f"⏳ Bảng vừa được làm mới, thử lại sau **{int(wait) + 1}s** nhé.", ephemeral=True)
    if len(_refresh_last) > 500:
        _refresh_last.clear()
    _refresh_last[msg_id] = now

    await interaction.response.defer()
    embed = await build_guild_embed(interaction.client, interaction.guild)
    await interaction.edit_original_response(embed=embed)
    _last_update[(interaction.guild.id, msg_id)] = time.time()   # panel vừa được làm mới → lùi mốc auto-update


class LeaderboardView(GuildContextView):
    """Persistent view (timeout=None, custom_id cố định) — không gắn dữ liệu riêng của message
    nào nên dùng chung cho cả `.bxh` lẻ lẫn panel tự cập nhật, sống qua restart."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Thứ Hạng Của Tôi", emoji="🔍", style=discord.ButtonStyle.primary,
                       custom_id="lb_my_rank")
    async def my_rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_my_rank(interaction)

    @discord.ui.button(label="Làm Mới", emoji="🔄", style=discord.ButtonStyle.secondary,
                       custom_id="lb_refresh")
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_refresh(interaction)


# ══════════════════════════════════════════════════════════════════
# COG
# ══════════════════════════════════════════════════════════════════
class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_update_loop.start()

    async def cog_load(self):
        # Đăng ký lại persistent view để nút sống sau khi bot restart.
        self.bot.add_view(LeaderboardView())

    def cog_unload(self):
        self.auto_update_loop.cancel()

    # ── .bxh ────────────────────────────────────────────────────────
    @commands.command(name="bxh", aliases=["leaderboard", "top"])
    async def bxh_cmd(self, ctx: commands.Context):
        """Dùng: .bxh — Bảng xếp hạng Top 10 chi tiêu (có nút Thứ Hạng Của Tôi / Làm Mới)."""
        await self._do_bxh(ctx)

    async def _do_bxh(self, ctx) -> None:
        embed = await build_guild_embed(self.bot, ctx.guild)
        msg = await ctx.reply(embed=embed, view=LeaderboardView(), mention_author=False)
        _last_update[(ctx.guild.id, msg.id)] = time.time()

    # ── .bxhpanel ───────────────────────────────────────────────────
    @commands.command(name="bxhpanel", aliases=["lbpanel"])
    async def bxhpanel_cmd(self, ctx: commands.Context, *, target: str = ""):
        """Dùng: .bxhpanel [#kênh] — đăng bảng xếp hạng TỰ CẬP NHẬT mỗi 5 giờ (admin).
        `.bxhpanel off` — tắt bảng tự cập nhật."""
        await self._do_panel(ctx, target)

    async def _do_panel(self, ctx, target: str) -> None:
        if not is_admin(ctx.author):
            return await ctx.reply("❌ Chỉ admin mới có quyền.")
        arg = target.strip()

        if arg.lower() in ("off", "tắt", "tat", "xoa", "xóa"):
            data = load_data()
            old = data.pop("leaderboard_panel", None)
            if not old:
                return await ctx.reply("ℹ️ Server này chưa bật bảng xếp hạng tự cập nhật.")
            save_data(data)
            await self._delete_panel_message(old)
            return await ctx.reply("✅ Đã tắt bảng xếp hạng tự cập nhật (message cũ đã được xoá nếu còn).")

        channel = ctx.channel
        if arg:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, arg)
            except commands.BadArgument:
                return await ctx.reply("❌ Không tìm thấy kênh đó. Dùng: `.bxhpanel #kênh` hoặc `.bxhpanel off`.")
        perms = channel.permissions_for(ctx.guild.me)
        if not (perms.send_messages and perms.embed_links):
            return await ctx.reply(f"❌ Bot thiếu quyền **Gửi tin nhắn** / **Nhúng liên kết** ở {channel.mention}.")

        embed = await build_guild_embed(self.bot, ctx.guild)
        msg = await channel.send(embed=embed, view=LeaderboardView())

        # load LẠI sau các await ở trên rồi ghi ngay (không có await giữa load và save)
        data = load_data()
        old = data.get("leaderboard_panel")
        data["leaderboard_panel"] = {"channel_id": channel.id, "message_id": msg.id}
        save_data(data)
        _last_update[(ctx.guild.id, msg.id)] = time.time()

        if old and old.get("message_id") != msg.id:
            await self._delete_panel_message(old)
        await ctx.reply(f"✅ Đã đăng bảng xếp hạng tại {channel.mention} — tự cập nhật mỗi "
                        f"**{AUTO_UPDATE_HOURS} giờ** (bấm 🔄 để làm mới ngay).")

    async def _delete_panel_message(self, panel: dict) -> None:
        try:
            ch = await get_or_fetch_channel(self.bot, panel.get("channel_id"))
            if ch is not None:
                msg = await ch.fetch_message(panel["message_id"])
                await msg.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    # ── Tự cập nhật ─────────────────────────────────────────────────
    @tasks.loop(minutes=15)
    async def auto_update_loop(self):
        now = time.time()
        for guild in self.bot.guilds:
            try:
                if not is_guild_authorized(guild.id) or not is_guild_loaded(guild.id):
                    continue
                token = set_current_guild(guild.id)
                try:
                    await self._auto_update_guild(guild, now)
                finally:
                    reset_current_guild(token)
            except Exception:
                log.exception(f"[LB] Lỗi tự cập nhật bảng xếp hạng guild {guild.id}")

    @auto_update_loop.before_loop
    async def _before_auto_update(self):
        await self.bot.wait_until_ready()
        await wait_data_cache_ready()

    async def _auto_update_guild(self, guild, now: float) -> None:
        panel = load_data().get("leaderboard_panel")
        if not panel:
            return
        key = (guild.id, panel["message_id"])
        if now - _last_update.get(key, 0.0) < AUTO_UPDATE_HOURS * 3600:
            return
        ch = await get_or_fetch_channel(self.bot, panel["channel_id"])
        if ch is None:
            log.warning(f"[LB] Không truy cập được kênh bảng xếp hạng guild {guild.id} — thử lại lần sau.")
            return
        try:
            msg = await ch.fetch_message(panel["message_id"])
        except discord.NotFound:
            data = load_data()                       # message đã bị xoá → ngừng theo dõi
            data.pop("leaderboard_panel", None)
            save_data(data)
            log.info(f"[LB] Message bảng xếp hạng guild {guild.id} đã bị xoá — tắt tự cập nhật.")
            return
        except discord.HTTPException as e:
            log.warning(f"[LB] Lỗi fetch message bảng xếp hạng guild {guild.id}: {e}")
            return
        embed = await build_guild_embed(self.bot, guild)
        await msg.edit(embed=embed)
        _last_update[key] = now


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
