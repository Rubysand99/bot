"""
cogs/ai_chat.py — AI Chat tích hợp Groq (gpt-oss).
Lệnh: .ai (admin — điều khiển bot bằng ngôn ngữ tự nhiên), .aireset, .mychat
Kênh AI tự động trả lời mọi tin nhắn (khách hàng).

v4.14.0 — Function calling (xem CHANGELOG):
- GROQ_MODELS đổi sang openai/gpt-oss-20b / openai/gpt-oss-120b — Groq đã deprecate
  llama-3.1-8b-instant + llama-3.3-70b-versatile (shutdown 16/08/2026), gemma2-9b-it
  đã chết từ 08/10/2025 (fallback cũ trong code thực ra không hoạt động từ lâu).
- Xoá AI_EXEC_SYSTEM/_call_groq_exec/_call_groq_clarify/_call_groq_fill/_run_action —
  hệ thống prompt-JSON tự chế cũ CHƯA TỪNG được gọi ở đâu (dead code, không có lệnh
  nào trigger) và một số action trỏ tới lệnh KHÔNG TỒN TẠI (ticketpanel/gend/greroll).
  Thay bằng native tool calling của Groq — xem core/ai_tools.py.
- AI trong kênh chat khách giờ có thể tự tra cứu ticket/seller/invite/lịch sử mua
  hàng của CHÍNH người hỏi qua QUERY_TOOL_SCHEMAS.
- Thêm lệnh `.ai <yêu cầu>` cho admin — điều khiển bot bằng ngôn ngữ tự nhiên qua
  ADMIN_TOOL_SCHEMAS, có xác nhận cho hành động nguy hiểm (AIConfirmView).
"""

import os
import json
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core.data import (
    ADMIN_IDS, get_cfg_ai_channel, _uname_plain,
    load_global_data, save_global_data,
    set_current_guild, reset_current_guild,
)
from core.rag import save_qa_to_rag, get_relevant_context
from core.ai_tools import (
    QUERY_TOOL_SCHEMAS, ADMIN_TOOL_SCHEMAS, DANGEROUS_TOOLS, TOOL_HANDLERS,
)
from cogs.logger import send_log

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ─────────────────────────────────────────────
# FORUM HỎI-ĐÁP ADMIN — kích hoạt khi RAG KHÔNG tìm được câu trả lời liên quan
# (không còn dựa vào AI tự đánh giá "chắc/không chắc" — model nhỏ tự đánh giá
# không đáng tin, xem CHANGELOG v4.13.1)
# ─────────────────────────────────────────────
AI_ASK_ADMIN_PENDING_FORUM_ID  = int(os.getenv("AI_ASK_ADMIN_PENDING_FORUM_ID", "0"))
AI_ASK_ADMIN_RESOLVED_FORUM_ID = int(os.getenv("AI_ASK_ADMIN_RESOLVED_FORUM_ID", "0"))

# Khi admin reply trong post Pending chỉ bằng 1 trong các từ này (không phân biệt
# hoa/thường, có thể kèm dấu câu cuối), coi như "không muốn trả lời" — bot tự thay
# bằng câu từ chối chuẩn thay vì lưu nguyên văn "kbt" làm câu trả lời cho khách.
NO_ANSWER_SHORTHANDS = {"kbt", "ko bt", "k bt", "không biết", "khong biet", "k biết", "no"}
DEFAULT_NO_ANSWER_REPLY = (
    "Mình chưa có thông tin cụ thể về vấn đề này. Bạn vui lòng mở ticket để "
    "được admin hỗ trợ trực tiếp nhé!"
)

# Model chính = gpt-oss-20b (nhanh, rẻ, đủ tốt cho tool calling + chat thường).
# Fallback = gpt-oss-120b (mạnh hơn khi model chính hết quota/lỗi).
# Cả 2 đều hỗ trợ native tool calling — xem https://console.groq.com/docs/tool-use/overview
GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
]

GROQ_SYSTEM = (
    "Bạn là trợ lý AI của TuyTam Store — một cửa hàng game. "
    "Hãy trả lời ngắn gọn, thân thiện, bằng tiếng Việt. "
    "Nếu có phần \"Thông tin đã xác nhận trước đó\" được cung cấp bên dưới, ưu tiên "
    "dùng thông tin đó thay vì đoán. "
    "Nếu người dùng hỏi về ticket/gói seller/invite/lịch sử mua hàng của CHÍNH họ, "
    "hãy dùng tool tương ứng để tra cứu thay vì đoán."
)

