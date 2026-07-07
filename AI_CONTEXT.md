# AI Context — TuyTam Bot (Rudeus Bot)

## Thông tin repo
- Repo: https://github.com/Rubysand99/bot.git
- Branch: main
- Deploy: Railway (auto-deploy khi push GitHub)
- Runtime: Python 3.11, discord.py 2.x, motor (async MongoDB)
- Bot hiện tại chạy **multi-guild** (2 server: TUYTAM COMMUNITY + OGGY COMMUNITY), version hiện tại: xem `BOT_VERSION` trong `bot.py`

### DB (MongoDB Atlas `tuytam_bot`)
- Collection `bot_data`:
  - `_id: "guild_<guild_id>"` — 1 document/guild (config riêng: kênh log, category, role, ticket counter, seller_subs, panel buttons, v.v.)
  - `_id: "main"` — 1 document GLOBAL, dùng cho data KHÔNG thuộc guild nào cụ thể: `_tempbans`, `_ip_records`, `_member_inviters`, `_pending_joins`, `_shared_ip` (chống multi-acc né qua server khác — xem phần Multi-guild bên dưới)
- Collection `giveaways` — tách riêng theo `message_id`, không thuộc guild nào trong cache

---

## Cấu trúc thư mục
```
~/bot/
├── bot.py              # Entry: load cogs, on_ready, on_message, legit/vouch handler, backfill
├── verify_server.py    # FastAPI verify server (chạy cùng bot, port từ env PORT) — KHÔNG đụng core/data.py
├── CHANGELOG.md
├── AI_CONTEXT.md       # File này — upload đầu mỗi chat
├── cogs/
│   ├── admin.py        # .st (settings UI), .help, .mkchannel, slash admin
│   ├── admin_views.py  # Tất cả Views/Modals cho admin (2000+ dòng) — KHÔNG phải Cog, không có on_ready/cog_load
│   ├── ai_chat.py      # Groq AI chat, chỉ admin dùng được
│   ├── giveaway.py     # /giveaway, .gwstatus, .gwpick, .gwreset
│   ├── invite.py       # Invite tracking 5 trạng thái + IP fake detection
│   ├── logger.py       # send_log() đa kênh 9 nhóm, daily 8h report
│   ├── mod.py          # Ban/Kick/Mute/Unmute/Warn + tempban MongoDB (global, không theo guild)
│   ├── seller.py       # Seller subscription: add/remove/list/panel, auto check hết hạn (mỗi giờ, lặp từng guild)
│   ├── shop_orders.py  # 🧪 QR VietQR + hàng đợi đơn hàng (thử nghiệm, toggle qua .st) — PHẢI có trong COGS ở bot.py mới hoạt động
│   └── ticket.py       # Panel (nút bật/tắt theo guild), buttons, modal, close/done logic
└── core/
    └── data.py         # MongoDB helpers, _data_cache (theo guild) + _global_cache, cfg getters/setters, guild-context contextvar
```

---

## ⚠️ KIẾN TRÚC MULTI-GUILD — bắt buộc đọc trước khi sửa bất kỳ file nào đụng tới data

Bot chạy nhiều guild cùng lúc, mỗi guild có 1 document Mongo riêng (`guild_<id>`). Để `load_data()`/`save_data()`
biết đang thao tác guild nào, `core/data.py` dùng 1 **`contextvars.ContextVar`** (`_current_guild_id`) —
**KHÔNG phải biến global thường**, vì mỗi asyncio Task có context riêng.

### Quy tắc bắt buộc
1. **`load_data()` / `save_data(data)`** — dữ liệu RIÊNG theo guild (config, ticket counter, seller_subs, panel buttons...).
   Chỉ hoạt động đúng nếu guild context đã được set trong TASK HIỆN TẠI.
2. **`load_global_data()` / `save_global_data(data)`** — dữ liệu CHUNG cho mọi guild, dùng khi entry tự chứa `guild_id`
   bên trong (vd `_tempbans`, `_ip_records`, `_member_inviters`, `_pending_joins`, `_shared_ip`). KHÔNG cần guild context.
