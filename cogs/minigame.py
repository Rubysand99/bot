# cogs/minigame.py
# Minigame cog: Bầu Cua, Nối Từ, Vua Tiếng Việt, Búa Kéo Bao
# Version: 3.6.0

import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import json
import os

# ─── Dữ liệu ───────────────────────────────────────────────
BAU_CUA_ICONS = {
    "bầu": "🎃",
    "cua": "🦀",
    "cá": "🐟",
    "gà":  "🐓",
    "tôm": "🦐",
    "nai": "🦌",
}
BAU_CUA_KEYS = list(BAU_CUA_ICONS.keys())

BKB_CHOICES = {"búa": "🔨", "kéo": "✂️", "bao": "📄"}
BKB_WIN = {"búa": "kéo", "kéo": "bao", "bao": "búa"}   # key thắng value

# Từ điển nối từ — dùng file nếu có, fallback sang list nhỏ
WORD_LIST_PATH = os.path.join(os.path.dirname(__file__), "../data/words_vi.txt")
FALLBACK_WORDS = [
    "học sinh", "sinh viên", "viên chức", "chức năng", "năng lực",
    "lực lượng", "lượng giá", "giá trị", "trị giá", "giá cả",
    "cả nhà", "nhà trường", "trường học", "học hành", "hành động",
    "động lực", "lực sĩ", "sĩ quan", "quan tâm", "tâm hồn",
    "hồn nhiên", "nhiên liệu", "liệu pháp", "pháp luật", "luật pháp",
    "pháp lý", "lý luận", "luận văn", "văn hóa", "hóa học",
    "học thuật", "thuật toán", "toán học", "học bổng", "bổng lộc",
    "lộc trời", "trời đất", "đất nước", "nước nhà", "nhà nước",
    "nước mắt", "mắt xích", "xích lô", "lô đề", "đề thi",
    "thi cử", "cử nhân", "nhân vật", "vật lý", "lý thuyết",
    "thuyết phục", "phục vụ", "vụ án", "án lệ", "lệ phí",
    "phí tổn", "tổn thất", "thất bại", "bại trận", "trận đấu",
    "đấu tranh", "tranh luận", "luận điểm", "điểm số", "số lượng",
]

def load_words():
    try:
        with open(WORD_LIST_PATH, encoding="utf-8") as f:
            return [w.strip().lower() for w in f if w.strip()]
    except Exception:
        return FALLBACK_WORDS

WORDS_VI = load_words()

