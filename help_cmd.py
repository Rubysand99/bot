# cogs/help_cmd.py — .help command
from config import *

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    if latency < 100:
        color, status = 0x57F287, "Tốt 🟢"
    elif latency < 200:
        color, status = 0xFEE75C, "Bình thường 🟡"
    else:
        color, status = 0xED4245, "Chậm 🔴"
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Độ trễ: **{latency}ms** — {status}",
        color=color
    )
    await ctx.reply(embed=embed)

HELP_CATEGORIES = {
    "chung": {
        "title": "🌐  Lệnh Chung",
        "fields": [
            ("`.ping`",                       "Kiểm tra độ trễ bot"),
            ("`.qr`",                         "Gửi mã QR thanh toán"),
            ("`.botinfo` / `.bi`",            "Thông tin bot (version, ping, uptime)"),
            ("`.serverinfo` / `.si`",         "Thông tin server Discord"),
            ("`.userinfo [@user]` / `.ui`",   "Thông tin thành viên"),
            ("`.sv` / `.dichvu` / `.service`","Xem thông tin dịch vụ Setup Server Discord"),
        ]
    },
    "dichvu": {
        "title": "🛠️  Dịch Vụ Setup Server Discord",
        "fields": [
            ("`.sv` / `.dichvu` / `.service`", "Gửi embed giới thiệu dịch vụ Setup Server Discord"),
            ("📦 Phù hợp với",                 "Game, học tập, shop bán hàng, tiền ảo, trading, nhóm bạn bè…"),
            ("✅ Chất lượng",                  "Thiết kế đúng nhu cầu, dùng bot mạnh (Dyno, MEE6, Carl-bot…)\nGiao diện thẩm mỹ, tối ưu quyền & vai trò"),
            ("💰 Giá",                         "Thoả thuận thoải mái — deal đến khi hai bên hài lòng"),
            ("🔧 Quy trình",                   "1️⃣ Bạn mô tả nhu cầu → 2️⃣ Tư vấn & báo giá → 3️⃣ Setup & bàn giao"),
            ("📩 Liên hệ",                     "Mở ticket hoặc nhắn trực tiếp để được tư vấn miễn phí!"),
        ]
    },
    "ticket": {
        "title": "🎫  Lệnh Ticket",
        "fields": [
            ("`.panel`",                      "Gửi panel tạo ticket *(admin)*"),
            ("`.setpanel #kênh`",             "Chỉ định kênh đặt panel ticket *(admin)*"),
            ("`.done`",                       "Hoàn thành đơn — +1 đơn & give role buyer *(admin/staff)*"),
            ("`.close`",                      "Đóng ticket — gửi transcript + mở form đánh giá *(admin/staff)*"),
            ("`.addnote <nội dung>`",         "Thêm ghi chú nội bộ vào ticket *(admin/staff)*"),
            ("`.ratings`",                    "Xem thống kê đánh giá từ khách *(admin)*"),
            ("`.orderbase`",                  "Gửi thông tin Order Base *(admin)*"),
            ("`.addseller <ID> <tên>`",       "Thêm seller vào danh sách chọn trong ticket *(admin)*"),
            ("`.removeseller <ID hoặc tên>`\n`.delseller` `.xoaseller`", "Xoá seller khỏi danh sách *(admin)*"),
            ("`.listseller`\n`.sellers`",     "Xem danh sách seller hiện tại *(admin)*"),
        ]
    },
    "mod": {
        "title": "🛡️  Lệnh Kiểm Duyệt",
        "fields": [
            ("`.clear <số>` / `.purge`",              "Xoá tin nhắn trong kênh (1–100) *(admin/staff)*"),
            ("`.addrole @user @role`",                "Thêm role cho thành viên *(admin)*"),
            ("`.removerole @user @role`",             "Xoá role của thành viên *(admin)*"),
            ("`.mkchannel <text/voice/category> <tên>`\n`.mkch` `.taokenh`",
                                                      "Tạo kênh mới đồng bộ font server *(admin)*"),
            ("`.createchannel <tên> [text/voice]` / `.cc`", "Tạo kênh cơ bản (không có font) *(admin)*"),
            ("`.deletechannel [#kênh]` / `.dc`",      "Xoá kênh (mặc định: kênh hiện tại) *(admin)*"),
            ("`.rename #kênh <tên mới>`",             "Đổi tên kênh, giữ icon & số đếm *(admin)*"),
            ("`.setperm #kênh @role xem=true ...`",   "Sửa quyền kênh nhanh *(admin)*"),
            ("`.emoji` / `.emoji <emoji>`",           "Thêm emoji từ ảnh/GIF hoặc server khác *(admin)*"),
            ("`.delemoji <emoji hoặc tên>`\n`.deleteemoji` `.xoaemoji`",
                                                      "Xoá emoji khỏi server (paste emoji hoặc gõ tên) *(admin)*"),
        ]
    },
    "giveaway": {
        "title": "🎉  Lệnh Giveaway",
        "fields": [
            ("`.gstart <time> <số người> <phần thưởng>`",  "Tạo giveaway — VD: `.gstart 1h 2 100m` *(admin)*"),
            ("`.gend <message_id>`",                        "Kết thúc giveaway sớm *(admin)*"),
            ("`.greroll <message_id>`",                     "Quay lại người thắng *(admin)*"),

            ("`.gwlist <message_id>`",                      "Xem danh sách người tham gia giveaway *(admin)*"),
            ("`/giveaway`",                                 "Tạo giveaway qua slash command *(admin)*"),
            ("`/gend`",                                     "Kết thúc giveaway qua slash command *(admin)*"),
            ("⚠️ Lưu ý",                                   "Nút **Tham gia** tự ẩn sau khi giveaway kết thúc. Giveaway được khôi phục tự động sau khi bot restart."),
        ]
    },
    "balance": {
        "title": "💰  Hệ Thống Số Dư",
        "fields": [
            ("`+ <số tiền>`",         "Nạp tiền vào (tự trừ phí 5%) — nhập trong kênh balance"),
            ("`- <số tiền>`",         "Chi tiền ra (số dư có thể âm) — nhập trong kênh balance"),
            ("`.balance` / `.bal`",   "Xem số dư & lịch sử giao dịch"),
            ("`.balset <số>`",        "Đặt số dư về giá trị bất kỳ *(admin)*"),
            ("`.balreset`",           "Reset toàn bộ số dư về 0 *(admin)*"),
        ]
    },
    "ai": {
        "title": "🤖  Lệnh AI (Groq — Miễn Phí)",
        "fields": [
            ("`.ai <câu hỏi>`",                   "Chat với AI, nhớ lịch sử 10 tin nhắn gần nhất"),
            ("`.ai tomtat [n]`",                  "Tóm tắt `n` tin nhắn gần nhất trong kênh (mặc định 30, tối đa 100)"),
            ("`.ai dich <ngôn ngữ> <văn bản>`",   "Dịch văn bản sang ngôn ngữ bất kỳ"),
            ("`.ai phantich [@user]`",             "Phân tích phong cách chat của user (mặc định: bạn)"),
            ("`.ai reset`",                        "Xoá lịch sử hội thoại AI của bạn"),
            ("`.mychat`",                          "Xoá lịch sử chat AI của bản thân"),
            ("`.aireset`",                         "Xoá lịch sử AI của tất cả user *(admin)*"),
            ("⚙️ Kênh AI tự động",                "Cài kênh AI riêng qua `.settings` → 🤖 AI Channel\nBot sẽ trả lời MỌI tin nhắn trong kênh đó"),
            ("⚠️ Lưu ý",                           "Cần cài `GROQ_API_KEY` trong Railway. Giới hạn free: 6000 req/ngày."),
        ]
    },
    "invite": {
        "title": "📨  Hệ Thống Invite",
        "fields": [
            ("`.invite [@user]`",           "Xem số lần invite của bản thân hoặc user khác"),
            ("`.invitetop [n]`",            "Bảng xếp hạng invite top N (mặc định 10) *(admin)*"),
            ("`.resetinvite @user`",        "Reset invite của 1 người *(admin)*"),
            ("`.resetinvite all`",          "Reset invite toàn bộ server *(admin)*"),
            ("⚙️ Net invite",               "Net = Tổng − Fake − Đã rời (luôn ≥ 0)"),
            ("⚠️ Fake invite",              "Member join rồi leave trong **10 phút** → không được tính"),
            ("🔒 Lưu ý",                   "Dữ liệu invite hoàn toàn độc lập với giveaway/buyer/ticket/balance\nBot cần quyền **Manage Server** để đọc invites"),
        ]
    },
    "caidat": {
        "title": "⚙️  Lệnh Cài Đặt",
        "fields": [
            ("`.settings` / `.st`",   "Xem & cấu hình toàn bộ bot (kênh, QR, AI, font…) *(admin)*"),
            ("`.setup`",              "Mở menu Setup Server — đổi font, rename hàng loạt *(admin)*"),
            ("`.setpanel #kênh`",     "Chỉ định kênh panel ticket *(admin)*"),
            ("`.sv` / `.dichvu`",     "Xem bảng giá sản phẩm"),
            ("`.giaset`\n`.setgia` `.pricemanager`", "Quản lý bảng giá — sửa/thêm/xoá/reset mục giá *(admin)*"),
            ("⚙️ Font server",        "Font được lưu tự động sau khi rename hàng loạt.\n`.mkchannel` dùng font này để tạo kênh mới."),
        ]
    },
    "kenh": {
        "title": "📌  Kênh & Cấu Hình Quan Trọng",
        "fields": [
            ("Transcript Channel",  "Cài qua `.settings` → embed ticket đóng + file HTML"),
            ("Feedback Channel",    "Cài qua `.settings` → embed đánh giá ⭐ của buyer"),
            ("AI Channel",         "Cài qua `.settings` → 🤖 AI Channel — bot tự trả lời mọi tin"),
            ("Balance Channel",    "Cài qua `.settings` → 💰 gõ `+` / `-` để nạp/chi"),
            ("Proof Channel",      "Cài qua `.settings` → gõ `done` để +1 số đơn"),
            ("Legit Channel",      "Cài qua `.settings` → gõ `+1legit` để +1 số legit"),
            ("Counter Channel",    "Cài qua `.settings` → tự động đếm số ticket"),
        ]
    },
}

