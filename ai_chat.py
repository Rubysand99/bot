# cogs/ai_chat.py — .ai .aireset .mychat
from config import *

@bot.command(name="aireset")
async def ai_reset(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin.")
    _ai_chat_history.clear()
    await ctx.reply("✅ Đã xoá toàn bộ lịch sử hội thoại AI.")

@bot.command(name="mychat")
async def my_chat_reset(ctx):
    if ctx.author.id in _ai_chat_history:
        del _ai_chat_history[ctx.author.id]
        await ctx.reply("✅ Đã xoá lịch sử chat AI của bạn.", delete_after=10)
    else:
        await ctx.reply("ℹ️ Bạn chưa có lịch sử chat AI.", delete_after=10)

@bot.command(name="ai")
async def ai_cmd(ctx, *, prompt: str = None):
    """
    Dùng AI ở bất kỳ kênh nào.
    Subcommands:
      .ai <câu hỏi>            — chat thường
      .ai tomtat [n]           — tóm tắt n tin nhắn gần nhất (mặc định 30)
      .ai dich <ngôn ngữ> ...  — dịch văn bản sang ngôn ngữ chỉ định
      .ai phantich @user       — phân tích phong cách chat của user
      .ai reset                — xoá lịch sử chat của bạn
    """
    if not prompt:
        embed = discord.Embed(
            title="🤖 Hướng dẫn dùng AI",
            color=0x5865F2,
            description=(
                "**`.ai <câu hỏi>`** — Chat với AI\n"
                "**`.ai tomtat [n]`** — Tóm tắt `n` tin nhắn gần nhất trong kênh (mặc định 30)\n"
                "**`.ai dich <ngôn ngữ> <văn bản>`** — Dịch văn bản\n"
                "**`.ai phantich @user`** — Phân tích phong cách chat của user\n"
                "**`.ai reset`** — Xoá lịch sử hội thoại của bạn\n\n"
                "💡 AI nhớ tối đa **10 tin nhắn** gần nhất trong hội thoại với bạn."
            )
        )
        return await ctx.reply(embed=embed)

    parts = prompt.strip().split()
    sub = parts[0].lower()

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
            if not msgs:
                return await ctx.reply("❌ Không có tin nhắn nào để tóm tắt.")
            chat_log = "\n".join(f"{_uname_plain(m.author)}: {m.content}" for m in msgs if m.content)[:4000]
            task = (
                f"Tóm tắt ngắn gọn nội dung cuộc trò chuyện sau trong kênh Discord "
                f"(bằng tiếng Việt, tối đa 300 từ):\n\n{chat_log}"
            )
            reply = await _call_groq(ctx.author.id, task)
        embed = discord.Embed(
            title=f"📋 Tóm tắt {len(msgs)} tin nhắn gần nhất",
            description=reply,
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
        return await ctx.reply(embed=embed)

    if sub == "dich":
        if len(parts) < 3:
            return await ctx.reply("❌ Dùng: `.ai dich <ngôn ngữ> <văn bản>`\nVí dụ: `.ai dich tiếng Anh xin chào bạn`")
        lang = parts[1]
        text = " ".join(parts[2:])
        async with ctx.typing():
            task = f"Dịch đoạn văn bản sau sang {lang}, chỉ trả về bản dịch, không giải thích:\n\n{text}"
            reply = await _call_groq(ctx.author.id, task)
        embed = discord.Embed(
            title=f"🌐 Dịch sang {lang}",
            color=0x57F287,
        )
        embed.add_field(name="📝 Gốc", value=text[:1024], inline=False)
        embed.add_field(name="✅ Dịch", value=reply[:1024], inline=False)
        embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
        return await ctx.reply(embed=embed)

    if sub == "phantich":
        target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        async with ctx.typing():
            msgs = [m async for m in ctx.channel.history(limit=200) if m.author.id == target.id and m.content]
            if len(msgs) < 5:
                return await ctx.reply(f"❌ Không đủ tin nhắn của {_uname(target)} để phân tích (cần ít nhất 5).")
            sample = "\n".join(m.content for m in msgs[:50])[:3000]
            task = (
                f"Phân tích phong cách chat của người dùng Discord tên '{_uname_plain(target)}' "
                f"dựa trên các tin nhắn sau. Nhận xét về: cách dùng từ, tính cách, sở thích, "
                f"mức độ hoạt động, emoji thường dùng. Trả lời bằng tiếng Việt, vui vẻ và thân thiện:\n\n{sample}"
            )
            reply = await _call_groq(ctx.author.id, task)
        embed = discord.Embed(
            title=f"🔍 Phân tích phong cách chat của {_uname(target)}",
            description=reply[:2000],
            color=0xEB459E,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
        return await ctx.reply(embed=embed)

    async with ctx.typing():
        reply = await _call_groq(ctx.author.id, prompt)
    if len(reply) <= 2000:
        await ctx.reply(reply)
    else:
        chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
        for chunk in chunks:
            await ctx.channel.send(chunk)

# ================= INVITE COMMANDS =================


