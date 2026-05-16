# cogs/minigame.py — v3.6.1 (fix race condition, cooldown, session safety)
import discord
from discord.ext import commands
from discord import app_commands
import random, asyncio, os, time

BAU_CUA_ICONS = {"bầu":"🎃","cua":"🦀","cá":"🐟","gà":"🐓","tôm":"🦐","nai":"🦌"}
BAU_CUA_KEYS  = list(BAU_CUA_ICONS.keys())
BAU_CUA_ALIAS = {"bau":"bầu","cua":"cua","ca":"cá","ga":"gà","tom":"tôm","nai":"nai"}
BKB_CHOICES   = {"búa":"🔨","kéo":"✂️","bao":"📄"}
BKB_WIN       = {"búa":"kéo","kéo":"bao","bao":"búa"}
BKB_ALIAS     = {"bua":"búa","keo":"kéo","bao":"bao","búa":"búa","kéo":"kéo"}

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
    "tranh luận","luận điểm","điểm số","số lượng",
]

VTV_QUESTIONS = [
    {"q":"Từ nào sau đây là từ láy?","choices":["A. học sinh","B. lung linh","C. đất nước","D. bàn ghế"],"ans":"B"},
    {"q":"\"Cô ấy có đôi mắt ___ như sao.\" Điền từ thích hợp:","choices":["A. sáng","B. long lanh","C. đen","D. to"],"ans":"B"},
    {"q":"Câu nào dùng biện pháp nhân hóa?","choices":["A. Mặt trăng tròn như cái đĩa","B. Gió ơi gió hỡi, gió về đâu","C. Con sông dài như dải lụa","D. Hoa nở rộ khắp vườn"],"ans":"B"},
    {"q":"Từ \"kiên nhẫn\" thuộc loại từ gì?","choices":["A. Danh từ","B. Động từ","C. Tính từ","D. Trạng từ"],"ans":"C"},
    {"q":"\"Nước chảy đá mòn\" có nghĩa là gì?","choices":["A. Đá rất cứng","B. Kiên trì ắt thành công","C. Nước rất mạnh","D. Không thể thay đổi"],"ans":"B"},
    {"q":"\"Trẻ em như búp trên cành\" dùng biện pháp tu từ nào?","choices":["A. Nhân hóa","B. Ẩn dụ","C. So sánh","D. Hoán dụ"],"ans":"C"},
    {"q":"Từ nào KHÔNG phải từ ghép?","choices":["A. học hành","B. xinh xắn","C. bàn tay","D. cây cối"],"ans":"B"},
    {"q":"\"Bán anh em xa, mua láng giềng gần\" thuộc thể loại gì?","choices":["A. Ca dao","B. Tục ngữ","C. Thành ngữ","D. Thơ"],"ans":"B"},
    {"q":"Chủ ngữ trong \"Mưa rơi lộp độp trên mái nhà\" là gì?","choices":["A. Mưa","B. Mái nhà","C. Lộp độp","D. Rơi"],"ans":"A"},
    {"q":"Từ nào viết đúng chính tả?","choices":["A. giản dị","B. dản dị","C. giản rị","D. zản dị"],"ans":"A"},
    {"q":"\"Đầu xuôi đuôi lọt\" có nghĩa là gì?","choices":["A. Bơi giỏi","B. Bắt đầu tốt thì kết thúc thuận lợi","C. Làm việc nhanh","D. Đầu to đuôi nhỏ"],"ans":"B"},
    {"q":"Từ nào là từ Hán Việt?","choices":["A. nhà cửa","B. gia đình","C. bàn ghế","D. cơm nước"],"ans":"B"},
    {"q":"\"Một con ngựa đau, cả tàu bỏ cỏ\" nói lên điều gì?","choices":["A. Ngựa ăn ít","B. Tinh thần đoàn kết","C. Nuôi ngựa tốn kém","D. Ngựa yếu thì bỏ"],"ans":"B"},
    {"q":"Câu \"Hoa hồng nở rực rỡ\" — vị ngữ là gì?","choices":["A. Hoa hồng","B. nở rực rỡ","C. rực rỡ","D. nở"],"ans":"B"},
    {"q":"Từ \"xanh\" trong \"Trời xanh\" và \"Xanh lá\" — quan hệ nghĩa là gì?","choices":["A. Từ đồng âm","B. Từ nhiều nghĩa","C. Từ trái nghĩa","D. Từ đồng nghĩa"],"ans":"B"},
]

