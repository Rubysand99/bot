"""
core/rag.py — Lưu trữ & tìm kiếm kiến thức Q&A bằng MongoDB Atlas Vector Search.

Nguồn dữ liệu: các câu hỏi AI không chắc đã được admin giải đáp trong forum
"đã xử lý" (xem cogs/ai_chat.py). Mỗi Q&A được embed thành vector, lưu vào
collection riêng "ai_knowledge", và có thể tìm lại bằng $vectorSearch khi
user hỏi câu tương tự sau này.

CẦN LÀM TRƯỚC KHI DÙNG:
1. Đăng ký API key embedding (khuyến nghị Voyage AI — voyageai.com — có free
   tier, chất lượng tốt cho tiếng Việt). Set env VOYAGE_API_KEY.
2. Tạo Atlas Vector Search Index trên collection "ai_knowledge", field "embedding":
   - Vào Atlas UI → Database → Search → Create Search Index → JSON Editor
   - Index name: ai_knowledge_vector_idx
   - Definition:
     {
       "fields": [
         { "type": "vector", "path": "embedding", "numDimensions": 512, "similarity": "cosine" },
         { "type": "filter", "path": "guild_id" }
       ]
     }
   (numDimensions=512 khớp với model voyage-3-lite bên dưới — đổi model thì đổi số này)
"""

import os
import logging
from datetime import datetime, timezone

import aiohttp

from core.data import get_db

log = logging.getLogger("rag")

VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_MODEL   = "voyage-3-lite"          # 512 chiều, rẻ, đủ tốt cho Q&A ngắn
VOYAGE_URL     = "https://api.voyageai.com/v1/embeddings"

VECTOR_INDEX_NAME  = "ai_knowledge_vector_idx"
RAG_SCORE_THRESHOLD = 0.80   # dưới ngưỡng này coi như "không tìm thấy" — CẦN TEST THỰC TẾ để tinh chỉnh

_col = None
def _get_knowledge_collection():
    global _col
    if _col is None:
        _col = get_db()["ai_knowledge"]
    return _col


# ══════════════════════════════════════════
# EMBEDDING
# ══════════════════════════════════════════
async def get_embedding(text: str, input_type: str = "document") -> list[float] | None:
    """input_type: 'document' khi lưu Q&A, 'query' khi tìm kiếm — Voyage tối ưu
    khác nhau cho 2 trường hợp này, nên PHẢI truyền đúng."""
    if not VOYAGE_API_KEY:
        log.error("[RAG] ❌ Thiếu VOYAGE_API_KEY — bỏ qua embedding.")
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                VOYAGE_URL,
                headers={"Authorization": f"Bearer {VOYAGE_API_KEY}", "Content-Type": "application/json"},
                json={"input": [text], "model": VOYAGE_MODEL, "input_type": input_type},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    log.error(f"[RAG] ❌ Voyage API lỗi {resp.status}: {err[:200]}")
                    return None
                data = await resp.json()
                return data["data"][0]["embedding"]
    except Exception as e:
        log.error(f"[RAG] ❌ Lỗi gọi embedding API: {e}")
        return None


async def get_embeddings_batch(texts: list[str], input_type: str = "document") -> list[list[float]] | None:
    """Embed NHIỀU đoạn text trong 1 lần gọi API — dùng cho backfill (vd message_search.py),
    giảm hẳn số lượt gọi Voyage so với embed từng câu một. Trả về list embedding ĐÚNG
    THỨ TỰ với texts đầu vào. Bên gọi tự chia batch vừa phải (vd 50 tin/lần) — hàm này
    không tự giới hạn kích thước batch."""
    if not VOYAGE_API_KEY:
        log.error("[RAG] ❌ Thiếu VOYAGE_API_KEY — bỏ qua embedding.")
        return None
    if not texts:
        return []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                VOYAGE_URL,
                headers={"Authorization": f"Bearer {VOYAGE_API_KEY}", "Content-Type": "application/json"},
                json={"input": texts, "model": VOYAGE_MODEL, "input_type": input_type},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    log.error(f"[RAG] ❌ Voyage API lỗi {resp.status}: {err[:200]}")
                    return None
                data = await resp.json()
                return [item["embedding"] for item in data["data"]]
    except Exception as e:
        log.error(f"[RAG] ❌ Lỗi gọi batch embedding API: {e}")
        return None


# ══════════════════════════════════════════
# LƯU / CẬP NHẬT Q&A
# ══════════════════════════════════════════
async def save_qa_to_rag(doc_id: str, guild_id: int, question: str, answer: str) -> bool:
    """Upsert 1 Q&A vào knowledge base. doc_id nên là resolved_thread_id (dạng str)
    để lần sau admin sửa câu trả lời, chỉ cần replace_one theo đúng _id này —
    tránh tồn tại 2 bản ghi (cũ + mới) cho cùng 1 câu hỏi."""
    embedding = await get_embedding(question, input_type="document")
    if embedding is None:
        return False

    col = _get_knowledge_collection()
    try:
        await col.replace_one(
            {"_id": doc_id},
            {
                "_id": doc_id,
                "guild_id": guild_id,
                "question": question,
                "answer": answer,
                "embedding": embedding,
                "updated_at": datetime.now(timezone.utc),
            },
            upsert=True,
        )
        return True
    except Exception as e:
        log.error(f"[RAG] ❌ Lỗi lưu vào MongoDB: {e}")
        return False


async def delete_qa_from_rag(doc_id: str) -> None:
    """Dùng khi admin xoá/huỷ 1 post resolved, tránh RAG trả lời theo data đã xoá."""
    col = _get_knowledge_collection()
    try:
        await col.delete_one({"_id": doc_id})
    except Exception as e:
        log.error(f"[RAG] ❌ Lỗi xoá khỏi MongoDB: {e}")


# ══════════════════════════════════════════
# TÌM KIẾM
# ══════════════════════════════════════════
async def search_rag(guild_id: int, query: str, top_k: int = 3) -> list[dict]:
    """Trả về list các Q&A gần nghĩa nhất, đã lọc theo guild_id, kèm score (0..1).
    Trả về [] nếu chưa cấu hình embedding hoặc lỗi — CHỖ GỌI phải tự xử lý
    trường hợp rỗng (coi như không có kiến thức liên quan)."""
    query_embedding = await get_embedding(query, input_type="query")
    if query_embedding is None:
        return []

    col = _get_knowledge_collection()
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 50,
                "limit": top_k,
                "filter": {"guild_id": guild_id},
            }
        },
        {
            "$project": {
                "question": 1,
                "answer": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    try:
        results = []
        async for doc in col.aggregate(pipeline):
            results.append(doc)
        return results
    except Exception as e:
        # Lỗi thường gặp nhất ở đây: chưa tạo Vector Search Index trên Atlas,
        # hoặc tên index sai lệch với VECTOR_INDEX_NAME.
        log.error(f"[RAG] ❌ Lỗi $vectorSearch: {e}")
        return []


async def get_relevant_context(guild_id: int, query: str) -> str | None:
    """Helper tiện dụng cho ai_chat.py: tìm Q&A liên quan, trả về đoạn text
    sẵn sàng nhét vào prompt, hoặc None nếu không có gì đủ tin cậy."""
    matches = await search_rag(guild_id, query, top_k=3)
    good = [m for m in matches if m.get("score", 0) >= RAG_SCORE_THRESHOLD]
    if not good:
        return None
    return "\n\n".join(f"Q: {m['question']}\nA: {m['answer']}" for m in good)
