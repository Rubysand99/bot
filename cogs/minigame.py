# cogs/minigame.py — v3.6.3
# Thêm: cá cược point, bảng xếp hạng, thống kê theo game
# Tỉ lệ: winner +0.9x, loser -1x

import discord
from discord.ext import commands
from discord import app_commands
import random, asyncio, os, time
from datetime import datetime, timezone

from core.data import (
    load_data, save_data, ADMIN_IDS, is_staff_member,
    get_user_points, add_user_points,
)

# ══════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════
WIN_RATE  = 0.9   # winner nhận +0.9x tiền cược
LOSE_RATE = 1.0   # loser mất -1x tiền cược

# ══════════════════════════════════════════
# DATA HELPERS — Minigame stats & bets
# ══════════════════════════════════════════

def get_mg_stats() -> dict:
    return load_data().get("minigame_stats", {})

def _save_mg_stats(stats: dict):
    data = load_data()
    data["minigame_stats"] = stats
    save_data(data)

def record_win(user_id: int, game: str):
    """Ghi nhận 1 lần thắng."""
    stats = get_mg_stats()
    key   = str(user_id)
    stats.setdefault(key, {"baucua": 0, "bkb": 0, "noitu": 0, "vtv": 0, "total": 0})
    if game in stats[key]:
        stats[key][game] += 1
    stats[key]["total"] += 1
    _save_mg_stats(stats)

def get_leaderboard(game: str = "total", top: int = 10) -> list:
    """Trả về [(user_id, wins)] sắp xếp giảm dần."""
    stats = get_mg_stats()
    rows  = []
    for uid, s in stats.items():
        wins = s.get(game, 0)
        if wins > 0:
            rows.append((int(uid), wins))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:top]

def get_noitu_channel() -> int:
    return load_data().get("noitu_channel_id", 0)

def set_noitu_channel(cid: int):
    data = load_data()
    data["noitu_channel_id"] = cid
    save_data(data)

# ══════════════════════════════════════════
# BẦU CUA
# ══════════════════════════════════════════
BAU_CUA_ICONS = {"bầu":"🎃","cua":"🦀","cá":"🐟","gà":"🐓","tôm":"🦐","nai":"🦌"}
BAU_CUA_KEYS  = list(BAU_CUA_ICONS.keys())
BAU_CUA_ALIAS = {"bau":"bầu","cua":"cua","ca":"cá","ga":"gà","tom":"tôm","nai":"nai"}

# ══════════════════════════════════════════
# BÚA KÉO BAO
# ══════════════════════════════════════════
BKB_CHOICES = {"búa":"🔨","kéo":"✂️","bao":"📄"}
BKB_WIN     = {"búa":"kéo","kéo":"bao","bao":"búa"}
BKB_ALIAS   = {"bua":"búa","keo":"kéo","bao":"bao","búa":"búa","kéo":"kéo"}

# ══════════════════════════════════════════
# NỐI TỪ
# ══════════════════════════════════════════
WORD_LIST_PATH = os.path.join(os.path.dirname(__file__), "../data/words_vi.txt")
FALLBACK_WORDS = [
    "học sinh","sinh viên","viên chức","chức năng","năng lực","lực lượng",
    "lượng giá","giá trị","trị giá","giá cả","cả nhà","nhà trường",
    "trường học","học hành","hành động","động lực","lực sĩ","sĩ quan",
    "quan tâm","tâm hồn","hồn nhiên","nhiên liệu","liệu pháp","pháp luật",
    "luật pháp","pháp lý","lý luận","luận văn","văn hóa","hóa học",
    "học thuật","thuật toán","toán học","học bổng","bổng lộc","lộc trời",
    "trời đất","đất nước","nước nhà","nhà nước","nước mắt","mắt xích",
    "xích lô","lô đề","đề thi","thi cử","cử nhân","nhân vật","vật lý",
    "lý thuyết","thuyết phục","phục vụ","vụ án","án lệ","lệ phí",
    "phí tổn","tổn thất","thất bại","bại trận","trận đấu","đấu tranh",
    "tranh luận","luận điểm","điểm số","số lượng","sinh hoạt","hoạt động",
    "động vật","vật chất","chất lượng","lượng tử","tử tế","tế bào",
]

NOITU_COOLDOWN = 3
noi_tu_sessions: dict = {}
vtv_sessions: dict    = {}

