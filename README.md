# 🤖 TuyTam Bot (Rudeus Bot)

Bot Discord đa server quản lý shop, ticket, giveaway cho TuyTam Store — kiến trúc multi-guild qua MongoDB, mỗi guild lưu data tách riêng.

## ✨ Tính năng chính

### 🎫 Ticket System
- Panel embed mở ticket theo nhiều loại (mua/bán DonutSMP, KingMC, One MC, Free Fire, Base, Acc Pre, giveaway, hỗ trợ)
- Gán role staff riêng cho từng loại ticket (multi-role, qua `.st` hoặc `.setrole`)
- Đóng ticket, xuất transcript HTML, relay tin nhắn admin qua webhook ("Ruby bot")
- Thống kê đơn hàng theo tháng, top buyer

### 🔨 Moderation
- Ban/Kick/Timeout/Warn với DM thông báo, tempban tự unban (sống sót qua restart)
- Automod: chặn link, invite, spam, từ cấm
- Whitelist role/user

### 🤖 AI Chat
- Tích hợp Groq (llama-3.x, gemma2) — chat, tóm tắt, dịch, phân tích văn bản
- Admin điều khiển bot bằng ngôn ngữ tự nhiên (tạo/xoá kênh, role, purge, ban/kick/mute — có bước xác nhận trước khi chạy)

### 📨 Invite Tracking
- Ghi nhận người mời ngay lúc member join, leaderboard theo tháng
- (Tính năng verify/IP chống fake acc đã được gỡ bỏ — xem CHANGELOG.md)

### 🎉 Giveaway
- Tạo qua modal, chọn thời gian/số người trúng/phần thưởng
- Reroll, kết thúc sớm, resume tự động sau khi bot restart (kể cả giveaway dài ngày)

### 🛒 Auto Buy — bán tài khoản Minecraft tự động
- **Chỉ seller còn hạn (`.seller list`) hoặc owner, và đã `.shopbank`** mới nạp kho/đăng bán được — đăng ký bank bằng `.shopbank` + **ảnh QR ngân hàng** (bot tự đọc) hoặc **admin gán giúp** bằng `.setbank <@seller|ID> <mã NH|BIN> <số TK> [tên]`
- `/add_acc` nạp thông tin đăng nhập vào kho → `/stock acc` đăng **card ảnh** (skin, cape, rank, stats, giá; header là **tên + icon server**) + nút **BUY**
- Khách bấm BUY → ticket riêng + **QR VietQR** (bank của seller đăng ký bằng `.shopbank`); **SePay báo tiền về là bot TỰ GIAO** tài khoản qua DM
- Chưa bật Shop Orders / seller chưa `.shopbank` → seller/staff bấm **Confirm** tay (giống bot autobuy cũ)
- Giao xong: card thành SOLD, kênh stock chuyển sang danh mục sold, gửi bill, cộng BXH `.bxh` + thống kê seller, nhắc khách vouch
- Hướng dẫn đầy đủ trong bot: `.help autobuy` (7 trang: tổng quan, cài đặt, đăng bán, khách mua, thanh toán, quản lý, sự cố) — chuyển trang bằng menu/nút
- Cấu hình: `.abset` (ticket/bill/youtube/2fa/lock/vouch/qr) — stock/sold dùng chung `.st` · `.abresend <user>` gửi lại DM · `/ab_import` nhập kho từ bot Node cũ · `/restock` liệt kê kênh stock

### 💰 Seller Subscription
- Theo dõi gian hàng thuê theo thời gian, cảnh báo sắp hết hạn + tự động hết hạn
- Thống kê doanh số theo seller

### 🧾 Shop Orders (VietQR) — *thử nghiệm*
- Sinh mã QR thanh toán động, hàng đợi xử lý đơn gắn vào `.done`
- Bật/tắt độc lập qua `.st`, mặc định tắt

### 📋 Vouch / Legit
- Reaction emoji tự động cho kênh legit/vouch (emoji cấu hình được riêng từng guild)
- Đổi tên kênh theo số lượng vouch, có hàng đợi retry khi bị Discord rate-limit (lưu MongoDB, sống sót qua restart)

## 📋 Lệnh chính

| Lệnh | Mô tả |
|------|-------|
| `.help` | Xem tất cả lệnh |
| `.panel` | Tạo panel ticket |
| `.sv` | Xem bảng giá dịch vụ |
| `.ai <câu hỏi>` | Chat với AI |
| `.st` | Cài đặt bot (kênh log, role ticket, emoji, bật/tắt tính năng...) |
| `.setrole <key> @role` | Gán role staff cho 1 loại ticket |
| `.baocao` | Xuất báo cáo 24h thủ công |

## ⚙️ Cài đặt

### Yêu cầu
- Python 3.11 (khớp `runtime.txt` — môi trường dev/Termux có thể khác, kiểm tra nếu gặp lỗi lạ)
- MongoDB Atlas
- Discord Bot Token (bật đủ Privileged Gateway Intents: Members, Message Content, Presence)

