"""
shared/logger.py — send_log() dùng chung cho MỌI bot con.

Đây CHỈ là phần hàm thuần (send_log + format + routing table) tách từ cogs/logger.py
bản gốc. Phần Cog (LoggerCog: .setlog/.testlog/.loginfo/.baocao/.setuplog + listener
member/role/command/interaction) KHÔNG nằm ở đây — đó là 1 cog thật (có state, task nền,
listener) nên tiếp tục sống dạng Cog, dự kiến đặt ở bot_core (xem AI_CONTEXT_CORE.md) vì
bản chất là admin/audit, không phải hạ tầng.

Mỗi bot con tự gọi:
    from shared.logger import send_log
    await send_log(self.bot, "TICKET_CREATE", "Tạo ticket", ..., guild_id=guild.id)
— dùng CHÍNH token/permission của bot đó để gửi vào kênh log. Bot đó phải được invite
kèm quyền "Send Messages" vào các kênh log tương ứng.

⚠️ Lưu ý khi tách bot thật: `daily_report_task` (ở LoggerCog, bot_core) đọc
get_ticket_history() (domain bot_ticket) VÀ load_giveaways_data() (domain bot_growth) —
2 domain KHÁC bot_core. Việc này vẫn hoạt động được vì Mongo dùng chung, nhưng bot_core
sẽ "biết" về schema của 2 bot kia. Đây là 1 điểm coupling CỐ Ý chấp nhận ở Phase 1 —
xem AI_CONTEXT_SHARED.md mục "Coupling đã biết" để theo dõi, cân nhắc tách report riêng
từng bot tự báo cáo phần của mình ở Phase sau nếu thấy phiền.
"""

import re as _re_log
from datetime import datetime, timezone, timedelta
import discord

from shared.data import set_current_guild

# NOTE: get_log_channel_by_group / get_cfg_log_rudy / get_or_fetch_channel hiện vẫn định
# nghĩa trong core/data.py bản gốc (accessor cfg_*, không phải hạ tầng) — import lại ở đây
# để tránh vòng lặp import, mỗi bot con sẽ có bản data_ext.py riêng định nghĩa 3 hàm này
# (rất ngắn, xem AI_CONTEXT_SHARED.md mục "Accessor log dùng chung"). Tạm thời trỏ về
# core.data để KHÔNG phá vỡ bot hiện tại trong lúc chưa tách bot thật (Phase 1).
from core.data import get_log_channel_by_group, get_cfg_log_rudy, get_or_fetch_channel

LOG_ICONS = {
    "TICKET_CREATE":   ("🎫", 0x57F287),
    "TICKET_CLOSE":    ("🔒", 0xED4245),
    "TICKET_DONE":     ("✅", 0x57F287),
    "TICKET_UNDONE":   ("↩️", 0xED4245),
    "TICKET_CLAIM":    ("🙋", 0x5865F2),
    "MOD_BAN":         ("🔨", 0xED4245),
    "MOD_KICK":        ("👢", 0xE67E22),
    "MOD_MUTE":        ("🔇", 0xF0A500),
    "MOD_WARN":        ("⚠️",  0xFEE75C),
    "MOD_CHANNEL_CLEAR": ("🗑️", 0xED4245),
    "GIVEAWAY":        ("🎉", 0xF1C40F),
    "GIVEAWAY_JOIN":   ("🙋", 0xF1C40F),
    "GIVEAWAY_START":  ("🎉", 0xF1C40F),
    "GIVEAWAY_END":    ("🏆", 0xF1C40F),
    "GIVEAWAY_REROLL": ("🔄", 0xF1C40F),
    "MEMBER_JOIN":     ("📥", 0x57F287),
    "MEMBER_LEAVE":    ("📤", 0xED4245),
    "ROLE_ADD":        ("🏷️", 0x57F287),
    "ROLE_REMOVE":     ("🏷️", 0xED4245),
    "CMD_USED":        ("⌨️",  0x5865F2),
    "SLASH_USED":      ("🔧", 0x5865F2),
    "INVITE":          ("📨", 0x9B59B6),
    "INVITE_JOIN":     ("📥", 0x9B59B6),
    "INVITE_LEFT":     ("🚪", 0xE67E22),
    "RATING":          ("⭐", 0xF1C40F),
    "AI_USED":         ("🤖", 0x1ABC9C),
    "SETTINGS":        ("⚙️",  0xFEE75C),
    "ERROR":           ("❌", 0xED4245),
    "INFO":            ("ℹ️",  0x5865F2),
    "SHOP_QR_SHOWN":       ("🧾", 0x2ECC71),
    "SHOP_QUEUE_DONE":     ("✅", 0x2ECC71),
}