3. Guild context được TỰ ĐỘNG set sẵn ở các nơi sau — code trong các hàm được gọi TỪ đây không cần tự set:
   - `bot.py`: `before_invoke` (lệnh `.command`), `GuildContextTree.interaction_check` (slash command), `on_message`
   - `core/data.py`: `GuildContextView` (thay `discord.ui.View`), `GuildContextModal` (thay `discord.ui.Modal`) —
     dùng `from core.data import GuildContextView as View, GuildContextModal as Modal` cho MỌI View/Modal có nút bấm
     cần đọc/ghi data theo guild.
4. **Bất kỳ nơi nào khác** gọi `load_data()`/`save_data()`/`send_log()` — đặc biệt: `on_ready`, `on_guild_join`,
   `on_member_join/remove/update`, `tasks.loop` nền, callback từ HTTP (verify_server), hoặc bất kỳ
   `asyncio.create_task()` nào — đều chạy trên **1 Task RIÊNG BIỆT**, không thừa hưởng context từ nơi khác.
   → **PHẢI tự gọi `set_current_guild(guild_id)`** trước khi đọc/ghi data trong các trường hợp này
   (xem ví dụ `seller.py: check_expiry_loop`, `logger.py: daily_report_task`).
5. **`send_log(bot, "EVENT_TYPE", "title", fields=[...], guild_id=guild.id)`** — **LUÔN LUÔN truyền `guild_id`**
   dù đang ở trong lệnh/nút bấm đã có context sẵn hay không. `send_log()` tự gọi `set_current_guild(guild_id)`
   ngay đầu hàm trước khi tra kênh log — thiếu `guild_id` là lỗi phổ biến nhất trong repo này, đã từng gây
   hàng loạt lỗi `[DATA] load_data() KHÔNG có guild context` / `Guild X chưa có trong cache`.
6. Khi thêm 1 Cog MỚI có `on_ready`/`tasks.loop`/`cog_load` lặp qua `bot.guilds` — **luôn** gọi
   `set_current_guild(guild.id)` đầu mỗi vòng lặp, TRƯỚC bất kỳ lệnh gọi `load_data()`/`send_log()` nào.

### Các vị trí ĐÃ TỪNG bị lỗi này (đã fix ở v4.10.3 — tham khảo khi thêm code mới tương tự)
- `cogs/invite.py: on_member_join` — thiếu `set_current_guild(member.guild.id)` đầu hàm → `_add_invite()` không lưu được khi có người join
- `cogs/invite.py: _handle_verify_result` — callback được `verify_server.py` trigger qua HTTP (Task hoàn toàn tách biệt, không thừa hưởng context từ đâu cả) → phải tự `set_current_guild()` đầu hàm
- `cogs/invite.py: on_member_remove` — cùng lỗi, ảnh hưởng -1 verify/+1 left khi user rời server
- `cogs/ticket.py: on_message` (webhook relay "Ruby bot") — đọc `load_data()` không có context → toggle `.st` không có tác dụng thật

