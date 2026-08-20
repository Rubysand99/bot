# AI Context — TuyTam Bot (Rudeus Bot)

## Thông tin repo
- Repo: https://github.com/Rubysand99/bot.git
- Branch: main
- Deploy: Railway (auto-deploy khi push GitHub)
- Runtime: Python 3.11, discord.py 2.x, motor (async MongoDB)
- Bot hỗ trợ **multi-guild** — nhưng từ v4.24.0, một guild chỉ hoạt động được sau khi
  admin (Ruby/TuyTam) **ủy quyền tường minh** qua lệnh `.as` (xem mục AUTH_GATE bên
  dưới). Mời bot vào server KHÔNG tự động làm server đó hoạt động được.
- Version hiện tại: xem `BOT_VERSION` trong `bot.py`

### DB (MongoDB Atlas `tuytam_bot`)
- Collection `bot_data`:
  - `_id: "guild_<guild_id>"` — 1 document/guild (config riêng: kênh log, category, role, ticket counter, seller_subs, panel buttons, toàn bộ `cfg_*`, v.v.)
  - `_id: "main"` — 1 document GLOBAL, dùng cho data KHÔNG thuộc guild nào cụ thể: `_tempbans`, `_ip_records`, `_member_inviters`, `_pending_joins`, `_shared_ip`, `_authorized_guilds` (danh sách guild đã ủy quyền qua `.as`)
- Collection `giveaways` — tách riêng theo `message_id`, không thuộc guild nào trong cache
- Collection `knowledge` (RAG) — Q&A đã lưu cho AI, lọc theo `guild_id` khi search (`core/rag.py`)
- Collection tin nhắn đã index cho AI search (`core/message_search.py`) — cũng lọc theo `guild_id`

---

## Cấu trúc thư mục
```
~/bot/
├── bot.py              # Entry: load cogs, AUTH_GATE (bot.check + interaction_check),
│                        # prefix per-guild (get_guild_prefix), on_ready (guard first_boot,
│                        # xem mục "on_ready KHÔNG chỉ chạy 1 lần" bên dưới), on_message
├── verify_server.py    # FastAPI verify server (chạy cùng bot, port từ env PORT) — KHÔNG đụng core/data.py
├── CHANGELOG.md
├── AI_CONTEXT.md        # File này — upload đầu mỗi chat, LUÔN đọc trước khi sửa bất kỳ file tính năng nào
├── cogs/
│   ├── admin.py         # .st (settings UI — DUY NHẤT nơi cấu hình role/kênh/category, xem mục
│   │                     # "KHÔNG hardcode ID" bên dưới), .as (ủy quyền server), .help, .mkchannel
│   ├── admin_views.py   # Tất cả Views/Modals cho admin (2500+ dòng) — KHÔNG phải Cog, không có
│   │                     # on_ready/cog_load. MỌI View/Modal admin-only PHẢI tự check ADMIN_IDS
│   │                     # (xem mục "interaction_check phải gọi super()" — lỗ hổng bảo mật đã gặp)
│   ├── ai_chat.py        # Groq AI chat — kênh public chỉ được agent "support" (tool đọc), agent
│   │                     # "ops" (tool nguy hiểm: ban/kick/xoá kênh...) CHỈ qua lệnh `.ai` (admin only)
│   ├── giveaway.py       # /giveaway, .gwstatus, .gwpick, .gwreset, .gwverify (bật/tắt yêu cầu verify)
│   ├── invite.py         # Invite tracking 5 trạng thái + IP fake detection (CỐ Ý dùng chung mọi
│   │                     # guild — xem load_global_data() — không phải bug)
│   ├── listings.py       # Listing sản phẩm — nút "Mua" public, nút quản lý check can_manage_listing
│   ├── logger.py         # send_log() đa kênh 9 nhóm (+ TICKET_UNDONE), daily 8h report (guard 2
│   │                     # lớp chống gửi trùng khi bot restart đúng giờ)
│   ├── message_search.py # Index tin nhắn cho AI search theo cfg_ai_search_channels (per-guild)
│   ├── mod.py            # Ban/Kick/Mute/Unmute/Warn + tempban MongoDB (global, không theo guild,
│   │                     # cố ý — chống né ban qua guild khác). Spam-cache/warn-cooldown key theo
│   │                     # (guild_id, user_id) — KHÔNG chỉ user_id (xem mục cache đa-guild)
│   ├── seller.py         # Seller subscription: add/remove/list/panel, auto check hết hạn (mỗi giờ,
│   │                     # lặp từng guild, có before_loop chờ wait_data_cache_ready())
│   ├── shop_orders.py    # 🧪 QR VietQR + hàng đợi đơn hàng (thử nghiệm, toggle qua .st) — PHẢI có
│   │                     # trong COGS ở bot.py mới hoạt động
│   └── ticket.py         # Panel (nút bật/tắt theo guild), buttons, modal, .done/.undone (trừ tiền
│                          # khi lỡ .done nhầm), close logic. `_open_tickets` cache key theo
│                          # (guild_id, user_id)
└── core/
    ├── data.py           # MongoDB helpers, _data_cache (theo guild) + _global_cache, cfg
    │                      # getters/setters (KHÔNG hardcode ID — xem mục riêng bên dưới),
    │                      # guild-context contextvar, GuildContextView/Modal (set context +
    │                      # AUTH_GATE check), AUTH_GATE helpers (is_guild_authorized, .as backend)
    ├── ai_agents.py       # System prompt + route_agent() phân loại support/ops/report
    ├── ai_tools.py        # QUERY_TOOL_SCHEMAS (đọc, an toàn) + ADMIN_TOOL_SCHEMAS (nguy hiểm,
    │                      # qua _invoke_cmd() — dùng get_guild_prefix() để build lệnh giả lập,
    │                      # KHÔNG hardcode ".")
    ├── rag.py             # Q&A embedding + search, lọc theo guild_id
    └── message_search.py  # Lưu/search tin nhắn đã index, lọc theo guild_id
```