# Câu hỏi Vua Tiếng Việt
VTV_QUESTIONS = [
    {"q": "Từ nào sau đây là từ láy?", "choices": ["A. học sinh", "B. lung linh", "C. đất nước", "D. bàn ghế"], "ans": "B"},
    {"q": "\"Cô ấy có đôi mắt ___ như sao.\" Điền từ thích hợp:", "choices": ["A. sáng", "B. long lanh", "C. đen", "D. to"], "ans": "B"},
    {"q": "Câu nào sau đây có dùng biện pháp tu từ nhân hóa?", "choices": ["A. Mặt trăng tròn như cái đĩa", "B. Gió ơi gió hỡi, gió về đâu", "C. Con sông dài như dải lụa", "D. Hoa nở rộ khắp vườn"], "ans": "B"},
    {"q": "Từ \"kiên nhẫn\" thuộc loại từ gì?", "choices": ["A. Danh từ", "B. Động từ", "C. Tính từ", "D. Trạng từ"], "ans": "C"},
    {"q": "Thành ngữ \"Nước chảy đá mòn\" có nghĩa là gì?", "choices": ["A. Đá rất cứng", "B. Kiên trì ắt thành công", "C. Nước rất mạnh", "D. Không thể thay đổi"], "ans": "B"},
    {"q": "Câu \"Trẻ em như búp trên cành\" sử dụng biện pháp tu từ nào?", "choices": ["A. Nhân hóa", "B. Ẩn dụ", "C. So sánh", "D. Hoán dụ"], "ans": "C"},
    {"q": "Từ nào KHÔNG phải từ ghép?", "choices": ["A. học hành", "B. xinh xắn", "C. bàn tay", "D. cây cối"], "ans": "B"},
    {"q": "\"Bán anh em xa, mua láng giềng gần\" — câu này thuộc thể loại gì?", "choices": ["A. Ca dao", "B. Tục ngữ", "C. Thành ngữ", "D. Thơ"], "ans": "B"},
    {"q": "Từ \"xanh\" trong câu \"Trời xanh\" và \"Xanh lá\" — quan hệ nghĩa là gì?", "choices": ["A. Từ đồng âm", "B. Từ nhiều nghĩa", "C. Từ trái nghĩa", "D. Từ đồng nghĩa"], "ans": "B"},
    {"q": "Chủ ngữ trong câu \"Mưa rơi lộp độp trên mái nhà\" là gì?", "choices": ["A. Mưa", "B. Mái nhà", "C. Lộp độp", "D. Rơi"], "ans": "A"},
    {"q": "Từ nào sau đây viết đúng chính tả?", "choices": ["A. giản dị", "B. dản dị", "C. giản rị", "D. zản dị"], "ans": "A"},
    {"q": "\"Đầu xuôi đuôi lọt\" có nghĩa là gì?", "choices": ["A. Bơi giỏi", "B. Bắt đầu tốt thì kết thúc thuận lợi", "C. Làm việc nhanh", "D. Đầu to đuôi nhỏ"], "ans": "B"},
    {"q": "Từ nào là từ Hán Việt?", "choices": ["A. nhà cửa", "B. gia đình", "C. bàn ghế", "D. cơm nước"], "ans": "B"},
    {"q": "Câu \"Hoa hồng nở rực rỡ\" — vị ngữ là gì?", "choices": ["A. Hoa hồng", "B. nở rực rỡ", "C. rực rỡ", "D. nở"], "ans": "B"},
    {"q": "\"Một con ngựa đau, cả tàu bỏ cỏ\" nói lên điều gì?", "choices": ["A. Ngựa ăn ít", "B. Tinh thần đoàn kết, đồng cảm", "C. Nuôi ngựa tốn kém", "D. Ngựa yếu thì bỏ"], "ans": "B"},
]

# ─── State quản lý game đang chạy ────────────────────────────
noi_tu_sessions = {}   # channel_id: {word, used, players, timeout_task}
vtv_sessions = {}      # channel_id: {question, scores, answered}

# ─── Helpers ─────────────────────────────────────────────────

def get_last_syllable(phrase: str) -> str:
    """Lấy âm tiết cuối của cụm từ."""
    return phrase.strip().split()[-1].lower()

def get_first_syllable(phrase: str) -> str:
    return phrase.strip().split()[0].lower()

def find_next_word(last_syl: str, used: set) -> str | None:
    """Tìm từ bắt đầu bằng last_syl chưa dùng."""
    candidates = [w for w in WORDS_VI if get_first_syllable(w) == last_syl and w not in used]
    return random.choice(candidates) if candidates else None

# ─── Cog ────────────────────────────────────────────────────

