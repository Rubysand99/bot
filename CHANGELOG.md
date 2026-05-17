# 📋 CHANGELOG — TuyTam Bot (Rudeus Bot)

---

## [v3.7.0] — 2026-05-17

### ✨ Thêm mới
- **🎲 Bầu Cua nhiều người** — Phiên cược 4-6 người, 30 giây:
  - `.bc open` — Mở phiên trong kênh chỉ định
  - Embed hiện 6 nút có emoji + tên mặt
  - Nhấn nút → Modal nhập số point cược (tối thiểu 1pt, không giới hạn tối đa)
  - Tự động lắc ngay khi tất cả đã chọn (không cần chờ hết 30s)
  - Tự động lắc sau 30s dù chưa đủ người
  - `.bc cancel` — Host/admin hủy phiên
  - `.setbaucua #kênh` — Admin cài kênh chơi
  - Tỉ lệ: x1→+0.9pt | x2→+1.8pt | x3→+2.7pt | Thua→-1pt

### 🗑️ Xóa
- Nối Từ — bỏ do từ điển hạn chế
- Vua Tiếng Việt — bỏ do ít câu hỏi

### 🔧 Thay đổi
- `core/data.py` — Thêm `baucua_channel_id: 0`
- `BOT_VERSION = "3.7.0"`

---

## [v3.6.3] — 2026-05-16
- Cá cược point cho tất cả game
- Bảng xếp hạng `.rank`
- Thống kê cá nhân `.mgstats`

## [v3.6.2] — 2026-05-16
- Kênh nối từ chỉ định, `.start` / `.stop`

## [v3.6.1] — 2026-05-16
- Fix race condition, cooldown, session safety

## [v3.6.0] — 2026-05-16
- 4 minigame: Bầu Cua, Búa Kéo Bao, Nối Từ, Vua Tiếng Việt

## [v3.5.2] — 2026-05-16
- `.clearshop`

## [v3.5.1] — 2026-05-16
- Hệ thống đổi quà

## [v3.5.0] — 2026-05-16
- Hệ thống tích điểm

## [v3.4.1] — 2026-05-15
- cogs/mod.py

## [v3.4.0] — 2026-05-14
- logger, slash commands

## [v3.3.5] — 2026-05-12
- Cấu trúc Cog, MongoDB
