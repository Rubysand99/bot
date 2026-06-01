# 🤖 Rudeus Bot — TuyTam Store

Bot Discord quản lý server, ticket, balance, giveaway cho TuyTam Store.

## ✨ Tính năng chính

### 🎫 Ticket System
- Tạo ticket mua hàng, hỗ trợ, giveaway qua panel embed
- Đóng ticket, xuất transcript HTML
- Thống kê đơn hàng theo tháng

### 💰 Hệ thống Balance
- Cộng/trừ/set số dư trong kênh balance chỉ định
- Phí 5% khi nạp, lịch sử giao dịch 100 bản ghi gần nhất
- Thống kê tổng nạp/chi/phí, danh sách buyer

### 🔨 Moderation
- Ban/Kick/Mute/Warn với DM thông báo
- Automod: chặn link, invite, spam, từ cấm
- Whitelist role/user

### 🤖 AI Chat
- Tích hợp Groq (llama-3, gemma2)
- Tóm tắt, dịch, phân tích văn bản
- Admin điều khiển bot bằng ngôn ngữ tự nhiên

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
| `.panel` | Tạo panel ticket |
| `.balance` | Xem số dư quỹ |
| `.sv` | Xem bảng giá dịch vụ |
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
GROQ_API_KEY=your_groq_key
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
│   ├── banking.py
│   ├── giveaway.py
│   ├── invite.py
│   ├── logger.py
│   ├── mod.py
│   ├── ticket.py
│   └── __init__.py
└── data/
    └── words_vi.txt
```

## 📊 Version
**v3.9.5** — Xem [CHANGELOG.md](CHANGELOG.md) để biết lịch sử thay đổi.