# ══════════════════════════════════════════
# VUA TIẾNG VIỆT
# ══════════════════════════════════════════
VTV_QUESTIONS = [
    {"q":"Từ nào sau đây là từ láy?","choices":["A. học sinh","B. lung linh","C. đất nước","D. bàn ghế"],"ans":"B"},
    {"q":"\"Cô ấy có đôi mắt ___ như sao.\" Điền từ:","choices":["A. sáng","B. long lanh","C. đen","D. to"],"ans":"B"},
    {"q":"Câu nào dùng biện pháp nhân hóa?","choices":["A. Mặt trăng tròn như cái đĩa","B. Gió ơi gió hỡi gió về đâu","C. Con sông dài như dải lụa","D. Hoa nở rộ khắp vườn"],"ans":"B"},
    {"q":"Từ \"kiên nhẫn\" thuộc loại từ gì?","choices":["A. Danh từ","B. Động từ","C. Tính từ","D. Trạng từ"],"ans":"C"},
    {"q":"\"Nước chảy đá mòn\" có nghĩa là gì?","choices":["A. Đá rất cứng","B. Kiên trì ắt thành công","C. Nước rất mạnh","D. Không thể thay đổi"],"ans":"B"},
    {"q":"\"Trẻ em như búp trên cành\" dùng biện pháp tu từ nào?","choices":["A. Nhân hóa","B. Ẩn dụ","C. So sánh","D. Hoán dụ"],"ans":"C"},
    {"q":"Từ nào KHÔNG phải từ ghép?","choices":["A. học hành","B. xinh xắn","C. bàn tay","D. cây cối"],"ans":"B"},
    {"q":"\"Bán anh em xa mua láng giềng gần\" thuộc thể loại gì?","choices":["A. Ca dao","B. Tục ngữ","C. Thành ngữ","D. Thơ"],"ans":"B"},
    {"q":"Chủ ngữ trong \"Mưa rơi lộp độp trên mái nhà\" là gì?","choices":["A. Mưa","B. Mái nhà","C. Lộp độp","D. Rơi"],"ans":"A"},
    {"q":"Từ nào viết đúng chính tả?","choices":["A. giản dị","B. dản dị","C. giản rị","D. zản dị"],"ans":"A"},
    {"q":"Từ nào là từ Hán Việt?","choices":["A. nhà cửa","B. gia đình","C. bàn ghế","D. cơm nước"],"ans":"B"},
    {"q":"\"Một con ngựa đau cả tàu bỏ cỏ\" nói lên điều gì?","choices":["A. Ngựa ăn ít","B. Tinh thần đoàn kết","C. Nuôi ngựa tốn kém","D. Ngựa yếu thì bỏ"],"ans":"B"},
    {"q":"Câu \"Hoa hồng nở rực rỡ\" — vị ngữ là gì?","choices":["A. Hoa hồng","B. nở rực rỡ","C. rực rỡ","D. nở"],"ans":"B"},
    {"q":"\"Đầu xuôi đuôi lọt\" có nghĩa là gì?","choices":["A. Bơi giỏi","B. Bắt đầu tốt thì kết thúc thuận lợi","C. Làm việc nhanh","D. Đầu to đuôi nhỏ"],"ans":"B"},
    {"q":"Từ \"xanh\" trong \"Trời xanh\" và \"Xanh lá\" quan hệ là gì?","choices":["A. Từ đồng âm","B. Từ nhiều nghĩa","C. Từ trái nghĩa","D. Từ đồng nghĩa"],"ans":"B"},
]

# ══════════════════════════════════════════
# WORD HELPERS
# ══════════════════════════════════════════
def load_words():
    try:
        with open(WORD_LIST_PATH, encoding="utf-8") as f:
            return [w.strip().lower() for w in f if w.strip()]
    except Exception:
        return FALLBACK_WORDS

WORDS_VI = load_words()

def last_syl(p: str) -> str:  return p.strip().split()[-1].lower()
def first_syl(p: str) -> str: return p.strip().split()[0].lower()

def find_next(syl: str, used: set):
    c = [w for w in WORDS_VI if first_syl(w) == syl and w not in used]
    return random.choice(c) if c else None

# ══════════════════════════════════════════
# BET HELPERS
# ══════════════════════════════════════════
def parse_bet(s: str) -> int | None:
    """Parse chuỗi bet: '10', '10p', '10pt' → int hoặc None."""
    s = s.lower().strip().rstrip("ppt").strip()
    try:
        v = int(s)
        return v if v > 0 else None
    except ValueError:
        return None

