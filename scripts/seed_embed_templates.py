"""
scripts/seed_embed_templates.py

Ghi thẳng 3 mẫu thông báo "gia-1", "gia-2", "gia-3" vào MongoDB (bỏ qua
in-memory cache của bot) — dùng 1 lần để không phải copy-paste tay 3 lần
qua .embed + nút 💾 Lưu làm mẫu.

⚠️ QUAN TRỌNG: bot cache dữ liệu theo guild trong RAM (core/data.py:
_data_cache), chỉ nạp lại từ Mongo lúc khởi động. Script này ghi trực tiếp
xuống Mongo nên PHẢI RESTART BOT sau khi chạy thì `.embeduse gia-1` mới
thấy được mẫu (nếu bạn deploy qua Railway, chỉ cần push code là bot tự
restart, chạy script này trước hoặc sau lúc push đều được — miễn bot có
khởi động lại 1 lần sau khi script chạy xong).

Cách chạy (Termux, cùng thư mục có core/data.py):
    python3 scripts/seed_embed_templates.py [GUILD_ID]

Nếu không truyền GUILD_ID, mặc định dùng server chính (LEGACY_MAIN_GUILD_ID
trong core/data.py). Cần biến môi trường MONGO_URI đã cấu hình (giống bot).
"""

import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("❌ Thiếu biến môi trường MONGO_URI!")

# Trùng với core/data.py — server chính (TuyTam Community).
DEFAULT_GUILD_ID = 1464407860640219189

GUILD_ID = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GUILD_ID

ORANGE = 0xF97316

TEMPLATES = {
    "gia-1": {
        "title": "📢 Thông báo điều chỉnh giá dịch vụ",
        "description": (
            "Xin chào tất cả thành viên! 👋\n\n"
            "Từ hôm nay mình chính thức quản lý toàn bộ shop dịch vụ tại server. "
            "Giá các mặt hàng dưới đây đã được cập nhật. Các đơn đã đặt trước thời "
            "điểm này vẫn giữ giá cũ.\n\n"
            "🎮 **Game Steam**\n"
            "• Acc offline đồng giá: **65.000đ**\n\n"
            "🔷 **Robux**\n"
            "• 250 Robux: **52.000đ**\n"
            "• 500 Robux: **94.000đ**\n"
            "• 750 Robux: **134.000đ**\n"
            "• 1000 Robux: **170.000đ**\n\n"
            "Xem tiếp phần Nacho & Decao ở thông báo kế tiếp 👇"
        ),
        "color": ORANGE, "image": None, "thumbnail": None, "footer": None,
    },
    "gia-2": {
        "title": "💎 Giá mới: Nacho & Decao",
        "description": (
            "💎 **Nacho**\n"
            "• 1 tháng: **100.000đ**\n"
            "• 2 tháng: **124.000đ**\n"
            "• 12 tháng: **904.000đ**\n\n"
            "👹 **Decao — Dạng login**\n"
            "• **40.000đ**\n• **50.000đ**\n• **60.000đ**\n• **67.000đ**\n"
            "• **79.000đ**\n• **84.000đ**\n• **97.000đ**\n• **104.000đ**\n"
            "• **108.000đ**\n• **114.000đ**\n• **130.000đ**\n\n"
            "👹 **Decao — Dạng gip**\n"
            "• **53.000đ**\n• **63.000đ**\n• **67.000đ**\n• **74.000đ**\n"
            "• **90.000đ**\n• **94.000đ**\n• **104.000đ**\n• **114.000đ**\n"
            "• **119.000đ**\n• **124.000đ**\n• **144.000đ**"
        ),
        "color": ORANGE, "image": None, "thumbnail": None, "footer": None,
    },
    "gia-3": {
        "title": "🎬 Giá mới: Gip Bundle & dịch vụ khác",
        "description": (
            "👹 **Decao — Gip Bundle**\n"
            "• x2 dc66: **90.000đ**\n• x3 dc66: **125.000đ**\n"
            "• x3 dc79: **145.000đ**\n• x2 dc92: **120.000đ**\n"
            "• x3 dc92: **170.000đ**\n• x2 dc105: **120.000đ**\n"
            "• x2 dc118: **155.000đ**\n• x3 dc118: **245.000đ**\n"
            "• x2 dc131: **175.000đ**\n\n"
            "🎬 **Dịch vụ khác**\n"
            "• Capcut Pro 7 ngày: **20.000đ**\n"
            "• Capcut Pro 1 tháng: **65.000đ**\n"
            "• Canva Pro 2 tháng: **20.000đ**\n"
            "• YouTube Premium: **20k/tháng**\n"
            "• Netflix: **65k/tháng**\n"
            "• ChatGPT Plus: đang hết hàng, cập nhật giá khi có lại\n\n"
            "📌 Mọi thắc mắc, vui lòng nhắn trực tiếp hoặc tạo ticket. "
            "Cảm ơn mọi người đã ủng hộ! ❤️"
        ),
        "color": ORANGE, "image": None, "thumbnail": None, "footer": None,
    },
}


def main():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    col = client["tuytam_bot"]["bot_data"]
    doc_id = f"guild_{GUILD_ID}"

    updates = {f"embed_templates.{name}": payload for name, payload in TEMPLATES.items()}
    result = col.update_one({"_id": doc_id}, {"$set": updates}, upsert=True)

    print(f"✅ Đã lưu {len(TEMPLATES)} mẫu vào document '{doc_id}': {', '.join(TEMPLATES)}")
    print(f"   matched={result.matched_count} modified={result.modified_count} upserted_id={result.upserted_id}")
    print("⚠️ Nhớ RESTART bot (hoặc git push để Railway tự deploy lại) thì "
          "`.embeduse gia-1` / `gia-2` / `gia-3` mới thấy được mẫu.")


if __name__ == "__main__":
    main()
