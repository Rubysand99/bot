"""
cogs/ai_chat.py — AI Chat tích hợp Groq (llama-3.x, gemma2).
Lệnh: .ai, .aireset, .mychat
Kênh AI tự động trả lời mọi tin nhắn.
"""

import os
import json
import re
import asyncio
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands

from core.data import ADMIN_IDS, get_cfg_ai_channel, _uname_plain, load_data, fmt_amount

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
_ai_chat_history: dict = {}   # user_id → list of {"role": ..., "content": ...}
_pending_actions: dict = {}   # user_id → {"action": ..., "params": ..., "missing": [...], "ctx_channel": int}
_pending_confirm: dict = {}   # user_id → {"action": dict, "ctx_channel": int, "prompt": str}
_undo_stack:      dict = {}   # user_id → {"description": str, "undo_fn": coroutine factory}

# Các action nguy hiểm cần xác nhận trước khi thực thi
DANGEROUS_ACTIONS = {"mod_ban", "mod_kick", "channel_delete", "purge", "role_delete"}

# System prompt để AI kiểm tra thiếu thông tin & hỏi lại
AI_CLARIFY_SYSTEM = """Bạn là AI kiểm tra xem một yêu cầu Discord có đủ thông tin để thực thi không.

CHỈ trả về JSON thuần, không markdown, không backtick.

GIÁ TRỊ MẶC ĐỊNH (tự điền, TUYỆT ĐỐI không hỏi):
- channel_create: type mặc định "text", privacy mặc định "public"
- mod_ban/kick/warn: reason mặc định "Vi phạm nội quy"
- mod_mute: duration mặc định "10m", reason mặc định "Vi phạm nội quy"
- purge: amount mặc định 10

QUAN TRỌNG: Với channel_create, KHÔNG BAO GIỜ hỏi về type hoặc privacy. Luôn tự điền default nếu thiếu.
Nếu params đã có type hoặc privacy (dù bất kỳ giá trị nào), giữ nguyên giá trị đó.

Với mỗi action, CHỈ hỏi khi thiếu thông tin BẮT BUỘC (không có default):

ticket_close/ticket_panel → không cần params gì cả, luôn ready
channel_create → BẮT BUỘC: name. Tự điền type="text", privacy="public" nếu thiếu. KHÔNG hỏi type hay privacy.
channel_delete/channel_rename → BẮT BUỘC: name
role_create/role_delete → BẮT BUỘC: name
role_add/role_remove → BẮT BUỘC: role_name, user_id
balance_add/sub/set → BẮT BUỘC: user_id, amount
point_add/set → BẮT BUỘC: user_id, amount
mod_ban/kick/warn → BẮT BUỘC: user_id (reason có default)
mod_mute → BẮT BUỘC: user_id (duration và reason có default)
purge → KHÔNG bắt buộc (amount có default 10)
giveaway_end/reroll → BẮT BUỘC: message_id

Nếu ĐỦ thông tin (kể cả dùng default):
{"status": "ready", "params": {...params đầy đủ kể cả default...}}

Nếu THIẾU thông tin BẮT BUỘC:
{"status": "need_info", "missing": ["field1"], "question": "câu hỏi ngắn gọn tiếng Việt"}

Ví dụ:
- action=ticket_panel, params={} → {"status": "ready", "params": {}}
- action=channel_create, params={name:"test"} → {"status": "ready", "params": {"name":"test","type":"text","privacy":"public"}}
- action=purge, params={} → {"status": "ready", "params": {"amount": 10}}
- action=mod_ban, params={user_id:"MENTIONED_USER"} → {"status": "ready", "params": {"user_id":"MENTIONED_USER","reason":"Vi phạm nội quy"}}
- action=role_add, params={role_name:"VIP"} → {"status": "need_info", "missing": ["user_id"], "question": "Thêm role VIP cho ai? (mention @user)"}"""


