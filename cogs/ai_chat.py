"""
cogs/ai_chat.py — AI Chat tích hợp Groq (llama-3.x, gemma2).
Lệnh: .ai, .aireset, .mychat
Kênh AI tự động trả lời mọi tin nhắn.
"""

import os
import json
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core.data import ADMIN_IDS, get_cfg_ai_channel, _uname_plain
from cogs.logger import send_log

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
DANGEROUS_ACTIONS = {"mod_ban", "mod_kick", "mod_mute"}  # Lệnh cần confirm trước khi chạy
_ai_chat_history: dict = {}   # user_id → {"messages": [...], "last_used": float timestamp}
AI_HISTORY_TTL = 7200  # 2 giờ — dọn history không hoạt động
_pending_actions: dict = {}   # user_id → {"action": ..., "params": ..., "missing": [...], "ctx_channel": int}
_pending_confirm: dict = {}   # user_id → action dict chờ xác nhận nguy hiểm

# System prompt để AI kiểm tra thiếu thông tin & hỏi lại
AI_CLARIFY_SYSTEM = """Bạn là AI kiểm tra xem một yêu cầu Discord có đủ thông tin để thực thi không.

CHỈ trả về JSON thuần, không markdown, không backtick.

Với mỗi action, kiểm tra params còn thiếu:

channel_create cần: name (tên kênh), type (text/voice), privacy (public/private)
role_create cần: name (tên role)
role_add/role_remove cần: role_name, user_id
mod_ban/kick/warn cần: user_id, reason
mod_mute cần: user_id, duration, reason
purge cần: amount
giveaway_end/reroll cần: message_id

Nếu ĐỦ thông tin:
{"status": "ready", "params": {...params đầy đủ...}}

Nếu THIẾU thông tin:
{"status": "need_info", "missing": ["field1", "field2"], "question": "câu hỏi ngắn gọn tiếng Việt để hỏi admin"}

Ví dụ:
- action=channel_create, params={name:"test"} → {"status": "need_info", "missing": ["type", "privacy"], "question": "Kênh `test` là text hay voice? Public hay private?"}
- action=channel_create, params={name:"test", type:"text", privacy:"public"} → {"status": "ready", "params": {name:"test", type:"text", privacy:"public"}}
- action=mod_ban, params={user_id:"MENTIONED_USER", reason:"spam"} → {"status": "ready", "params": {user_id:"MENTIONED_USER", reason:"spam"}}"""


AI_FILL_SYSTEM = """Bạn phân tích câu trả lời của admin để điền vào các field còn thiếu.

CHỈ trả về JSON thuần, không markdown, không backtick.

Input: {"missing_fields": [...], "answer": "câu trả lời của admin"}
Output: {"field1": "giá trị", "field2": "giá trị", ...}

Quy tắc:
- type: "text"/"voice" (từ: text, văn bản, chữ → "text"; voice, giọng nói, âm thanh → "voice")  
- privacy: "public"/"private" (từ: công khai, mọi người → "public"; riêng tư, private, ẩn → "private")
- duration: giữ nguyên chuỗi gốc (10m, 1h, 1d...)
- reason: giữ nguyên câu
- amount: parse số (50k→50000, 1tr→1000000)"""


# ─────────────────────────────────────────────
# AI EXECUTOR — phân tích intent & chạy lệnh
# ─────────────────────────────────────────────

