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
