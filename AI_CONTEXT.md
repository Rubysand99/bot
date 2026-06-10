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
