# CHANGELOG — TuyTam Bot (Rudeus Bot)

## [v4.5.0] — 2026-06-14

### 🐛 Sửa lỗi
- `cogs/logger.py` — **Fix `.setuplog` không nhận kênh log đã đổi font chữ**: dùng `discord.utils.get(name=ch_name)` so sánh tên kênh chính xác → nếu tên kênh có font Unicode (vd: `𝗹𝗼𝗴-𝘁𝗶𝗰𝗸𝗲𝘁`) sẽ không match → tạo kênh mới → không bao giờ set channel ID đúng → log không gửi được. Fix: dùng `_strip_unicode_font()` để normalize tên trước khi so sánh
- `cogs/invite.py` — **Fix DM thông báo fake hiển thị "0 tài khoản khác"**: `_ip_records` cache dùng key `"1_2_3_4"` (dấu `_`) nhưng lookup dùng `ip` raw (`"1.2.3.4"`) → `shared_users` luôn rỗng → số đếm sai trong DM
- `cogs/logger.py` — **Fix báo cáo 8h sáng gửi 2 lần khi bot restart**: `_last_report_date` chỉ lưu in-memory → reset về `None` mỗi lần restart → gửi lại nếu restart trong khung 01:00–01:59 UTC. Fix: kiểm tra thêm `_daily_report_date` trong MongoDB trước khi gửi

---

## [v4.4.0] — 2026-06-12

### ✨ Tính năng mới
- `cogs/admin_views.py` — `.mkchannel` thêm 2 dropdown mới:
  - **③ Quyền truy cập**: `🌐 Public` (mặc định) / `🔒 Private` — private ẩn kênh với `@everyone`, chỉ bot + admin thấy
  - **④ Khoá gửi tin**: `🔓 Mở` (mặc định) / `🔐 Khoá (read-only)` — lock chặn `@everyone` gửi tin trong kênh public
- `cogs/admin_views.py` — Kênh tạo ra áp `overwrites` ngay lúc tạo (bot + admin luôn full quyền)
- `cogs/admin_views.py` — Embed kết quả hiển thị thêm cột **Quyền** và **Khoá**
- `cogs/admin_views.py` — Đổi tên kênh / category: thêm ô **Icon mới** (để trống = giữ icon cũ)
- `cogs/admin.py` — Cập nhật embed hướng dẫn `.mkchannel` (5 bước rõ ràng)
- `cogs/admin.py` — Cập nhật `.help admin` mô tả `.mkchannel`

---

## [v4.3.0] — 2026-06-10

### 🐛 Sửa lỗi nghiêm trọng
- `cogs/invite.py` + `core/data.py` — **Fix bug IP check không hoạt động**: MongoDB không cho phép dấu `.` trong field name → key IP dạng `"1.2.3.4"` không bao giờ lưu/đọc đúng → mọi acc clone đều qua verify mà không bị phát hiện
- `core/data.py` — **Fix race condition**: `save_data()` ghi MongoDB bất đồng bộ (`create_task`), nếu 2 acc verify gần nhau cùng `load_data()` trước khi task ghi xong → IP acc đầu bị mất, acc sau không thấy trùng

### ✨ Tính năng mới
- `core/data.py` — Thêm `atomic_register_ip()`: dùng MongoDB `$addToSet` ghi IP trực tiếp, tránh race condition
- `core/data.py` — Thêm `get_ip_users_mongo()`: đọc IP thẳng từ MongoDB (không qua cache) khi check collision
- `cogs/invite.py` — `_check_ip_collision` và `_register_ip` chuyển thành `async`, đọc/ghi MongoDB trực tiếp
- `cogs/invite.py` — `.checkip` và `.ipstats` đọc thẳng MongoDB thay vì in-memory cache
- `cogs/invite.py` — Lệnh `.backfillip [số]` (admin): đọc lại lịch sử kênh log general, parse IP từ `INVITE_VERIFY`/`INVITE_FAKE`, backfill vào `_ip_records` (mặc định 2000 msg, idempotent)
- `cogs/admin.py` — Cập nhật `.help invite` thêm `.checkip`, `.ipstats`, `.backfillip`

### 🔧 Thay đổi kỹ thuật
- Key IP trong MongoDB đổi từ `"1.2.3.4"` → `"1_2_3_4"` (dấu `.` → `_`) để tương thích MongoDB field name

---

## [v4.2.0] — 2026-06-08

