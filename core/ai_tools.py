"""
core/ai_tools.py — Tool registry cho AI Chat function calling (v4.14.0).

Thay thế hoàn toàn hệ thống prompt-JSON cũ (AI_EXEC_SYSTEM/_call_groq_exec/_run_action
trong ai_chat.py — chưa từng được gọi ở đâu, xem CHANGELOG v4.14.0) bằng native tool
calling của Groq (model tự trả về `tool_calls` có JSON schema, không cần tự viết
prompt "phân tích intent" nữa). Xem: https://console.groq.com/docs/tool-use/overview

CÁCH THÊM TOOL MỚI:
1. Thêm schema vào QUERY_TOOL_SCHEMAS (mọi user trong kênh AI dùng được, CHỈ ĐỌC data)
   hoặc ADMIN_TOOL_SCHEMAS (chỉ admin, có thể ghi/xoá data — xem DANGEROUS_TOOLS).
2. Thêm handler async cùng tên vào TOOL_HANDLERS. Handler nhận (ctx, params: dict)
   -> trả về str (kết quả, được feed lại cho model để model tự soạn câu trả lời).
   `ctx` có thể là discord.ext.commands.Context (lệnh .ai) hoặc discord.Message
   (chat thường trong kênh AI) — cả 2 đều có .guild/.author/.channel/.mentions
   nên query-tool handler dùng chung được; admin-tool handler cần ctx thật (có .bot).
3. Nếu tool có khả năng phá hoại (xoá, ban, kick...) → thêm tên vào DANGEROUS_TOOLS
   để bắt buộc admin xác nhận qua AIConfirmView trước khi chạy.
"""

import discord

from core.data import (
    ADMIN_IDS, get_user_total_spent, get_user_ticket_history,
)
from cogs.seller import is_active_seller, _get_one as _seller_get_one
from cogs.ticket import has_ticket
from cogs.invite import _get_net_invites, _get_net_invites_alltime


# ─────────────────────────────────────────────
# QUERY TOOLS — mọi user trong kênh AI dùng được, chỉ đọc data của CHÍNH họ,
# không cần xác nhận.
# ─────────────────────────────────────────────
QUERY_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "check_ticket_status",
            "description": "Kiểm tra người dùng hiện có ticket nào đang mở không.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_seller_status",
            "description": "Kiểm tra gói seller (subscription bán hàng) của người dùng còn hạn hay đã hết hạn.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_invite_stats",
            "description": "Kiểm tra số lượt mời (invite) — verify/fake/rời server — của người dùng trong tháng này và tổng all-time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_purchase_history",
            "description": "Kiểm tra tổng số tiền đã mua hàng và số lượng ticket đã từng tạo của người dùng.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# ─────────────────────────────────────────────
