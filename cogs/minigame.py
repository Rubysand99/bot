# cogs/minigame.py — v3.7.0
# Bầu Cua nhiều người: .bc open, embed nút bấm, tự chọn mặt + point
# Giữ: Búa Kéo Bao, BXH, Thống kê
# Bỏ: Nối Từ, Vua Tiếng Việt

import discord
from cogs.logger import send_log
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
import random, asyncio, time
from datetime import datetime, timezone

from core.data import (
    load_data, save_data, ADMIN_IDS, is_staff_member,
    get_user_points, add_user_points,
    get_mg_stats, record_win_async, get_leaderboard,
)

WIN_RATE = 0.9

# ══════════════════════════════════════════
# CONFIG KÊNH BẦU CUA
# ══════════════════════════════════════════
def get_baucua_channel() -> int:
    return load_data().get("baucua_channel_id", 0)

def set_baucua_channel(cid: int):
    data = load_data()
    data["baucua_channel_id"] = cid
    save_data(data)

# ══════════════════════════════════════════
# BẦU CUA DATA
# ══════════════════════════════════════════
BAU_CUA_ICONS = {
    "bầu": "🎃", "cua": "🦀", "cá": "🐟",
    "gà":  "🐓", "tôm": "🦐", "nai": "🦌",
}
BAU_CUA_KEYS  = list(BAU_CUA_ICONS.keys())
BAU_CUA_ALIAS = {"bau":"bầu","cua":"cua","ca":"cá","ga":"gà","tom":"tôm","nai":"nai"}

# ══════════════════════════════════════════
# BÚA KÉO BAO
# ══════════════════════════════════════════
BKB_CHOICES = {"búa":"🔨","kéo":"✂️","bao":"📄"}
BKB_WIN     = {"búa":"kéo","kéo":"bao","bao":"búa"}
BKB_ALIAS   = {"bua":"búa","keo":"kéo","bao":"bao","búa":"búa","kéo":"kéo"}

# ══════════════════════════════════════════
# SESSION ĐANG CHẠY
# baucua_sessions[channel_id] = {
#   host_id, bets: {user_id: {choice, amount}},
#   min_players, max_players, status, message, task
# }
# ══════════════════════════════════════════
baucua_sessions: dict = {}


def parse_bet(s: str) -> int | None:
    s = s.lower().strip().rstrip("ppt").strip()
    try:
        v = int(s)
        return v if v > 0 else None
    except ValueError:
        return None