---

## 🔒 AUTH_GATE — Hệ thống ủy quyền server (thêm từ v4.24.0)

Mời bot vào 1 server **KHÔNG** làm server đó hoạt động được. Admin (Ruby/TuyTam) phải
tự ủy quyền bằng `.as <guild_id>` (dùng được cả qua DM bot, không cần đang ở server đó).

- `.as <guild_id>` (không truyền id → áp dụng server đang gõ) — **toggle**: chưa ủy quyền
  → bật; đã ủy quyền → thu hồi ngay lập tức. Việc ghi Mongo được `await` trực tiếp
  (KHÔNG dùng task nền) để tránh mất trạng thái nếu Discord reconnect ngay sau đó.
- `.serverlist` — xem tất cả server bot đang ở + trạng thái ✅/🔒.
- Server CHƯA ủy quyền: **mọi** lệnh `.command`/slash command bị chặn (trừ chính `.as`),
  mọi tính năng tự động (auto-sold, AI channel, legit/vouch, ticket, mod...) đều bị bỏ qua.
- Cơ chế chặn nằm ở **3 lớp** — khi thêm tính năng mới đọc/ghi data theo guild, phải chắc
  chắn nó đi qua ít nhất 1 trong 3 lớp này:
  1. `bot.py: _global_guild_authorization_check` (global `bot.check`) — chặn prefix command.
  2. `bot.py: GuildContextTree.interaction_check` — chặn slash command.
  3. `core/data.py: GuildContextView.interaction_check` / `GuildContextModal.interaction_check`
     — chặn nút bấm/select/modal. **Đây là lớp hay bị quên nhất** — 1 số View tự
     override `interaction_check()` và gọi `set_current_guild()` trực tiếp thay vì gọi
     `super().interaction_check()` trước, vô tình che mất luôn AUTH_GATE (bug thật đã
     gặp ở `SetupMainView`/`MkChannelView`/`_PageView`, xem CHANGELOG v4.25.3).
     **Quy tắc**: mọi override `interaction_check()` PHẢI gọi
     `if not await super().interaction_check(interaction): return False` TRƯỚC KHI thêm
     điều kiện riêng (vd admin-only), không được tự set context/return True mà bỏ qua super().