AI_EXEC_SYSTEM = """Bạn là AI điều khiển bot Discord TuyTam Store. Phân tích yêu cầu của admin (kể cả sai chính tả, thiếu dấu, viết tắt) và trả về JSON.

CHỈ trả về JSON thuần, không markdown, không backtick, không giải thích.

Tự suy luận intent từ ngôn ngữ tự nhiên và map sang action phù hợp nhất:

NHÓM TICKET:
- "đóng/đóg/dong/close ticket" → {"action": "ticket_close", "params": {}}
- "tạo ticket panel" → {"action": "ticket_panel", "params": {}}

NHÓM CHANNEL:
- "tạo kênh/channel [tên]" → {"action": "channel_create", "params": {"name": "tên", "type": "text"}}
- "tạo voice/kênh voice [tên]" → {"action": "channel_create", "params": {"name": "tên", "type": "voice"}}
- "xoá kênh/channel này" → {"action": "channel_delete", "params": {}}
- "đổi tên kênh [tên mới]" → {"action": "channel_rename", "params": {"name": "tên mới"}}

NHÓM ROLE:
- "tạo role [tên]" → {"action": "role_create", "params": {"name": "tên"}}
- "xoá role [tên]" → {"action": "role_delete", "params": {"name": "tên"}}
- "thêm role [tên] cho @user" → {"action": "role_add", "params": {"role_name": "tên", "user_id": "MENTIONED_USER"}}
- "xoá role [tên] của @user" → {"action": "role_remove", "params": {"role_name": "tên", "user_id": "MENTIONED_USER"}}


NHÓM MOD:
- "ban @user [lý do]" → {"action": "mod_ban", "params": {"user_id": "MENTIONED_USER", "reason": "lý do"}}
- "kick @user [lý do]" → {"action": "mod_kick", "params": {"user_id": "MENTIONED_USER", "reason": "lý do"}}
- "mute @user [thời gian] [lý do]" → {"action": "mod_mute", "params": {"user_id": "MENTIONED_USER", "duration": "10m", "reason": "lý do"}}
- "warn @user [lý do]" → {"action": "mod_warn", "params": {"user_id": "MENTIONED_USER", "reason": "lý do"}}
- "xoá [số] tin nhắn" → {"action": "purge", "params": {"amount": số}}

NHÓM GIVEAWAY:
- "kết thúc/end giveaway [id]" → {"action": "giveaway_end", "params": {"message_id": "id"}}
- "reroll giveaway [id]" → {"action": "giveaway_reroll", "params": {"message_id": "id"}}

KHÔNG HIỂU: {"action": "unknown", "params": {"reason": "mô tả ngắn lý do"}}

QUY TẮC:
- Số tiền: "50k"=50000, "1tr"=1000000, "100đ"=100
- user_id: nếu có @mention → "MENTIONED_USER", không có → ""
- confirm_msg: mô tả ngắn gọn hành động bằng tiếng Việt

Format: {"action": "...", "params": {...}, "confirm_msg": "..."}"""



# ─────────────────────────────────────────────
# CONFIRM VIEW — cho lệnh nguy hiểm
# ─────────────────────────────────────────────
class AIConfirmView(discord.ui.View):
    """Yêu cầu admin xác nhận trước khi chạy lệnh nguy hiểm (ban/kick/mute)."""
    def __init__(self, ctx, action: dict):
        super().__init__(timeout=30)
        self.ctx    = ctx
        self.action = action

    @discord.ui.button(label="✅ Xác nhận", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Chỉ người ra lệnh mới xác nhận được.", ephemeral=True)
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="⚙️ Đang thực thi...", view=self)
        result = await _run_action(self.ctx, self.action)
        await interaction.followup.send(result)

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Chỉ người ra lệnh mới huỷ được.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(content="🚫 Đã huỷ.", view=None)

    async def on_timeout(self):
        try:
            await self.message.edit(content="⏰ Hết thời gian xác nhận — đã huỷ.", view=None)
        except Exception:
            pass