GROQ_ADMIN_SYSTEM = (
    "Bạn là AI điều khiển bot Discord TuyTam Store cho admin. Phân tích yêu cầu của "
    "admin (kể cả sai chính tả, thiếu dấu, viết tắt) và gọi tool phù hợp nhất. "
    "Nếu yêu cầu THIẾU thông tin bắt buộc (vd thiếu lý do ban, thiếu tên kênh...), "
    "ĐỪNG gọi tool — hãy hỏi lại admin bằng 1 câu ngắn gọn tiếng Việt. "
    "Nếu yêu cầu không rõ hành động nào, trả lời ngắn gọn rằng bạn không hiểu và "
    "gợi ý admin mô tả rõ hơn hoặc dùng lệnh trực tiếp."
)

AI_HISTORY_LIMIT = 10
_ai_chat_history: dict = {}   # user_id → {"messages": [...], "last_used": float timestamp}
AI_HISTORY_TTL = 7200  # 2 giờ — dọn history không hoạt động
MAX_TOOL_ROUNDS = 4     # số vòng lặp tool-calling tối đa trước khi ép trả lời cuối


def normalize_admin_answer(content: str) -> str:
    """Nếu admin reply chỉ là 1 shorthand kiểu 'kbt'/'không biết' -> thay bằng câu
    từ chối chuẩn, tránh lưu nguyên văn shorthand vào RAG làm khách hoang mang."""
    cleaned = content.strip().lower().rstrip("!.?~ ")
    if cleaned in NO_ANSWER_SHORTHANDS:
        return DEFAULT_NO_ANSWER_REPLY
    return content


# ─────────────────────────────────────────────
# CONFIRM VIEW — cho tool nguy hiểm (DANGEROUS_TOOLS)
# ─────────────────────────────────────────────
class AIConfirmView(discord.ui.View):
    """Yêu cầu admin xác nhận trước khi chạy tool nguy hiểm (ban/kick/mute/xoá...)."""
    def __init__(self, ctx, tool_name: str, params: dict):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.tool_name = tool_name
        self.params = params
        self.message = None

    @discord.ui.button(label="✅ Xác nhận", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Chỉ người ra lệnh mới xác nhận được.", ephemeral=True)
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="⚙️ Đang thực thi...", embed=None, view=self)
        handler = TOOL_HANDLERS.get(self.tool_name)
        result = await handler(self.ctx, self.params) if handler else f"❌ Không tìm thấy tool `{self.tool_name}`."
        await interaction.followup.send(result)

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Chỉ người ra lệnh mới huỷ được.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(content="🚫 Đã huỷ.", embed=None, view=None)

    async def on_timeout(self):
        if not self.message:
            return
        try:
            await self.message.edit(content="⏰ Hết thời gian xác nhận — đã huỷ.", embed=None, view=None)
        except Exception:
            pass


# ─────────────────────────────────────────────
# GROQ TOOL CALLING — low-level API call + agent loop
# ─────────────────────────────────────────────
async def _call_groq_tools(messages: list, tools: list | None = None) -> dict:
    """Gọi Groq chat completions, trả về message dict của assistant
    (có thể chứa "tool_calls" nếu model quyết định gọi tool)."""
    if not GROQ_API_KEY:
        return {"role": "assistant", "content": "❌ Chưa cài `GROQ_API_KEY` trong biến môi trường."}

    import aiohttp
    body_base = {"messages": messages, "max_tokens": 1024, "temperature": 0.4}
    if tools:
        body_base["tools"] = tools
        body_base["tool_choice"] = "auto"

    last_err = "Unknown error"
    for model in GROQ_MODELS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": model, **body_base},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        last_err = f"Model `{model}` hết quota"
                        continue
                    if resp.status != 200:
                        err = await resp.text()
                        print(f"[AI] ⚠️ Model {model} lỗi {resp.status}: {err[:200]}")
                        last_err = f"Lỗi {resp.status}"
                        continue
                    data = await resp.json()
                    return data["choices"][0]["message"]
        except Exception as e:
            last_err = str(e)
            continue

    return {"role": "assistant", "content": f"⚠️ AI tạm thời không khả dụng ({last_err}). Vui lòng thử lại sau ít phút."}