### ✨ Tính năng mới
- `cogs/invite.py` — Role `UNVERIFY` gán ngay khi join, không xem được kênh nào
- `cogs/invite.py` — Sau khi verify: tự động gán role `VERIFY`, xóa `UNVERIFY`
- `cogs/invite.py` — Trùng IP: vẫn verify được nhưng lưu `_shared_ip` data, tài khoản thứ 2+ bị chặn giveaway
- `cogs/invite.py` — Bot gửi DM giải thích rõ tình trạng cho cả tài khoản primary lẫn bị chặn
- `cogs/invite.py` — Auto-kick sau **24h** nếu member vẫn còn role UNVERIFY (chưa verify)
- `cogs/invite.py` — Lệnh `.checkip @user` (admin): xem toàn bộ tài khoản chung IP, ai được/bị chặn giveaway
- `cogs/giveaway.py` — Chặn tham gia giveaway nếu IP bị blocked, hiển thị ephemeral giải thích lý do

### 🔧 Cấu hình role (trong `invite.py`)
```
UNVERIFY_ROLE_ID = 1500512964065755288
VERIFY_ROLE_ID   = 1464411190808805540
VERIFY_GUILDS    = {1500513085096726528, 1500512893139943455}
```

---

## [v4.1.0] — 2026-06-08

### 🗑️ Xoá tính năng
- `cogs/banking.py` — Xoá toàn bộ cog banking (webhook SePay, log GD, `.banktoday`, `.banksearch`, v.v.)
- `bot.py` — Xoá `"cogs.banking"` khỏi danh sách COGS
- `core/data.py` — Xoá `_col_banktxs`, `MAX_TX_HISTORY_CACHE`, `banking_cfg` trong `_default_data()`, và block load `banking_txs` trong `init_data_cache()`
- `cogs/logger.py` — Xoá `BANK_TXNS` khỏi `LOG_ICONS` + `LOG_ROUTES`, xoá field **🏦 Ngân hàng** trong daily report, xoá block thu thập data banking

---

## [v4.0.0] — 2026-06-02

### 🔒 Bảo mật
- `core/data.py` — Xoá hoàn toàn hardcode fallback `ADMIN_IDS`. Nếu env `ADMIN_IDS` chưa set, bot log `CRITICAL` và không ai có quyền admin cho đến khi cài đúng env

### ⚡ Cải tiến hiệu năng
- `core/data.py` + `cogs/banking.py` — Tách `banking_txs` ra collection MongoDB riêng (`tuytam_bot.banking_txs`). Mỗi GD là 1 document độc lập, không còn ghi đè toàn bộ main document mỗi lần có giao dịch mới
- `cogs/banking.py` — Cache 500 GD gần nhất vào memory khi khởi động, đọc từ cache thay vì query MongoDB mỗi request

### 🧹 Refactor
- `cogs/admin.py` → tách UI Views/Modals (~1544 dòng) ra `cogs/admin_views.py`. `admin.py` còn ~771 dòng, dễ maintain hơn
- `cogs/ticket.py` + `cogs/mod.py` — Thêm `import logging`, thay 27 bare `except: pass` → `except Exception` (typed), những chỗ Discord API giữ silent, những chỗ logic khác log debug

### 📖 Help & Docs
- `cogs/admin.py` — `.help` cập nhật đầy đủ:
  - **Ticket**: thêm `.setpanel`, `.orderbase`, `.setsl`/`.removesl`/`.listsl` (stock limit)
  - **Banking**: thêm `.banktoday`, `.banksearch`, alias `.bstats`
  - **Log**: thêm `.baocao`, cập nhật nhóm log (thêm `banking`, bỏ `balance`)
  - **AI Chat**: thêm mục mới `.aireset`, `.mychat`
  - Overview embed: thêm field AI Chat

### 🗑️ Xoá tính năng
- `cogs/balance.py` — Xoá toàn bộ hệ thống balance (cộng/trừ số dư kênh)
- Xoá mọi references đến balance system trong `bot.py`, `core/data.py`, `cogs/admin.py`, `cogs/logger.py`, `cogs/ai_chat.py`, `cogs/ticket.py`

---

## [v3.9.5] — 2026-06-01

