"""
cogs/ai_chat.py — AI Chat tích hợp Groq (llama-3.x, gemma2).
Lệnh: .ai, .aireset, .mychat
Kênh AI tự động trả lời mọi tin nhắn.
"""

import os
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core.data import ADMIN_IDS, get_cfg_ai_channel, _uname_plain

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_MODELS = [
    "llama-3.1-8b-instant",      # primary — 500k token/ngày
    "llama-3.3-70b-versatile",   # fallback 1 — 100k token/ngày
    "gemma2-9b-it",              # fallback 2 — 500k token/ngày
]

GROQ_SYSTEM = (
    "Bạn là trợ lý AI của TuyTam Store — một cửa hàng game. "
    "Hãy trả lời ngắn gọn, thân thiện, bằng tiếng Việt. "
    "Nếu không biết thông tin cụ thể về cửa hàng, hãy hướng dẫn user mở ticket để được hỗ trợ."
)

AI_HISTORY_LIMIT = 10
_ai_chat_history: dict = {}  # user_id → list of {"role": ..., "content": ...}


async def _call_groq(user_id: int, user_message: str) -> str:
    if not GROQ_API_KEY:
        return "❌ Chưa cài `GROQ_API_KEY` trong biến môi trường."

    history = _ai_chat_history.setdefault(user_id, [])
    history.append({"role": "user", "content": user_message})
    if len(history) > AI_HISTORY_LIMIT * 2:
        _ai_chat_history[user_id] = history[-(AI_HISTORY_LIMIT * 2):]
        history = _ai_chat_history[user_id]

    messages = [{"role": "system", "content": GROQ_SYSTEM}] + history
    last_err = "Unknown error"

    import aiohttp
    for model in GROQ_MODELS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "max_tokens": 1024, "temperature": 0.7},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        print(f"[AI] ⚠️ Model {model} hết quota, thử model tiếp...")
                        last_err = f"Model `{model}` hết quota"
                        continue
                    if resp.status != 200:
                        err = await resp.text()
                        last_err = f"Lỗi {resp.status}"
                        continue
                    data  = await resp.json()
                    reply = data["choices"][0]["message"]["content"]
            _ai_chat_history[user_id].append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            last_err = str(e)
            continue

    return f"⚠️ AI tạm thời không khả dụng ({last_err}). Vui lòng thử lại sau ít phút."


async def handle_ai_message(message: discord.Message):
    ai_ch_id = get_cfg_ai_channel()
    if not ai_ch_id or message.channel.id != ai_ch_id:
        return
    async with message.channel.typing():
        reply = await _call_groq(message.author.id, message.content)
    if len(reply) <= 2000:
        await message.reply(reply, mention_author=False)
    else:
        for chunk in [reply[i:i+1990] for i in range(0, len(reply), 1990)]:
            await message.channel.send(chunk)