async def run_ai_tools_agent(ctx, is_admin: bool, user_content: str, history: list | None = None):
    """Vòng lặp tool-calling chính. Trả về tuple (final_text, pending_confirm):
    - pending_confirm là None nếu AI đã trả lời xong (final_text = câu trả lời).
    - pending_confirm là {"name": tool_name, "params": {...}} nếu gặp tool nguy hiểm
      cần admin xác nhận trước — final_text khi đó là None.
    `ctx` cần có .guild/.author/.channel/.message (dùng message thật hoặc commands.Context).
    """
    tools = list(QUERY_TOOL_SCHEMAS)
    if is_admin:
        tools += ADMIN_TOOL_SCHEMAS

    messages = [{"role": "system", "content": GROQ_ADMIN_SYSTEM if is_admin else GROQ_SYSTEM}]
    messages += (history or [])
    messages.append({"role": "user", "content": user_content})

    for _ in range(MAX_TOOL_ROUNDS):
        msg = await _call_groq_tools(messages, tools)
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return (msg.get("content") or "").strip(), None

        # Tool nguy hiểm -> KHÔNG chạy ngay, trả về cho caller để hiện confirm view
        for call in tool_calls:
            name = call.get("function", {}).get("name")
            if name in DANGEROUS_TOOLS:
                try:
                    params = json.loads(call["function"].get("arguments") or "{}")
                except Exception:
                    params = {}
                return None, {"name": name, "params": params}

        # Tool an toàn -> chạy hết, feed kết quả lại cho model rồi lặp tiếp
        messages.append(msg)
        for call in tool_calls:
            name = call.get("function", {}).get("name")
            try:
                params = json.loads(call["function"].get("arguments") or "{}")
            except Exception:
                params = {}
            handler = TOOL_HANDLERS.get(name)
            result = await handler(ctx, params) if handler else f"Không tìm thấy tool `{name}`."
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "name": name,
                "content": result,
            })

    return "🤔 Yêu cầu cần quá nhiều bước xử lý, bạn thử mô tả đơn giản/cụ thể hơn nhé.", None


async def _call_groq(user_id: int, user_message: str, extra_context: str | None = None) -> str:
    """Chat thường (không tool) — giữ lại cho tương thích, hiện KHÔNG còn dùng trực
    tiếp trong handle_ai_message (đã chuyển sang run_ai_tools_agent), nhưng vẫn hữu
    ích nếu cần gọi Groq thuần text ở nơi khác."""
    if not GROQ_API_KEY:
        return "❌ Chưa cài `GROQ_API_KEY` trong biến môi trường."

    system_content = GROQ_SYSTEM
    if extra_context:
        system_content += "\n\nThông tin đã xác nhận trước đó (ưu tiên dùng):\n" + extra_context
    messages = [{"role": "system", "content": system_content}, {"role": "user", "content": user_message}]
    msg = await _call_groq_tools(messages, tools=None)
    return (msg.get("content") or "").strip()


