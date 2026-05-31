## [v3.9.5] — 2026-05-31

### 🔧 Sửa lỗi / Refactor
- `core/data.py` — Chuyển `BOT_VERSION` & `BOT_UPDATED` vào đây làm single source of truth
- `bot.py`, `admin.py`, `ticket.py` — Import `BOT_VERSION`/`BOT_UPDATED` từ `core.data` thay vì hardcode riêng lẻ
- `ai_chat.py` — Đưa `import aiohttp` và `from core.data import load_data, fmt_amount` lên top-level (xóa 5 local import lặp bên trong hàm)
- `admin.py` — Xóa `from core.data import get_cfg_legit_channel` và `import re as _re` lặp trong thân hàm `.backfill` (đã có ở top-level)
- `banking.py` — Log cảnh báo khi `CASSO_SECRET` chưa được set lúc khởi động

---

## [v3.9.4] — 2026-05-23

### 🔧 Sửa lỗi
- Fix duplicate lệnh `.tru` trong banking.py
- Fix FakeCtx lambda trong slash `/stats`, `/txlog`, `/wallet`
- Xoá dead code `giveaway_timer()` trong giveaway.py
- Xoá `import hashlib` không dùng trong mod.py
- Đồng bộ `BOT_VERSION` trong ticket.py lên `3.9.4`

### ✨ Tính năng
- Banking: Tích hợp SePay webhook (Vietinbank + MB Bank)
- Banking: Ví ảo phí giao dịch 500đ/GD
- Mod: Discord native timeout thay thế role Muted
- Mod: Anti-spam ảnh/sticker với auto-timeout 5 phút
- Mod: Caps filter có thể tuỳ chỉnh ngưỡng %
- AI: Multi-turn clarify khi thiếu thông tin lệnh
- Setup: Phân trang kênh khi server có >25 kênh

---

## [v3.8.0] — 2026-04-15

### ✨ Tính năng
- Thêm hệ thống banking với Casso webhook
- Thêm ví ảo phí giao dịch
- Cải thiện auto-mod với whitelist role/user

---