async def _call_groq_exec(prompt: str) -> dict:
    """Gọi Groq với system prompt executor, trả về dict JSON."""
    if not GROQ_API_KEY:
        return {"action": "unknown", "params": {"reason": "Chưa cài GROQ_API_KEY"}, "confirm_msg": ""}

    import aiohttp
    messages = [
        {"role": "system", "content": AI_EXEC_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    for model in GROQ_MODELS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "max_tokens": 256, "temperature": 0.1},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 429:
                        continue
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    raw = data["choices"][0]["message"]["content"].strip()
                    # Strip markdown nếu có
                    raw = re.sub(r"```json|```", "", raw).strip()
                    return json.loads(raw)
        except Exception:
            continue

    return {"action": "unknown", "params": {"reason": "AI tạm thời không khả dụng"}, "confirm_msg": ""}


async def _call_groq_clarify(action: str, params: dict) -> dict:
    """Kiểm tra params đủ chưa, nếu thiếu trả về câu hỏi."""
    if not GROQ_API_KEY:
        return {"status": "ready", "params": params}
    import aiohttp
    prompt = json.dumps({"action": action, "params": params}, ensure_ascii=False)
    messages = [
        {"role": "system", "content": AI_CLARIFY_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    for model in GROQ_MODELS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "max_tokens": 256, "temperature": 0.1},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status not in (200,): continue
                    data = await resp.json()
                    raw  = re.sub(r"```json|```", "", data["choices"][0]["message"]["content"]).strip()
                    return json.loads(raw)
        except Exception:
            continue
    return {"status": "ready", "params": params}


async def _call_groq_fill(missing_fields: list, answer: str) -> dict:
    """Parse câu trả lời của admin để điền vào fields còn thiếu."""
    if not GROQ_API_KEY:
        return {}
    import aiohttp
    prompt = json.dumps({"missing_fields": missing_fields, "answer": answer}, ensure_ascii=False)
    messages = [
        {"role": "system", "content": AI_FILL_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    for model in GROQ_MODELS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "max_tokens": 128, "temperature": 0.1},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status not in (200,): continue
                    data = await resp.json()
                    raw  = re.sub(r"```json|```", "", data["choices"][0]["message"]["content"]).strip()
                    return json.loads(raw)
        except Exception:
            continue
    return {}


async def _run_action(ctx, action: dict) -> str:
    """Thực thi action từ AI, trả về message kết quả."""
    act    = action.get("action", "unknown")
    params = action.get("params", {})
    mentioned_user = ctx.message.mentions[0] if ctx.message.mentions else None

    def resolve_user():
        if params.get("user_id") == "MENTIONED_USER" and mentioned_user:
            return mentioned_user
        return None

    async def invoke_cmd(name: str, *args):
        """Helper: invoke lệnh bot theo tên."""
        cmd = ctx.bot.get_command(name)
        if not cmd:
            return False, f"❌ Không tìm thấy lệnh `{name}`."
        try:
            ctx.message.content = f".{name} " + " ".join(str(a) for a in args)
            new_ctx = await ctx.bot.get_context(ctx.message)
            await cmd.invoke(new_ctx)
            return True, None
        except Exception as e:
            return False, f"❌ Lỗi `{name}`: {e}"

    # ── TICKET ──
    if act == "ticket_close":
        ok, err = await invoke_cmd("done")
        return "✅ Đã đóng ticket." if ok else err

    if act == "ticket_panel":
        ok, err = await invoke_cmd("ticketpanel")
        return "✅ Đã tạo ticket panel." if ok else err

    # ── CHANNEL ──
    if act == "channel_create":
        name     = params.get("name", "kênh-mới").lower().replace(" ", "-")
        ch_type  = params.get("type", "text")
        privacy  = params.get("privacy", "public")
        overwrites = {}
        if privacy == "private":
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                ctx.guild.me: discord.PermissionOverwrite(view_channel=True),
            }
        try:
            if ch_type == "voice":
                ch = await ctx.guild.create_voice_channel(name, category=ctx.channel.category, overwrites=overwrites)
            else:
                ch = await ctx.guild.create_text_channel(name, category=ctx.channel.category, overwrites=overwrites)
            label = f"{'🔒 private' if privacy == 'private' else '🌐 public'} {'voice' if ch_type == 'voice' else 'text'}"
            return f"✅ Đã tạo channel {ch.mention} ({label})."
        except Exception as e:
            return f"❌ Lỗi tạo channel: {e}"

    if act == "channel_delete":
        try:
            ch_name = ctx.channel.name
            await ctx.channel.delete(reason=f"Xoá bởi AI — admin {ctx.author}")
            return f"✅ Đã xoá channel `{ch_name}`."
        except Exception as e:
            return f"❌ Lỗi xoá channel: {e}"

    if act == "channel_rename":
        name = params.get("name", "")
        if not name:
            return "❌ Thiếu tên mới."
        try:
            old = ctx.channel.name
            await ctx.channel.edit(name=name.lower().replace(" ", "-"))
            return f"✅ Đổi tên channel `{old}` → `{name}`."
        except Exception as e:
            return f"❌ Lỗi đổi tên: {e}"

    # ── ROLE ──
    if act == "role_create":
        name = params.get("name", "")
        if not name:
            return "❌ Thiếu tên role."
        try:
            role = await ctx.guild.create_role(name=name, reason=f"Tạo bởi AI — admin {ctx.author}")
            return f"✅ Đã tạo role `{role.name}`."
        except Exception as e:
            return f"❌ Lỗi tạo role: {e}"

    if act == "role_delete":
        name = params.get("name", "")
        role = discord.utils.get(ctx.guild.roles, name=name)
        if not role:
            return f"❌ Không tìm thấy role `{name}`."
        try:
            await role.delete(reason=f"Xoá bởi AI — admin {ctx.author}")
            return f"✅ Đã xoá role `{name}`."
        except Exception as e:
            return f"❌ Lỗi xoá role: {e}"

    if act == "role_add":
        user = resolve_user()
        if not user:
            return "❌ Cần mention @user."
        role_name = params.get("role_name", "")
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            return f"❌ Không tìm thấy role `{role_name}`."
        try:
            await user.add_roles(role, reason=f"Thêm bởi AI — admin {ctx.author}")
            return f"✅ Đã thêm role `{role.name}` cho {user.display_name}."
        except Exception as e:
            return f"❌ Lỗi thêm role: {e}"

    if act == "role_remove":
        user = resolve_user()
        if not user:
            return "❌ Cần mention @user."
        role_name = params.get("role_name", "")
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            return f"❌ Không tìm thấy role `{role_name}`."
        try:
            await user.remove_roles(role, reason=f"Xoá bởi AI — admin {ctx.author}")
            return f"✅ Đã xoá role `{role.name}` của {user.display_name}."
        except Exception as e:
            return f"❌ Lỗi xoá role: {e}"

    # ── PURGE ──
    if act == "purge":
        amount = int(params.get("amount", 10))
        try:
            deleted = await ctx.channel.purge(limit=amount)
            return f"✅ Đã xoá {len(deleted)} tin nhắn."
        except Exception as e:
            return f"❌ Lỗi purge: {e}"


    # ── POINT ──
    # ── MOD ──
    if act in ("mod_ban", "mod_kick", "mod_mute", "mod_warn"):
        user = resolve_user()
        if not user:
            return "❌ Cần mention @user."
        reason = params.get("reason", "Không có lý do")
        cmd_map = {"mod_ban": "ban", "mod_kick": "kick", "mod_mute": "mute", "mod_warn": "warn"}
        if act == "mod_mute":
            ok, err = await invoke_cmd(cmd_map[act], user.id, params.get("duration", "10m"), reason)
        else:
            ok, err = await invoke_cmd(cmd_map[act], user.id, reason)
        if not ok: return err
        labels = {"mod_ban": "Ban", "mod_kick": "Kick", "mod_mute": "Mute", "mod_warn": "Warn"}
        return f"✅ {labels[act]} {user.display_name} — lý do: {reason}."

    # ── GIVEAWAY ──
    if act in ("giveaway_end", "giveaway_reroll"):
        msg_id = params.get("message_id", "")
        cmd_map = {"giveaway_end": "gend", "giveaway_reroll": "greroll"}
        ok, err = await invoke_cmd(cmd_map[act], msg_id)
        if not ok: return err
        labels = {"giveaway_end": "Kết thúc", "giveaway_reroll": "Reroll"}
        return f"✅ {labels[act]} giveaway."

    # ── UNKNOWN ──
    reason = params.get("reason", "Không hiểu yêu cầu")
    return f"🤔 **{reason}**\nThử mô tả rõ hơn hoặc dùng lệnh trực tiếp."


async def _call_groq(user_id: int, user_message: str) -> str:
    if not GROQ_API_KEY:
        return "❌ Chưa cài `GROQ_API_KEY` trong biến môi trường."

    import time as _time
    now = _time.time()

    # Dọn TTL — xóa history cũ hơn AI_HISTORY_TTL
    stale = [uid for uid, v in _ai_chat_history.items() if now - v.get("last_used", 0) > AI_HISTORY_TTL]
    for uid in stale:
        del _ai_chat_history[uid]

    entry = _ai_chat_history.setdefault(user_id, {"messages": [], "last_used": now})
    history = entry["messages"]
    history.append({"role": "user", "content": user_message})
    if len(history) > AI_HISTORY_LIMIT * 2:
        entry["messages"] = history[-(AI_HISTORY_LIMIT * 2):]
        history = entry["messages"]
    entry["last_used"] = now

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
                        print(f"[AI] ⚠️ Model {model} lỗi {resp.status}: {err[:200]}")
                        last_err = f"Lỗi {resp.status}"
                        continue
                    data  = await resp.json()
                    reply = data["choices"][0]["message"]["content"]
            _ai_chat_history[user_id]["messages"].append({"role": "assistant", "content": reply})
            _ai_chat_history[user_id]["last_used"] = _time.time()
            return reply
        except Exception as e:
            last_err = str(e)
            continue

    return f"⚠️ AI tạm thời không khả dụng ({last_err}). Vui lòng thử lại sau ít phút."


async def handle_ai_message(message: discord.Message):
    ai_ch_id = get_cfg_ai_channel()
    if not ai_ch_id or message.channel.id != ai_ch_id:
        return
    # Bỏ qua nếu là lệnh bot (bắt đầu bằng prefix . / / hoặc !)
    if message.content and message.content[0] in ('.', '/', '!'):
        return
    async with message.channel.typing():
        reply = await _call_groq(message.author.id, message.content)
    if len(reply) <= 2000:
        await message.reply(reply, mention_author=False)
    else:
        for chunk in [reply[i:i+1990] for i in range(0, len(reply), 1990)]:
            await message.channel.send(chunk)

    bot_ref = message._state._get_client()
    await send_log(
        bot_ref, "AI_USED", "AI Chat",
        fields=[
            ("👤 User",    f"{message.author.mention} (`{message.author.id}`)", True),
            ("💬 Tin nhắn", f"`{message.content[:200]}`",                       False),
            ("🤖 Phản hồi", f"`{reply[:200]}`",                                 False),
        ],
        user=message.author,
    )


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
        """Bắt câu trả lời khi admin đang trong trạng thái pending."""
        if message.author.bot:
            return
        if message.author.id not in ADMIN_IDS:
            return
        if message.author.id not in _pending_actions:
            return
        pending = _pending_actions[message.author.id]
        # Chỉ xử lý nếu cùng channel và không phải lệnh bot
        if message.channel.id != pending["ctx_channel"]:
            return
        if message.content.startswith((".","!","/")):
            return

        # Xoá pending ngay để tránh loop
        del _pending_actions[message.author.id]

        async with message.channel.typing():
            filled = await _call_groq_fill(pending["missing"], message.content)

        # Merge params
        params = {**pending["params"], **filled}
        action = {"action": pending["action"], "params": params, "confirm_msg": ""}

        # Kiểm tra lại lần nữa xem đã đủ chưa
        async with message.channel.typing():
            clarify = await _call_groq_clarify(pending["action"], params)

        if clarify.get("status") == "need_info":
            # Vẫn còn thiếu → hỏi tiếp
            _pending_actions[message.author.id] = {
                "action":      pending["action"],
                "params":      params,
                "missing":     clarify.get("missing", []),
                "ctx_channel": message.channel.id,
                "original":    pending["original"],
            }
            embed = discord.Embed(
                title="🤖 AI cần thêm thông tin",
                description=f"❓ {clarify.get('question', 'Vui lòng cung cấp thêm thông tin.')}",
                color=0xF0A500,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="Trả lời trực tiếp vào đây (không cần gõ .ai)")
            return await message.reply(embed=embed)

        # Đủ rồi → kiểm tra nguy hiểm trước khi thực thi
        action["params"] = clarify.get("params", params)
        ctx = await self.bot.get_context(message)

        if action.get("action") in DANGEROUS_ACTIONS:
            confirm_msg = action.get("confirm_msg", "Thực hiện hành động này")
            embed = discord.Embed(
                title="⚠️ Xác nhận lệnh nguy hiểm",
                description=f"**Yêu cầu:** {pending['original']}\n**Thực hiện:** {confirm_msg}\n\n⏰ Tự động huỷ sau 30 giây.",
                color=0xED4245,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"Bởi {_uname_plain(message.author)}")
            view = AIConfirmView(ctx, action)
            view.message = await message.reply(embed=embed, view=view)
            return

        embed = discord.Embed(
            title="🤖 AI → Bot",
            description=f"**Yêu cầu:** {pending['original']}\n**Thực hiện:** Đang xử lý...",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Bởi {_uname_plain(message.author)}")
        await message.reply(embed=embed)

        async with message.channel.typing():
            result = await _run_action(ctx, action)
        await message.channel.send(result)

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