def apply_bet(winner_id: int, loser_id: int, bet: int):
    """Trừ/cộng point sau khi có kết quả."""
    gain = int(bet * WIN_RATE)
    add_user_points(winner_id, +gain, f"minigame_win bet={bet}")
    add_user_points(loser_id,  -bet,  f"minigame_lose bet={bet}")
    return gain

# ══════════════════════════════════════════
# NỐI TỪ on_message helper
# ══════════════════════════════════════════
async def _process_word(session: dict, word: str, author: discord.Member, channel: discord.TextChannel):
    async with session["lock"]:
        uid, now = author.id, time.time()
        if now - session["player_last_time"].get(uid, 0) < NOITU_COOLDOWN:
            wait = int(NOITU_COOLDOWN - (now - session["player_last_time"].get(uid, 0)))
            await channel.send(f"⏳ {author.mention} chờ **{wait}s**!", delete_after=4)
            return
        if session["last_player"] == uid and len(session["used"]) > 2:
            await channel.send(f"❌ {author.mention} phải để người khác nối trước!", delete_after=4)
            return
        if word in session["used"]:
            await channel.send(f"❌ Từ **{word}** đã dùng rồi!", delete_after=6)
            return
        if word not in WORDS_VI:
            await channel.send(f"❌ Từ **{word}** không có trong từ điển!", delete_after=6)
            return
        req = last_syl(session["word"])
        if first_syl(word) != req:
            await channel.send(f"❌ {author.mention} phải nối từ bắt đầu bằng **`{req}`**!", delete_after=6)
            return

        session["used"].add(word)
        session["word"]                  = word
        session["last_player"]           = uid
        session["player_last_time"][uid] = now

        nxt   = last_syl(word)
        bot_w = find_next(nxt, session["used"])

        if bot_w:
            session["used"].add(bot_w)
            session["word"] = bot_w
            e = discord.Embed(color=discord.Color.green())
            e.add_field(name=f"✅ {author.display_name}", value=f"**{word}**",  inline=True)
            e.add_field(name="🤖 Bot Rudeus",             value=f"**{bot_w}**", inline=True)
            e.set_footer(text=f"Nối từ bắt đầu bằng '{last_syl(bot_w)}'")
            await channel.send(embed=e)
        else:
            # Người chơi thắng bot
            record_win(uid, "noitu")
            bet = session.get("bet", 0)
            msg = (
                f"✅ **{author.display_name}** nối: **{word}**\n"
                f"🤖 Bot hết từ bắt đầu bằng **`{nxt}`**!\n"
                f"🏆 **{author.display_name} THẮNG!**"
            )
            if bet > 0:
                gain = int(bet * WIN_RATE)
                add_user_points(uid, +gain, "noitu_win")
                msg += f"\n💎 Nhận **+{gain} point** (cược {bet}pt)"
            del noi_tu_sessions[channel.id]
            await channel.send(msg)