# ADMIN TOOLS — chỉ được đưa cho model khi người gọi nằm trong ADMIN_IDS.
# Migrate từ hệ thống AI_EXEC_SYSTEM cũ, đã sửa lại tên lệnh cho ĐÚNG với
# lệnh thật trong bot (bản cũ trỏ tới "ticketpanel"/"gend"/"greroll" — các
# lệnh KHÔNG TỒN TẠI, xem CHANGELOG v4.14.0).
# ─────────────────────────────────────────────
ADMIN_TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "channel_create",
        "description": "Tạo kênh Discord mới (text hoặc voice), public hoặc private, trong category hiện tại.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tên kênh"},
                "channel_type": {"type": "string", "enum": ["text", "voice"]},
                "privacy": {"type": "string", "enum": ["public", "private"]},
            },
            "required": ["name", "channel_type", "privacy"],
        },
    }},
    {"type": "function", "function": {
        "name": "channel_delete",
        "description": "Xoá kênh Discord hiện tại (kênh đang chat). Không thể hoàn tác.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "channel_rename",
        "description": "Đổi tên kênh hiện tại.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Tên mới"}},
            "required": ["name"],
        },
    }},
    {"type": "function", "function": {
        "name": "role_create",
        "description": "Tạo role mới trong server.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    }},
    {"type": "function", "function": {
        "name": "role_delete",
        "description": "Xoá role khỏi server theo tên. Không thể hoàn tác.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Tên role cần xoá"}},
            "required": ["name"],
        },
    }},
    {"type": "function", "function": {
        "name": "role_add",
        "description": "Thêm role cho user được mention trong tin nhắn.",
        "parameters": {
            "type": "object",
            "properties": {"role_name": {"type": "string"}},
            "required": ["role_name"],
        },
    }},
    {"type": "function", "function": {
        "name": "role_remove",
        "description": "Xoá role của user được mention trong tin nhắn.",
        "parameters": {
            "type": "object",
            "properties": {"role_name": {"type": "string"}},
            "required": ["role_name"],
        },
    }},
    {"type": "function", "function": {
        "name": "purge",
        "description": "Xoá hàng loạt tin nhắn gần nhất trong kênh hiện tại.",
        "parameters": {
            "type": "object",
            "properties": {"amount": {"type": "integer", "description": "Số lượng tin nhắn cần xoá"}},
            "required": ["amount"],
        },
    }},
    {"type": "function", "function": {
        "name": "mod_ban",
        "description": "Ban user được mention khỏi server.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    }},
    {"type": "function", "function": {
        "name": "mod_kick",
        "description": "Kick user được mention khỏi server.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    }},
    {"type": "function", "function": {
        "name": "mod_mute",
        "description": "Mute (timeout) user được mention.",
        "parameters": {
            "type": "object",
            "properties": {
                "duration": {"type": "string", "description": "Thời gian mute, vd 10m, 1h, 1d"},
                "reason": {"type": "string"},
            },
            "required": ["duration", "reason"],
        },
    }},
    {"type": "function", "function": {
        "name": "mod_warn",
        "description": "Cảnh cáo (warn) user được mention. Không cần xác nhận trước.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    }},
    {"type": "function", "function": {
        "name": "ticket_close",
        "description": "Đóng ticket hiện tại (tương đương lệnh .close) — chỉ hoạt động trong kênh ticket.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "ticket_panel",
        "description": "Gửi ticket panel (nút bấm mở ticket) vào kênh hiện tại.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "giveaway_reset",
        "description": "Khôi phục 1 giveaway bị kết thúc nhầm, theo gw_id.",
        "parameters": {
            "type": "object",
            "properties": {"gw_id": {"type": "string", "description": "ID giveaway (số)"}},
            "required": ["gw_id"],
        },
    }},
]

# Tool ghi/xoá dữ liệu quan trọng hoặc ảnh hưởng thành viên -> BẮT BUỘC admin bấm
# xác nhận qua AIConfirmView trước khi handler thật sự chạy.
DANGEROUS_TOOLS = {
    "channel_delete", "role_delete", "purge",
    "mod_ban", "mod_kick", "mod_mute",
}


# ─────────────────────────────────────────────
# Helper dùng chung cho admin tool: invoke lệnh bot có sẵn theo tên
# (tái sử dụng toàn bộ logic nghiệp vụ + logging đã có trong cog gốc,
# thay vì viết lại). Yêu cầu `ctx` là commands.Context thật (có .bot, .message).
# ─────────────────────────────────────────────
async def _invoke_cmd(ctx, name: str, *args) -> tuple[bool, str | None]:
    cmd = ctx.bot.get_command(name)
    if not cmd:
        return False, f"❌ Không tìm thấy lệnh `.{name}` trong bot."
    try:
        ctx.message.content = f".{name} " + " ".join(str(a) for a in args)
        new_ctx = await ctx.bot.get_context(ctx.message)
        await cmd.invoke(new_ctx)
        return True, None
    except Exception as e:
        return False, f"❌ Lỗi khi chạy `.{name}`: {e}"


def _resolve_mentioned_user(ctx):
    mentions = getattr(ctx.message, "mentions", None) if hasattr(ctx, "message") else getattr(ctx, "mentions", None)
    return mentions[0] if mentions else None


# ─────────────────────────────────────────────
# QUERY HANDLERS
# ─────────────────────────────────────────────
async def _h_check_ticket_status(ctx, params: dict) -> str:
    open_ticket = await has_ticket(ctx.guild, ctx.author)
    return "Người dùng đang có 1 ticket mở." if open_ticket else "Người dùng hiện không có ticket nào đang mở."


async def _h_check_seller_status(ctx, params: dict) -> str:
    doc = _seller_get_one(ctx.guild.id, ctx.author.id)
    if not doc:
        return "Người dùng chưa từng đăng ký gói seller."
    active = is_active_seller(ctx.guild.id, ctx.author.id)
    expires = doc.get("expires_at", "?")
    return (f"Gói seller đang HOẠT ĐỘNG, hết hạn lúc {expires} (UTC)." if active
            else f"Gói seller ĐÃ HẾT HẠN lúc {expires} (UTC).")


async def _h_check_invite_stats(ctx, params: dict) -> str:
    _, _, ver_m, fake_m, left_m, net_m = _get_net_invites(ctx.author.id)
    _, _, ver_a, fake_a, left_a, net_a = _get_net_invites_alltime(ctx.author.id)
    return (f"Tháng này: {ver_m} verify, {fake_m} fake, {left_m} rời server, net {net_m}. "
            f"All-time: {ver_a} verify, {fake_a} fake, {left_a} rời server, net {net_a}.")


async def _h_check_purchase_history(ctx, params: dict) -> str:
    spent = get_user_total_spent(ctx.author.id)
    history = get_user_ticket_history(ctx.author.id)
    return f"Tổng đã chi tiêu: {spent:,}đ qua {len(history)} ticket đã từng tạo."


# ─────────────────────────────────────────────
# ADMIN HANDLERS
# ─────────────────────────────────────────────
async def _h_channel_create(ctx, params: dict) -> str:
    name = params.get("name", "kenh-moi").lower().replace(" ", "-")
    ch_type = params.get("channel_type", "text")
    privacy = params.get("privacy", "public")
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


async def _h_channel_delete(ctx, params: dict) -> str:
    try:
        ch_name = ctx.channel.name
        await ctx.channel.delete(reason=f"Xoá bởi AI — admin {ctx.author}")
        return f"✅ Đã xoá channel `{ch_name}`."
    except Exception as e:
        return f"❌ Lỗi xoá channel: {e}"


async def _h_channel_rename(ctx, params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "❌ Thiếu tên mới."
    try:
        old = ctx.channel.name
        await ctx.channel.edit(name=name.lower().replace(" ", "-"))
        return f"✅ Đổi tên channel `{old}` → `{name}`."
    except Exception as e:
        return f"❌ Lỗi đổi tên: {e}"


async def _h_role_create(ctx, params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "❌ Thiếu tên role."
    try:
        role = await ctx.guild.create_role(name=name, reason=f"Tạo bởi AI — admin {ctx.author}")
        return f"✅ Đã tạo role `{role.name}`."
    except Exception as e:
        return f"❌ Lỗi tạo role: {e}"


async def _h_role_delete(ctx, params: dict) -> str:
    name = params.get("name", "")
    role = discord.utils.get(ctx.guild.roles, name=name)
    if not role:
        return f"❌ Không tìm thấy role `{name}`."
    try:
        await role.delete(reason=f"Xoá bởi AI — admin {ctx.author}")
        return f"✅ Đã xoá role `{name}`."
    except Exception as e:
        return f"❌ Lỗi xoá role: {e}"


async def _h_role_add(ctx, params: dict) -> str:
    user = _resolve_mentioned_user(ctx)
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


async def _h_role_remove(ctx, params: dict) -> str:
    user = _resolve_mentioned_user(ctx)
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


async def _h_purge(ctx, params: dict) -> str:
    try:
        amount = int(params.get("amount", 10))
    except (TypeError, ValueError):
        amount = 10
    try:
        deleted = await ctx.channel.purge(limit=amount)
        return f"✅ Đã xoá {len(deleted)} tin nhắn."
    except Exception as e:
        return f"❌ Lỗi purge: {e}"


async def _h_mod_ban(ctx, params: dict) -> str:
    user = _resolve_mentioned_user(ctx)
    if not user:
        return "❌ Cần mention @user."
    reason = params.get("reason", "Không có lý do")
    ok, err = await _invoke_cmd(ctx, "ban", user.id, reason)
    return err if not ok else f"✅ Đã ban {user.display_name} — lý do: {reason}."


async def _h_mod_kick(ctx, params: dict) -> str:
    user = _resolve_mentioned_user(ctx)
    if not user:
        return "❌ Cần mention @user."
    reason = params.get("reason", "Không có lý do")
    ok, err = await _invoke_cmd(ctx, "kick", user.id, reason)
    return err if not ok else f"✅ Đã kick {user.display_name} — lý do: {reason}."


async def _h_mod_mute(ctx, params: dict) -> str:
    user = _resolve_mentioned_user(ctx)
    if not user:
        return "❌ Cần mention @user."
    duration = params.get("duration", "10m")
    reason = params.get("reason", "Không có lý do")
    ok, err = await _invoke_cmd(ctx, "timeout", user.id, duration, reason)
    return err if not ok else f"✅ Đã mute {user.display_name} {duration} — lý do: {reason}."


async def _h_mod_warn(ctx, params: dict) -> str:
    user = _resolve_mentioned_user(ctx)
    if not user:
        return "❌ Cần mention @user."
    reason = params.get("reason", "Không có lý do")
    ok, err = await _invoke_cmd(ctx, "warn", user.id, reason)
    return err if not ok else f"✅ Đã warn {user.display_name} — lý do: {reason}."


async def _h_ticket_close(ctx, params: dict) -> str:
    ok, err = await _invoke_cmd(ctx, "close")
    return err if not ok else "✅ Đã đóng ticket."


async def _h_ticket_panel(ctx, params: dict) -> str:
    ok, err = await _invoke_cmd(ctx, "panel")
    return err if not ok else "✅ Đã gửi ticket panel."


async def _h_giveaway_reset(ctx, params: dict) -> str:
    gw_id = params.get("gw_id", "")
    if not gw_id:
        return "❌ Thiếu gw_id."
    ok, err = await _invoke_cmd(ctx, "gwreset", gw_id)
    return err if not ok else f"✅ Đã khôi phục giveaway #{gw_id}."


TOOL_HANDLERS = {
    "check_ticket_status": _h_check_ticket_status,
    "check_seller_status": _h_check_seller_status,
    "check_invite_stats": _h_check_invite_stats,
    "check_purchase_history": _h_check_purchase_history,
    "channel_create": _h_channel_create,
    "channel_delete": _h_channel_delete,
    "channel_rename": _h_channel_rename,
    "role_create": _h_role_create,
    "role_delete": _h_role_delete,
    "role_add": _h_role_add,
    "role_remove": _h_role_remove,
    "purge": _h_purge,
    "mod_ban": _h_mod_ban,
    "mod_kick": _h_mod_kick,
    "mod_mute": _h_mod_mute,
    "mod_warn": _h_mod_warn,
    "ticket_close": _h_ticket_close,
    "ticket_panel": _h_ticket_panel,
    "giveaway_reset": _h_giveaway_reset,
}