# ══════════════════════════════════════════
# MODAL — Nhập số point cược
# ══════════════════════════════════════════
class BetModal(Modal, title="💰 Nhập số point cược"):
    amount = TextInput(
        label="Số point muốn cược (tối thiểu 1)",
        placeholder="VD: 10",
        min_length=1,
        max_length=10,
    )

    def __init__(self, choice: str, session: dict):
        super().__init__()
        self.choice  = choice
        self.session = session

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id

        # Parse số tiền
        try:
            amount = int(self.amount.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ Số point không hợp lệ!", ephemeral=True)

        if amount < 1:
            return await interaction.response.send_message("❌ Tối thiểu 1 point!", ephemeral=True)

        # Kiểm tra point
        pts = get_user_points(uid)
        if pts < amount:
            return await interaction.response.send_message(
                f"❌ Bạn chỉ có **{pts} point**, không đủ cược **{amount} point**!", ephemeral=True
            )

        # Nếu đã đặt rồi thì đổi
        old = self.session["bets"].get(uid)
        self.session["bets"][uid] = {"choice": self.choice, "amount": amount}

        icon = BAU_CUA_ICONS[self.choice]
        if old:
            msg = f"🔄 Đã đổi cược: {BAU_CUA_ICONS[old['choice']]} **{old['choice']}** {old['amount']}pt → {icon} **{self.choice}** **{amount}pt**"
        else:
            msg = f"✅ Đã đặt cược: {icon} **{self.choice}** — **{amount} point**"

        await interaction.response.send_message(msg, ephemeral=True)

        # Cập nhật embed
        await _update_session_embed(self.session)

        # Nếu đủ người tối thiểu và tất cả đã chọn → lắc ngay
        await _check_auto_shake(self.session)


# ══════════════════════════════════════════
# VIEW — Embed bầu cua với 6 nút
# ══════════════════════════════════════════
class BauCuaView(View):
    def __init__(self, session: dict):
        super().__init__(timeout=30)
        self.session = session

        for key, icon in BAU_CUA_ICONS.items():
            btn = Button(
                label=key.capitalize(),
                emoji=icon,
                style=discord.ButtonStyle.primary,
                custom_id=f"baucua_{key}",
            )
            btn.callback = self._make_callback(key)
            self.add_item(btn)

    def _make_callback(self, choice: str):
        async def callback(interaction: discord.Interaction):
            session = self.session
            if session.get("status") != "open":
                return await interaction.response.send_message("❌ Phiên đã kết thúc!", ephemeral=True)

            # Hiện modal nhập point
            modal = BetModal(choice=choice, session=session)
            await interaction.response.send_modal(modal)
        return callback

    async def on_timeout(self):
        session = self.session
        if session.get("status") == "open":
            await _shake_and_result(session)


# ══════════════════════════════════════════
# HELPERS SESSION
# ══════════════════════════════════════════
def _build_embed(session: dict, title: str = "🎲 Bầu Cua Tôm Cá — Đang mở cược!") -> discord.Embed:
    bets   = session["bets"]
    total  = len(bets)
    min_p  = session["min_players"]
    max_p  = session["max_players"]

    e = discord.Embed(title=title, color=discord.Color.gold())
    e.description = (
        f"Nhấn nút để chọn mặt và nhập point cược!\n"
        f"👥 Người chơi: **{total}/{min_p}-{max_p}**\n"
        f"⏰ Tự động lắc sau **30 giây** hoặc khi đủ người"
    )

    # Danh sách người đã đặt
    if bets:
        lines = []
        for uid, b in bets.items():
            icon = BAU_CUA_ICONS[b["choice"]]
            lines.append(f"{icon} **{b['choice']}** — <@{uid}> ({b['amount']}pt)")
        e.add_field(name="📋 Danh sách cược", value="\n".join(lines), inline=False)
    else:
        e.add_field(name="📋 Danh sách cược", value="*Chưa có ai đặt cược*", inline=False)

    e.set_footer(text="Tỉ lệ: x1→+0.9pt | x2→+1.8pt | x3→+2.7pt | Thua→-1pt")
    return e


async def _update_session_embed(session: dict):
    try:
        msg = session.get("message")
        if msg:
            await msg.edit(embed=_build_embed(session))
    except Exception:
        pass


async def _check_auto_shake(session: dict):
    """Lắc ngay nếu tất cả người đã đặt và đủ người tối thiểu."""
    bets  = session["bets"]
    total = len(bets)
    if total >= session["min_players"] and session.get("status") == "open":
        # Hủy task timeout nếu có
        task = session.get("task")
        if task and not task.done():
            task.cancel()
        await _shake_and_result(session)


async def _shake_and_result(session: dict):
    if session.get("status") != "open":
        return
    session["status"] = "done"

    cid  = session["channel_id"]
    bets = session["bets"]

    # Xóa session
    baucua_sessions.pop(cid, None)

    # Disable view
    msg = session.get("message")
    if msg:
        view = BauCuaView(session)
        for item in view.children:
            item.disabled = True
        try:
            await msg.edit(view=view)
        except Exception:
            pass

    # Không có ai đặt
    if not bets:
        channel = session.get("channel_obj")
        if channel:
            await channel.send("⚠️ Không có ai đặt cược, phiên kết thúc!")
        return

    # Lắc xúc xắc
    dice = [random.choice(BAU_CUA_KEYS) for _ in range(3)]
    dice_str = "  ".join(BAU_CUA_ICONS[d] for d in dice)

    # Tính kết quả từng người
    winners = []
    losers  = []
    for uid, b in bets.items():
        choice = b["choice"]
        amount = b["amount"]
        hits   = dice.count(choice)
        icon   = BAU_CUA_ICONS[choice]
        if hits > 0:
            gain = int(amount * hits * WIN_RATE)
            add_user_points(uid, +gain, f"baucua_multi_win hits={hits} bet={amount}")
            await record_win_async(uid, "baucua")
            winners.append((uid, choice, amount, hits, gain, icon))
        else:
            add_user_points(uid, -amount, f"baucua_multi_lose bet={amount}")
            losers.append((uid, choice, amount, icon))

    # Build kết quả embed
    e = discord.Embed(
        title="🎲 Kết Quả Bầu Cua!",
        color=discord.Color.green() if winners else discord.Color.red(),
        timestamp=datetime.now(timezone.utc)
    )
    e.add_field(name="🎯 Xúc xắc lắc được", value=dice_str, inline=False)

    if winners:
        win_lines = []
        for uid, choice, amount, hits, gain, icon in winners:
            win_lines.append(f"🏆 <@{uid}> — {icon} **{choice}** x{hits} → **+{gain}pt**")
        e.add_field(name="✅ Thắng", value="\n".join(win_lines), inline=False)

    if losers:
        lose_lines = []
        for uid, choice, amount, icon in losers:
            lose_lines.append(f"💸 <@{uid}> — {icon} **{choice}** → **-{amount}pt**")
        e.add_field(name="❌ Thua", value="\n".join(lose_lines), inline=False)

    channel = session.get("channel_obj")
    if channel:
        await channel.send(embed=e)
        await send_log(channel.guild._state._get_client(), "MINIGAME", "Kết thúc Bầu Cua",
            fields=[("Xúc xắc", " ".join(str(d) for d in session.get("dice", [])), True),
                    ("Thắng", str(len(winners)), True), ("Thua", str(len(losers)), True)])


async def _session_timeout(session: dict):
    """Task chạy ngầm đếm 30s rồi lắc."""
    await asyncio.sleep(30)
    if session.get("status") == "open":
        await _shake_and_result(session)


# ══════════════════════════════════════════
# COG
# ══════════════════════════════════════════
class Minigame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ════════════════════════════════════════
    # .setbaucua — Admin cài kênh
    # ════════════════════════════════════════
    @commands.command(name="setbaucua")
    async def set_baucua_cmd(self, ctx, channel: discord.TextChannel = None):
        """Admin chỉ định kênh chơi bầu cua."""
        if ctx.author.id not in ADMIN_IDS and not is_staff_member(ctx.author):
            return await ctx.reply("❌ Chỉ admin/staff mới dùng được.")
        if channel is None:
            cid = get_baucua_channel()
            if cid:
                ch = ctx.guild.get_channel(cid)
                return await ctx.reply(f"🎲 Kênh bầu cua: {ch.mention if ch else f'<#{cid}>'}")
            return await ctx.reply("🎲 Chưa cài. Dùng `.setbaucua #kênh`.")
        set_baucua_channel(channel.id)
        await ctx.reply(f"✅ Đã cài kênh bầu cua: {channel.mention}")

    # ════════════════════════════════════════
    # .bc open — Mở phiên bầu cua
    # ════════════════════════════════════════
    @commands.group(name="bc", invoke_without_command=True)
    async def bc_group(self, ctx):
        await ctx.reply(
            "🎲 **Bầu Cua Tôm Cá**\n"
            "`.bc open` — Mở phiên cược nhiều người\n"
            "`.bkb <búa|kéo|bao> [point]` — Búa Kéo Bao với bot\n"
            "`.rank` — Bảng xếp hạng\n"
            "`.mgstats` — Thống kê cá nhân"
        )

    @bc_group.command(name="open")
    async def bc_open(self, ctx):
        """Mở phiên Bầu Cua nhiều người (4-6 người, 30 giây)."""
        cid       = ctx.channel.id
        bc_cid    = get_baucua_channel()

        # Kiểm tra kênh
        if bc_cid and cid != bc_cid and ctx.author.id not in ADMIN_IDS:
            ch = ctx.guild.get_channel(bc_cid)
            return await ctx.reply(f"❌ Bầu Cua chỉ chơi trong {ch.mention if ch else f'<#{bc_cid}>'}!")

        # Kiểm tra phiên đang mở
        if cid in baucua_sessions:
            return await ctx.reply("⚠️ Đang có phiên Bầu Cua! Chờ phiên kết thúc.")

        # Tạo session
        session = {
            "channel_id":  cid,
            "channel_obj": ctx.channel,
            "host_id":     ctx.author.id,
            "bets":        {},
            "min_players": 4,
            "max_players": 6,
            "status":      "open",
            "message":     None,
            "task":        None,
        }
        baucua_sessions[cid] = session

        # Gửi embed + view
        view = BauCuaView(session)
        embed = _build_embed(session)
        msg  = await ctx.send(embed=embed, view=view)
        session["message"] = msg

        # Task timeout 30s
        task = asyncio.create_task(_session_timeout(session))
        session["task"] = task

    # ════════════════════════════════════════
    # .bc cancel — Hủy phiên (host/admin)
    # ════════════════════════════════════════
    @bc_group.command(name="cancel")
    async def bc_cancel(self, ctx):
        """Hủy phiên Bầu Cua đang mở."""
        cid = ctx.channel.id
        if cid not in baucua_sessions:
            return await ctx.reply("❌ Không có phiên nào đang mở.")
        session = baucua_sessions[cid]
        if ctx.author.id != session["host_id"] and ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ người mở phiên hoặc admin mới hủy được.")
        session["status"] = "cancelled"
        task = session.get("task")
        if task and not task.done():
            task.cancel()
        baucua_sessions.pop(cid, None)
        await ctx.reply("🛑 Phiên Bầu Cua đã bị hủy!")

    # ════════════════════════════════════════
    # ✂️ BÚA KÉO BAO
    # ════════════════════════════════════════
    @commands.command(name="bkb", aliases=["bukebao", "rps"])
    async def bkb(self, ctx, choice: str = None, bet_str: str = None):
        """✂️ Búa Kéo Bao — .bkb <búa|kéo|bao> [point_cược]"""
        if not choice:
            opts = "  ".join(f"{v}`{k}`" for k, v in BKB_CHOICES.items())
            return await ctx.reply(f"✂️ **Búa Kéo Bao**\n{opts}\nVD: `.bkb búa 10`")

        choice = BKB_ALIAS.get(choice.lower().strip(), choice.lower().strip())
        if choice not in BKB_CHOICES:
            return await ctx.reply("❌ Chọn: `búa`, `kéo`, `bao`")

        bet = 0
        if bet_str:
            bet = parse_bet(bet_str) or 0
            if bet > 0:
                pts = get_user_points(ctx.author.id)
                if pts < bet:
                    return await ctx.reply(f"❌ Bạn chỉ có **{pts} point**, không đủ cược **{bet} point**!")

        bot_c = random.choice(list(BKB_CHOICES.keys()))
        draw  = (choice == bot_c)
        win   = (not draw and BKB_WIN[choice] == bot_c)

        if draw:  result, color = "🤝 **Hòa!**",        discord.Color.yellow()
        elif win: result, color = "🏆 **Bạn thắng!**",  discord.Color.green()
        else:     result, color = "💀 **Bot thắng!**",  discord.Color.red()

        bet_result = ""
        if bet > 0 and not draw:
            if win:
                gain = int(bet * WIN_RATE)
                add_user_points(ctx.author.id, +gain, f"bkb_win bet={bet}")
                await record_win_async(ctx.author.id, "bkb")
                bet_result = f"\n💎 **+{gain} point** | Tổng: **{get_user_points(ctx.author.id)} pt**"
            else:
                add_user_points(ctx.author.id, -bet, f"bkb_lose bet={bet}")
                bet_result = f"\n💸 **-{bet} point** | Tổng: **{get_user_points(ctx.author.id)} pt**"
        elif win and bet == 0:
            await record_win_async(ctx.author.id, "bkb")

        e = discord.Embed(title="✂️ Búa Kéo Bao", color=color)
        e.add_field(name=ctx.author.display_name, value=f"{BKB_CHOICES[choice]} **{choice}**",    inline=True)
        e.add_field(name="vs",                    value="⚔️",                                      inline=True)
        e.add_field(name="Bot Rudeus",            value=f"{BKB_CHOICES[bot_c]} **{bot_c}**",       inline=True)
        e.add_field(name="Kết quả",               value=result + bet_result,                       inline=False)
        if bet > 0:
            e.set_footer(text=f"Cược: {bet}pt | Thắng +{int(bet*WIN_RATE)}pt | Thua -{bet}pt | Hòa hoàn tiền")
        await ctx.reply(embed=e)
        await send_log(ctx.bot, "MINIGAME", f"BKB — {ctx.author.display_name}",
            fields=[("Chọn", choice, True), ("Bot", bot_c, True), ("Kết quả", result, True)])

    @app_commands.command(name="bkb", description="✂️ Búa Kéo Bao với bot")
    @app_commands.describe(chon="búa, kéo hoặc bao", cuoc="Số point muốn cược")
    async def bkb_slash(self, interaction, chon: str, cuoc: int = 0):
        await self.bkb(await commands.Context.from_interaction(interaction), chon, str(cuoc) if cuoc else None)

    # ════════════════════════════════════════
    # 🏆 BẢNG XẾP HẠNG
    # ════════════════════════════════════════
    @commands.command(name="rank", aliases=["xephang", "leaderboard"])
    async def rank_cmd(self, ctx, game: str = "total"):
        """🏆 Bảng xếp hạng — .rank [baucua|bkb]"""
        game_map = {
            "baucua":"baucua","bc":"baucua",
            "bkb":"bkb","rps":"bkb",
            "total":"total","all":"total",
        }
        game_key = game_map.get(game.lower(), "total")
        labels   = {
            "baucua": "🎲 Bầu Cua",
            "bkb":    "✂️ Búa Kéo Bao",
            "total":  "🎮 Tất cả game",
        }
        rows = get_leaderboard(game_key, top=10)
        if not rows:
            return await ctx.reply(f"📊 Chưa có dữ liệu thắng cho **{labels.get(game_key,'?')}**.")

        medals = ["🥇","🥈","🥉"] + ["🏅"]*7
        lines  = []
        for i, (uid, wins) in enumerate(rows):
            member = ctx.guild.get_member(uid)
            name   = member.display_name if member else f"User {uid}"
            lines.append(f"{medals[i]} **{name}** — **{wins}** lần thắng")

        e = discord.Embed(
            title=f"🏆 Bảng Xếp Hạng — {labels.get(game_key,'?')}",
            description="\n".join(lines),
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        e.set_footer(text="Dùng .rank baucua | .rank bkb")
        await ctx.reply(embed=e)

    @app_commands.command(name="rank", description="🏆 Bảng xếp hạng minigame")
    @app_commands.describe(game="total / baucua / bkb")
    async def rank_slash(self, interaction, game: str = "total"):
        await self.rank_cmd(await commands.Context.from_interaction(interaction), game)

    # ════════════════════════════════════════
    # 📊 THỐNG KÊ CÁ NHÂN
    # ════════════════════════════════════════
    @commands.command(name="mgstats", aliases=["gamestats", "mystats"])
    async def mgstats_cmd(self, ctx, member: discord.Member = None):
        """📊 Thống kê minigame cá nhân."""
        target = member or ctx.author
        stats  = get_mg_stats().get(str(target.id), {})
        pts    = get_user_points(target.id)

        e = discord.Embed(
            title=f"📊 Thống Kê — {target.display_name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        e.set_thumbnail(url=target.display_avatar.url)
        e.add_field(name="🎲 Bầu Cua",     value=f"**{stats.get('baucua',0)}** lần thắng", inline=True)
        e.add_field(name="✂️ Búa Kéo Bao", value=f"**{stats.get('bkb',0)}** lần thắng",   inline=True)
        e.add_field(name="🏆 Tổng thắng",  value=f"**{stats.get('total',0)}** lần",        inline=True)
        e.add_field(name="💎 Point",        value=f"**{pts:,} pt**",                        inline=True)
        await ctx.reply(embed=e)

    @app_commands.command(name="mgstats", description="📊 Thống kê minigame cá nhân")
    @app_commands.describe(thanh_vien="Để trống = xem của bạn")
    async def mgstats_slash(self, interaction, thanh_vien: discord.Member = None):
        await self.mgstats_cmd(await commands.Context.from_interaction(interaction), thanh_vien)

    # ════════════════════════════════════════
    # ℹ️ HELP
    # ════════════════════════════════════════
    @commands.command(name="minigame", aliases=["mg", "games"])
    async def mg_help(self, ctx):
        bc_cid  = get_baucua_channel()
        bc_kenh = f"📌 Kênh: <#{bc_cid}>" if bc_cid else "💡 Chưa cài — `.setbaucua #kênh`"
        e = discord.Embed(title="🎮 Minigame — Hướng Dẫn", color=discord.Color.blurple())
        e.add_field(
            name="🎲 Bầu Cua Tôm Cá (Nhiều người)",
            value=(
                f"`.bc open` — Mở phiên 30s\n"
                f"Nhấn nút chọn mặt → nhập point cược\n"
                f"4-6 người, tự động lắc khi đủ người\n"
                f"{bc_kenh}\n"
                f"Tỉ lệ: x1→**+0.9pt** | x2→**+1.8pt** | x3→**+2.7pt**"
            ),
            inline=False
        )
        e.add_field(
            name="✂️ Búa Kéo Bao (1 người vs Bot)",
            value=(
                "`.bkb <búa|kéo|bao>` — Chơi không cược\n"
                "`.bkb <lựa chọn> <point>` — Cược point\n"
                "Thắng: **+0.9pt/pt** | Thua: **-1pt/pt** | Hòa: hoàn tiền"
            ),
            inline=False
        )
        e.add_field(
            name="🏆 Xếp hạng & Thống kê",
            value=(
                "`.rank` — BXH tổng\n"
                "`.rank baucua` / `.rank bkb` — BXH từng game\n"
                "`.mgstats` / `.mgstats @user` — Thống kê cá nhân"
            ),
            inline=False
        )
        e.set_footer(text="Tất cả đều có slash command /tên tương ứng")
        await ctx.reply(embed=e)

    def cog_unload(self):
        baucua_sessions.clear()


async def setup(bot):
    await bot.add_cog(Minigame(bot))