NOITU_COOLDOWN = 3
noi_tu_sessions: dict = {}
vtv_sessions: dict    = {}

def load_words():
    try:
        with open(WORD_LIST_PATH, encoding="utf-8") as f:
            return [w.strip().lower() for w in f if w.strip()]
    except Exception:
        return FALLBACK_WORDS

WORDS_VI = load_words()

def last_syl(p): return p.strip().split()[-1].lower()
def first_syl(p): return p.strip().split()[0].lower()
def find_next(syl, used):
    c = [w for w in WORDS_VI if first_syl(w) == syl and w not in used]
    return random.choice(c) if c else None


class Minigame(commands.Cog):
    def __init__(self, bot): self.bot = bot

    # ── BẦU CUA ──
    @commands.command(name="baucua", aliases=["bc"])
    async def bau_cua(self, ctx, bet: str = None):
        """🎲 Bầu Cua — .baucua <bầu|cua|cá|gà|tôm|nai>"""
        if not bet:
            icons = "  ".join(f"{v}`{k}`" for k,v in BAU_CUA_ICONS.items())
            return await ctx.reply(f"🎲 **Bầu Cua Tôm Cá**\n{icons}\nVD: `.baucua bầu`")
        bet = BAU_CUA_ALIAS.get(bet.lower().strip(), bet.lower().strip())
        if bet not in BAU_CUA_KEYS:
            return await ctx.reply(f"❌ Chọn: {', '.join(BAU_CUA_KEYS)}")
        dice = [random.choice(BAU_CUA_KEYS) for _ in range(3)]
        hits = dice.count(bet)
        icon = BAU_CUA_ICONS[bet]
        res_line = "  ".join(BAU_CUA_ICONS[d] for d in dice)
        msgs = {0:(f"❌ Thua! Không có **{icon} {bet}**.",discord.Color.red()),
                1:(f"✅ Thắng x1! **{icon} {bet}** 1 lần.",discord.Color.green()),
                2:(f"🎉 Thắng x2! **{icon} {bet}** 2 lần!",discord.Color.gold()),
                3:(f"🏆 JACKPOT x3! **{icon} {bet}** cả 3!",discord.Color.orange())}
        out, color = msgs[hits]
        e = discord.Embed(title="🎲 Bầu Cua Tôm Cá", color=color)
        e.add_field(name="Bạn chọn", value=f"{icon} **{bet}**", inline=True)
        e.add_field(name="Kết quả lắc", value=res_line, inline=False)
        e.add_field(name="Kết quả", value=out, inline=False)
        e.set_footer(text=ctx.author.display_name)
        await ctx.reply(embed=e)

    @app_commands.command(name="baucua", description="🎲 Chơi Bầu Cua Tôm Cá")
    @app_commands.describe(chon="bầu, cua, cá, gà, tôm, nai")
    async def bau_cua_slash(self, interaction, chon: str):
        await self.bau_cua(await commands.Context.from_interaction(interaction), chon)

    # ── BÚA KÉO BAO ──
    @commands.command(name="bkb", aliases=["bukebao","rps"])
    async def bkb(self, ctx, choice: str = None):
        """✂️ Búa Kéo Bao — .bkb <búa|kéo|bao>"""
        if not choice:
            opts = "  ".join(f"{v}`{k}`" for k,v in BKB_CHOICES.items())
            return await ctx.reply(f"✂️ **Búa Kéo Bao**\n{opts}\nVD: `.bkb búa`")
        choice = BKB_ALIAS.get(choice.lower().strip(), choice.lower().strip())
        if choice not in BKB_CHOICES:
            return await ctx.reply("❌ Chọn: `búa`, `kéo`, `bao`")
        bot_c = random.choice(list(BKB_CHOICES.keys()))
        if choice == bot_c:   result,color = "🤝 **Hòa!**",        discord.Color.yellow()
        elif BKB_WIN[choice]==bot_c: result,color = "🏆 **Bạn thắng!**", discord.Color.green()
        else:                 result,color = "💀 **Bot thắng!**",  discord.Color.red()
        e = discord.Embed(title="✂️ Búa Kéo Bao", color=color)
        e.add_field(name=ctx.author.display_name, value=f"{BKB_CHOICES[choice]} **{choice}**", inline=True)
        e.add_field(name="vs", value="⚔️", inline=True)
        e.add_field(name="Bot Rudeus", value=f"{BKB_CHOICES[bot_c]} **{bot_c}**", inline=True)
        e.add_field(name="Kết quả", value=result, inline=False)
        await ctx.reply(embed=e)

    @app_commands.command(name="bkb", description="✂️ Búa Kéo Bao với bot")
    @app_commands.describe(chon="búa, kéo hoặc bao")
    async def bkb_slash(self, interaction, chon: str):
        await self.bkb(await commands.Context.from_interaction(interaction), chon)

    # ── NỐI TỪ ── (FIX: lock + cooldown per-user + chặn nối 2 lần liên tiếp)
    @commands.command(name="noitu", aliases=["nt"])
    async def noi_tu(self, ctx, *, action: str = None):
        """🔤 Nối Từ — .noitu start | .noitu <từ> | .noitu stop"""
        cid = ctx.channel.id
        if not action:
            return await ctx.reply("🔤 **Nối Từ**\n`.noitu start` — Bắt đầu\n`.noitu <từ>` — Nối\n`.noitu stop` — Dừng")
        action = action.strip().lower()

        if action == "start":
            if cid in noi_tu_sessions:
                return await ctx.reply("⚠️ Đang có game! Dùng `.noitu stop` để dừng.")
            w = random.choice(WORDS_VI)
            noi_tu_sessions[cid] = {"word":w,"used":{w},"lock":asyncio.Lock(),"last_player":None,"player_last_time":{}}
            e = discord.Embed(title="🔤 Nối Từ bắt đầu!", color=discord.Color.blue(),
                description=f"Từ đầu tiên: **{w}**\nNối từ bắt đầu bằng **`{last_syl(w)}`**!")
            e.set_footer(text=".noitu <từ> để nối | .noitu stop để dừng")
            return await ctx.send(embed=e)

        if action == "stop":
            if cid not in noi_tu_sessions:
                return await ctx.reply("❌ Không có game nào đang chạy.")
            del noi_tu_sessions[cid]
            return await ctx.reply("🛑 Game Nối Từ đã dừng!")

        if cid not in noi_tu_sessions:
            return await ctx.reply("❌ Chưa có game! Dùng `.noitu start`.")

        s = noi_tu_sessions[cid]
        async with s["lock"]:   # FIX: tránh race condition
            uid, now = ctx.author.id, time.time()
            # FIX: cooldown per-user
            if now - s["player_last_time"].get(uid,0) < NOITU_COOLDOWN:
                wait = int(NOITU_COOLDOWN-(now-s["player_last_time"].get(uid,0)))
                return await ctx.reply(f"⏳ Chờ **{wait}s**!", delete_after=5)
            # FIX: chặn nối 2 lần liên tiếp
            if s["last_player"] == uid and len(s["used"]) > 2:
                return await ctx.reply("❌ Phải để người khác nối trước!", delete_after=5)
            if action in s["used"]:
                return await ctx.reply(f"❌ Từ **{action}** đã dùng rồi!")
            if action not in WORDS_VI:
                return await ctx.reply(f"❌ Từ **{action}** không có trong từ điển!")
            req = last_syl(s["word"])
            if first_syl(action) != req:
                return await ctx.reply(f"❌ Phải bắt đầu bằng **`{req}`**!")
            s["used"].add(action); s["word"]=action; s["last_player"]=uid; s["player_last_time"][uid]=now
            nxt = last_syl(action)
            bot_w = find_next(nxt, s["used"])
            if bot_w:
                s["used"].add(bot_w); s["word"]=bot_w
                e = discord.Embed(color=discord.Color.green())
                e.add_field(name=f"✅ {ctx.author.display_name}", value=f"**{action}**", inline=True)
                e.add_field(name="🤖 Bot Rudeus", value=f"**{bot_w}**", inline=True)
                e.set_footer(text=f"Nối từ bắt đầu bằng '{last_syl(bot_w)}'")
                await ctx.send(embed=e)
            else:
                del noi_tu_sessions[cid]
                await ctx.reply(f"✅ **{ctx.author.display_name}** nối: **{action}**\n🤖 Bot hết từ bắt đầu bằng **`{nxt}`**!\n🏆 **{ctx.author.display_name} THẮNG!**")

    @app_commands.command(name="noitu", description="🔤 Chơi Nối Từ tiếng Việt")
    @app_commands.describe(hanh_dong="start / stop / <từ cần nối>")
    async def noi_tu_slash(self, interaction, hanh_dong: str):
        await self.noi_tu(await commands.Context.from_interaction(interaction), action=hanh_dong)

    # ── VUA TIẾNG VIỆT ── (FIX: timestamp, tự dọn hết hạn, dọn ngay khi đúng)
    @commands.command(name="vtviet", aliases=["vtv","vuatv"])
    async def vtv(self, ctx, action: str = None):
        """👑 Vua Tiếng Việt — .vtviet | .vtviet A/B/C/D"""
        cid = ctx.channel.id
        if action and action.upper() in ["A","B","C","D"]:
            if cid not in vtv_sessions:
                return await ctx.reply("❌ Không có câu hỏi nào! Dùng `.vtviet`.")
            s = vtv_sessions[cid]
            if time.time() > s["expire_time"]:  # FIX: check timestamp
                del vtv_sessions[cid]
                return await ctx.reply("⏰ Câu hỏi đã hết hạn!")
            uid = ctx.author.id
            if uid in s["answered"]:
                return await ctx.reply("⚠️ Bạn đã trả lời rồi!")
            s["answered"].add(uid)
            ans, correct = action.upper(), s["question"]["ans"]
            if ans == correct:
                del vtv_sessions[cid]  # FIX: dọn ngay
                e = discord.Embed(title="✅ Chính xác!",
                    description=f"**{ctx.author.display_name}** đúng! Đáp án: **{correct}**",
                    color=discord.Color.green())
            else:
                e = discord.Embed(title="❌ Sai rồi!",
                    description=f"**{ctx.author.display_name}** chọn **{ans}**, đúng là **{correct}**.\nNgười khác vẫn có thể trả lời!",
                    color=discord.Color.red())
            return await ctx.send(embed=e)

        # Lấy câu mới — FIX: tự dọn session hết hạn
        if cid in vtv_sessions:
            if time.time() > vtv_sessions[cid]["expire_time"]:
                del vtv_sessions[cid]
            else:
                return await ctx.reply("⚠️ Đang có câu chưa ai trả lời đúng! Dùng `.vtviet A/B/C/D`.")

        q = random.choice(VTV_QUESTIONS)
        expire = time.time() + 60
        vtv_sessions[cid] = {"question":q,"answered":set(),"expire_time":expire}
        e = discord.Embed(title="👑 Vua Tiếng Việt",
            description=f"**{q['q']}**\n\n" + "\n".join(q["choices"]),
            color=discord.Color.purple())
        e.set_footer(text="Trả lời .vtviet A/B/C/D | Hết hạn sau 60 giây")
        await ctx.send(embed=e)
        await asyncio.sleep(60)
        if cid in vtv_sessions and vtv_sessions[cid]["expire_time"] == expire:
            del vtv_sessions[cid]
            try: await ctx.send(f"⏰ Hết giờ! Đáp án đúng là **{q['ans']}**.")
            except: pass

    @app_commands.command(name="vtviet", description="👑 Vua Tiếng Việt")
    @app_commands.describe(tra_loi="Bỏ trống = lấy câu hỏi | A/B/C/D = trả lời")
    async def vtv_slash(self, interaction, tra_loi: str = None):
        await self.vtv(await commands.Context.from_interaction(interaction), action=tra_loi)

    # ── HELP ──
    @commands.command(name="minigame", aliases=["mg","games"])
    async def mg_help(self, ctx):
        e = discord.Embed(title="🎮 Danh sách Minigame", color=discord.Color.blurple())
        e.add_field(name="🎲 Bầu Cua", value="`.baucua <bầu|cua|cá|gà|tôm|nai>` — Lắc 3 xúc xắc, thắng x1/x2/x3", inline=False)
        e.add_field(name="✂️ Búa Kéo Bao", value="`.bkb <búa|kéo|bao>` — Đấu với bot", inline=False)
        e.add_field(name="🔤 Nối Từ", value="`.noitu start/stop/<từ>` — Nối từ tiếng Việt", inline=False)
        e.add_field(name="👑 Vua Tiếng Việt", value="`.vtviet` — Câu hỏi | `.vtviet A/B/C/D` — Trả lời", inline=False)
        e.set_footer(text="Tất cả đều có slash command /tên tương ứng")
        await ctx.reply(embed=e)

    def cog_unload(self):
        noi_tu_sessions.clear()
        vtv_sessions.clear()


async def setup(bot):
    await bot.add_cog(Minigame(bot))
