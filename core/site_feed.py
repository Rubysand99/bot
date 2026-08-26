"""
core/site_feed.py — Đẩy tin nhắn từ các kênh public được chọn lên website
(trang chủ TuyTam Community, section "Cập Nhật Mới Nhất") theo thời gian thực.

Cách hoạt động: on_message ở bot.py gọi handle_site_feed() cho MỌI tin nhắn.
Nếu tin nhắn nằm trong 1 trong các kênh bên dưới → lưu vào Mongo collection
"site_feed" (KHÔNG đụng tới collection "bot_data"/"giveaways" hiện có).
website-ruby-main đọc lại collection này để hiển thị trên web.

2 kênh cố định của TuyTam Community — không phải setting theo guild (giống
CHANGELOG_CHANNEL_ID ở bot.py), vì tính năng này chỉ phục vụ đúng 1 server.
"""

import logging
import discord

from core.data import get_db

log = logging.getLogger("site_feed")

WATCHED_CHANNELS = {
    1464426646546284716: "thongbao",   # kênh thông báo
    1483446243777581149: "legit",      # kênh legit
}

MAX_PER_CHANNEL = 30   # số tin tối đa giữ lại trong Mongo cho mỗi kênh — dọn bớt tin cũ hơn


async def handle_site_feed(message: discord.Message):
    """Gọi từ on_message (bot.py) cho MỌI tin nhắn — tự bỏ qua nếu không phải
    kênh đang theo dõi. Lỗi Mongo (mất mạng, timeout...) chỉ log, KHÔNG raise,
    để không làm crash on_message hay ảnh hưởng các handler khác (handle_sold,
    handle_ai_message, legit/vouch...) chạy cùng trong on_message."""
    label = WATCHED_CHANNELS.get(message.channel.id)
    if not label:
        return
    if message.author.bot:
        return
    # Bỏ system message (pin, boost, member join card...) — chỉ lấy tin nhắn thường/reply
    if message.type not in (discord.MessageType.default, discord.MessageType.reply):
        return
    if not message.content and not message.attachments:
        return  # tin trống (chỉ sticker/embed) không có gì để hiển thị đẹp trên web

    try:
        col = get_db()["site_feed"]
        doc = {
            "_id":            message.id,
            "channel_id":     message.channel.id,
            "channel_label":  label,
            "author_name":    message.author.display_name,
            "author_avatar":  message.author.display_avatar.url,
            "content":        message.content[:500],
            "attachment_url": message.attachments[0].url if message.attachments else None,
            "jump_url":       message.jump_url,
            "timestamp":      message.created_at,
        }
        await col.insert_one(doc)

        # Dọn bớt tin cũ — chỉ giữ MAX_PER_CHANNEL tin mới nhất mỗi kênh
        old_ids = [
            d["_id"] async for d in
            col.find({"channel_id": message.channel.id}, {"_id": 1})
               .sort("timestamp", -1)
               .skip(MAX_PER_CHANNEL)
        ]
        if old_ids:
            await col.delete_many({"_id": {"$in": old_ids}})
    except Exception as e:
        log.error(f"[SITE_FEED] ❌ Lỗi khi lưu tin nhắn {message.id} (kênh {label}): {e}")


async def handle_site_feed_delete(payload: "discord.RawMessageDeleteEvent"):
    """Gọi từ on_raw_message_delete (bot.py). Dùng RAW event (không phải
    on_message_delete thường) vì raw event bắt được CẢ tin nhắn không còn trong cache
    nội bộ của discord.py (tin cũ, bot restart...) — on_message_delete thường chỉ bắn
    khi tin còn trong cache. Không có bước này thì tin bị xoá trên Discord (nhầm, vi
    phạm, nội dung nhạy cảm...) vẫn hiện nguyên trên web công khai tới khi tự rớt khỏi
    giới hạn MAX_PER_CHANNEL."""
    if payload.channel_id not in WATCHED_CHANNELS:
        return
    try:
        col = get_db()["site_feed"]
        await col.delete_one({"_id": payload.message_id})
    except Exception as e:
        log.error(f"[SITE_FEED] ❌ Lỗi xoá tin {payload.message_id}: {e}")


async def handle_site_feed_edit(message: discord.Message):
    """Gọi từ on_message_edit (bot.py). Cập nhật lại content/attachment nếu tin đã
    sửa từng được lưu vào site_feed — update_one trên _id không tồn tại là no-op an
    toàn (tin gốc chưa từng được lưu, ví dụ sửa embed link không đổi content)."""
    if message.channel.id not in WATCHED_CHANNELS:
        return
    try:
        col = get_db()["site_feed"]
        await col.update_one(
            {"_id": message.id},
            {"$set": {
                "content":        message.content[:500],
                "attachment_url": message.attachments[0].url if message.attachments else None,
            }},
        )
    except Exception as e:
        log.error(f"[SITE_FEED] ❌ Lỗi cập nhật tin {message.id}: {e}")