async def handle_ai_message(message: discord.Message):
    ai_ch_id = get_cfg_ai_channel()
    if not ai_ch_id or message.channel.id != ai_ch_id:
        return
    # Bỏ qua nếu là lệnh bot (bắt đầu bằng prefix . / / hoặc !)
    if message.content and message.content[0] in ('.', '/', '!'):
        return

    now = datetime.now(timezone.utc).timestamp()
    # Dọn TTL — xóa history cũ hơn AI_HISTORY_TTL
    stale = [uid for uid, v in _ai_chat_history.items() if now - v.get("last_used", 0) > AI_HISTORY_TTL]
    for uid in stale:
        del _ai_chat_history[uid]

    entry = _ai_chat_history.setdefault(message.author.id, {"messages": [], "last_used": now})
    history = entry["messages"]

    # Tra RAG trước — nếu có Q&A tương tự đã được admin xác nhận, AI sẽ ưu tiên dùng
    rag_context = await get_relevant_context(message.guild.id, message.content)
    user_content = message.content
    if rag_context:
        user_content = (
            f"{message.content}\n\n[Thông tin đã xác nhận trước đó — ưu tiên dùng]: {rag_context}"
        )

    async with message.channel.typing():
        reply, pending = await run_ai_tools_agent(message, is_admin=False, user_content=user_content, history=history)

    # Query tools không nằm trong DANGEROUS_TOOLS nên pending sẽ luôn None ở nhánh
    # khách hàng, nhưng vẫn xử lý phòng hờ nếu sau này thêm tool mới.
    if pending is not None:
        reply = "🤔 Yêu cầu này cần admin xử lý, bạn vui lòng mở ticket nhé."

    reply = (reply or "").strip()
    if not reply:
        reply = DEFAULT_NO_ANSWER_REPLY

    # Lưu vào history (KHÔNG lưu rag_context/tool messages vào history lâu dài,
    # chỉ lưu câu hỏi gốc + câu trả lời cuối, tránh phình context các lượt sau)
    history.append({"role": "user", "content": message.content})
    history.append({"role": "assistant", "content": reply})
    if len(history) > AI_HISTORY_LIMIT * 2:
        entry["messages"] = history[-(AI_HISTORY_LIMIT * 2):]
    entry["last_used"] = now

    # RAG KHÔNG tìm được gì liên quan đủ tin cậy -> LUÔN gửi cho admin xử lý,
    # không dựa vào AI tự đánh giá "chắc/không chắc" nữa (xem CHANGELOG v4.13.1)
    needs_admin = rag_context is None

    if len(reply) <= 2000:
        await message.reply(reply, mention_author=False)
    else:
        for chunk in [reply[i:i+1990] for i in range(0, len(reply), 1990)]:
            await message.channel.send(chunk)

    bot_ref = message._state._get_client()

    if needs_admin:
        await create_pending_question(
            bot_ref,
            guild_id=message.guild.id,
            user=message.author,
            question=message.content,
            ai_draft=reply,
        )

    await send_log(
        bot_ref, "AI_USED", "AI Chat",
        fields=[
            ("👤 User",    f"{message.author.mention} (`{message.author.id}`)", True),
            ("💬 Tin nhắn", f"`{message.content[:200]}`",                       False),
            ("🤖 Phản hồi", f"`{reply[:200]}`",                                 False),
            ("📚 Dùng RAG", "✅ Có" if rag_context else "Không",                True),
            ("❓ Cần admin", "✅ Có" if needs_admin else "Không",                True),
        ],
        user=message.author,
    )