LOG_ROUTES: dict[str, str] = {
    "TICKET_CREATE":   "ticket",
    "TICKET_CLOSE":    "ticket",
    "TICKET_DONE":     "ticket",
    "TICKET_UNDONE":   "ticket",
    "TICKET_CLAIM":    "ticket",
    "MOD_BAN":         "mod",
    "MOD_KICK":        "mod",
    "MOD_MUTE":        "mod",
    "MOD_WARN":        "mod",
    "MOD_CHANNEL_CLEAR": "mod",
    "GIVEAWAY":        "giveaway",
    "GIVEAWAY_JOIN":   "giveaway",
    "GIVEAWAY_START":  "giveaway",
    "GIVEAWAY_END":    "giveaway",
    "GIVEAWAY_REROLL": "giveaway",
    "MEMBER_JOIN":     "member",
    "MEMBER_LEAVE":    "member",
    "ROLE_ADD":        "role",
    "ROLE_REMOVE":     "role",
    "AI_USED":         "ai",
    "CMD_USED":        "admin",
    "SLASH_USED":      "admin",
    "SETTINGS":        "admin",
    "INVITE":          "invite",
    "INVITE_JOIN":     "invite",
    "INVITE_LEFT":     "invite",
    "RATING":          "general",
    "ERROR":           "general",
    "INFO":            "general",
    "SHOP_QR_SHOWN":       "shop",
    "SHOP_QUEUE_DONE":     "shop",
}

LOG_GROUP_LABELS: dict[str, str] = {
    "ticket":   "🎫 Ticket",
    "mod":      "🛡️ Mod",
    "giveaway": "🎉 Giveaway",
    "member":   "👥 Member",
    "role":     "🏷️ Role",
    "ai":       "🤖 AI",
    "admin":    "⌨️ Admin",
    "invite":   "📨 Invite",
    "general":  "📋 General",
    "shop":     "🛒 Shop Order",
}


def get_log_channel(group: str) -> int | None:
    return get_log_channel_by_group(group)


def _depinged(value: str) -> str:
    """Vô hiệu hoá mention user/role còn sót lại trong giá trị field log."""
    zwsp = "\u200b"
    value = _re_log.sub(r"<@&(\d+)>", f"<@&{zwsp}" + r"\1>", value)
    value = _re_log.sub(r"<@!?(\d+)>", f"<@{zwsp}" + r"\1>", value)
    return value


def _fmt_log_text(
    event_type: str,
    title: str,
    fields: list[tuple] = None,
    description: str = None,
    user: discord.Member | discord.User = None,
) -> str:
    icon, _ = LOG_ICONS.get(event_type, ("📋", 0))
    now_vn = datetime.now(timezone(timedelta(hours=7)))
    time_str = now_vn.strftime("%d/%m/%Y %H:%M")

    lines = []
    header = f"{icon} `[{event_type}]` **{title}**"
    if user:
        header += f"  •  _{user}_"
    lines.append(header)

    if description:
        short_desc = _depinged(description[:200].replace("\n", " "))
        lines.append(f"> {short_desc}")

    if fields:
        field_parts = []
        for f in fields:
            name  = f[0]
            value = _depinged(str(f[1])[:80])
            field_parts.append(f"**{name}:** {value}")
        for i in range(0, len(field_parts), 3):
            lines.append("› " + "  ·  ".join(field_parts[i:i + 3]))

    lines.append(f"-# 🕐 {time_str} UTC+7")
    return "\n".join(lines)


async def send_log(
    bot: discord.Client,
    event_type: str,
    title: str,
    fields: list[tuple] = None,
    description: str = None,
    user: discord.Member | discord.User = None,
    color: int = None,
    footer: str = None,
    guild_id: int = None,
):
    """Gửi log vào kênh tương ứng với nhóm của event_type, bằng CHÍNH `bot` được truyền vào
    (mỗi bot con dùng token/permission của chính nó). Fallback về kênh log_rudy nếu nhóm
    chưa được cài. guild_id BẮT BUỘC truyền khi gọi từ background task / listener chạy Task
    riêng — xem AI_CONTEXT_SHARED.md mục AUTH_GATE & contextvar."""
    if bot is None:
        return

    if guild_id:
        set_current_guild(guild_id)

    text = _fmt_log_text(event_type, title, fields, description, user)

    group   = LOG_ROUTES.get(event_type, "general")
    ch_id   = get_log_channel(group) or get_cfg_log_rudy()
    if not ch_id:
        print(f"[LOG] ⚠️ Không có kênh log cho nhóm '{group}' ({event_type}), bỏ qua.")
        return

    channel = None
    if guild_id:
        guild = bot.get_guild(guild_id)
        if guild:
            channel = guild.get_channel(ch_id)
    if not channel:
        channel = await get_or_fetch_channel(bot, ch_id)

    if not channel:
        print(f"[LOG] ⚠️ Không tìm được kênh {ch_id} cho '{group}' ({event_type}), bỏ qua.")
        return
    try:
        await channel.send(text)
    except Exception as e:
        print(f"[LOG] ❌ Không gửi được log {event_type} → #{channel.name}: {e}")