- Listener chạy Task riêng (không qua `bot.py: on_message`) — `on_member_join/remove`
  (invite.py), automod `on_message` (mod.py), ticket relay `on_message` (ticket.py), AI
  forum-reply/search-index `on_message` (ai_chat.py, message_search.py) — đều PHẢI tự
  check `is_guild_authorized(guild_id)` ở đầu hàm, KHÔNG tự động thừa hưởng AUTH_GATE từ
  đâu cả.

---

## 🚫 KHÔNG hardcode ID role/kênh/category trong code (thêm từ v4.31.0)

**Quy tắc:** mọi role/kênh/category riêng của 1 guild PHẢI là 1 giá trị `cfg_*` đọc qua
`get_cfg_*()`/ghi qua `set_cfg_*()` (hoặc `save_cfg(key, value)` cho giá trị đơn giản),
KHÔNG BAO GIỜ hardcode ID trực tiếp trong code làm "mặc định" cho mọi guild — kể cả khi
comment ghi "chỉ đúng cho TuyTam". Cách cũ này đã gây ra 5+ bug thật (`DONE_ROLE_ID`,
`TRANSCRIPT_CHANNEL_ID`, `MEMBER_ROLE_IDS`, `WELCOME_GUILDS`, `BUILDER_BASE_ROLE_ID`) —
tính năng liên quan **im lặng không chạy** ở bất kỳ guild nào khác TuyTam, không lỗi
không log.

- Guild MỚI (kể cả TuyTam nếu tạo document từ đầu) mặc định "chưa cài" (0 / `[]`).
- **TuyTam Community cụ thể** được backfill giá trị lịch sử tự động, ĐÚNG 1 LẦN, qua
  `_TUYTAM_LEGACY_CFG_MIGRATION` (dict ở đầu `core/data.py`) + logic trong
  `_mongo_load()` — chỉ áp dụng cho `LEGACY_MAIN_GUILD_ID` (`1464407860640219189`),
  KHÔNG áp dụng cho guild nào khác. Field nào TuyTam đã có giá trị thật (kể cả tự đổi
  qua `.st`) sẽ KHÔNG bị ghi đè.
- **Toàn bộ cấu hình role/kênh/category đi qua `.st`** (`cogs/admin.py: settings_cmd` +
  `cogs/admin_views.py: SettingsView`) — dùng `_send_role_select`/`_send_channel_select`/
  `_send_category_select`/`_send_multi_role_select` (helper có sẵn, tái dùng được) thay
  vì viết lệnh riêng cho từng mục. Nếu cần thêm 1 mục cấu hình role/kênh mới: thêm
  `cfg_*` field + getter/setter ở `core/data.py`, thêm 1 nút trong `SettingsView` gọi
  helper tương ứng — KHÔNG viết lệnh `.xyz` riêng.
- Prefix bot (`.`) CŨNG cấu hình được per-guild qua `.st` (`get_guild_prefix()`,
  `bot.py: _get_prefix`) — bất kỳ chỗ nào TỰ DỰNG message/lệnh giả lập (vd
  `core/ai_tools.py: _invoke_cmd`) PHẢI dùng `get_guild_prefix(guild.id)`, KHÔNG hardcode `.`.

---

## ⚠️ KIẾN TRÚC MULTI-GUILD — bắt buộc đọc trước khi sửa bất kỳ file nào đụng tới data

Bot chạy nhiều guild cùng lúc, mỗi guild có 1 document Mongo riêng (`guild_<id>`). Để `load_data()`/`save_data()`
biết đang thao tác guild nào, `core/data.py` dùng 1 **`contextvars.ContextVar`** (`_current_guild_id`) —
**KHÔNG phải biến global thường**, vì mỗi asyncio Task có context riêng.

