# 📋 CHANGELOG — TuyTam Bot (Rudeus Bot)

> **Hướng dẫn cho AI:** Mỗi lần sửa code, hãy thêm 1 entry mới vào đầu danh sách bên dưới.
> Format: `## [vX.X.X] — YYYY-MM-DD` rồi liệt kê thay đổi theo nhóm.
> Tăng version: patch (x.x.**X**) khi sửa lỗi nhỏ, minor (x.**X**.0) khi thêm tính năng, major (**X**.0.0) khi thay đổi lớn.
> Cập nhật `BOT_VERSION` trong `bot.py` và `cogs/admin.py` cho khớp.

---

## [v3.5.0] — 2026-05-16

### ✨ Thêm mới
- `cogs/point.py` — Hệ thống tích điểm hoàn chỉnh:
  - `.redeem <mã>` — User nhập mã nhận point (1 lần/24h, cooldown tự động)
  - `.point [@user]` — Xem point hiện có + cooldown còn lại
  - `.addpoint @user <số>` — Admin cộng/trừ point thủ công
  - `.gencode [@user]` — Admin tạo mã (hết hạn theo config)
  - `.pointcfg [key value]` — Xem và sửa cấu hình point
  - `.pointlog [@seller]` — Thống kê tiền cần bù cho seller
  - `.buixong @seller <tiền>` — Đánh dấu đã bù tiền seller
  - Hỗ trợ `@mention`, ID, hoặc username trong tất cả lệnh
- `backend/main.py` — FastAPI backend deploy trên Render:
  - `GET /code/generate` — Website gọi để tạo mã tự động sau khi vượt Linkvertise
  - `POST /code/redeem` — Bot gọi để xác minh mã và cộng point
  - `GET /user/{id}/points` — Lấy point của user
  - Bảo mật bằng `X-API-Secret` header
- `index.html` — Trang destination Linkvertise tự động hiện mã + đếm ngược hết hạn
- Tích hợp point vào `.done`:
  - Nếu buyer có point → bot hỏi staff có dùng không
  - Tự động trừ point, tính giảm giá (tối đa 20% giá trị đơn)
  - Tự động ghi nhận tiền cần bù cho seller
- Thống kê ticket: `.ticketinfo [@user]`, `.thongke [MM/YYYY]`
- Automod whitelist: `.automod addrole/delrole/adduser/deluser/whitelist`

### 🔧 Thay đổi
- `core/data.py` — Thêm các field: `user_points`, `point_codes`, `point_log`, `seller_compensation`, `point_cfg`, `ticket_history`
- `cogs/ticket.py` — Xoá rating, seller management, nút Mua (claim); thêm lịch sử đơn
- `cogs/admin.py` — Cập nhật help đầy đủ, version 3.5.0
- `cogs/mod.py` — Thêm whitelist user/role cho automod
- Biến môi trường mới trên Railway: `POINT_API_URL`, `POINT_API_SECRET`

### 🐛 Sửa lỗi
- Fix 2 hàm `help_cmd` trùng lặp trong `admin.py`
- Fix automod check whitelist dùng `whitelist_users` thay vì chỉ `whitelist_roles`

---

## [v3.4.1] — 2026-05-15

### ✨ Thêm mới
- `cogs/mod.py` — Hệ thống mod đầy đủ:
  - **Ban/Unban/Kick/Mute/Unmute** — có DM thông báo cho user, log vào kênh log rudy
  - **Slowmode/Lock/Unlock** — quản lý kênh
  - **Warn system** — cảnh cáo + tự động phạt theo số warn (mute → kick → ban)
  - **Auto-mod** — xoá link, xoá invite Discord, anti-spam, từ cấm
  - Tất cả lệnh đều có cả dạng prefix (`.ban`) và slash (`/ban`)
- Lệnh automod group: `.automod on/off/links/invites/spam/addword/delword/words`

### 🔧 Thay đổi
- Thêm `cogs.mod` vào COGS list trong `bot.py`
- Dữ liệu mod lưu vào MongoDB qua `load_data()`/`save_data()`

