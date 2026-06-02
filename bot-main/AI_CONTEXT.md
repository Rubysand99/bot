# AI Context — Bot Deploy Info

## GitHub
- Repo: https://github.com/Rubysand99/bot.git
- Branch: main
- Đã cài git credential, không cần nhập token lại

## Termux workflow
Khi AI sửa xong và xuất file zip, chạy lệnh sau:

```bash
cd ~
unzip /sdcard/Download/bot-main-fixed.zip -d bot-main-fixed
cp -r bot-main-fixed/* ~/bot/
cd ~/bot
git add .
git commit -m "fix: mô tả sửa lỗi"
git push origin main
rm -rf ~/bot-main-fixed
```

## Lưu ý
- File zip AI xuất tên: bot-main-fixed.zip
- Sau khi copy xong nên xoá thư mục bot-main-fixed để tránh rác
- Kiểm tra không có file tên "-H" hoặc "-d" bị tạo nhầm sau cp
