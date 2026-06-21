# AI Context — TuyTam Bot

## Thông tin repo
- Repo: https://github.com/Rubysand99/bot.git
- Branch: main
- Deploy: Railway (auto-deploy khi push GitHub)
- Runtime: Python, discord.py, MongoDB Atlas

## Cấu trúc thư mục
```
~/bot/
├── bot.py
├── verify_server.py
├── CHANGELOG.md
├── cogs/
│   ├── invite.py      # Invite tracking, verify, IP check
│   ├── giveaway.py
│   ├── ticket.py
│   ├── admin.py       # Lệnh admin + .help
│   ├── admin_views.py
│   ├── mod.py
│   ├── logger.py      # Hệ thống log đa kênh
│   ├── seller.py      # Seller subscription system
│   └── ai_chat.py
└── core/
    └── data.py        # MongoDB helpers, cache, atomic ops
```

## Termux workflow
File AI sửa xong → tải về `/sdcard/Download/` → chạy lệnh sau:

```bash
cd ~/bot
cp /sdcard/Download/<tên_file> <đường_dẫn_trong_bot>
git add <đường_dẫn_1> <đường_dẫn_2> ...
git commit -m "fix/feat: mô tả"
git push origin main
```

### Ví dụ 1 file:
```bash
cd ~/bot
cp /sdcard/Download/invite.py cogs/invite.py
git add cogs/invite.py
git commit -m "fix: mô tả"
git push origin main
```

### Ví dụ nhiều file:
```bash
cd ~/bot
cp /sdcard/Download/invite.py cogs/invite.py
cp /sdcard/Download/data.py core/data.py
cp /sdcard/Download/admin.py cogs/admin.py
cp /sdcard/Download/CHANGELOG.md CHANGELOG.md
git add cogs/invite.py core/data.py cogs/admin.py CHANGELOG.md
git commit -m "fix: mô tả"
git push origin main
```

## Lưu ý
- Git credential đã lưu sẵn, không cần nhập token
- Kiểm tra không có file tên "-H" hoặc "-d" bị tạo nhầm sau cp
- Nếu conflict: `git fetch origin && git reset --hard origin/main` rồi copy lại

---

## ⚠️ Yêu cầu bắt buộc với AI

**Sau mỗi lần sửa hoặc tạo file xong**, AI phải tự động làm các bước sau mà KHÔNG cần Ruby nhắc:

### 1. Viết changelog entry
Theo đúng format của CHANGELOG.md:
```
## [vX.Y.Z] — YYYY-MM-DD

### ✨ Tính năng mới
- `cogs/file.py` — Mô tả ngắn gọn bằng tiếng Việt

### 🐛 Sửa lỗi
- `cogs/file.py` — Mô tả ngắn gọn bằng tiếng Việt

### ♻️ Thay đổi
- `cogs/file.py` — Mô tả ngắn gọn bằng tiếng Việt
```
Bỏ section nào không có nội dung.

### 2. Đề xuất version bump
- **patch** (x.x.+1) — chỉ sửa bug, không thêm tính năng
- **minor** (x.+1.0) — thêm tính năng mới, không breaking change
- **major** (+1.0.0) — thay đổi lớn, breaking change

### 3. Xuất lệnh Termux hoàn chỉnh
Bao gồm: cp file, cập nhật version trong bot.py, git add/commit/push CHANGELOG.md.

Ví dụ output cuối mỗi task:
```
📋 Changelog entry (thêm vào đầu CHANGELOG.md):
## [v4.6.0] — 2026-06-21
### 🐛 Sửa lỗi
- `cogs/seller.py` — Fix send_log thiếu guild_id trong check_expiry_loop
- `cogs/logger.py` — Thêm param guild_id vào send_log()

---

⚡ Lệnh Termux:
cd ~/bot
cp /sdcard/Download/seller.py cogs/seller.py
cp /sdcard/Download/logger.py cogs/logger.py
sed -i 's/BOT_VERSION = "4.5.0"/BOT_VERSION = "4.6.0"/' bot.py
sed -i 's/BOT_UPDATED = "[^"]*"/BOT_UPDATED = "2026-06-21"/' bot.py
# Thêm changelog entry vào đầu CHANGELOG.md (sau dòng # CHANGELOG...)
git add cogs/seller.py cogs/logger.py bot.py CHANGELOG.md
git commit -m "fix: seller send_log guild_id — v4.6.0"
git push origin main
```