# ─────────────────────────────────────────────
# FORUM PENDING — AI không chắc, chờ admin trả lời
# ─────────────────────────────────────────────
async def create_pending_question(bot, guild_id: int, user: discord.abc.User,
                                    question: str, ai_draft: str) -> None:
    if not AI_ASK_ADMIN_PENDING_FORUM_ID:
        return
    forum = bot.get_channel(AI_ASK_ADMIN_PENDING_FORUM_ID)
    if not isinstance(forum, discord.ForumChannel):
        logging.getLogger("ai").warning("[AI] ⚠️ AI_ASK_ADMIN_PENDING_FORUM_ID không phải Forum Channel.")
        return

    guild = bot.get_guild(guild_id)
    embed = discord.Embed(
        title="🤔 AI chưa chắc câu trả lời này",
        color=0xF0A500,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="👤 Người hỏi", value=f"{user} (`{user.id}`)", inline=False)
    embed.add_field(name="🏠 Server", value=guild.name if guild else str(guild_id), inline=True)
    embed.add_field(name="💬 Câu hỏi", value=question[:1000], inline=False)
    embed.add_field(name="🤖 AI đã trả lời tạm", value=ai_draft[:1000], inline=False)
    embed.set_footer(text="Reply trong post này để giải đáp — sẽ tự chuyển sang forum Đã xử lý")

    thread_name = question.strip()[:90] or f"Câu hỏi từ {user}"
    result = await forum.create_thread(name=thread_name, embed=embed)
    thread = result.thread

    gdata = load_global_data()
    pending = gdata.setdefault("ai_pending_questions", {})
    pending[str(thread.id)] = {
        "guild_id": guild_id,
        "user_id": user.id,
        "question": question,
        "ai_draft": ai_draft,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_global_data(gdata)


# ─────────────────────────────────────────────
# FORUM RESOLVED — admin đã trả lời, lưu vào RAG
# ─────────────────────────────────────────────
async def create_resolved_post(bot, guild_id: int, user_id: int, question: str,
                                 ai_draft: str, admin_answer: str, answered_by: int) -> int | None:
    if not AI_ASK_ADMIN_RESOLVED_FORUM_ID:
        return None
    forum = bot.get_channel(AI_ASK_ADMIN_RESOLVED_FORUM_ID)
    if not isinstance(forum, discord.ForumChannel):
        return None

    guild = bot.get_guild(guild_id)
    embed = discord.Embed(
        title="✅ Đã giải đáp",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🏠 Server", value=guild.name if guild else str(guild_id), inline=True)
    embed.add_field(name="💬 Câu hỏi", value=question[:1000], inline=False)
    embed.add_field(name="🤖 AI đã nghĩ", value=ai_draft[:1000], inline=False)
    embed.add_field(name="✅ Giải đáp của admin", value=admin_answer[:1000], inline=False)
    embed.set_footer(text="Nhắn tin mới trong post này để SỬA câu trả lời — AI sẽ cập nhật theo")

    thread_name = question.strip()[:90] or "Đã giải đáp"
    result = await forum.create_thread(name=thread_name, embed=embed)
    thread = result.thread

    gdata = load_global_data()
    resolved = gdata.setdefault("ai_resolved_threads", {})
    resolved[str(thread.id)] = {
        "guild_id": guild_id,
        "user_id": user_id,
        "question": question,
        "ai_draft": ai_draft,
        "starter_message_id": thread.id,  # trong forum, id tin nhắn mở đầu == id thread
    }
    save_global_data(gdata)

    await save_qa_to_rag(doc_id=str(thread.id), guild_id=guild_id, question=question, answer=admin_answer)
    return thread.id


async def _handle_pending_reply(bot, message: discord.Message) -> bool:
    """Admin reply trong post PENDING -> tạo post RESOLVED + lưu RAG + archive post cũ.
    Trả về True nếu đã xử lý (để listener chính không xử lý tiếp)."""
    gdata = load_global_data()
    pending = gdata.get("ai_pending_questions", {})
    entry = pending.get(str(message.channel.id))
    if not entry:
        return False

    token = set_current_guild(entry["guild_id"])
    try:
        resolved_id = await create_resolved_post(
            bot,
            guild_id=entry["guild_id"],
            user_id=entry["user_id"],
            question=entry["question"],
            ai_draft=entry["ai_draft"],
            admin_answer=normalize_admin_answer(message.content),
            answered_by=message.author.id,
        )
        if resolved_id:
            await message.add_reaction("✅")
            try:
                await message.channel.send(
                    f"✅ Đã lưu vào forum **Đã xử lý** và dạy AI. Post này sẽ đóng lại."
                )
                await message.channel.edit(archived=True, locked=True)
            except discord.HTTPException:
                pass

        # Xoá khỏi hàng đợi pending
        pending.pop(str(message.channel.id), None)
        gdata["ai_pending_questions"] = pending
        save_global_data(gdata)
    finally:
        reset_current_guild(token)
    return True


async def _handle_resolved_edit(bot, message: discord.Message) -> bool:
    """Admin nhắn tin MỚI trong post RESOLVED (không phải tin mở đầu) -> coi là
    sửa câu trả lời, cập nhật embed gốc + ghi đè lại vector trong RAG."""
    gdata = load_global_data()
    resolved = gdata.get("ai_resolved_threads", {})
    entry = resolved.get(str(message.channel.id))
    if not entry:
        return False

    token = set_current_guild(entry["guild_id"])
    try:
        new_answer = normalize_admin_answer(message.content.strip())
        if not new_answer:
            return True

        ok = await save_qa_to_rag(
            doc_id=str(message.channel.id),
            guild_id=entry["guild_id"],
            question=entry["question"],
            answer=new_answer,
        )

        try:
            starter = await message.channel.fetch_message(message.channel.id)
            if starter.embeds:
                embed = starter.embeds[0]
                for i, field in enumerate(embed.fields):
                    if field.name == "✅ Giải đáp của admin":
                        embed.set_field_at(i, name=field.name, value=new_answer[:1000], inline=field.inline)
                        break
                await starter.edit(embed=embed)
        except discord.HTTPException:
            pass

        await message.add_reaction("✅" if ok else "⚠️")
    finally:
        reset_current_guild(token)
    return True


class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cleanup_task = bot.loop.create_task(self._cleanup_history_loop())

    def cog_unload(self):
        self._cleanup_task.cancel()

    async def _cleanup_history_loop(self):
        """Dọn history AI không hoạt động sau AI_HISTORY_TTL giây (mặc định 2h)."""
        import asyncio as _asyncio
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await _asyncio.sleep(1800)  # kiểm tra mỗi 30 phút
            now = datetime.now(timezone.utc).timestamp()
            stale = [uid for uid, v in _ai_chat_history.items()
                     if now - v.get("last_used", 0) > AI_HISTORY_TTL]
            for uid in stale:
                _ai_chat_history.pop(uid, None)
            if stale:
                print(f"[AI] 🧹 Đã dọn {len(stale)} history cũ")

    @commands.command(name="ai")
    async def ai_command(self, ctx, *, prompt: str = None):
        """Admin điều khiển bot bằng ngôn ngữ tự nhiên qua tool calling.
        VD: .ai tạo kênh test riêng tư | .ai ban @user spam | .ai đóng ticket này"""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin dùng được lệnh này.")
        if not prompt:
            return await ctx.reply("❓ Dùng: `.ai <yêu cầu>` — vd `.ai tạo kênh test riêng tư`")

        async with ctx.typing():
            reply, pending = await run_ai_tools_agent(ctx, is_admin=True, user_content=prompt, history=[])

        if pending:
            tool_name, params = pending["name"], pending["params"]
            embed = discord.Embed(
                title="⚠️ Xác nhận hành động nguy hiểm",
                description=(
                    f"**Yêu cầu:** {prompt}\n**Tool:** `{tool_name}`\n**Params:** `{params}`\n\n"
                    f"⏰ Tự động huỷ sau 30 giây."
                ),
                color=0xED4245,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"Bởi {_uname_plain(ctx.author)}")
            view = AIConfirmView(ctx, tool_name, params)
            view.message = await ctx.reply(embed=embed, view=view)
            return

        await ctx.reply((reply or "✅ Đã xử lý.")[:2000])

    @commands.command(name="aireset", aliases=["airst"])
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Bắt câu trả lời khi admin reply trong forum Pending/Resolved."""
        if message.author.bot:
            return
        if message.author.id not in ADMIN_IDS:
            return

        # Reply trong forum PENDING (câu hỏi AI không chắc) hoặc RESOLVED (sửa đáp án)
        if isinstance(message.channel, discord.Thread):
            if message.channel.parent_id == AI_ASK_ADMIN_PENDING_FORUM_ID:
                if await _handle_pending_reply(self.bot, message):
                    return
            elif message.channel.parent_id == AI_ASK_ADMIN_RESOLVED_FORUM_ID:
                # Tin nhắn ĐẦU TIÊN trong thread (id == thread.id) là embed do bot gửi,
                # không phải admin -> bỏ qua, chỉ xử lý các tin nhắn SAU đó
                if message.id != message.channel.id:
                    if await _handle_resolved_edit(self.bot, message):
                        return

    # ── SLASH COMMANDS ──
    @discord.app_commands.command(name="aireset", description="Xoá toàn bộ lịch sử AI (admin)")
    async def slash_aireset(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        _ai_chat_history.clear()
        await interaction.response.send_message("✅ Đã xoá toàn bộ lịch sử AI.", ephemeral=True)

    @discord.app_commands.command(name="mychat", description="Xoá lịch sử chat AI của bạn")
    async def slash_mychat(self, interaction: discord.Interaction):
        if interaction.user.id in _ai_chat_history:
            del _ai_chat_history[interaction.user.id]
            await interaction.response.send_message("✅ Đã xoá lịch sử chat AI của bạn.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ Bạn chưa có lịch sử chat AI.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AICog(bot))