# ══════════════════════════════════════════
# COG
# ══════════════════════════════════════════
class Minigame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── on_message ─────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        cid       = message.channel.id
        noitu_cid = get_noitu_channel()
        if cid != noitu_cid or cid not in noi_tu_sessions:
            return
        content = message.content.strip().lower()
        if content.startswith(".") or content.startswith("/"):
            return
        if len(content.split()) > 3:
            return
        session = noi_tu_sessions.get(cid)
        if session and session.get("dedicated"):
            await _process_word(session, content, message.author, message.channel)

    # ════════════════════════════════════════
    # .setnoitu
    # ════════════════════════════════════════
    @commands.command(name="setnoitu")
    async def set_noitu_cmd(self, ctx, channel: discord.TextChannel = None):
        """Admin chỉ định kênh nối từ."""
        if ctx.author.id not in ADMIN_IDS and not is_staff_member(ctx.author):
            return await ctx.reply("❌ Chỉ admin/staff mới dùng được.")
        if channel is None:
            cid = get_noitu_channel()
            if cid:
                ch = ctx.guild.get_channel(cid)
                return await ctx.reply(f"🔤 Kênh nối từ: {ch.mention if ch else f'<#{cid}>'}")
            return await ctx.reply("🔤 Chưa cài. Dùng `.setnoitu #kênh`.")
        set_noitu_channel(channel.id)
        await ctx.reply(f"✅ Đã cài kênh nối từ: {channel.mention}\nDùng `.start` để bắt đầu, nhắn từ thẳng để nối.")

    # ════════════════════════════════════════
    # .start
    # ════════════════════════════════════════
    @commands.command(name="start")
    async def noitu_start(self, ctx, bet_str: str = None):
        """🔤 Bắt đầu Nối Từ. Tùy chọn: .start <số_point_cược>"""
        cid       = ctx.channel.id
        noitu_cid = get_noitu_channel()

        if noitu_cid and cid != noitu_cid and ctx.author.id not in ADMIN_IDS:
            ch = ctx.guild.get_channel(noitu_cid)
            return await ctx.reply(f"❌ Game chỉ chạy trong {ch.mention if ch else f'<#{noitu_cid}>'}!")

        if cid in noi_tu_sessions:
            return await ctx.reply("⚠️ Đang có game rồi! Dùng `.stop` để dừng.")

        # Parse cược
        bet = 0
        if bet_str:
            bet = parse_bet(bet_str) or 0
            if bet > 0:
                pts = get_user_points(ctx.author.id)
                if pts < bet:
                    return await ctx.reply(f"❌ Bạn chỉ có **{pts} point**, không đủ cược **{bet} point**!")

        w = random.choice(WORDS_VI)
        noi_tu_sessions[cid] = {
            "word":             w,
            "used":             {w},
            "lock":             asyncio.Lock(),
            "last_player":      None,
            "player_last_time": {},
            "dedicated":        (cid == noitu_cid and noitu_cid != 0),
            "bet":              bet,
        }

        bet_info = f"\n💰 Cược: **{bet} point** — thắng nhận **+{int(bet*WIN_RATE)}pt**, thua mất **-{bet}pt**" if bet > 0 else ""
        e = discord.Embed(
            title="🔤 Nối Từ bắt đầu!",
            color=discord.Color.blue(),
            description=(
                f"Từ đầu tiên: **{w}**\n"
                f"Hãy nối từ bắt đầu bằng **`{last_syl(w)}`**!\n"
                f"💬 Nhắn thẳng từ vào kênh, không cần prefix!"
                f"{bet_info}"
            )
        )
        e.set_footer(text=".stop để dừng game")
        await ctx.send(embed=e)

    @app_commands.command(name="start", description="🔤 Bắt đầu game Nối Từ")
    @app_commands.describe(cuoc="Số point muốn cược (không bắt buộc)")
    async def start_slash(self, interaction, cuoc: int = 0):
        ctx = await commands.Context.from_interaction(interaction)
        await self.noitu_start(ctx, str(cuoc) if cuoc else None)

    # ════════════════════════════════════════
    # .stop
    # ════════════════════════════════════════
    @commands.command(name="stop")
    async def noitu_stop(self, ctx):
        """🔤 Dừng game Nối Từ."""
        cid = ctx.channel.id
        if cid not in noi_tu_sessions:
            return await ctx.reply("❌ Không có game nào đang chạy.")
        del noi_tu_sessions[cid]
        await ctx.reply("🛑 Game Nối Từ đã dừng!")

    @app_commands.command(name="stop", description="🔤 Dừng game Nối Từ")
    async def stop_slash(self, interaction):
        await self.noitu_stop(await commands.Context.from_interaction(interaction))

    # ════════════════════════════════════════
    # 🎲 BẦU CUA
    # ════════════════════════════════════════
    @commands.command(name="baucua", aliases=["bc"])
    async def bau_cua(self, ctx, bet_or_choice: str = None, bet_str: str = None):
        """
        🎲 Bầu Cua — .baucua <mặt> [point_cược]
        VD: .baucua bầu 10
        """
        if not bet_or_choice:
            icons = "  ".join(f"{v}`{k}`" for k, v in BAU_CUA_ICONS.items())
            return await ctx.reply(
                f"🎲 **Bầu Cua Tôm Cá**\n{icons}\n"
                f"Dùng: `.baucua <mặt>` hoặc `.baucua <mặt> <point_cược>`\n"
                f"VD: `.baucua bầu 10` — cược 10 point"
            )

        bet_target = BAU_CUA_ALIAS.get(bet_or_choice.lower().strip(), bet_or_choice.lower().strip())
        if bet_target not in BAU_CUA_KEYS:
            return await ctx.reply(f"❌ Chọn: {', '.join(BAU_CUA_KEYS)}")

        # Parse cược
        bet = 0
        if bet_str:
            bet = parse_bet(bet_str) or 0
            if bet > 0:
                pts = get_user_points(ctx.author.id)
                if pts < bet:
                    return await ctx.reply(f"❌ Bạn chỉ có **{pts} point**, không đủ cược **{bet} point**!")

        dice = [random.choice(BAU_CUA_KEYS) for _ in range(3)]
        hits = dice.count(bet_target)
        icon = BAU_CUA_ICONS[bet_target]

        win = hits > 0
        msgs = {
            0: (f"❌ Thua! Không có **{icon} {bet_target}**.", discord.Color.red()),
            1: (f"✅ Thắng x1! **{icon} {bet_target}** 1 lần.",  discord.Color.green()),
            2: (f"🎉 Thắng x2! **{icon} {bet_target}** 2 lần!", discord.Color.gold()),
            3: (f"🏆 JACKPOT x3! **{icon} {bet_target}** cả 3!", discord.Color.orange()),
        }
        out, color = msgs[hits]

        # Xử lý point cược
        bet_result = ""
        if bet > 0:
            if win:
                # Bầu cua: thắng nhân hits (x1/x2/x3) × WIN_RATE
                gain = int(bet * hits * WIN_RATE)
                add_user_points(ctx.author.id, +gain, f"baucua_win hits={hits} bet={bet}")
                record_win(ctx.author.id, "baucua")
                new_pts = get_user_points(ctx.author.id)
                bet_result = f"\n💎 **+{gain} point** | Tổng: **{new_pts} pt**"
            else:
                add_user_points(ctx.author.id, -bet, f"baucua_lose bet={bet}")
                new_pts = get_user_points(ctx.author.id)
                bet_result = f"\n💸 **-{bet} point** | Tổng: **{new_pts} pt**"
        elif win:
            record_win(ctx.author.id, "baucua")

        e = discord.Embed(title="🎲 Bầu Cua Tôm Cá", color=color)
        e.add_field(name="Bạn chọn",    value=f"{icon} **{bet_target}**",                        inline=True)
        if bet > 0:
            e.add_field(name="Cược",    value=f"**{bet} point**",                                inline=True)
        e.add_field(name="Kết quả lắc", value="  ".join(BAU_CUA_ICONS[d] for d in dice),         inline=False)
        e.add_field(name="Kết quả",     value=out + bet_result,                                   inline=False)
        e.set_footer(text=ctx.author.display_name)
        await ctx.reply(embed=e)

    @app_commands.command(name="baucua", description="🎲 Chơi Bầu Cua Tôm Cá")
    @app_commands.describe(chon="bầu, cua, cá, gà, tôm, nai", cuoc="Số point muốn cược")
    async def bau_cua_slash(self, interaction, chon: str, cuoc: int = 0):
        ctx = await commands.Context.from_interaction(interaction)
        await self.bau_cua(ctx, chon, str(cuoc) if cuoc else None)

    # ════════════════════════════════════════
    # ✂️ BÚA KÉO BAO
    # ════════════════════════════════════════
    @commands.command(name="bkb", aliases=["bukebao", "rps"])
    async def bkb(self, ctx, choice: str = None, bet_str: str = None):
        """
        ✂️ Búa Kéo Bao — .bkb <búa|kéo|bao> [point_cược]
        VD: .bkb búa 10
        """
        if not choice:
            opts = "  ".join(f"{v}`{k}`" for k, v in BKB_CHOICES.items())
            return await ctx.reply(
                f"✂️ **Búa Kéo Bao**\n{opts}\n"
                f"Dùng: `.bkb <lựa chọn>` hoặc `.bkb <lựa chọn> <point_cược>`\n"
                f"VD: `.bkb búa 10`"
            )

        choice = BKB_ALIAS.get(choice.lower().strip(), choice.lower().strip())
        if choice not in BKB_CHOICES:
            return await ctx.reply("❌ Chọn: `búa`, `kéo`, `bao`")

        # Parse cược
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

        if draw:   result, color = "🤝 **Hòa!**",        discord.Color.yellow()
        elif win:  result, color = "🏆 **Bạn thắng!**",  discord.Color.green()
        else:      result, color = "💀 **Bot thắng!**",  discord.Color.red()

        # Xử lý point cược
        bet_result = ""
        if bet > 0 and not draw:
            if win:
                gain = int(bet * WIN_RATE)
                add_user_points(ctx.author.id, +gain, f"bkb_win bet={bet}")
                record_win(ctx.author.id, "bkb")
                new_pts = get_user_points(ctx.author.id)
                bet_result = f"\n💎 **+{gain} point** | Tổng: **{new_pts} pt**"
            else:
                add_user_points(ctx.author.id, -bet, f"bkb_lose bet={bet}")
                new_pts = get_user_points(ctx.author.id)
                bet_result = f"\n💸 **-{bet} point** | Tổng: **{new_pts} pt**"
        elif win and bet == 0:
            record_win(ctx.author.id, "bkb")

        e = discord.Embed(title="✂️ Búa Kéo Bao", color=color)
        e.add_field(name=ctx.author.display_name, value=f"{BKB_CHOICES[choice]} **{choice}**",    inline=True)
        e.add_field(name="vs",                    value="⚔️",                                      inline=True)
        e.add_field(name="Bot Rudeus",            value=f"{BKB_CHOICES[bot_c]} **{bot_c}**",       inline=True)
        e.add_field(name="Kết quả",               value=result + bet_result,                       inline=False)
        if bet > 0:
            e.set_footer(text=f"Cược: {bet} pt | Thắng +{int(bet*WIN_RATE)}pt | Thua -{bet}pt")
        await ctx.reply(embed=e)

    @app_commands.command(name="bkb", description="✂️ Búa Kéo Bao với bot")
    @app_commands.describe(chon="búa, kéo hoặc bao", cuoc="Số point muốn cược")
    async def bkb_slash(self, interaction, chon: str, cuoc: int = 0):
        ctx = await commands.Context.from_interaction(interaction)
        await self.bkb(ctx, chon, str(cuoc) if cuoc else None)

    # ════════════════════════════════════════
    # 👑 VUA TIẾNG VIỆT
    # ════════════════════════════════════════
    @commands.command(name="vtviet", aliases=["vtv", "vuatv"])
    async def vtv(self, ctx, action: str = None, bet_str: str = None):
        """
        👑 Vua Tiếng Việt
        .vtviet [point_cược] — Lấy câu hỏi
        .vtviet A/B/C/D — Trả lời
        """
        cid = ctx.channel.id

        # Trả lời câu hỏi
        if action and action.upper() in ["A", "B", "C", "D"]:
            if cid not in vtv_sessions:
                return await ctx.reply("❌ Không có câu hỏi! Dùng `.vtviet`.")
            s = vtv_sessions[cid]
            if time.time() > s["expire_time"]:
                del vtv_sessions[cid]
                return await ctx.reply("⏰ Câu hỏi đã hết hạn!")
            uid = ctx.author.id
            if uid in s["answered"]:
                return await ctx.reply("⚠️ Bạn đã trả lời rồi!")
            s["answered"].add(uid)
            ans, correct = action.upper(), s["question"]["ans"]
            correct_ans  = ans == correct

            bet_result = ""
            if correct_ans:
                record_win(uid, "vtv")
                bet = s.get("bet", 0)
                if bet > 0:
                    gain = int(bet * WIN_RATE)
                    add_user_points(uid, +gain, f"vtv_win bet={bet}")
                    new_pts = get_user_points(uid)
                    bet_result = f"\n💎 **+{gain} point** | Tổng: **{new_pts} pt**"
                del vtv_sessions[cid]
                e = discord.Embed(title="✅ Chính xác!",
                    description=f"**{ctx.author.display_name}** đúng! Đáp án: **{correct}**{bet_result}",
                    color=discord.Color.green())
            else:
                bet = s.get("bet", 0)
                if bet > 0:
                    add_user_points(uid, -bet, f"vtv_lose bet={bet}")
                    new_pts = get_user_points(uid)
                    bet_result = f"\n💸 **-{bet} point** | Tổng: **{new_pts} pt**"
                e = discord.Embed(title="❌ Sai rồi!",
                    description=f"**{ctx.author.display_name}** chọn **{ans}**, đúng là **{correct}**.\nNgười khác vẫn có thể trả lời!{bet_result}",
                    color=discord.Color.red())
            return await ctx.send(embed=e)

        # Lấy câu hỏi mới
        if cid in vtv_sessions:
            if time.time() > vtv_sessions[cid]["expire_time"]:
                del vtv_sessions[cid]
            else:
                return await ctx.reply("⚠️ Đang có câu chưa ai đúng! Dùng `.vtviet A/B/C/D`.")

        # Parse cược (action có thể là số point)
        bet = 0
        if action and action.isdigit():
            bet = int(action)
            if bet > 0:
                pts = get_user_points(ctx.author.id)
                if pts < bet:
                    return await ctx.reply(f"❌ Bạn chỉ có **{pts} point**, không đủ cược **{bet} point**!")

        q      = random.choice(VTV_QUESTIONS)
        expire = time.time() + 60
        vtv_sessions[cid] = {"question": q, "answered": set(), "expire_time": expire, "bet": bet}

        bet_info = f"\n💰 Cược: **{bet} point** — trả lời đúng nhận **+{int(bet*WIN_RATE)}pt**, sai mất **-{bet}pt**" if bet > 0 else ""
        e = discord.Embed(title="👑 Vua Tiếng Việt",
            description=f"**{q['q']}**\n\n" + "\n".join(q["choices"]) + bet_info,
            color=discord.Color.purple())
        e.set_footer(text="Trả lời .vtviet A/B/C/D | Hết hạn sau 60 giây")
        await ctx.send(embed=e)

        await asyncio.sleep(60)
        if cid in vtv_sessions and vtv_sessions[cid]["expire_time"] == expire:
            del vtv_sessions[cid]
            try: await ctx.send(f"⏰ Hết giờ! Đáp án đúng là **{q['ans']}**.")
            except: pass

    @app_commands.command(name="vtviet", description="👑 Vua Tiếng Việt")
    @app_commands.describe(tra_loi="A/B/C/D để trả lời, hoặc số point để cược khi lấy câu hỏi")
    async def vtv_slash(self, interaction, tra_loi: str = None):
        await self.vtv(await commands.Context.from_interaction(interaction), action=tra_loi)

    # ════════════════════════════════════════
    # 🏆 BẢNG XẾP HẠNG
    # ════════════════════════════════════════
    @commands.command(name="rank", aliases=["xephang", "leaderboard"])
    async def rank_cmd(self, ctx, game: str = "total"):
        """
        🏆 Bảng xếp hạng minigame
        .rank           — Tổng tất cả game
        .rank baucua    — Bầu Cua
        .rank bkb       — Búa Kéo Bao
        .rank noitu     — Nối Từ
        .rank vtv       — Vua Tiếng Việt
        """
        game_map = {
            "baucua": "baucua", "bc": "baucua",
            "bkb": "bkb", "bukebao": "bkb", "rps": "bkb",
            "noitu": "noitu", "nt": "noitu",
            "vtv": "vtv", "vtviet": "vtv", "vuatv": "vtv",
            "total": "total", "all": "total",
        }
        game_key = game_map.get(game.lower(), "total")
        game_labels = {
            "baucua": "🎲 Bầu Cua",
            "bkb":    "✂️ Búa Kéo Bao",
            "noitu":  "🔤 Nối Từ",
            "vtv":    "👑 Vua Tiếng Việt",
            "total":  "🎮 Tất cả game",
        }
        label = game_labels.get(game_key, "🎮 Tất cả game")
        rows  = get_leaderboard(game_key, top=10)

        if not rows:
            return await ctx.reply(f"📊 Chưa có dữ liệu thắng cho **{label}**.")

        medals = ["🥇","🥈","🥉"] + ["🏅"] * 7
        lines  = []
        for i, (uid, wins) in enumerate(rows):
            member = ctx.guild.get_member(uid)
            name   = member.display_name if member else f"User {uid}"
            lines.append(f"{medals[i]} **{name}** — **{wins}** lần thắng")

        e = discord.Embed(
            title=f"🏆 Bảng Xếp Hạng — {label}",
            description="\n".join(lines),
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        e.set_footer(text="Dùng .rank <game> để xem từng game")
        await ctx.reply(embed=e)

    @app_commands.command(name="rank", description="🏆 Bảng xếp hạng minigame")
    @app_commands.describe(game="total / baucua / bkb / noitu / vtv")
    async def rank_slash(self, interaction, game: str = "total"):
        await self.rank_cmd(await commands.Context.from_interaction(interaction), game)

    # ════════════════════════════════════════
    # 📊 THỐNG KÊ CÁ NHÂN
    # ════════════════════════════════════════
    @commands.command(name="mgstats", aliases=["gamestats", "mystats"])
    async def mgstats_cmd(self, ctx, member: discord.Member = None):
        """📊 Xem thống kê minigame của bản thân hoặc người khác."""
        target = member or ctx.author
        stats  = get_mg_stats().get(str(target.id), {})
        pts    = get_user_points(target.id)

        e = discord.Embed(
            title=f"📊 Thống Kê Minigame — {target.display_name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        e.set_thumbnail(url=target.display_avatar.url)
        e.add_field(name="🎲 Bầu Cua",         value=f"**{stats.get('baucua',0)}** lần thắng", inline=True)
        e.add_field(name="✂️ Búa Kéo Bao",     value=f"**{stats.get('bkb',0)}** lần thắng",   inline=True)
        e.add_field(name="🔤 Nối Từ",           value=f"**{stats.get('noitu',0)}** lần thắng", inline=True)
        e.add_field(name="👑 Vua Tiếng Việt",   value=f"**{stats.get('vtv',0)}** lần thắng",   inline=True)
        e.add_field(name="🏆 Tổng thắng",       value=f"**{stats.get('total',0)}** lần",        inline=True)
        e.add_field(name="💎 Point hiện có",    value=f"**{pts:,} pt**",                        inline=True)
        await ctx.reply(embed=e)

    @app_commands.command(name="mgstats", description="📊 Thống kê minigame cá nhân")
    @app_commands.describe(thanh_vien="Để trống = xem của bạn")
    async def mgstats_slash(self, interaction, thanh_vien: discord.Member = None):
        ctx = await commands.Context.from_interaction(interaction)
        await self.mgstats_cmd(ctx, thanh_vien)

    # ════════════════════════════════════════
    # ℹ️ HELP
    # ════════════════════════════════════════
    @commands.command(name="minigame", aliases=["mg", "games"])
    async def mg_help(self, ctx):
        noitu_cid = get_noitu_channel()
        nt_kenh   = f"📌 Kênh: <#{noitu_cid}>" if noitu_cid else "💡 Chưa cài — `.setnoitu #kênh`"
        e = discord.Embed(title="🎮 Minigame — Hướng Dẫn", color=discord.Color.blurple())
        e.add_field(
            name="🔤 Nối Từ",
            value=(
                f"`.start` — Bắt đầu | `.stop` — Dừng\n"
                f"`.start <point>` — Bắt đầu kèm cược\n"
                f"{nt_kenh}\n"
                f"Sau start: nhắn từ thẳng vào kênh!"
            ),
            inline=False
        )
        e.add_field(
            name="🎲 Bầu Cua Tôm Cá",
            value=(
                "`.baucua <mặt>` — Chơi không cược\n"
                "`.baucua <mặt> <point>` — Cược point\n"
                "Thắng x1→ **+0.9pt/pt** | x2→ **+1.8pt/pt** | x3→ **+2.7pt/pt**"
            ),
            inline=False
        )
        e.add_field(
            name="✂️ Búa Kéo Bao",
            value=(
                "`.bkb <búa|kéo|bao>` — Chơi không cược\n"
                "`.bkb <lựa chọn> <point>` — Cược point\n"
                "Thắng: **+0.9pt/pt cược** | Thua: **-1pt/pt cược**"
            ),
            inline=False
        )
        e.add_field(
            name="👑 Vua Tiếng Việt",
            value=(
                "`.vtviet` — Câu hỏi không cược\n"
                "`.vtviet <point>` — Câu hỏi kèm cược\n"
                "`.vtviet A/B/C/D` — Trả lời (60s)\n"
                "Đúng: **+0.9pt/pt cược** | Sai: **-1pt/pt cược**"
            ),
            inline=False
        )
        e.add_field(
            name="🏆 Xếp hạng & Thống kê",
            value=(
                "`.rank` — BXH tổng | `.rank <game>` — BXH từng game\n"
                "`.mgstats` — Thống kê cá nhân\n"
                "Game: `baucua` | `bkb` | `noitu` | `vtv`"
            ),
            inline=False
        )
        e.set_footer(text="Tất cả đều có slash command /tên tương ứng")
        await ctx.reply(embed=e)

    def cog_unload(self):
        noi_tu_sessions.clear()
        vtv_sessions.clear()


async def setup(bot):
    await bot.add_cog(Minigame(bot))
