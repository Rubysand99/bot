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

### 📨 Invite Tracking + Chống Fake Acc
- Đếm invite theo 5 trạng thái: total/unverify/verify/fake/left, leaderboard theo tháng
- Verify server (FastAPI) xác minh IP qua link riêng cho từng member, phát hiện multi-acc/VPN
- Backfill IP lịch sử (`.backfillip`)

### 🎉 Giveaway
- Tạo qua modal, chọn thời gian/số người trúng/phần thưởng
- Reroll, kết thúc sớm, resume tự động sau khi bot restart (kể cả giveaway dài ngày)

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
| `.backfillip` | Quét lại IP lịch sử cho member cũ |

## ⚙️ Cài đặt

### Yêu cầu
- Python 3.11 (khớp `runtime.txt` — môi trường dev/Termux có thể khác, kiểm tra nếu gặp lỗi lạ)
- MongoDB Atlas
- Discord Bot Token (bật đủ Privileged Gateway Intents: Members, Message Content, Presence)

### Biến môi trường (Railway)
```env
TOKEN=your_discord_token
MONGO_URI=your_mongodb_uri
ADMIN_RUBY_ID=discord_user_id
ADMIN_TUYTAM_ID=discord_user_id
GROQ_API_KEY=your_groq_key
VERIFY_SECRET=random_secret_string
VERIFY_BASE_URL=https://your-app.up.railway.app
PORT=8000
```
`ADMIN_RUBY_ID`/`ADMIN_TUYTAM_ID` là 2 biến riêng biệt (không gộp chung 1 biến `ADMIN_IDS`) — mỗi biến 1 user ID.

### Cấu trúc file
```
bot-main/
├── bot.py                  # Entry point: load cogs, on_ready, on_message
├── verify_server.py        # FastAPI — xác minh IP, chạy chung process với bot
├── AI_CONTEXT.md           # Bối cảnh dự án cho AI session (kiến trúc, quy ước code)
├── CHANGELOG.md
├── README.md
├── requirements.txt
├── runtime.txt
├── Procfile
├── core/
│   ├── __init__.py
│   └── data.py             # MongoDB, cache theo guild (ContextVar), mọi hàm đọc/ghi data
└── cogs/
    ├── __init__.py
    ├── admin.py             # Commands admin, .st, .help, xử lý đơn "đã bán"
    ├── admin_views.py       # View/Modal cho admin.py (setup, settings, role picker...)
    ├── ai_chat.py           # AI Chat (Groq) + AI điều khiển bot có xác nhận
    ├── giveaway.py
    ├── invite.py            # Invite tracking + verify/IP fraud
    ├── logger.py            # Log đa kênh + báo cáo 24h
    ├── mod.py               # Ban/kick/timeout/warn/automod
    ├── seller.py            # Seller subscription
    ├── shop_orders.py       # VietQR (thử nghiệm)
    └── ticket.py            # Ticket + vouch/legit
```

Kiến trúc multi-guild: mỗi guild có 1 document Mongo riêng (`guild_<id>`), truy cập qua `load_data()`/`save_data()` — các hàm này đọc guild hiện tại từ `contextvars.ContextVar`, xem chi tiết quy ước trong `AI_CONTEXT.md`.

## 📊 Version
**v4.11.5** — Xem [CHANGELOG.md](CHANGELOG.md) để biết lịch sử thay đổi.