### Biến môi trường
```env
TOKEN=your_discord_token
MONGO_URI=your_mongodb_uri
ADMIN_RUBY_ID=discord_user_id
ADMIN_TUYTAM_ID=discord_user_id
GROQ_API_KEY=your_groq_key
SEPAY_WEBHOOK_API_KEY=random_secret_string   # khớp với API Key khai trong SePay (webhook /webhook/sepay)
PORT=8000

# Tuỳ chọn
TUYTAM_NOTIFY_ID=discord_user_id   # người nhận thông báo shop (mặc định = ADMIN_TUYTAM_ID)
GEMINI_API_KEY=your_gemini_key     # bật thêm model Gemini cho AI chat
LOG_LEVEL=INFO
ADMIN_DEBUG=0
```
`ADMIN_RUBY_ID`/`ADMIN_TUYTAM_ID` là 2 biến riêng biệt (không gộp chung 1 biến `ADMIN_IDS`) — mỗi biến 1 user ID.

### Triển khai (VPS)
Bot chạy trên VPS Ubuntu dưới dạng service systemd `tuytam-bot` (không còn dùng Railway; `Procfile` chỉ còn là di sản).
- Môi trường: `/root/bot` + `venv/` riêng, chạy `python bot.py`.
- Tự cập nhật: script `autoupdate.sh` (đặt ngoài repo, chạy mỗi 5 phút) làm lần lượt:
  1. `git fetch`; nếu không có commit mới trên nhánh hiện tại thì thoát, KHÔNG restart.
  2. `git merge --ff-only`; nếu `requirements.txt` đổi thì `pip install -r` lại.
  3. `systemctl restart tuytam-bot`, đợi 20 giây rồi kiểm tra service còn chạy.
  4. Nếu service lỗi: `git reset --hard` về commit cũ, ghi commit lỗi vào `/root/.tuytam_bad_commit` (bị bỏ qua cho đến khi có commit mới), cài lại thư viện và restart.
- Log cập nhật: `/var/log/tuytam-autoupdate.log`; log bot: `journalctl -u tuytam-bot`.
- ⚠️ MỌI commit mới lên `main` (kể cả chỉ sửa tài liệu) đều làm bot restart trong vài giây, và script chỉ phát hiện lỗi lúc khởi động — hãy chạy test (`python3 -m unittest discover -s tests -p "test_*.py"`) trước khi push.
- Webhook SePay (`/webhook/sepay`) cần URL công khai trỏ tới `PORT` của bot (qua reverse proxy hoặc mở cổng).

### Cấu trúc file
```
bot-main/
├── bot.py                  # Entry point: load cogs, on_ready, on_message
├── verify_server.py        # FastAPI — webhook SePay (/webhook/sepay) + /health, chạy chung process với bot
├── bot_ai.py / bot_ticket.py / bot_shop.py / bot_growth.py   # entry point riêng cho từng bot con (pilot)
├── AI_CONTEXT.md           # Bối cảnh dự án cho AI session (kiến trúc, quy ước code)
├── CHANGELOG.md
├── README.md
├── requirements.txt
├── runtime.txt
├── Procfile                # di sản từ thời Railway (VPS dùng systemd)
├── shared/
│   ├── data.py             # Hạ tầng dùng chung: Mongo cache theo guild (ContextVar), admin, AUTH_GATE
│   ├── auth_gate.py        # Cổng ủy quyền server + log lệnh
│   └── logger.py           # send_log() dùng chung
├── assets/autobuy/         # Nền card (card_bg.png) + font (font.ttf; bỏ Minecraft.ttf vào đây nếu muốn)
├── core/
│   ├── autobuy_logic.py / autobuy_card.py / autobuy_help_data.py   # Auto Buy: hàm thuần, vẽ card Pillow, nội dung .help autobuy
│   ├── data.py             # Accessor riêng từng tính năng (ticket, seller, giveaway, cfg_*...)
│   ├── ai_tools.py / ai_agents.py / rag.py / message_search.py / site_feed.py
│   └── __init__.py
├── tests/                  # python3 -m unittest discover -s tests -p "test_*.py"
└── cogs/
    ├── __init__.py
    ├── admin.py             # Commands admin, .st, .help, xử lý đơn "đã bán"
    ├── admin_views.py       # View/Modal cho admin.py (setup, settings, role picker...)
    ├── ai_chat.py           # AI Chat (Groq) + AI điều khiển bot có xác nhận
    ├── giveaway.py
    ├── invite.py            # Invite tracking
    ├── autobuy.py           # Auto Buy: kho acc MC, card ảnh, ticket + QR, tự giao qua SePay
    ├── autobuy_help.py      # Giao diện `.help autobuy` (menu chọn trang)
    ├── leaderboard.py       # Bảng xếp hạng chi tiêu (.bxh)
    ├── legit.py             # Vouch/legit + đổi tên kênh có hàng đợi
    ├── listings.py          # Đăng sản phẩm (/post, .addlisting)
    ├── logger.py            # Log đa kênh + báo cáo 24h
    ├── mod.py               # Ban/kick/timeout/warn/automod
    ├── seller.py            # Seller subscription
    ├── shop_admin.py        # Bảng giá, đơn "sold", DM hỏi giá/người mua
    ├── shop_orders.py       # VietQR + SePay (thử nghiệm)
    └── ticket.py            # Ticket + vouch/legit
```

Kiến trúc multi-guild: mỗi guild có 1 document Mongo riêng (`guild_<id>`), truy cập qua `load_data()`/`save_data()` — các hàm này đọc guild hiện tại từ `contextvars.ContextVar`, xem chi tiết quy ước trong `AI_CONTEXT.md`.

## 📊 Version
**v4.66.0** (xem `BOT_VERSION` trong `bot.py`) — Xem [CHANGELOG.md](CHANGELOG.md) để biết lịch sử thay đổi.