### Quy tắc bắt buộc
1. **`load_data()` / `save_data(data)`** — dữ liệu RIÊNG theo guild (config, ticket counter, seller_subs, panel buttons...).
   Chỉ hoạt động đúng nếu guild context đã được set trong TASK HIỆN TẠI.
2. **`load_global_data()` / `save_global_data(data)`** — dữ liệu CHUNG cho mọi guild, dùng khi entry tự chứa `guild_id`
   bên trong (vd `_tempbans`, `_ip_records`, `_member_inviters`, `_pending_joins`, `_shared_ip`, `_authorized_guilds`). KHÔNG cần guild context.
3. Guild context được TỰ ĐỘNG set sẵn ở các nơi sau — code trong các hàm được gọi TỪ đây không cần tự set:
   - `bot.py`: `before_invoke` (lệnh `.command`), `GuildContextTree.interaction_check` (slash command), `on_message`
   - `core/data.py`: `GuildContextView` (thay `discord.ui.View`), `GuildContextModal` (thay `discord.ui.Modal`) —
     dùng `from core.data import GuildContextView as View, GuildContextModal as Modal` cho MỌI View/Modal có nút bấm
     cần đọc/ghi data theo guild. Set context XONG các class này còn check AUTH_GATE — xem mục AUTH_GATE ở trên.
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

### Cache trong RAM (KHÔNG phải Mongo) cũng phải phân biệt theo guild
Ngoài `load_data()`/`save_data()` (đã tự động cô lập theo guild qua contextvar), file nào tự
giữ 1 dict/cache trong RAM để tra cứu nhanh (không qua Mongo mỗi lần) — vd "user nào đang có
ticket mở", "user gửi mấy tin trong 5s gần đây" — PHẢI tự thêm `guild_id` vào KEY của cache
đó, KHÔNG chỉ key theo `user_id`. Nếu không, 1 user hoạt động ở NHIỀU guild cùng lúc (đúng
tinh thần multi-guild của bot) sẽ bị tính gộp giữa các guild — đã gặp thật ở 3 chỗ:
`_open_tickets` (ticket.py — user có ticket ở guild A, mở ticket ở guild B lại xoá nhầm
cache của guild A), `_spam_cache`/`_image_cache`/`_warn_cooldown` (mod.py — bị auto-mod
mute nhầm vì "spam" dù mỗi guild riêng lẻ đều dưới ngưỡng). Pattern chuẩn: dùng tuple
`(guild_id, user_id)` làm key thay vì chỉ `user_id`.

### `on_ready()` KHÔNG chỉ chạy 1 lần lúc khởi động
Discord gateway reconnect (rớt mạng, Railway restart container, session bị Discord
invalidate...) khiến `on_ready()` **refire** bất cứ lúc nào trong suốt vòng đời bot —
không chỉ 1 lần lúc khởi động thật. Bất kỳ logic nào trong `on_ready()` (hoặc hàm nó gọi)
mà KHÔNG an toàn chạy lại nhiều lần sẽ gây bug thật khi reconnect xảy ra — đã gặp:
- `init_data_cache()` reset sạch `_data_cache`/`_global_cache` mỗi lần refire → mất mọi
  thay đổi RAM chưa kịp ghi Mongo nền. **Fix:** chỉ full-load lần gọi đầu, refire sau chỉ
  nạp guild mới (xem `core/data.py: init_data_cache`).
- `resume_active_giveaways()`/`resume_pending_sold_views()` tạo THÊM task mới (không huỷ
  task cũ) mỗi lần refire → 2 task độc lập cho cùng 1 giveaway/đơn hàng → hết giờ, CẢ 2
  cùng chạy → giveaway công bố kết quả 2 lần / ping admin trùng lặp.
- Embed "Bot Khởi Động" gửi lại vào kênh changelog mỗi lần reconnect → spam.
**Fix chung** (xem `bot.py: on_ready`): gom mọi bước "chỉ an toàn chạy 1 lần" vào khối
`if first_boot:` (guard bằng cờ module-level `_on_ready_first_boot_done`).
Khi thêm code mới vào `on_ready()`, LUÔN tự hỏi: "nếu hàm này chạy lại y hệt 5 phút sau
(reconnect), có tạo ra gì trùng lặp/task chờ chồng chéo không?" — nếu có, đặt vào khối
`if first_boot:` hoặc tự viết guard chống chạy trùng riêng (xem `_resume_pending_renames`
— đã tự check `.done()` trước khi tạo task mới, làm ĐÚNG ngay từ đầu).