### ✨ Tính năng mới
- `giveaway.py` — Thêm lệnh `.gwstatus`: xem toàn bộ giveaway đang chạy và đã kết thúc trong data
  - 🟢 Đang chạy: GW ID, phần thưởng, thời gian còn lại, số người tham gia, kênh, message ID
  - 🔴 Đã kết thúc: GW ID, phần thưởng, winner, số người tham gia, kênh, message ID
- `admin.py` — Cập nhật `.help giveaway` thêm lệnh `.gwstatus`

---

## [v3.9.4] — 2026-05-23

### ✨ Tính năng mới
- `admin.py` — Cập nhật `.help` toàn bộ (ticket/point/ai/invite/dichvu/giveaway/mod/banking/log/admin)
- `bot.py` — Cập nhật `CHANGELOG_CHANNEL_ID`, parse CHANGELOG.md khi khởi động, hiển thị entry mới nhất

---

## [v3.8.1] — 2026-05-29

### 🔧 Sửa lỗi / Cải tiến
- `ticket.py` — Ticket **Order Base** ping thêm role `BUILDER_BASE_ROLE_ID` (1484158340849205308) khi tạo kênh

---

## [v3.8.0] — 2026-05-22

### 🔧 Sửa lỗi
- `ticket.py` — Xóa `.mkchannel` trùng → fix `CommandRegistrationError` (admin.py không load được)

---

## [v3.7.9] — 2026-05-22

### 🔧 Sửa lỗi / Cải tiến
- `core/data.py` — Thêm `get_or_fetch_channel()` (cache → fetch_channel)
- `admin/ticket/giveaway/bot` — Thay toàn bộ `bot.get_channel()` → `get_or_fetch_channel()`
- `.backfill` + auto-backfill: xử lý đúng thứ tự cũ→mới, thả ✅ + đổi tên kênh +1

---

## [v3.7.8] — 2026-05-22

### ✨ Tính năng mới
- `admin.py` — `.backfill [số]`: quét kênh legit, thả ✅ cho tin +1legit bị bỏ sót (mặc định 25, max 100)

---

## [v3.7.7] — 2026-05-22

### ✨ Tính năng mới
- `admin.py` — `.help` overview + `.help <mục>` chi tiết, alias tiếng Việt

---

## [v3.7.6] — 2026-05-22

### 🔧 Cải tiến
- `giveaway.py` — Embed giveaway giữ nguyên sau khi kết thúc, disable nút + gửi tin winner riêng

---

## [v3.7.5] — 2026-05-22

### 🔧 Sửa lỗi
- `admin.py` — Xóa `.qr` prefix trùng với `ticket.py`
- `ticket.py` — `.mkchannel` → `.sellerchannel`/`.sch`; `.done` chỉ ADMIN_IDS
- `core/data.py` — Thêm `get_seller_qr`, `save_seller_qr`, `get_all_seller_qr`

---

## [v3.7.4] — 2026-05-20

### 🔧 Cải tiến
- `core/data.py` — `BUILDER_BASE_ROLE_ID`, cập nhật `is_staff_member()`
- `ticket.py` — Builder Base tự động vào overwrites khi tạo ticket

---

## [v3.7.3] — 2026-05-18

### ✨ Tính năng mới
- `backend/main.py` — LootLabs postback → Discord webhook embed (mã/point/hạn/unique_id)

---

## [v3.7.2] — 2026-05-18

### 🔧 Cải tiến
- `point.py` — Redeem thành công + `.gencode` → log embed vào `CODE_GEN_LOG_CHANNEL_ID`

---

## [v3.7.1] — 2026-05-17

### ✨ Tính năng mới
- `.setpoint <ID> <số>`, `.pointall`/`.allpoints`/`.pointlist` (top 20, tổng point)

---

## [v3.7.0] — 2026-05-17

### ✨ Tính năng mới
- Bầu Cua nhiều người: `.bc open/cancel`, `.setbaucua`, 4-6 người, 30s, tỉ lệ x1→+0.9pt
- Xóa: Nối Từ, Vua Tiếng Việt

---

## [v3.4.x – v3.6.x] — 2026-05-14 đến 2026-05-16

### ✨ Tính năng mới
- Point system đầy đủ, FastAPI/Render, Linkvertise, `.shop .exchange .addreward .delreward .clearshop`
- Cá cược point minigame (WIN_RATE 0.9x), `.rank`, `.mgstats`
- `mod.py` Ban/Kick/Mute/Warn/Automod; `logger.py`; slash commands
- Tách bot.py 6000 dòng → cấu trúc Cog, MongoDB + cache