# Slash command equivalents (hiển thị trong help chung)
_SLASH_SUMMARY = (
    "`/ping` `/qr` `/botinfo` `/serverinfo` `/userinfo`\n"
    "`/clear` `/addrole` `/removerole` `/createchannel` `/deletechannel`\n"
    "`/giveaway` `/gend`"
)

@bot.command(name="help")
async def help_cmd(ctx, category: str = None):
    if category is None:
        embed = discord.Embed(
            title="📋  Trợ Lý TuyTam Store — Danh Sách Lệnh",
            description=(
                "Dùng **`.help <mục>`** để xem chi tiết từng nhóm lệnh.\n"
                "Slash commands `/` cũng khả dụng cho hầu hết lệnh!"
            ),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        cats = [
            ("🌐 `.help chung`",    "`.ping` `.qr` `.botinfo` `.serverinfo` `.userinfo`"),
            ("🛠️ `.help dichvu`",   "`.sv` — Giới thiệu dịch vụ Setup Server Discord"),
            ("🎫 `.help ticket`",   "`.panel` `.done` `.close` `.addnote` `.addseller` `.listseller`"),
            ("🛡️ `.help mod`",      "`.clear` `.addrole` `.removerole` `.mkchannel` `.emoji` `.delemoji`"),
            ("🎉 `.help giveaway`", "`.gstart` `.gend` `.greroll` `.gwlist`  +  `/giveaway` `/gend`"),
            ("💰 `.help balance`",  "`.balance` `.balset` `.balreset`  +  nạp/chi trong kênh balance"),
            ("🤖 `.help ai`",       "`.ai` `.ai tomtat` `.ai dich` `.ai phantich` `.mychat` `.aireset`"),
            ("📨 `.help invite`",   "`.invite` `.invitetop` `.resetinvite`"),
            ("⚙️ `.help caidat`",   "`.settings` `.setup` `.setpanel` `.sv` `.giaset`"),
            ("📌 `.help kenh`",     "Transcript, Feedback, AI, Balance, Proof, Legit, Counter channel"),
        ]
        for name, desc in cats:
            embed.add_field(name=name, value=desc, inline=False)
        embed.add_field(
            name="⚡ Slash Commands",
            value=_SLASH_SUMMARY,
            inline=False
        )
        embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  Prefix: .  |  Slash: /  |  *(admin)* = chỉ admin dùng được")
        return await ctx.reply(embed=embed)

    cat = category.lower()

    if cat not in HELP_CATEGORIES:
        keys = " / ".join(f"`{k}`" for k in HELP_CATEGORIES)
        return await ctx.reply(f"❌ Mục không tồn tại! Chọn: {keys}")

    data = HELP_CATEGORIES[cat]
    is_admin = ctx.author.id in ADMIN_IDS
    embed = discord.Embed(
        title=data["title"],
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    for field in data["fields"]:
        # field có thể là tuple 2 phần tử hoặc 3 phần tử (cmd, desc, "admin_only")
        if len(field) == 3 and field[2] == "admin_only" and not is_admin:
            continue
        cmd_str, desc = field[0], field[1]
        embed.add_field(name=cmd_str, value=desc, inline=False)
    embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  Dùng .help để xem tất cả mục  |  *(admin)* = chỉ admin")
    await ctx.reply(embed=embed)

# ================= MODERATION =================