AI_FILL_SYSTEM = """Bạn phân tích câu trả lời của admin để điền vào các field còn thiếu.

CHỈ trả về JSON thuần, không markdown, không backtick.

Input: {"action": "tên action", "missing_fields": [...], "answer": "câu trả lời của admin"}
Output: {"field1": "giá trị", "field2": "giá trị", ...}

Quy tắc mapping:
- type: "text"/"voice" (text/văn bản/chữ → "text"; voice/giọng/âm thanh → "voice")
- privacy: "public"/"private" (công khai/mọi người → "public"; riêng tư/private/ẩn → "private")
- duration: giữ nguyên chuỗi (10m, 1h, 1d...)
- reason: giữ nguyên câu
- amount: parse số (50k→50000, 1tr→1000000, 100đ→100)
- name: giữ nguyên chuỗi (tên kênh, tên role, v.v.)

Ngữ cảnh action để suy luận:
- Nếu action=ticket_panel và answer là tên sản phẩm/game (vd: "skeleton", "money") → đây là loại panel, map vào field "panel_type" hoặc "name"
- Nếu action=balance_add/sub/set và answer là số → map vào "amount"
- Nếu answer là một từ duy nhất và chỉ thiếu 1 field → map thẳng vào field đó
- Nếu không chắc → vẫn cố gắng map hợp lý nhất, không trả về {}"""


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
- "tạo kênh/channel [tên]" → {"action": "channel_create", "params": {"name": "tên", "type": "text", "privacy": "public"}}
- "tạo kênh/channel [tên] private/riêng tư" → {"action": "channel_create", "params": {"name": "tên", "type": "text", "privacy": "private"}}
- "tạo kênh text [tên] private/riêng tư" → {"action": "channel_create", "params": {"name": "tên", "type": "text", "privacy": "private"}}
- "tạo voice/kênh voice [tên]" → {"action": "channel_create", "params": {"name": "tên", "type": "voice", "privacy": "public"}}
- "tạo voice/kênh voice [tên] private/riêng tư" → {"action": "channel_create", "params": {"name": "tên", "type": "voice", "privacy": "private"}}
- "xoá kênh/channel này" → {"action": "channel_delete", "params": {}}
- "đổi tên kênh [tên mới]" → {"action": "channel_rename", "params": {"name": "tên mới"}}

NHÓM ROLE:
- "tạo role [tên]" → {"action": "role_create", "params": {"name": "tên"}}
- "xoá role [tên]" → {"action": "role_delete", "params": {"name": "tên"}}
- "thêm role [tên] cho @user" → {"action": "role_add", "params": {"role_name": "tên", "user_id": "MENTIONED_USER"}}
- "xoá role [tên] của @user" → {"action": "role_remove", "params": {"role_name": "tên", "user_id": "MENTIONED_USER"}}

NHÓM BALANCE:
- "cộng/thêm [số]k/đ cho @user" → {"action": "balance_add", "params": {"user_id": "MENTIONED_USER", "amount": số}}
- "trừ [số]k/đ của @user" → {"action": "balance_sub", "params": {"user_id": "MENTIONED_USER", "amount": số}}
- "set/đặt balance @user [số]" → {"action": "balance_set", "params": {"user_id": "MENTIONED_USER", "amount": số}}

NHÓM POINT:
- "cộng/thêm [số] point cho @user" → {"action": "point_add", "params": {"user_id": "MENTIONED_USER", "amount": số}}
- "set point @user [số]" → {"action": "point_set", "params": {"user_id": "MENTIONED_USER", "amount": số}}

NHÓM MOD:
- "ban @user [lý do]" → {"action": "mod_ban", "params": {"user_id": "MENTIONED_USER", "reason": "lý do"}}
- "kick @user [lý do]" → {"action": "mod_kick", "params": {"user_id": "MENTIONED_USER", "reason": "lý do"}}
- "mute @user [thời gian] [lý do]" → {"action": "mod_mute", "params": {"user_id": "MENTIONED_USER", "duration": "10m", "reason": "lý do"}}
- "warn @user [lý do]" → {"action": "mod_warn", "params": {"user_id": "MENTIONED_USER", "reason": "lý do"}}
- "xoá [số] tin nhắn" → {"action": "purge", "params": {"amount": số}}

NHÓM GIVEAWAY:
- "kết thúc/end giveaway [id]" → {"action": "giveaway_end", "params": {"message_id": "id"}}
- "reroll giveaway [id]" → {"action": "giveaway_reroll", "params": {"message_id": "id"}}

NHÓM MINIGAME:

KHÔNG HIỂU: {"action": "unknown", "params": {"reason": "mô tả ngắn lý do"}}

QUY TẮC:
- Số tiền: "50k"=50000, "1tr"=1000000, "100đ"=100
- user_id: nếu có @mention → "MENTIONED_USER", không có → ""
- confirm_msg: mô tả ngắn gọn hành động bằng tiếng Việt