class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="aireset")
    async def ai_reset(self, ctx):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")
        _ai_chat_history.clear()
        await ctx.reply("✅ Đã xoá toàn bộ lịch sử hội thoại AI.")

    @commands.command(name="mychat")
    async def my_chat_reset(self, ctx):
        if ctx.author.id in _ai_chat_history:
            del _ai_chat_history[ctx.author.id]
            await ctx.reply("✅ Đã xoá lịch sử chat AI của bạn.", delete_after=10)
        else:
            await ctx.reply("ℹ️ Bạn chưa có lịch sử chat AI.", delete_after=10)

    @commands.command(name="ai")
    async def ai_cmd(self, ctx, *, prompt: str = None):
        if not prompt:
            embed = discord.Embed(
                title="🤖 Hướng dẫn dùng AI", color=0x5865F2,
                description=(
                    "**`.ai <câu hỏi>`** — Chat với AI\n"
                    "**`.ai tomtat [n]`** — Tóm tắt `n` tin nhắn gần nhất (mặc định 30)\n"
                    "**`.ai dich <ngôn ngữ> <văn bản>`** — Dịch văn bản\n"
                    "**`.ai phantich @user`** — Phân tích phong cách chat của user\n"
                    "**`.ai reset`** — Xoá lịch sử hội thoại của bạn\n\n"
                    "💡 AI nhớ tối đa **10 tin nhắn** gần nhất."
                )
            )
            return await ctx.reply(embed=embed)

        parts = prompt.strip().split()
        sub   = parts[0].lower()

        if sub == "reset":
            if ctx.author.id in _ai_chat_history:
                del _ai_chat_history[ctx.author.id]
            return await ctx.reply("✅ Đã xoá lịch sử chat AI của bạn.", delete_after=10)

        if sub == "tomtat":
            limit = 30
            if len(parts) > 1 and parts[1].isdigit():
                limit = max(5, min(int(parts[1]), 100))
            async with ctx.typing():
                msgs = [m async for m in ctx.channel.history(limit=limit + 1) if not m.author.bot and m.id != ctx.message.id]
                msgs.reverse()
                if not msgs: return await ctx.reply("❌ Không có tin nhắn nào để tóm tắt.")
                chat_log = "\n".join(f"{_uname_plain(m.author)}: {m.content}" for m in msgs if m.content)[:4000]
                task  = f"Tóm tắt ngắn gọn nội dung cuộc trò chuyện sau trong kênh Discord (bằng tiếng Việt, tối đa 300 từ):\n\n{chat_log}"
                reply = await _call_groq(ctx.author.id, task)
            embed = discord.Embed(title=f"📋 Tóm tắt {len(msgs)} tin nhắn gần nhất", description=reply, color=0x5865F2, timestamp=datetime.now(timezone.utc))
            embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
            return await ctx.reply(embed=embed)

        if sub == "dich":
            if len(parts) < 3:
                return await ctx.reply("❌ Dùng: `.ai dich <ngôn ngữ> <văn bản>`")
            lang  = parts[1]
            text  = " ".join(parts[2:])
            async with ctx.typing():
                task  = f"Dịch đoạn văn bản sau sang {lang}, chỉ trả về bản dịch, không giải thích:\n\n{text}"
                reply = await _call_groq(ctx.author.id, task)
            embed = discord.Embed(title=f"🌐 Dịch sang {lang}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="📝 Gốc",    value=text[:500],  inline=False)
            embed.add_field(name="✅ Dịch",   value=reply[:500], inline=False)
            embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
            return await ctx.reply(embed=embed)

        if sub == "phantich":
            target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
            async with ctx.typing():
                msgs = [m async for m in ctx.channel.history(limit=50) if m.author.id == target.id and m.content and m.id != ctx.message.id]
                if len(msgs) < 3:
                    return await ctx.reply(f"❌ Cần ít nhất 3 tin nhắn của {target.display_name} để phân tích.")
                msgs.reverse()
                chat_log = "\n".join(f"{_uname_plain(m.author)}: {m.content}" for m in msgs)[:4000]
                task  = f"Hãy phân tích phong cách chat của người dùng '{_uname_plain(target)}' dựa trên các tin nhắn sau (bằng tiếng Việt, súc tích):\n\n{chat_log}"
                reply = await _call_groq(ctx.author.id, task)
            embed = discord.Embed(title=f"🔍 Phân Tích Chat — {target.display_name}", description=reply, color=0x9B59B6, timestamp=datetime.now(timezone.utc))
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
            return await ctx.reply(embed=embed)

        # chat thường
        async with ctx.typing():
            reply = await _call_groq(ctx.author.id, prompt)
        if len(reply) <= 2000:
            await ctx.reply(reply)
        else:
            for chunk in [reply[i:i+1990] for i in range(0, len(reply), 1990)]:
                await ctx.channel.send(chunk)


async def setup(bot):
    await bot.add_cog(AICog(bot))