### Các vị trí ĐÃ TỪNG bị lỗi thiếu `set_current_guild()` (tham khảo khi thêm code mới tương tự)
- `cogs/invite.py: on_member_join` — thiếu `set_current_guild(member.guild.id)` đầu hàm → `_add_invite()` không lưu được khi có người join
- `cogs/invite.py: _handle_verify_result` — callback được `verify_server.py` trigger qua HTTP (Task hoàn toàn tách biệt, không thừa hưởng context từ đâu cả) → phải tự `set_current_guild()` đầu hàm
- `cogs/invite.py: on_member_remove` — cùng lỗi, ảnh hưởng -1 verify/+1 left khi user rời server
- `cogs/ticket.py: on_message` (webhook relay "Ruby bot") — đọc `load_data()` không có context → toggle `.st` không có tác dụng thật

Nếu gặp lỗi này ở vị trí MỚI (không nằm trong danh sách trên), cách debug nhanh nhất: thêm tạm 1 dòng
`print(guild_id, flush=True)` + kiểm tra hàm gọi có phải listener/task chạy Task riêng không
(xem quy tắc #3 và #4 ở trên).

---

## Conventions quan trọng
- **Admin gate:** `if ctx.author.id not in ADMIN_IDS: return` — import từ `core.data`
- **Staff check:** `is_staff_member()` — ADMIN_IDS + support role + seller role + builder role (tất cả đều `cfg_*`, không hardcode)
- **Log:** `await send_log(bot, "EVENT_TYPE", "title", fields=[...], guild_id=guild.id)` — xem mục Multi-guild ở trên, **guild_id bắt buộc**
- **Channel fetch:** dùng `get_or_fetch_channel(bot, id)` — KHÔNG dùng `bot.get_channel()`
- **Data load/save (theo guild):** `load_data()` / `save_data(data)` qua `core/data.py`
- **Data load/save (chung mọi guild):** `load_global_data()` / `save_global_data(data)` qua `core/data.py`
- **View/Modal có nút bấm đọc/ghi data:** dùng `GuildContextView`/`GuildContextModal` (alias `View`/`Modal`) thay vì `discord.ui.View`/`discord.ui.Modal` trực tiếp. Nếu View đó CHỈ dành cho admin, PHẢI tự override `interaction_check()` gọi `super()` trước rồi check `ADMIN_IDS` — xem mục AUTH_GATE.
- **View/Modal admin-only gửi qua `interaction.response.send_message`:** LUÔN kèm `ephemeral=True` nếu có `view=` — thiếu cái này từng khiến member thường click được nút admin trong panel `.setup` (lỗ hổng bảo mật thật, xem CHANGELOG v4.29.0).
- **Không hardcode ID role/kênh/category:** xem mục riêng ở trên — luôn qua `cfg_*` + `.st`.
- **ADMIN_IDS:** đọc từ env `ADMIN_IDS` (comma-separated), không hardcode
- Response PUBLIC (không ephemeral) cho user thường, trừ ticket panel button và MỌI thứ admin-only (xem trên)

## Log event types → nhóm kênh
```
ticket   → TICKET_CREATE, TICKET_CLOSE, TICKET_DONE, TICKET_UNDONE, TICKET_CLAIM
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

### 4. Trước khi sửa/tạo bất kỳ file tính năng nào
Đọc file này (`AI_CONTEXT.md`) trước — đặc biệt mục AUTH_GATE, "KHÔNG hardcode ID", và
"Cache trong RAM cũng phải phân biệt theo guild" ở trên, vì đây là 3 lớp bug đã lặp lại
nhiều lần nhất trong lịch sử sửa lỗi của repo này.