Format: {"action": "...", "params": {...}, "confirm_msg": "..."}"""


async def _call_groq_exec(prompt: str) -> dict:
    """Gọi Groq với system prompt executor, trả về dict JSON."""
    if not GROQ_API_KEY:
        return {"action": "unknown", "params": {"reason": "Chưa cài GROQ_API_KEY"}, "confirm_msg": ""}

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


async def _call_groq_fill(missing_fields: list, answer: str, action: str = "") -> dict:
    """Parse câu trả lời của admin để điền vào fields còn thiếu."""
    if not GROQ_API_KEY:
        return {}
    prompt = json.dumps({"action": action, "missing_fields": missing_fields, "answer": answer}, ensure_ascii=False)
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


async def _run_action(ctx, action: dict) -> tuple[str, object]:
    """Thực thi action từ AI, trả về (message kết quả, undo_fn hoặc None)."""
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
        return ("✅ Đã đóng ticket." if ok else err, None)

    if act == "ticket_panel":
        ok, err = await invoke_cmd("ticketpanel")
        return ("✅ Đã tạo ticket panel." if ok else err, None)

    # ── CHANNEL ──
    if act == "channel_create":
        name     = params.get("name", "kênh-mới").lower().replace(" ", "-")
        ch_type  = params.get("type", "text")
        privacy  = params.get("privacy", "public")

        bot_perms = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True,
            manage_messages=True, read_message_history=True, embed_links=True, attach_files=True,
        )
        overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False), ctx.guild.me: bot_perms} if privacy == "private" else {ctx.guild.me: bot_perms}
        try:
            if ch_type == "voice":
                ch = await ctx.guild.create_voice_channel(name, category=ctx.channel.category, overwrites=overwrites)
            else:
                ch = await ctx.guild.create_text_channel(name, category=ctx.channel.category, overwrites=overwrites)
            label = f"{'🔒 private' if privacy == 'private' else '🌐 public'} {'voice' if ch_type == 'voice' else 'text'}"

            async def _undo_channel_create(channel=ch):
                await channel.delete(reason="Undo tạo channel bởi AI")
            return (f"✅ Đã tạo channel {ch.mention} ({label}).", _undo_channel_create)
        except Exception as e:
            return (f"❌ Lỗi tạo channel: {e}", None)

    if act == "channel_delete":
        try:
            ch_name = ctx.channel.name
            # Lưu lại category và overwrites để undo
            cat = ctx.channel.category
            ch_type_save = type(ctx.channel)
            await ctx.channel.delete(reason=f"Xoá bởi AI — admin {ctx.author}")
            return (f"✅ Đã xoá channel `{ch_name}`.", None)  # Không thể undo xoá kênh
        except Exception as e:
            return (f"❌ Lỗi xoá channel: {e}", None)

    if act == "channel_rename":
        name = params.get("name", "")
        if not name:
            return ("❌ Thiếu tên mới.", None)
        try:
            old = ctx.channel.name
            await ctx.channel.edit(name=name.lower().replace(" ", "-"))
            async def _undo_rename(channel=ctx.channel, old_name=old):
                await channel.edit(name=old_name, reason="Undo đổi tên channel bởi AI")
            return (f"✅ Đổi tên channel `{old}` → `{name}`.", _undo_rename)
        except Exception as e:
            return (f"❌ Lỗi đổi tên: {e}", None)

    # ── ROLE ──
    if act == "role_create":
        name = params.get("name", "")
        if not name:
            return ("❌ Thiếu tên role.", None)
        try:
            role = await ctx.guild.create_role(name=name, reason=f"Tạo bởi AI — admin {ctx.author}")
            async def _undo_role_create(r=role):
                await r.delete(reason="Undo tạo role bởi AI")
            return (f"✅ Đã tạo role `{role.name}`.", _undo_role_create)
        except Exception as e:
            return (f"❌ Lỗi tạo role: {e}", None)

    if act == "role_delete":
        name = params.get("name", "")
        role = discord.utils.get(ctx.guild.roles, name=name)
        if not role:
            return (f"❌ Không tìm thấy role `{name}`.", None)
        try:
            await role.delete(reason=f"Xoá bởi AI — admin {ctx.author}")
            return (f"✅ Đã xoá role `{name}`.", None)  # Không thể restore role đã xoá
        except Exception as e:
            return (f"❌ Lỗi xoá role: {e}", None)

    if act == "role_add":
        user = resolve_user()
        if not user:
            return ("❌ Cần mention @user.", None)
        role_name = params.get("role_name", "")
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            return (f"❌ Không tìm thấy role `{role_name}`.", None)
        try:
            await user.add_roles(role, reason=f"Thêm bởi AI — admin {ctx.author}")
            async def _undo_role_add(u=user, r=role):
                await u.remove_roles(r, reason="Undo thêm role bởi AI")
            return (f"✅ Đã thêm role `{role.name}` cho {user.display_name}.", _undo_role_add)
        except Exception as e:
            return (f"❌ Lỗi thêm role: {e}", None)

    if act == "role_remove":
        user = resolve_user()
        if not user:
            return ("❌ Cần mention @user.", None)
        role_name = params.get("role_name", "")
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            return (f"❌ Không tìm thấy role `{role_name}`.", None)
        try:
            await user.remove_roles(role, reason=f"Xoá bởi AI — admin {ctx.author}")
            async def _undo_role_remove(u=user, r=role):
                await u.add_roles(r, reason="Undo xoá role bởi AI")
            return (f"✅ Đã xoá role `{role.name}` của {user.display_name}.", _undo_role_remove)
        except Exception as e:
            return (f"❌ Lỗi xoá role: {e}", None)

    # ── PURGE ──
    if act == "purge":
        amount = int(params.get("amount", 10))
        try:
            deleted = await ctx.channel.purge(limit=amount)
            return (f"✅ Đã xoá {len(deleted)} tin nhắn.", None)  # Không thể undo purge
        except Exception as e:
            return (f"❌ Lỗi purge: {e}", None)

    # ── BALANCE ──
    if act in ("balance_add", "balance_sub", "balance_set"):
        user = resolve_user()
        if not user:
            return ("❌ Cần mention @user.", None)
        amount = int(params.get("amount", 0))
        cmd_map = {"balance_add": "addbal", "balance_sub": "subbal", "balance_set": "setbal"}
        ok, err = await invoke_cmd(cmd_map[act], user.id, amount)
        if not ok: return (err, None)
        labels = {"balance_add": "Cộng", "balance_sub": "Trừ", "balance_set": "Set"}
        # Undo: reverse operation
        undo_cmd = {"balance_add": "subbal", "balance_sub": "addbal"}
        if act in undo_cmd:
            async def _undo_bal(u=user, a=amount, cmd=undo_cmd[act]):
                undo_ctx_like = type("FakeCtx", (), {"bot": ctx.bot, "message": ctx.message, "guild": ctx.guild, "author": ctx.author, "channel": ctx.channel})()
                undo_ctx_like.message = ctx.message
                c = ctx.bot.get_command(cmd)
                if c:
                    ctx.message.content = f".{cmd} {u.id} {a}"
                    nc = await ctx.bot.get_context(ctx.message)
                    await c.invoke(nc)
            return (f"✅ {labels[act]} {amount:,} VNĐ cho {user.display_name}.", _undo_bal)
        return (f"✅ {labels[act]} {amount:,} VNĐ cho {user.display_name}.", None)

    # ── POINT ──
    if act in ("point_add", "point_set"):
        user = resolve_user()
        if not user:
            return ("❌ Cần mention @user.", None)
        amount = int(params.get("amount", 0))
        cmd_map = {"point_add": "addpoint", "point_set": "setpoint"}
        ok, err = await invoke_cmd(cmd_map[act], user.id, amount)
        if not ok: return (err, None)
        labels = {"point_add": "Cộng", "point_set": "Set"}
        return (f"✅ {labels[act]} {amount} point cho {user.display_name}.", None)

    # ── MOD ──
    if act in ("mod_ban", "mod_kick", "mod_mute", "mod_warn"):
        user = resolve_user()
        if not user:
            return ("❌ Cần mention @user.", None)
        reason = params.get("reason", "Không có lý do")
        cmd_map = {"mod_ban": "ban", "mod_kick": "kick", "mod_mute": "mute", "mod_warn": "warn"}
        if act == "mod_mute":
            ok, err = await invoke_cmd(cmd_map[act], user.id, params.get("duration", "10m"), reason)
        else:
            ok, err = await invoke_cmd(cmd_map[act], user.id, reason)
        if not ok: return (err, None)
        labels = {"mod_ban": "Ban", "mod_kick": "Kick", "mod_mute": "Mute", "mod_warn": "Warn"}
        return (f"✅ {labels[act]} {user.display_name} — lý do: {reason}.", None)

    # ── GIVEAWAY ──
    if act in ("giveaway_end", "giveaway_reroll"):
        msg_id = params.get("message_id", "")
        cmd_map = {"giveaway_end": "gend", "giveaway_reroll": "greroll"}
        ok, err = await invoke_cmd(cmd_map[act], msg_id)
        if not ok: return (err, None)
        labels = {"giveaway_end": "Kết thúc", "giveaway_reroll": "Reroll"}
        return (f"✅ {labels[act]} giveaway.", None)

    # ── UNKNOWN ──
    reason = params.get("reason", "Không hiểu yêu cầu")
    return (f"🤔 **{reason}**\nThử mô tả rõ hơn hoặc dùng lệnh trực tiếp.", None)


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


class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    @commands.command(name="ai")
    async def ai_cmd(self, ctx, *, prompt: str = None):
        if not prompt:
            if ctx.author.id not in ADMIN_IDS:
                return
            embed = discord.Embed(
                title="🤖 Hướng dẫn dùng AI", color=0x5865F2,
                description=(
                    "**`.ai <câu hỏi/yêu cầu>`** — Chat với AI hoặc điều khiển bot\n\n"
                    "💬 **Chat thường:**\n"
                    "› `.ai nitro là gì?`\n"
                    "› `.ai hôm nay có gì hot không`\n\n"
                    "🔧 **Điều khiển bot** *(Admin)*:\n"
                    "› `.ai đóng ticket này`\n"
                    "› `.ai cộng 50k cho @user`\n"
                    "› `.ai ban @user lý do spam`\n\n"
                    "📋 **Lệnh đặc biệt:**\n"
                    "› `.ai tomtat [n]` — Tóm tắt `n` tin nhắn gần nhất\n"
                    "› `.ai dich <ngôn ngữ> <văn bản>` — Dịch văn bản\n"
                    "› `.ai phantich @user` — Phân tích phong cách chat\n"
                    "› `.ai reset` — Xoá lịch sử hội thoại\n\n"
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

        # ── UNDO ──
        if sub == "undo":
            if ctx.author.id not in ADMIN_IDS:
                return
            entry = _undo_stack.pop(ctx.author.id, None)
            if not entry:
                return await ctx.reply("❌ Không có hành động nào để hoàn tác.")
            try:
                await entry["undo_fn"]()
                await ctx.reply(f"↩️ Đã hoàn tác: {entry['description']}")
            except Exception as e:
                await ctx.reply(f"❌ Không thể hoàn tác: {e}")
            return

        # ── BÁO CÁO HÀNG NGÀY ──
        if sub in ("baocao", "report"):
            if ctx.author.id not in ADMIN_IDS:
                return
            return await _send_daily_report(ctx.channel, ctx.guild)

        # ── GIỜ CAO ĐIỂM ──
        if sub in ("caodiem", "peak"):
            if ctx.author.id not in ADMIN_IDS:
                return
            return await _send_peak_hours(ctx.channel)

        # ── CÀI KÊNH BÁO CÁO ──
        if sub == "setreport":
            if ctx.author.id not in ADMIN_IDS:
                return
            ch = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
            from core.data import set_log_channel_db
            set_log_channel_db("REPORT", ch.id)
            return await ctx.reply(f"✅ Báo cáo tự động sẽ gửi vào {ch.mention} lúc **8:00 sáng** mỗi ngày.")

        # ── Chỉ ADMIN ──
        if ctx.author.id not in ADMIN_IDS:
            return

        async with ctx.typing():
            action = await _call_groq_exec(prompt)

        act = action.get("action", "unknown")

        if act == "unknown":
            # AI không nhận ra lệnh → chat thường
            async with ctx.typing():
                reply = await _call_groq(ctx.author.id, prompt)
            if len(reply) <= 2000:
                return await ctx.reply(reply)
            for chunk in [reply[i:i+1990] for i in range(0, len(reply), 1990)]:
                await ctx.channel.send(chunk)
            return

        # Kiểm tra params đủ chưa
        async with ctx.typing():
            clarify = await _call_groq_clarify(act, action.get("params", {}))

        if clarify.get("status") == "need_info":
            # Lưu trạng thái chờ
            _pending_actions[ctx.author.id] = {
                "action":      act,
                "params":      action.get("params", {}),
                "missing":     clarify.get("missing", []),
                "ctx_channel": ctx.channel.id,
                "original":    prompt,
            }
            embed = discord.Embed(
                title="🤖 AI cần thêm thông tin",
                description=f"**Yêu cầu:** {prompt}\n\n❓ {clarify.get('question', 'Vui lòng cung cấp thêm thông tin.')}",
                color=0xF0A500,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="Trả lời trực tiếp vào đây (không cần gõ .ai)")
            return await ctx.reply(embed=embed)

        # Đủ thông tin → kiểm tra có cần confirm không
        action["params"] = clarify.get("params", action.get("params", {}))

        if act in DANGEROUS_ACTIONS:
            # Lưu vào pending_confirm, hỏi xác nhận
            _pending_confirm[ctx.author.id] = {
                "action":      action,
                "ctx_channel": ctx.channel.id,
                "prompt":      prompt,
            }
            label_map = {
                "mod_ban": f"🔨 Ban **{action['params'].get('user_id', 'user')}**",
                "mod_kick": f"👢 Kick **{action['params'].get('user_id', 'user')}**",
                "channel_delete": f"🗑️ Xoá kênh **{ctx.channel.name}**",
                "purge": f"🧹 Xoá **{action['params'].get('amount', 10)}** tin nhắn",
                "role_delete": f"🗑️ Xoá role **{action['params'].get('name', '?')}**",
            }
            embed = discord.Embed(
                title="⚠️ Xác nhận hành động nguy hiểm",
                description=f"{label_map.get(act, act)}\n\n**Gõ `có` hoặc `yes` để xác nhận, `không` để huỷ.**",
                color=0xE74C3C,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="Trả lời trực tiếp vào đây • Hết 30 giây sẽ tự huỷ")
            await ctx.reply(embed=embed)

            async def _expire_confirm(uid=ctx.author.id):
                await asyncio.sleep(30)
                if uid in _pending_confirm:
                    del _pending_confirm[uid]
            asyncio.create_task(_expire_confirm())
            return

        # Không nguy hiểm → thực thi luôn
        confirm = action.get("confirm_msg", "")
        embed = discord.Embed(
            title="🤖 AI → Bot",
            description=f"**Yêu cầu:** {prompt}\n**Thực hiện:** {confirm}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)
        async with ctx.typing():
            result, undo_fn = await _run_action(ctx, action)
        if undo_fn:
            _undo_stack[ctx.author.id] = {"description": result, "undo_fn": undo_fn}
        return await ctx.send(result + (" _(Gõ `.ai undo` để hoàn tác)_" if undo_fn else ""))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Bắt câu trả lời khi admin đang trong trạng thái pending / confirm."""
        if message.author.bot:
            return
        if message.author.id not in ADMIN_IDS:
            return

        uid = message.author.id
        content = message.content.strip()

        # ── XỬ LÝ CONFIRM ──
        if uid in _pending_confirm:
            pending = _pending_confirm[uid]
            if message.channel.id != pending["ctx_channel"]:
                pass  # không return, vẫn check pending_actions bên dưới
            elif content.startswith((".", "!", "/")):
                pass
            else:
                del _pending_confirm[uid]
                if content.lower() in ("có", "co", "yes", "y", "ok", "xác nhận", "đồng ý"):
                    ctx = await self.bot.get_context(message)
                    async with message.channel.typing():
                        result, undo_fn = await _run_action(ctx, pending["action"])
                    if undo_fn:
                        _undo_stack[uid] = {"description": result, "undo_fn": undo_fn}
                    await message.channel.send(result + (" _(Gõ `.ai undo` để hoàn tác)_" if undo_fn else ""))
                else:
                    await message.channel.send("🚫 Đã huỷ hành động.")
                return

        if uid not in _pending_actions:
            return
        pending = _pending_actions[uid]
        # Chỉ xử lý nếu cùng channel và không phải lệnh bot
        if message.channel.id != pending["ctx_channel"]:
            return
        if content.startswith((".", "!", "/")):
            return

        # Xoá pending ngay để tránh loop
        del _pending_actions[uid]

        async with message.channel.typing():
            filled = await _call_groq_fill(pending["missing"], message.content, pending["action"])


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

        # Đủ rồi → thực thi
        action["params"] = clarify.get("params", params)
        embed = discord.Embed(
            title="🤖 AI → Bot",
            description=f"**Yêu cầu:** {pending['original']}\n**Thực hiện:** Đang xử lý...",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Bởi {_uname_plain(message.author)}")
        await message.reply(embed=embed)

        # Tạo fake ctx từ message gốc
        ctx = await self.bot.get_context(message)
        async with message.channel.typing():
            result, undo_fn = await _run_action(ctx, action)
        if undo_fn:
            _undo_stack[uid] = {"description": result, "undo_fn": undo_fn}
        await message.channel.send(result + (" _(Gõ `.ai undo` để hoàn tác)_" if undo_fn else ""))

    # ── SLASH COMMANDS ──
    @discord.app_commands.command(name="ai", description="Chat với AI Groq")
    @discord.app_commands.describe(prompt="Câu hỏi hoặc yêu cầu của bạn")
    async def slash_ai(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer()
        reply = await _call_groq(interaction.user.id, prompt)
        if len(reply) <= 2000:
            await interaction.followup.send(reply)
        else:
            for chunk in [reply[i:i+1990] for i in range(0, len(reply), 1990)]:
                await interaction.followup.send(chunk)

    @discord.app_commands.command(name="aireset", description="Xoá toàn bộ lịch sử AI (admin)")
    async def slash_aireset(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.")
        _ai_chat_history.clear()
        await interaction.response.send_message("✅ Đã xoá toàn bộ lịch sử AI.")

    @discord.app_commands.command(name="mychat", description="Xoá lịch sử chat AI của bạn")
    async def slash_mychat(self, interaction: discord.Interaction):
        if interaction.user.id in _ai_chat_history:
            del _ai_chat_history[interaction.user.id]
            await interaction.response.send_message("✅ Đã xoá lịch sử chat AI của bạn.")
        else:
            await interaction.response.send_message("ℹ️ Bạn chưa có lịch sử chat AI.")

    async def cog_load(self):
        self._daily_report_task = asyncio.create_task(self._daily_report_loop())

    def cog_unload(self):
        if hasattr(self, "_daily_report_task"):
            self._daily_report_task.cancel()

    async def _daily_report_loop(self):
        """Tự động gửi báo cáo lúc 8:00 sáng (UTC+7) mỗi ngày."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.now(timezone.utc)
            # 8:00 sáng UTC+7 = 1:00 UTC
            target_hour_utc = 1
            next_run = now.replace(hour=target_hour_utc, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run = next_run.replace(day=next_run.day + 1)
            wait_secs = (next_run - now).total_seconds()
            await asyncio.sleep(wait_secs)

            # Tìm kênh log để gửi báo cáo
            from core.data import get_log_channel_by_group, get_or_fetch_channel
            ch_id = get_log_channel_by_group("REPORT") or get_log_channel_by_group("BANKING")
            if not ch_id:
                continue
            for guild in self.bot.guilds:
                ch = await get_or_fetch_channel(self.bot, ch_id)
                if ch:
                    await _send_daily_report(ch, guild)
                    break


# ══════════════════════════════════════════
# BÁO CÁO & PHÂN TÍCH
# ══════════════════════════════════════════

async def _send_daily_report(channel, guild):
    """Gửi báo cáo tổng hợp ngày hôm qua."""
    from cogs.banking import get_bank_txs, fmt_vnd, _stats_period

    now = datetime.now(timezone.utc)
    # Hôm qua (UTC+7)
    tz_offset = 7 * 3600
    yesterday_start = (now.replace(hour=0, minute=0, second=0, microsecond=0)
                       .replace(day=now.day - 1 if now.hour < 17 else now.day))

    data = load_data()
    history = data.get("ticket_history", [])

    # Tickets hôm qua
    yesterday_tickets = []
    for t in history:
        try:
            dt = datetime.fromisoformat(t.get("closed_at", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            # So sánh theo ngày VN (UTC+7)
            dt_vn_date = (dt.timestamp() + tz_offset) // 86400
            now_vn_date = (now.timestamp() + tz_offset) // 86400
            if dt_vn_date == now_vn_date - 1:
                yesterday_tickets.append(t)
        except Exception:
            continue

    total_revenue   = sum(t.get("amount", 0) for t in yesterday_tickets)
    ticket_count    = len(yesterday_tickets)
    avg_per_ticket  = total_revenue // ticket_count if ticket_count else 0

    # Top sản phẩm
    item_counts: dict = {}
    for t in yesterday_tickets:
        item = t.get("item_type", "other")
        item_counts[item] = item_counts.get(item, 0) + 1
    top_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    # Banking hôm qua
    txs = get_bank_txs()
    bank_yesterday = _stats_period(txs, yesterday_start)

    embed = discord.Embed(
        title=f"📊 Báo Cáo Ngày — {(now.replace(day=now.day - 1)).strftime('%d/%m/%Y')}",
        color=0x2ECC71,
        timestamp=now,
    )
    embed.add_field(
        name="🎫 Ticket",
        value=f"Tổng: **{ticket_count}** ticket\nDoanh thu: **{fmt_amount(total_revenue)}**\nTB/ticket: **{fmt_amount(avg_per_ticket)}**",
        inline=True,
    )
    embed.add_field(
        name="🏦 Ngân hàng",
        value=f"📥 Vào: **{fmt_vnd(bank_yesterday['in'])}**\n📤 Ra: **{fmt_vnd(bank_yesterday['out'])}**\n💰 Net: **{fmt_vnd(bank_yesterday['net'])}**",
        inline=True,
    )
    if top_items:
        _labels = {"money": "💰 Money", "skeleton": "💀 Skeleton", "other": "📦 Khác"}
        lines = [f"{_labels.get(k, k)}: **{v}** lần" for k, v in top_items]
        embed.add_field(name="🏆 Sản phẩm bán chạy", value="\n".join(lines), inline=False)

    # So sánh với hôm kia
    if ticket_count == 0 and total_revenue == 0:
        embed.description = "📭 Không có giao dịch nào hôm qua."
    embed.set_footer(text="TuyTam Store  •  Báo cáo tự động lúc 8:00 sáng  •  Dùng .ai baocao để xem ngay")
    await channel.send(embed=embed)


async def _send_peak_hours(channel):
    """Phân tích giờ cao điểm dựa trên ticket_history."""

    data    = load_data()
    history = data.get("ticket_history", [])

    if len(history) < 10:
        return await channel.send("❌ Cần ít nhất 10 ticket trong lịch sử để phân tích giờ cao điểm.")

    # Đếm số ticket theo giờ (UTC+7)
    hour_counts = [0] * 24
    for t in history:
        try:
            dt = datetime.fromisoformat(t.get("closed_at", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            hour_vn = (dt.hour + 7) % 24
            hour_counts[hour_vn] += 1
        except Exception:
            continue

    total = sum(hour_counts)
    if total == 0:
        return await channel.send("❌ Không đủ dữ liệu.")

    # Top 5 giờ cao điểm
    top5 = sorted(range(24), key=lambda h: hour_counts[h], reverse=True)[:5]
    # Giờ thấp điểm nhất (chỉ lấy giờ có ít nhất 1 ticket)
    low = sorted([h for h in range(24) if hour_counts[h] > 0], key=lambda h: hour_counts[h])[:3]

    # Build bar chart bằng emoji
    max_count = max(hour_counts)
    bar_lines  = []
    for h in range(24):
        pct   = hour_counts[h] / max_count if max_count else 0
        bars  = int(pct * 10)
        tag   = " 🔥" if h in top5[:3] else (" 💤" if h in low else "")
        bar_lines.append(f"`{h:02d}h` {'█' * bars}{'░' * (10 - bars)} **{hour_counts[h]}**{tag}")

    embed = discord.Embed(
        title="⏰ Phân Tích Giờ Cao Điểm",
        description="\n".join(bar_lines),
        color=0xF39C12,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="🔥 Giờ bận nhất",
        value="\n".join(f"`{h:02d}:00–{h+1:02d}:00` — {hour_counts[h]} ticket" for h in top5),
        inline=True,
    )
    embed.add_field(
        name="💤 Giờ ít nhất",
        value="\n".join(f"`{h:02d}:00–{h+1:02d}:00` — {hour_counts[h]} ticket" for h in low),
        inline=True,
    )
    embed.set_footer(text=f"Phân tích từ {total} ticket • Múi giờ UTC+7  •  Dùng .ai caodiem để xem lại")
    await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AICog(bot))

