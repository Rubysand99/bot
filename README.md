# 🤖 Rudeus Bot — TuyTam Store

Bot Discord quản lý server, ticket, point, minigame cho TuyTam Store.

## ✨ Tính năng chính

### 🎫 Ticket System
- Tạo ticket mua hàng, hỗ trợ, giveaway qua panel embed
- Đóng ticket, xuất transcript HTML
- Thống kê đơn hàng theo tháng

### 💎 Hệ thống Point
- Redeem mã nhận point, đổi quà trong shop
- Admin cộng/trừ/set point theo ID
- Thống kê point toàn server

### 🎲 Minigame
- **Bầu Cua nhiều người** — 4-6 người cùng cược, tự động lắc
- **Búa Kéo Bao** — đấu với bot, có cá cược
- Bảng xếp hạng, thống kê cá nhân

### 🔨 Moderation
- Ban/Kick/Mute/Warn với DM thông báo
- Automod: chặn link, invite, spam, từ cấm
- Whitelist role/user

### 🤖 AI Chat
- Tích hợp Groq (llama-3, gemma2)
- Tóm tắt, dịch, phân tích văn bản

### 📨 Invite Tracking
- Đếm invite net/fake/left
- Leaderboard invite

### 🎉 Giveaway
- Tạo giveaway với nút tham gia
- Check invite winner

## 📋 Lệnh chính

| Lệnh | Mô tả |
|------|-------|
| `.help` | Xem tất cả lệnh |
| `.bc open` | Mở phiên Bầu Cua |
| `.bkb <búa\|kéo\|bao>` | Búa Kéo Bao vs Bot |
| `.rank` | Bảng xếp hạng minigame |
| `.point` | Xem point của bản thân |
| `.shop` | Xem cửa hàng đổi quà |
| `.redeem <mã>` | Nhận point bằng mã |
| `.panel` | Tạo panel ticket |
| `.ai <câu hỏi>` | Chat với AI |
| `.st` | Cài đặt bot |

## ⚙️ Cài đặt

### Yêu cầu
- Python 3.10+
- MongoDB Atlas
- Discord Bot Token

### Biến môi trường (Railway)
```env
TOKEN=your_discord_token
MONGO_URI=your_mongodb_uri
ADMIN_IDS=id1,id2,id3
POINT_API_URL=https://your-app.onrender.com
POINT_API_SECRET=your_secret
```

### Cấu trúc file
```
tuytam_bot/
├── bot.py
├── CHANGELOG.md
├── README.md
├── requirements.txt
├── runtime.txt
├── core/
│   └── data.py
├── cogs/
│   ├── admin.py
│   ├── ai_chat.py
│   ├── balance.py
│   ├── giveaway.py
│   ├── invite.py
│   ├── logger.py
│   ├── minigame.py
│   ├── mod.py
│   ├── point.py
│   └── ticket.py
└── data/
    └── words_vi.txt
```

## 📊 Version
**v3.7.1** — Xem [CHANGELOG.md](CHANGELOG.md) để biết lịch sử thay đổi.
