"""
shared/logger.py — Hạ tầng log THUẦN dùng chung cho mọi bot con: bảng tra cứu
LOG_ICONS/LOG_ROUTES/LOG_GROUP_LABELS + send_log()/get_log_channel(). KHÔNG có Cog,
KHÔNG có state, KHÔNG có task nền/listener — phần đó (lệnh .setlog/.setuplog/.testlog/
.loginfo/.baocao, listener member/command/interaction, daily report) nằm ở
cogs/logger.py, file đó import lại các định nghĩa dưới đây.

⚠️ File này KHÔNG được tự import lại chính nó (`shared.logger`) — bug thật đã gặp:
nội dung Cog của cogs/logger.py bị copy nhầm vào đây, khiến file tự import tên của
chính nó lúc còn khởi tạo dở → ImportError circular import, sập toàn bộ cogs phụ
thuộc send_log() (xem CHANGELOG mục fix lỗi này).

⚠️ send_log(guild_id=...) LUÔN tự gọi set_current_guild(guild_id) đầu hàm trước khi
tra kênh log — xem AI_CONTEXT.md mục "KIẾN TRÚC MULTI-GUILD" quy tắc #5. Đây là lý do
mọi lệnh gọi send_log() trong repo bắt buộc truyền guild_id.
"""

from datetime import datetime, timezone

import discord

DEFAULT_COLOR = 0x5865F2

# ══════════════════════════════════════════
# NHÓM KÊNH LOG — nhãn hiển thị (.setlog / .loginfo / .testlog)
# ══════════════════════════════════════════
LOG_GROUP_LABELS: dict[str, str] = {
    "ticket":   "🎫 Ticket",
    "mod":      "🛡️ Mod",
    "giveaway": "🎉 Giveaway",
    "member":   "👥 Member",
    "role":     "🏷️ Role",
    "ai":       "🤖 AI",
    "admin":    "⚙️ Admin",
    "invite":   "📨 Invite",
    "general":  "📋 General",
    "shop":     "🛒 Shop",
}

# event_type -> icon hiển thị trong title embed
LOG_ICONS: dict[str, str] = {
    # ticket
    "TICKET_CREATE": "🎫", "TICKET_CLOSE": "🔒", "TICKET_DONE": "✅",
    "TICKET_UNDONE": "↩️", "TICKET_CLAIM": "🙋",
    # mod
    "MOD_BAN": "🔨", "MOD_KICK": "👢", "MOD_MUTE": "🔇", "MOD_WARN": "⚠️",
    "MOD_CHANNEL_CLEAR": "🧹",
    # giveaway
    "GIVEAWAY_START": "🎉", "GIVEAWAY_END": "🏁", "GIVEAWAY_REROLL": "🔁",
    "GIVEAWAY_JOIN": "🙋",
    # member
    "MEMBER_JOIN": "📥", "MEMBER_LEAVE": "📤",
    # role
    "ROLE_ADD": "➕", "ROLE_REMOVE": "➖",
    # ai
    "AI_USED": "🤖",
    # admin
    "CMD_USED": "⌨️", "SLASH_USED": "⚡", "SETTINGS": "⚙️", "ADMIN": "⚙️",
    # invite
    "INVITE_JOIN": "📨", "INVITE_VERIFY": "✅", "INVITE_FAKE": "🚨",
    "INVITE_LEFT": "📤", "INVITE": "📨",
    # shop
    "SHOP_LISTING_CREATE": "🛒", "SHOP_QUEUE_DONE": "📦", "SHOP_QR_SHOWN": "🧾",
    # general (fallback)
    "INFO": "ℹ️", "ERROR": "❌", "RATING": "⭐",
}

# event_type -> nhóm kênh (group key trong LOG_GROUP_LABELS) — theo đúng bảng
# "Log event types → nhóm kênh" trong AI_CONTEXT.md
LOG_ROUTES: dict[str, str] = {
    "TICKET_CREATE": "ticket", "TICKET_CLOSE": "ticket", "TICKET_DONE": "ticket",
    "TICKET_UNDONE": "ticket", "TICKET_CLAIM": "ticket",

    "MOD_BAN": "mod", "MOD_KICK": "mod", "MOD_MUTE": "mod", "MOD_WARN": "mod",
    "MOD_CHANNEL_CLEAR": "mod",

    "GIVEAWAY_START": "giveaway", "GIVEAWAY_END": "giveaway",
    "GIVEAWAY_REROLL": "giveaway", "GIVEAWAY_JOIN": "giveaway",

    "MEMBER_JOIN": "member", "MEMBER_LEAVE": "member",

    "ROLE_ADD": "role", "ROLE_REMOVE": "role",

    "AI_USED": "ai",

    "CMD_USED": "admin", "SLASH_USED": "admin", "SETTINGS": "admin", "ADMIN": "admin",

    "INVITE_JOIN": "invite", "INVITE_VERIFY": "invite", "INVITE_FAKE": "invite",
    "INVITE_LEFT": "invite", "INVITE": "invite",

    "SHOP_LISTING_CREATE": "shop", "SHOP_QUEUE_DONE": "shop", "SHOP_QR_SHOWN": "shop",

    "INFO": "general", "ERROR": "general", "RATING": "general",
}


def get_log_channel(group: str) -> int | None:
    """Lấy channel_id đã cấu hình cho 1 nhóm log, của GUILD hiện tại trong contextvar
    (xem core/data.py: get_log_channel_by_group). Import cục bộ để tránh vòng lặp
    import (core/data.py cũng import từ shared/data.py, không đụng shared/logger.py,
    nhưng cogs/logger.py import cả 2 nên vẫn phải cẩn thận thứ tự load)."""
    from core.data import get_log_channel_by_group
    return get_log_channel_by_group(group)


async def send_log(
    bot,
    event_type: str,
    title: str,
    *,
    fields: list[tuple[str, str, bool]] | None = None,
    description: str | None = None,
    user=None,
    color: int | None = None,
    guild_id: int | None = None,
):
    """Gửi 1 embed log vào kênh của nhóm tương ứng với event_type (fallback về kênh
    log_rudy nếu nhóm đó chưa cài kênh riêng, và bỏ qua im lặng nếu cả 2 đều chưa cài).

    LUÔN truyền guild_id (xem AI_CONTEXT.md mục KIẾN TRÚC MULTI-GUILD, quy tắc #5) —
    hàm này tự set_current_guild(guild_id) đầu tiên, TRƯỚC khi gọi bất kỳ hàm nào đọc
    load_data() (get_log_channel/get_cfg_log_rudy), để load_data() luôn thao tác đúng
    guild dù send_log() được gọi từ listener/task không có context tự nhiên.
    """
    from core.data import set_current_guild, get_cfg_log_rudy, get_or_fetch_channel

    if guild_id is not None:
        set_current_guild(guild_id)

    group = LOG_ROUTES.get(event_type, "general")
    icon = LOG_ICONS.get(event_type, "📋")

    ch_id = get_log_channel(group) or get_cfg_log_rudy()
    if not ch_id:
        return  # Chưa cài kênh nào cho nhóm này lẫn fallback — bỏ qua im lặng

    channel = await get_or_fetch_channel(bot, ch_id)
    if channel is None:
        return

    embed = discord.Embed(
        title=f"{icon} {title}",
        description=description,
        color=color if color is not None else DEFAULT_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if user is not None:
        avatar = getattr(user, "display_avatar", None)
        if avatar:
            embed.set_thumbnail(url=avatar.url)

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[LOGGER] ❌ Lỗi gửi log ({event_type}): {e}")