---

## [v3.4.0] — 2026-05-14

### ✨ Thêm mới
- `cogs/logger.py` — Hệ thống log tập trung, ghi mọi hoạt động bot vào kênh **log rudy**
- Slash commands cho tất cả lệnh prefix: `/close`, `/done`, `/addnote`, `/ratings`, `/addseller`, `/listseller`, `/balance`, `/balset`, `/balreset`, `/ai`, `/aireset`, `/mychat`, `/invite`, `/invitetop`, `/resetinvite`
- Prefix commands mới: `.ping`, `.userinfo`, `.serverinfo`
- Alias mới: `.st` (settings), `.b` (balance), `.i` (invite), `.h` (help), `.ui` (userinfo), `.si` (serverinfo)

### 🔧 Thay đổi
- Loại bỏ `cfg_log_channel` — thay bằng `cfg_log_rudy` làm kênh log duy nhất
- `.help` cập nhật hiển thị đầy đủ cả lệnh `.` và `/`
- Cấu trúc bot tách thành nhiều Cog: `ticket`, `balance`, `ai_chat`, `invite`, `giveaway`, `admin`, `logger`

### 🐛 Sửa lỗi
- Fix `CommandAlreadyRegistered` do `bot.tree.add_command()` thủ công trùng với `@app_commands.command`
- Fix slash sync 0 commands do sync chạy trước khi cog load xong

---

## [v3.3.5] — 2026-05-12

### ✨ Thêm mới
- Tách `bot.py` 6000 dòng thành cấu trúc Cog (`core/`, `cogs/`)
- `cogs/giveaway.py` — Giveaway với nút tham gia, confirm view, check invite winner
- `cogs/ai_chat.py` — AI chat tích hợp Groq (llama-3, gemma2) với fallback model
- `cogs/invite.py` — Invite tracking: đếm net/fake/left, leaderboard, fake detect tự động
- `cogs/balance.py` — Balance channel: gõ `+số`/`-số` tự động nạp/chi, phí 5%
- `cogs/ticket.py` — Ticket system: panel, close, done, transcript HTML, rating, seller

### 🔧 Thay đổi
- Toàn bộ data lưu MongoDB (motor), cache in-memory
- `bot.py` gọn còn ~150 dòng

---

## [v3.x.x] — Trước 2026-05-12

- Các phiên bản cũ chạy trên `bot.py` đơn file (~6000 dòng)
- Tính năng cốt lõi: ticket, balance, giveaway, AI, invite, log transcript, feedback

---

> **Kênh log trong bot:**
> | Kênh | Mục đích | Cài bằng |
> |------|----------|----------|
> | Log Rudy (`cfg_log_rudy`) | Mọi hoạt động bot | `.st` → 📋 Log Channel |
> | Transcript (`TRANSCRIPT_CHANNEL_ID`) | Transcript khi đóng ticket | Hardcode `data.py` |
> | Feedback (`FEEDBACK_CHANNEL_ID`) | Đánh giá ⭐ từ user | Hardcode `data.py` |
> | Changelog (`CHANGELOG_CHANNEL_ID`) | Thông báo bot restart | Hardcode `data.py` |

> **Cấu trúc file:**
> ```
> tuytam_bot/
> ├── bot.py
> ├── CHANGELOG.md         ← file này
> ├── requirements.txt
> ├── core/
> │   ├── __init__.py
> │   └── data.py          ← MongoDB, cache, helpers
> └── cogs/
>     ├── __init__.py
>     ├── logger.py        ← log tập trung
>     ├── ticket.py        ← ticket system + lịch sử đơn
>     ├── balance.py       ← (stub, không dùng)
>     ├── ai_chat.py       ← Groq AI
>     ├── invite.py        ← invite tracking
>     ├── giveaway.py      ← giveaway
>     ├── mod.py           ← ban/kick/mute/warn/automod
>     ├── point.py         ← hệ thống point + seller compensation
>     └── admin.py         ← settings, sv, help
> ```