class Minigame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ════════════════════════════════════════════
    # 🎲 BẦU CUA
    # ════════════════════════════════════════════

    @commands.command(name="baucua", aliases=["bc"])
    async def bau_cua(self, ctx, bet_target: str = None):
        """
        🎲 Chơi Bầu Cua Tôm Cá
        Cú pháp: `.baucua <bầu|cua|cá|gà|tôm|nai>`
        """
        if bet_target is None:
            icons = "  ".join(f"{v}`{k}`" for k, v in BAU_CUA_ICONS.items())
            await ctx.reply(
                f"🎲 **Bầu Cua Tôm Cá**\nChọn một ô để cược:\n{icons}\n"
                f"Dùng: `.baucua <tên>` — VD: `.baucua bầu`"
            )
            return

        bet_target = bet_target.lower().strip()
        if bet_target not in BAU_CUA_KEYS:
            await ctx.reply(f"❌ Không có ô **{bet_target}**! Chọn: {', '.join(BAU_CUA_KEYS)}")
            return

        # Lắc 3 xúc xắc
        dice = [random.choice(BAU_CUA_KEYS) for _ in range(3)]
        result_line = "  ".join(BAU_CUA_ICONS[d] for d in dice)
        hits = dice.count(bet_target)

        # Build message
        icon = BAU_CUA_ICONS[bet_target]
        if hits == 0:
            outcome = f"❌ Thua! Không có **{icon} {bet_target}** nào."
        elif hits == 1:
            outcome = f"✅ Thắng x1! **{icon} {bet_target}** xuất hiện 1 lần."
        elif hits == 2:
            outcome = f"🎉 Thắng x2! **{icon} {bet_target}** xuất hiện 2 lần!"
        else:
            outcome = f"🏆 THẮNG x3! **{icon} {bet_target}** cả 3 mặt! Jackpot!"

        embed = discord.Embed(title="🎲 Bầu Cua Tôm Cá", color=discord.Color.gold())
        embed.add_field(name="Bạn chọn", value=f"{icon} **{bet_target}**", inline=True)
        embed.add_field(name="Kết quả lắc", value=result_line, inline=False)
        embed.add_field(name="Kết quả", value=outcome, inline=False)
        embed.set_footer(text=f"Người chơi: {ctx.author.display_name}")
        await ctx.reply(embed=embed)

    @app_commands.command(name="baucua", description="🎲 Chơi Bầu Cua Tôm Cá")
    @app_commands.describe(chon="Chọn ô cược: bầu, cua, cá, gà, tôm, nai")
    async def bau_cua_slash(self, interaction: discord.Interaction, chon: str):
        ctx = await commands.Context.from_interaction(interaction)
        await self.bau_cua(ctx, chon)

    # ════════════════════════════════════════════
    # ✂️ BÚA KÉO BAO
    # ════════════════════════════════════════════

    @commands.command(name="bkb", aliases=["bukebao", "rps"])
    async def bua_keo_bao(self, ctx, choice: str = None):
        """
        ✂️ Chơi Búa Kéo Bao với bot
        Cú pháp: `.bkb <búa|kéo|bao>`
        """
        if choice is None:
            opts = "  ".join(f"{v}`{k}`" for k, v in BKB_CHOICES.items())
            await ctx.reply(f"✂️ **Búa Kéo Bao**\n{opts}\nDùng: `.bkb <búa|kéo|bao>`")
            return

        choice = choice.lower().strip()
        # alias
        alias_map = {"bua": "búa", "keo": "kéo", "bao": "bao"}
        choice = alias_map.get(choice, choice)

        if choice not in BKB_CHOICES:
            await ctx.reply(f"❌ Chọn một trong: `búa`, `kéo`, `bao`")
            return

        bot_choice = random.choice(list(BKB_CHOICES.keys()))

        user_icon = BKB_CHOICES[choice]
        bot_icon  = BKB_CHOICES[bot_choice]

        if choice == bot_choice:
            result = "🤝 **Hòa!**"
            color = discord.Color.yellow()
        elif BKB_WIN[choice] == bot_choice:
            result = "🏆 **Bạn thắng!**"
            color = discord.Color.green()
        else:
            result = "💀 **Bot thắng!**"
            color = discord.Color.red()

        embed = discord.Embed(title="✂️ Búa Kéo Bao", color=color)
        embed.add_field(name=f"{ctx.author.display_name}", value=f"{user_icon} **{choice}**", inline=True)
        embed.add_field(name="vs", value="⚔️", inline=True)
        embed.add_field(name="Bot Rudeus", value=f"{bot_icon} **{bot_choice}**", inline=True)
        embed.add_field(name="Kết quả", value=result, inline=False)
        await ctx.reply(embed=embed)

    @app_commands.command(name="bkb", description="✂️ Chơi Búa Kéo Bao với bot")
    @app_commands.describe(chon="Chọn: búa, kéo hoặc bao")
    async def bkb_slash(self, interaction: discord.Interaction, chon: str):
        ctx = await commands.Context.from_interaction(interaction)
        await self.bua_keo_bao(ctx, chon)

    # ════════════════════════════════════════════
    # 🔤 NỐI TỪ
    # ════════════════════════════════════════════

    @commands.command(name="noitu", aliases=["nt"])
    async def noi_tu(self, ctx, *, action: str = None):
        """
        🔤 Trò chơi Nối Từ — nối từ tiếng Việt theo âm tiết cuối
        `.noitu start` — Bắt đầu game
        `.noitu <từ>` — Nối từ
        `.noitu stop` — Dừng game
        """
        cid = ctx.channel.id

        if action is None:
            await ctx.reply(
                "🔤 **Nối Từ**\n"
                "`.noitu start` — Bắt đầu\n"
                "`.noitu <từ>` — Nối từ (VD: `.noitu học sinh`)\n"
                "`.noitu stop` — Dừng game"
            )
            return

        action = action.strip().lower()

        # ── START ──
        if action == "start":
            if cid in noi_tu_sessions:
                await ctx.reply("⚠️ Đang có game Nối Từ trong kênh này rồi! Dùng `.noitu stop` để dừng.")
                return
            start_word = random.choice(WORDS_VI)
            noi_tu_sessions[cid] = {
                "word": start_word,
                "used": {start_word},
                "last_player": None,
            }
            last_syl = get_last_syllable(start_word)
            embed = discord.Embed(
                title="🔤 Nối Từ bắt đầu!",
                description=f"Từ đầu tiên: **{start_word}**\nHãy nối từ bắt đầu bằng **`{last_syl}`**!",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Dùng .noitu <từ> để nối | .noitu stop để dừng")
            await ctx.send(embed=embed)
            return

        # ── STOP ──
        if action == "stop":
            if cid not in noi_tu_sessions:
                await ctx.reply("❌ Không có game Nối Từ nào đang chạy.")
                return
            del noi_tu_sessions[cid]
            await ctx.reply("🛑 Game Nối Từ đã dừng!")
            return

        # ── PLAY ──
        if cid not in noi_tu_sessions:
            await ctx.reply("❌ Chưa có game! Dùng `.noitu start` để bắt đầu.")
            return

        session = noi_tu_sessions[cid]
        word = action  # action là từ người chơi nhập
        word = word.strip().lower()

        # Kiểm tra đã dùng chưa
        if word in session["used"]:
            await ctx.reply(f"❌ Từ **{word}** đã được dùng rồi!")
            return

        # Kiểm tra tồn tại trong từ điển
        if word not in WORDS_VI:
            await ctx.reply(f"❌ Từ **{word}** không có trong từ điển!")
            return

        # Kiểm tra khớp âm tiết đầu
        required = get_last_syllable(session["word"])
        first    = get_first_syllable(word)
        if first != required:
            await ctx.reply(f"❌ Phải nối từ bắt đầu bằng **`{required}`**, bạn nhập **`{first}`**!")
            return

        # Hợp lệ
        session["used"].add(word)
        session["word"] = word
        session["last_player"] = ctx.author.id
        next_syl = get_last_syllable(word)

        # Bot tự tìm từ tiếp theo
        bot_word = find_next_word(next_syl, session["used"])
        if bot_word:
            session["used"].add(bot_word)
            session["word"] = bot_word
            bot_next = get_last_syllable(bot_word)
            embed = discord.Embed(color=discord.Color.green())
            embed.add_field(name=f"✅ {ctx.author.display_name}", value=f"**{word}**", inline=True)
            embed.add_field(name="🤖 Bot Rudeus", value=f"**{bot_word}**", inline=True)
            embed.set_footer(text=f"Hãy nối từ bắt đầu bằng '{bot_next}'")
            await ctx.send(embed=embed)
        else:
            # Bot thua
            del noi_tu_sessions[cid]
            await ctx.reply(
                f"✅ **{ctx.author.display_name}** nối: **{word}**\n"
                f"🤖 Bot không tìm được từ bắt đầu bằng **`{next_syl}`**!\n"
                f"🏆 **{ctx.author.display_name} THẮNG!**"
            )

    @app_commands.command(name="noitu", description="🔤 Chơi Nối Từ tiếng Việt")
    @app_commands.describe(hanh_dong="start / stop / <từ cần nối>")
    async def noi_tu_slash(self, interaction: discord.Interaction, hanh_dong: str):
        ctx = await commands.Context.from_interaction(interaction)
        await self.noi_tu(ctx, action=hanh_dong)

    # ════════════════════════════════════════════
    # 👑 VUA TIẾNG VIỆT
    # ════════════════════════════════════════════

    @commands.command(name="vtviet", aliases=["vtv", "vuatv"])
    async def vua_tieng_viet(self, ctx, action: str = None):
        """
        👑 Vua Tiếng Việt — Trắc nghiệm kiến thức tiếng Việt
        `.vtviet` — Nhận câu hỏi ngẫu nhiên
        `.vtviet <A|B|C|D>` — Trả lời câu hỏi đang mở
        """
        cid = ctx.channel.id

        # Trả lời câu hỏi đang mở
        if action and action.upper() in ["A", "B", "C", "D"]:
            if cid not in vtv_sessions:
                await ctx.reply("❌ Không có câu hỏi nào đang mở! Dùng `.vtviet` để bắt đầu.")
                return
            session = vtv_sessions[cid]
            uid = ctx.author.id
            if uid in session["answered"]:
                await ctx.reply("⚠️ Bạn đã trả lời câu này rồi!")
                return

            session["answered"].add(uid)
            ans = action.upper()
            correct = session["question"]["ans"]

            if ans == correct:
                session["scores"][uid] = session["scores"].get(uid, 0) + 1
                score = session["scores"][uid]
                del vtv_sessions[cid]
                embed = discord.Embed(
                    title="✅ Chính xác!",
                    description=f"**{ctx.author.display_name}** trả lời đúng!\nĐáp án: **{correct}**\nĐiểm: **{score}** ✨",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Sai rồi!",
                    description=f"**{ctx.author.display_name}** chọn **{ans}**, đáp án đúng là **{correct}**.",
                    color=discord.Color.red()
                )
                # Vẫn giữ câu hỏi cho người khác
                await ctx.send(embed=embed)
            return

        # Tạo câu hỏi mới
        if cid in vtv_sessions:
            await ctx.reply("⚠️ Đang có câu hỏi chưa ai trả lời đúng! Hãy trả lời câu hiện tại trước.")
            return

        q = random.choice(VTV_QUESTIONS)
        vtv_sessions[cid] = {
            "question": q,
            "scores": {},
            "answered": set(),
        }

        choices_str = "\n".join(q["choices"])
        embed = discord.Embed(
            title="👑 Vua Tiếng Việt",
            description=f"**{q['q']}**\n\n{choices_str}",
            color=discord.Color.purple()
        )
        embed.set_footer(text="Trả lời bằng .vtviet A / B / C / D | Câu hỏi tự hết sau 60 giây")
        msg = await ctx.send(embed=embed)

        # Timeout 60s
        await asyncio.sleep(60)
        if cid in vtv_sessions and vtv_sessions[cid]["question"] is q:
            del vtv_sessions[cid]
            try:
                await msg.reply(f"⏰ Hết giờ! Đáp án đúng là **{q['ans']}**.")
            except Exception:
                pass

    @app_commands.command(name="vtviet", description="👑 Vua Tiếng Việt — câu hỏi trắc nghiệm")
    @app_commands.describe(tra_loi="Bỏ trống để lấy câu hỏi mới, hoặc nhập A/B/C/D để trả lời")
    async def vtv_slash(self, interaction: discord.Interaction, tra_loi: str = None):
        ctx = await commands.Context.from_interaction(interaction)
        await self.vua_tieng_viet(ctx, action=tra_loi)

    # ════════════════════════════════════════════
    # ℹ️ HELP MINIGAME
    # ════════════════════════════════════════════

    @commands.command(name="minigame", aliases=["mg", "games"])
    async def minigame_help(self, ctx):
        """Xem danh sách minigame"""
        embed = discord.Embed(
            title="🎮 Danh sách Minigame",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="🎲 Bầu Cua Tôm Cá",
            value="`.baucua <bầu|cua|cá|gà|tôm|nai>`\nLắc 3 xúc xắc, đoán mặt xuất hiện",
            inline=False
        )
        embed.add_field(
            name="✂️ Búa Kéo Bao",
            value="`.bkb <búa|kéo|bao>`\nĐấu với bot Rudeus",
            inline=False
        )
        embed.add_field(
            name="🔤 Nối Từ",
            value="`.noitu start` — Bắt đầu\n`.noitu <từ>` — Nối từ tiếp theo\n`.noitu stop` — Dừng",
            inline=False
        )
        embed.add_field(
            name="👑 Vua Tiếng Việt",
            value="`.vtviet` — Lấy câu hỏi trắc nghiệm\n`.vtviet A/B/C/D` — Trả lời",
            inline=False
        )
        embed.set_footer(text="Tất cả lệnh đều có slash command /tên tương ứng")
        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Minigame(bot))
