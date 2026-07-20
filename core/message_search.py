"""
core/message_search.py — Lưu & tìm kiếm tin nhắn cũ bằng semantic search,
tái dùng embedding client (Voyage AI) từ core/rag.py.

CẦN TẠO THÊM 1 VECTOR SEARCH INDEX RIÊNG trên Atlas (khác với ai_knowledge):
- Database: tuytam_bot
- Collection: message_history
- Index name: message_history_vector_idx
- Definition (JSON Editor):
  {
    "fields": [
      { "type": "vector", "path": "embedding", "numDimensions": 512, "similarity": "cosine" },
      { "type": "filter", "path": "guild_id" }
    ]
  }
"""

import logging
from datetime import datetime, timezone

from pymongo import ReplaceOne

from core.data import get_db
from core.rag import get_embedding, get_embeddings_batch

log = logging.getLogger("message_search")

VECTOR_INDEX_NAME = "message_history_vector_idx"

# Bỏ qua tin nhắn không đáng embed — tiết kiệm phí Voyage đáng kể so với
# index MỌI tin nhắn (lời chào, "ok", emoji đơn, v.v. không có giá trị tìm kiếm)
MIN_MESSAGE_LENGTH = 15

_col = None
def _get_collection():
    global _col
    if _col is None:
        _col = get_db()["message_history"]
    return _col


def is_indexable(content: str, is_bot: bool, is_command: bool) -> bool:
    """Lọc noise trước khi embed — dùng chung cho cả backfill lẫn index liên tục."""
    if is_bot or is_command:
        return False
    return len((content or "").strip()) >= MIN_MESSAGE_LENGTH


# ══════════════════════════════════════════
# LƯU — 1 tin (index liên tục qua on_message)
# ══════════════════════════════════════════
async def save_message(guild_id: int, channel_id: int, message_id: int, author_id: int,
                        content: str, created_at: datetime) -> bool:
    embedding = await get_embedding(content, input_type="document")
    if embedding is None:
        return False
    col = _get_collection()
    try:
        await col.replace_one(
            {"_id": message_id},
            {
                "_id": message_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "author_id": author_id,
                "content": content[:2000],
                "embedding": embedding,
                "created_at": created_at,
                "indexed_at": datetime.now(timezone.utc),
            },
            upsert=True,
        )
        return True
    except Exception as e:
        log.error(f"[MSG_SEARCH] ❌ Lỗi lưu message {message_id}: {e}")
        return False


# ══════════════════════════════════════════
# LƯU — nhiều tin cùng lúc (backfill .aiindex)
# ══════════════════════════════════════════
async def save_messages_batch(messages: list[dict]) -> int:
    """messages: list dict {guild_id, channel_id, message_id, author_id, content, created_at}.
    Tự bỏ qua tin ĐÃ index từ trước (tránh embed lại tốn phí khi chạy .aiindex nhiều lần),
    embed phần còn lại theo batch, rồi ghi 1 lần bằng bulk_write. Trả về số tin đã lưu mới."""
    if not messages:
        return 0

    col = _get_collection()

    ids = [m["message_id"] for m in messages]
    existing_ids = set()
    try:
        async for doc in col.find({"_id": {"$in": ids}}, {"_id": 1}):
            existing_ids.add(doc["_id"])
    except Exception as e:
        log.error(f"[MSG_SEARCH] ❌ Lỗi kiểm tra tin đã index: {e}")

    new_messages = [m for m in messages if m["message_id"] not in existing_ids]
    if not new_messages:
        return 0

    texts = [m["content"] for m in new_messages]
    embeddings = await get_embeddings_batch(texts, input_type="document")
    if embeddings is None or len(embeddings) != len(new_messages):
        log.error("[MSG_SEARCH] ❌ Batch embedding thất bại hoặc thiếu kết quả.")
        return 0

    ops = [
        ReplaceOne(
            {"_id": m["message_id"]},
            {
                "_id": m["message_id"],
                "guild_id": m["guild_id"],
                "channel_id": m["channel_id"],
                "author_id": m["author_id"],
                "content": m["content"][:2000],
                "embedding": emb,
                "created_at": m["created_at"],
                "indexed_at": datetime.now(timezone.utc),
            },
            upsert=True,
        )
        for m, emb in zip(new_messages, embeddings)
    ]

    try:
        result = await col.bulk_write(ops, ordered=False)
        return result.upserted_count + result.modified_count
    except Exception as e:
        log.error(f"[MSG_SEARCH] ❌ Lỗi bulk_write: {e}")
        return 0


# ══════════════════════════════════════════
# TÌM KIẾM
# ══════════════════════════════════════════
async def search_messages(guild_id: int, query: str, top_k: int = 5) -> list[dict]:
    query_embedding = await get_embedding(query, input_type="query")
    if query_embedding is None:
        return []

    col = _get_collection()
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 100,
                "limit": top_k,
                "filter": {"guild_id": guild_id},
            }
        },
        {
            "$project": {
                "content": 1, "channel_id": 1, "author_id": 1,
                "created_at": 1, "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    try:
        results = []
        async for doc in col.aggregate(pipeline):
            results.append(doc)
        return results
    except Exception as e:
        # Lỗi thường gặp nhất: chưa tạo message_history_vector_idx trên Atlas
        log.error(f"[MSG_SEARCH] ❌ Lỗi $vectorSearch: {e}")
        return []