Log của `load_data()`/`save_data()` giờ chỉ in 1 dòng cảnh báo ngắn (KHÔNG còn dump full stack trace
`traceback.format_stack()` như trước — đoạn debug tạm đó đã được gỡ ở v4.10.3 sau khi xác định xong
các nguồn gốc phổ biến nhất, tránh flood log hàng trăm dòng mỗi lần listener chạy). Nếu gặp lỗi này ở
vị trí MỚI (không nằm trong danh sách trên), cách debug nhanh nhất: thêm tạm 1 dòng
`print(guild_id, flush=True)` + kiểm tra hàm gọi có phải listener/task chạy Task riêng không
(xem quy tắc #3 và #4 ở trên).

---

## Conventions quan trọng
- **Admin gate:** `if ctx.author.id not in ADMIN_IDS: return` — import từ `core.data`
- **Staff check:** `is_staff_member()` — ADMIN_IDS + support role + seller role
- **Log:** `await send_log(bot, "EVENT_TYPE", "title", fields=[...], guild_id=guild.id)` — xem mục Multi-guild ở trên, **guild_id bắt buộc**
- **Channel fetch:** dùng `get_or_fetch_channel(bot, id)` — KHÔNG dùng `bot.get_channel()`
- **Data load/save (theo guild):** `load_data()` / `save_data(data)` qua `core/data.py`
- **Data load/save (chung mọi guild):** `load_global_data()` / `save_global_data(data)` qua `core/data.py`
- **View/Modal có nút bấm đọc/ghi data:** dùng `GuildContextView`/`GuildContextModal` (alias `View`/`Modal`) thay vì `discord.ui.View`/`discord.ui.Modal` trực tiếp
- **ADMIN_IDS:** đọc từ env `ADMIN_IDS` (comma-separated), không hardcode
- Response PUBLIC (không ephemeral), trừ ticket panel button

## Log event types → nhóm kênh
```
ticket   → TICKET_CREATE, TICKET_CLOSE, TICKET_DONE, TICKET_CLAIM
mod      → MOD_BAN, MOD_KICK, MOD_MUTE, MOD_WARN
giveaway → GIVEAWAY_START, GIVEAWAY_END, GIVEAWAY_REROLL
member   → MEMBER_JOIN, MEMBER_LEAVE
role     → ROLE_ADD, ROLE_REMOVE
ai       → AI_USED
admin    → CMD_USED, SLASH_USED, SETTINGS
invite   → INVITE_JOIN, INVITE_VERIFY, INVITE_FAKE, INVITE_LEFT
general  → INFO, ERROR, RATING (fallback)
```

---

## Termux workflow
File AI sửa xong → tải về `/sdcard/Download/` → chạy:

```bash
cd ~/bot
cp /sdcard/Download/<tên_file> <đường_dẫn>
git add <file1> <file2> ...
git commit -m "fix/feat: mô tả"
git push origin main
```

**Lưu ý:**
- Git credential đã lưu sẵn, không cần nhập token
- Nếu conflict: `git fetch origin && git reset --hard origin/main` rồi copy lại
- Kiểm tra không có file tên `-H` hoặc `-d` bị tạo nhầm sau `cp`

---

## ⚠️ Yêu cầu bắt buộc với AI

**Sau mỗi lần sửa hoặc tạo file xong**, AI phải tự động làm các bước sau **KHÔNG cần Ruby nhắc**:

### 1. Viết changelog entry theo format chuẩn
```
## [vX.Y.Z] — YYYY-MM-DD

### ✨ Tính năng mới
- `cogs/file.py` — Mô tả ngắn gọn tiếng Việt

### 🐛 Sửa lỗi
- `cogs/file.py` — Mô tả ngắn gọn tiếng Việt

### ♻️ Thay đổi
- `cogs/file.py` — Mô tả ngắn gọn tiếng Việt

---
```
Bỏ section nào không có nội dung.

### 2. Đề xuất version bump
- **patch** `x.x.+1` — chỉ sửa bug
- **minor** `x.+1.0` — thêm tính năng mới
- **major** `+1.0.0` — thay đổi lớn / breaking change

### 3. Xuất lệnh Termux hoàn chỉnh
Bao gồm: cp file, sed cập nhật version trong bot.py, git add/commit/push kèm CHANGELOG.md.

**Ví dụ output cuối mỗi task:**
```
📋 Changelog (thêm vào đầu CHANGELOG.md):
─────────────────────────────────────
## [v4.6.0] — 2026-06-21

### 🐛 Sửa lỗi
- `cogs/seller.py` — Fix send_log thiếu guild_id trong check_expiry_loop
- `cogs/logger.py` — Thêm param guild_id vào hàm send_log()

---
─────────────────────────────────────

⚡ Lệnh Termux:
cd ~/bot
cp /sdcard/Download/seller.py cogs/seller.py
cp /sdcard/Download/logger.py cogs/logger.py
sed -i 's/BOT_VERSION = "4.5.0"/BOT_VERSION = "4.6.0"/' bot.py
sed -i 's/BOT_UPDATED = "[^"]*"/BOT_UPDATED = "2026-06-21"/' bot.py
git add cogs/seller.py cogs/logger.py bot.py CHANGELOG.md
git commit -m "fix: seller send_log guild_id — v4.6.0"
git push origin main
```
