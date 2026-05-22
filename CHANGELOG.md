# 📋 CHANGELOG — TuyTam Bot (Rudeus Bot)

> Format: `## [vX.X.X] — YYYY-MM-DD`
> Patch (x.x.X) sửa lỗi | Minor (x.X.0) thêm tính năng | Major (X.0.0) thay đổi lớn
> Cập nhật `BOT_VERSION` trong `bot.py` và `cogs/admin.py`

---

## [v3.7.7] — 2026-05-22

### ✨ Thêm mới
- `cogs/admin.py` — Lệnh `.help` hỗ trợ sub-topic: `.help mod`, `.help ticket`, `.help point`, `.help minigame`, `.help ai`, `.help invite`, `.help dichvu`, `.help giveaway`, `.help admin`
- `.help` không có tham số → embed tổng quan gọn (3 cột inline), có hướng dẫn dùng `.help <mục>`
- `.help <mục>` → embed chi tiết từng phần với đầy đủ cú pháp, alias, mô tả
- Hỗ trợ alias tiếng Việt: `.help dịch vụ`, `.help điểm`, `.help game`…
- `BOT_VERSION = "3.7.7"`

---

## [v3.7.6] — 2026-05-22

### 🐛 Sửa lỗi
- `cogs/giveaway.py` — Embed giveaway sau khi kết thúc giữ nguyên, không bị thay thế; chỉ disable nút tham gia và gửi 1 tin nhắn thông báo winner riêng (có link dẫn đến embed gốc)

---

## [v3.7.5] — 2026-05-22

### 🐛 Sửa lỗi
- `cogs/admin.py` — Xóa lệnh `.qr` (prefix) bị trùng với phiên bản đầy đủ hơn trong `cogs/ticket.py`
- `cogs/ticket.py` — Đổi tên lệnh `.mkchannel` (seller) thành `.sellerchannel` / `.sch` để fix `CommandRegistrationError` conflict với `.mkchannel` của admin
- `cogs/ticket.py` — Lệnh `.done` và `/done` và nút "Hoàn thành đơn" chỉ cho phép `ADMIN_IDS`, seller không dùng được
- `core/data.py` — Thêm `get_seller_qr`, `save_seller_qr`, `get_all_seller_qr` (fix `ImportError` khiến `cogs.ticket` không load được)
- Đồng bộ `BOT_VERSION = "3.5.0"` thống nhất giữa `ticket.py` và `admin.py`

---

## [v3.7.4] — 2026-05-20

### ✨ Thêm mới
- `core/data.py` — Thêm `BUILDER_BASE_ROLE_ID = 1484158340849205308`, cập nhật `is_staff_member()` để role **Builder Base** có quyền dùng lệnh staff trong ticket
- `cogs/ticket.py` — Role **Builder Base** được tự động thêm vào overwrites khi tạo ticket mới (quyền giống role Seller)
- `BOT_VERSION = "3.7.4"`

---

## [v3.7.3] — 2026-05-18

### ✨ Thêm mới
- `backend/main.py` — Sau khi LootLabs postback tạo mã, backend tự động gửi embed vào kênh Discord `1504434579967316021` qua **Discord Webhook** (gồm: mã, point, thời gian hết hạn, unique_id)
- Thêm biến môi trường `DISCORD_WEBHOOK_URL` vào Render để kích hoạt tính năng này
- `BOT_VERSION = "3.7.3"`

---

## [v3.7.2] — 2026-05-18

### 🔧 Thay đổi
- `cogs/point.py` — Khi user **redeem mã thành công**, bot tự động gửi log embed vào kênh `#1504434579967316021` (gồm: user, mã, point nhận, tổng point)
- `cogs/point.py` — Khi **admin dùng `.gencode`** tạo mã, bot gửi log embed vào kênh tương tự (gồm: mã, point, hết hạn, dành cho ai, admin tạo)
- `bot.py` — Thêm constant `CODE_GEN_LOG_CHANNEL_ID = 1504434579967316021`
- `BOT_VERSION = "3.7.2"`

---

## [v3.7.1] — 2026-05-17

### ✨ Thêm mới
- `.setpoint <ID> <số>` — Admin set point chính xác cho user theo ID (kể cả user không trong server)
- `.pointall` / `.allpoints` / `.pointlist` — Admin xem thống kê point toàn server, top 20, tổng point

### 🔧 Thay đổi
- `.help` — Cập nhật section Point và Minigame
- `README.md` — Viết lại đầy đủ
- `BOT_VERSION = "3.7.1"`

---

## [v3.7.0] — 2026-05-17

### ✨ Thêm mới
- **🎲 Bầu Cua nhiều người**:
  - `.bc open` — Mở phiên cược 4-6 người, 30 giây
  - Embed 6 nút emoji, nhấn → Modal nhập point (tối thiểu 1pt)
  - Tự động lắc khi đủ người hoặc hết 30s
  - `.bc cancel` — Hủy phiên
  - `.setbaucua #kênh` — Cài kênh chơi
  - Tỉ lệ: x1→+0.9pt | x2→+1.8pt | x3→+2.7pt | Thua→-1pt

### 🗑️ Xóa
- Nối Từ (từ điển hạn chế)
- Vua Tiếng Việt (ít câu hỏi)

### 🔧 Thay đổi
- `core/data.py` — Thêm `baucua_channel_id`
- `BOT_VERSION = "3.7.0"`

---

## [v3.6.3] — 2026-05-16

### ✨ Thêm mới
- Cá cược point cho tất cả minigame (WIN_RATE 0.9x)
- `.rank [baucua|bkb|noitu|vtv]` — Bảng xếp hạng
- `.mgstats [@user]` — Thống kê cá nhân

---

## [v3.6.2] — 2026-05-16

### ✨ Thêm mới
- Kênh nối từ chỉ định — nhắn thẳng không cần prefix
- `.setnoitu #kênh`, `.start`, `.stop`

---

## [v3.6.1] — 2026-05-16

### 🐛 Sửa lỗi
- Race condition nối từ (`asyncio.Lock`)
- Cooldown per-user, chặn nối 2 lần liên tiếp
- Session VTV dùng `expire_time` timestamp
- Alias không dấu bầu cua / bkb

---

## [v3.6.0] — 2026-05-16

### ✨ Thêm mới
- 4 minigame: Bầu Cua, Búa Kéo Bao, Nối Từ, Vua Tiếng Việt
- `data/words_vi.txt` — Từ điển nối từ

---

## [v3.5.2] — 2026-05-16
- `.clearshop` — Admin xoá toàn bộ shop

## [v3.5.1] — 2026-05-16
- `.shop`, `.exchange`, `.addreward`, `.delreward`
- Point redesign: chỉ dùng đổi quà

## [v3.5.0] — 2026-05-16
- Hệ thống point đầy đủ
- FastAPI backend trên Render
- Tích hợp Linkvertise

## [v3.4.1] — 2026-05-15
- `cogs/mod.py` — Ban/Kick/Mute/Warn/Automod đầy đủ

## [v3.4.0] — 2026-05-14
- `cogs/logger.py`, slash commands cho tất cả lệnh
- `.ping`, `.userinfo`, `.serverinfo`

## [v3.3.5] — 2026-05-12
- Tách `bot.py` 6000 dòng thành cấu trúc Cog
- MongoDB + cache in-memory
- `cogs/`: ticket, balance, ai_chat, invite, giveaway, admin, logger
