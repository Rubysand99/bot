# CHANGELOG — TuyTam Bot (Rudeus Bot)

## [v4.11.5] — 2026-07-13

### ✨ Tính năng mới
- `.st` — Thêm 2 field trạng thái vào embed: **🪄 Relay Tin Admin (Ticket)** (🟢/🔴) và **🔘 Panel Buttons** (`X/7 bật`). Nút toggle relay giờ cập nhật ngay field trong embed khi bấm (giống pattern nút Shop Orders), thay vì chỉ báo qua tin nhắn ephemeral riêng

### 🐛 Sửa lỗi
- `cogs/giveaway.py` — Thay 7 `except:` trần còn sót (dòng 304/311/394/426/454/772/805) bằng `except Exception:` — bare except nuốt cả `asyncio.CancelledError`/`KeyboardInterrupt`
- `core/data.py` — Thêm `cleanup_resolved_sold_price()`, gọi mỗi ngày từ `daily_report_task` (đã có guild context sẵn) — dọn entry cũ hơn 7 ngày, đúng như comment cũ đã hứa nhưng chưa từng code

### ♻️ Thay đổi
- Xoá `data/words_vi.txt` — dữ liệu chết cho game "Nối Từ" đã gỡ từ v3.7.0, không còn ai import
- Xoá 3 hàm chết trong `core/data.py`: `get_panel_buttons_config`/`is_panel_button_enabled`/`set_panel_button_enabled` (field `panel_buttons`) — không ai dùng, bị hệ thống mới trong `ticket.py` (field `cfg_panel_buttons`) thay thế từ lâu mà không dọn
- Dọn docstring trùng lặp đầu `admin_views.py` (sót lại từ lúc tách file khỏi `admin.py`)
- Viết lại hoàn toàn README.md — bản cũ ghi version v3.9.5 và biến môi trường `ADMIN_IDS` không còn tồn tại trong code

### 📝 Đính chính audit trước (không phải bug thật, đã re-verify trước khi sửa)
- `GiveawayModal`, `AIConfirmView`, `ConfirmView` (invite.py) **đã** dùng `GuildContextView`/`GuildContextModal` qua alias `as View`/`as Modal` — audit trước đọc nhầm tên alias thành `discord.ui.View/Modal` thô
- `mod.py` — `_auto_unban` (tempban mới) **đã** truyền `guild_id=guild.id` cho `send_log()` từ trước — không thiếu như audit trước ghi nhận
- `admin_views.py`/`ticket.py` — 2 chỗ từng bị nghi bare `except:` thực ra đã là `except Exception:` sẵn — chỉ `giveaway.py` có bug thật (đã sửa ở trên)

---

## [v4.11.4] — 2026-07-12

### 🐛 Sửa lỗi
- `cogs/ticket.py` — **`.setrole`/`.listroles` ghi/đọc field Mongo chết** (`ticket_role_ids`, `ticket_type_roles`) **không hề được đọc khi cấp quyền ticket thật** (logic cấp quyền chỉ đọc `ticket_multi_roles` qua `get_ticket_role_ids()`). Lệnh báo "✅ thành công" nhưng role gán qua `.setrole` không có tác dụng gì — ticket luôn rơi về fallback mặc định (support/seller/builder). Viết lại để `.setrole` ghi thẳng vào `ticket_multi_roles` (cùng field UI `.st` dùng), `.listroles` đọc đúng field đó
- `cogs/logger.py` — `_send_daily_report()` đếm giveaway running/ended từ `load_giveaways_data()` **không lọc theo guild** (cache giveaway tách theo `message_id`, không tách theo guild) → mọi guild nhận cùng một con số gộp trong report hằng ngày. Giờ nhận `guild` làm tham số, lọc giveaway theo `channel.guild.id` trước khi đếm
- `cogs/invite.py` — `.backfillip`: thay `self.bot.get_channel(ch_id) or await self.bot.fetch_channel(ch_id)` (có thể ném exception chưa bắt nếu kênh log bị xoá) bằng `get_or_fetch_channel()` sẵn có (có try/except, trả `None` an toàn)
- `bot.py` — Bump `BOT_VERSION` "4.11.2" → "4.11.4" (entry v4.11.3 trước đó bị bỏ sót bump)

### ♻️ Thay đổi
- Xoá `deploy.sh` — không phải script deploy tái sử dụng, mà là log lệnh Termux của 1 session ngày 2026-05-30 (v4.0.0) bị lỡ commit vào repo, nhúng sẵn bản `admin.py` cũ thiếu toàn bộ tính năng seller-stats/DM-escalation từ v4.7+. Nguy cơ cao nếu chạy nhầm (tự `git push` bản cũ đè lên `origin main`)

### ✅ Đã kiểm tra, không cần sửa
- `verify_server.py` lấy IP qua `X-Forwarded-For` hop đầu tiên (`.split(",")[0]`) — xác nhận qua tài liệu chính thức Railway (Central Station, 3/2026): edge proxy của Railway **chèn IP thật vào đầu chuỗi**, hop đầu đáng tin cậy cho kiến trúc Railway cụ thể. Giữ nguyên code

---

## [v4.11.3] — 2026-07-09

### 🐛 Sửa lỗi
- `cogs/giveaway.py` — `_giveaway_timer_task`: thêm `set_current_guild(channel.guild.id)` ngay sau khi fetch được channel. Task này chạy qua `asyncio.create_task()` và có thể `sleep()` hàng giờ/ngày (đặc biệt khi resume lúc khởi động, trước vòng lặp set context cho từng guild trong `on_ready`) nên guild context bị "đóng băng" là None suốt đời task, khiến `end_giveaway()` → `send_log()`/`load_data()` không xác định được guild, mất log GIVEAWAY_END và có thể mất luôn các thao tác dùng data theo guild khác trong luồng kết thúc giveaway

---

## [v4.11.2] — 2026-07-09

### ✨ Tính năng mới
- `core/data.py` — Thêm field `_pending_renames` vào global data để lưu bền hàng đợi rename legit/vouch
- `bot.py` — Hàng đợi retry rename (khi bị Discord rate limit) giờ lưu qua Mongo thay vì RAM, resume lại đúng số mục tiêu cuối cùng khi bot restart (`_resume_pending_renames`, gọi từ `on_ready`)

---

─────────────────────────────────────
[v4.11.0] — 2026-07-08
✨ Tính năng mới
core/data.py — Thêm cfg_legit_emoji/cfg_vouch_emoji theo guild (mặc định ✅)
cogs/admin_views.py — Thêm EmojiConfigModal + 2 nút trong .st để đổi emoji legit/vouch (hỗ trợ unicode và custom emoji <:name:id>)
bot.py — _handle_legit/_handle_vouch/_backfill_legit dùng emoji đã cấu hình thay vì hardcode ✅
─────────────────────────────────────

## [v4.10.3] — 2026-07-08

### 🐛 Sửa lỗi
- `cogs/invite.py` — **`on_member_join` không set guild context** → mọi `_add_invite()` (total/unverify) khi có người join **không được lưu vào MongoDB** (xác nhận qua log lỗi thực tế `[DATA] ❌ save_data() được gọi mà KHÔNG có guild context`)
- `cogs/invite.py` — **`_handle_verify_result` (callback từ `verify_server.py` qua HTTP, Task hoàn toàn tách biệt) không có guild context** → verify xong nhưng **không -1 unverify/+1 verify được**, lỗi nặng nhất vì âm thầm phá vỡ toàn bộ hệ thống đếm invite mỗi lần user verify
- `cogs/invite.py` — **`on_member_remove` không set guild context** → -1 verify/+1 left khi user rời server cũng không được lưu
- `cogs/admin_views.py` — `CreateRoleModal.on_submit`: gọi `log.debug(...)` nhưng file không import `log` → `NameError` (crash) khi nhập màu hex sai lúc tạo role
- `cogs/ticket.py` — `on_message` (webhook relay "Ruby bot") đọc `load_data()` không có guild context → toggle bật/tắt qua `.st` không có tác dụng thật, luôn dùng mặc định

### ♻️ Thay đổi
- Rà soát toàn bộ repo: dọn ~70 import không dùng, biến local chết (`found_mid`, `invite_valid`, `notif`, `any_set`, `item_key`...), f-string thừa không có placeholder, xoá `global` thừa không cần thiết trong `core/data.py`
- `.gitignore` — bổ sung `__pycache__/`, `*.pyc`, `.env`, `*.log`, `venv/` (trước đây chỉ ignore `nohup.out`)
- `/botinfo` — dùng nốt `import platform` (trước đây import thừa không dùng) để thêm field 🐍 Python version

---

## [v4.10.2] — 2026-07-07

### 🐛 Sửa lỗi
- `cogs/admin.py` — `.help giveaway` ghi sai `.gpick`, sửa thành `.gwpick` (tên lệnh thật)

### ♻️ Thay đổi
- `cogs/admin.py` — Viết lại `.help` đầy đủ: thêm mục Shop Orders (VietQR), bổ sung `.setrole`/`.listroles` (ticket), `.verify`/`.serverlist`/`.leaveguild`/`.testip` (invite), `.gwreset` (giveaway)

---

## [v4.10.1] — 2026-07-07

### 🐛 Sửa lỗi
- `core/data.py` — Thêm `wait_data_cache_ready()` (asyncio.Event) tránh race condition lúc khởi động
- `cogs/seller.py`, `cogs/logger.py` — `before_loop` chờ data cache sẵn sàng, không chỉ `wait_until_ready()`
- `cogs/mod.py` — `on_message` (automod) tự set guild context, tránh đọc config rỗng
- `cogs/admin_views.py` — **Toàn bộ View/Modal (.st, setup server, buy roles, prefix...) không lưu được data do thiếu guild context** — đổi sang GuildContextView/Modal, vá 3 override `interaction_check`

## [v4.9.0] — 2026-07-03

### ✨ Tính năng mới
- `cogs/ticket.py` — **Relay Tin Admin trong Ticket**: khi admin (`ADMIN_IDS`) gửi tin nhắn thường (không phải lệnh) trong kênh ticket, bot tự động xoá tin gốc và gửi lại y hệt qua webhook tên cố định **"Ruby bot"**, avatar dùng **avatar của chính bot**. Hỗ trợ cả nội dung text lẫn file đính kèm
- `cogs/admin_views.py` — Panel `.st` thêm nút **🪄 Relay Tin Admin (Ticket)** để bật/tắt tính năng (`cfg_ticket_relay`, mặc định BẬT)

### 🔧 Thay đổi kỹ thuật
- `cogs/ticket.py` — Webhook được tạo/lấy 1 lần cho mỗi kênh ticket rồi cache trong `TicketCog._relay_webhook_cache` (tránh gọi API tạo webhook lặp lại); tự bỏ qua nếu bot thiếu quyền `Manage Webhooks`

---

## [v4.8.0] — 2026-06-22

### ✨ Tính năng mới
- `cogs/admin.py` — Nút "💰 Nhập giá" trong DM giờ **sống sót qua restart bot**: `bot.py` gọi `resume_pending_sold_views()` ở `on_ready`, đọc lại mọi đơn `pending_sold_price` còn tồn và đăng ký lại persistent view theo đúng `message_id` của từng DM (TuyTam và/hoặc Ruby)
- `cogs/admin.py` — **Escalation 24h**: nếu sau 24h admin TuyTam chưa điền giá, bot tự động DM thêm cho `ADMIN_RUBY_ID` kèm nút nhập giá riêng. Nút bên DM TuyTam **không bị thu hồi** — TuyTam vẫn bấm được nếu online trễ
- `cogs/admin.py` — Khi 1 trong 2 admin (TuyTam hoặc Ruby) điền giá xong: admin còn lại được DM báo "đơn đã được xử lý bởi ai — giá bao nhiêu"; nếu admin còn lại bấm nút sau đó, bot cũng hiển thị ngay thông tin đó thay vì báo lỗi chung
- `core/data.py` — Mở rộng `pending_sold_price` thêm `tuytam_message_id`, `ruby_message_id`, `escalated`; thêm `get_all_pending_sold_price()`, `set_pending_sold_dm()`, `mark_pending_sold_escalated()`
- `core/data.py` — Thêm `resolved_sold_price` + `mark_pending_sold_resolved()` / `get_resolved_sold_price()`: lưu lại đơn đã xử lý để trả lời chính xác khi admin còn lại bấm nút trễ

---

## [v4.7.0] — 2026-06-22

### ✨ Tính năng mới
- `cogs/admin.py` — `handle_sold()` (lệnh `sold`/`SOLD` trong kênh Stock) giờ tự **parse giá từ tên kênh** (vd: `✅𝟏𝟑𝟎𝐤-𝐧𝐨𝐧-𝟏𝐜𝐚𝐩𝐞` → `130000`, bỏ font Unicode + ✅/dấu trước số) và **ghi nhận thống kê doanh số cho seller** đã gõ lệnh — chỉ tính nếu seller có gói `.seller add` còn hạn (check qua `cogs/seller.is_active_seller`)
- `cogs/admin.py` — Nếu không parse được giá từ tên kênh: bot vẫn chuyển kênh sang Sold như cũ, lưu `pending_sold_price` và **DM cho `ADMIN_TUYTAM_ID`** kèm nút "💰 Nhập giá" → mở Modal nhập tay (vd: `130k`, `1m2`, `1tr5`) → ghi nhận đúng seller, đúng kênh
- `core/data.py` — Thêm `add_seller_sale()`, `get_seller_sales()`, `get_seller_sales_stats()`: lưu lịch sử sold-stock vào `seller_sales` (list), tính thống kê **24h + all-time** theo từng seller
- `core/data.py` — Thêm `add_pending_sold_price()`, `get_pending_sold_price()`, `remove_pending_sold_price()`: lưu đơn đang chờ admin điền giá thủ công vào `pending_sold_price`
- `core/data.py` — `parse_amount()` hỗ trợ thêm dạng `<số>m<1-chữ-số>` (vd: `1m2` = 1.200.000), tương tự `1tr5` đã có sẵn
- `cogs/seller.py` — Thêm `is_active_seller(guild_id, user_id)`: kiểm tra seller có gói còn hạn hay không (dùng bởi `admin.py`)
- `cogs/logger.py` — Báo cáo 8h sáng (`_send_daily_report`) thêm field **🏪 Doanh Số Seller (Sold-Stock)**: hiển thị top 10 seller theo doanh thu all-time, mỗi dòng có cả **24h** và **all-time** (số đơn + doanh thu)

### 🔧 Thay đổi kỹ thuật
- Nếu seller gõ `sold` nhưng KHÔNG có gói `.seller add` còn hạn → kênh vẫn được chuyển sang Sold như bình thường, nhưng **không** ghi nhận vào thống kê doanh số

---

## [v4.5.0] — 2026-06-14

### 🐛 Sửa lỗi
- `cogs/logger.py` — **Fix `.setuplog` không nhận kênh log đã đổi font chữ**: dùng `discord.utils.get(name=ch_name)` so sánh tên kênh chính xác → nếu tên kênh có font Unicode (vd: `𝗹𝗼𝗴-𝘁𝗶𝗰𝗸𝗲𝘁`) sẽ không match → tạo kênh mới → không bao giờ set channel ID đúng → log không gửi được. Fix: dùng `_strip_unicode_font()` để normalize tên trước khi so sánh
- `cogs/invite.py` — **Fix DM thông báo fake hiển thị "0 tài khoản khác"**: `_ip_records` cache dùng key `"1_2_3_4"` (dấu `_`) nhưng lookup dùng `ip` raw (`"1.2.3.4"`) → `shared_users` luôn rỗng → số đếm sai trong DM
- `cogs/logger.py` — **Fix báo cáo 8h sáng gửi 2 lần khi bot restart**: `_last_report_date` chỉ lưu in-memory → reset về `None` mỗi lần restart → gửi lại nếu restart trong khung 01:00–01:59 UTC. Fix: kiểm tra thêm `_daily_report_date` trong MongoDB trước khi gửi

---

## [v4.4.0] — 2026-06-12

### ✨ Tính năng mới
- `cogs/admin_views.py` — `.mkchannel` thêm 2 dropdown mới:
  - **③ Quyền truy cập**: `🌐 Public` (mặc định) / `🔒 Private` — private ẩn kênh với `@everyone`, chỉ bot + admin thấy
  - **④ Khoá gửi tin**: `🔓 Mở` (mặc định) / `🔐 Khoá (read-only)` — lock chặn `@everyone` gửi tin trong kênh public
- `cogs/admin_views.py` — Kênh tạo ra áp `overwrites` ngay lúc tạo (bot + admin luôn full quyền)
- `cogs/admin_views.py` — Embed kết quả hiển thị thêm cột **Quyền** và **Khoá**
- `cogs/admin_views.py` — Đổi tên kênh / category: thêm ô **Icon mới** (để trống = giữ icon cũ)
- `cogs/admin.py` — Cập nhật embed hướng dẫn `.mkchannel` (5 bước rõ ràng)
- `cogs/admin.py` — Cập nhật `.help admin` mô tả `.mkchannel`

---

## [v4.3.0] — 2026-06-10

### 🐛 Sửa lỗi nghiêm trọng
- `cogs/invite.py` + `core/data.py` — **Fix bug IP check không hoạt động**: MongoDB không cho phép dấu `.` trong field name → key IP dạng `"1.2.3.4"` không bao giờ lưu/đọc đúng → mọi acc clone đều qua verify mà không bị phát hiện
- `core/data.py` — **Fix race condition**: `save_data()` ghi MongoDB bất đồng bộ (`create_task`), nếu 2 acc verify gần nhau cùng `load_data()` trước khi task ghi xong → IP acc đầu bị mất, acc sau không thấy trùng

### ✨ Tính năng mới
- `core/data.py` — Thêm `atomic_register_ip()`: dùng MongoDB `$addToSet` ghi IP trực tiếp, tránh race condition
- `core/data.py` — Thêm `get_ip_users_mongo()`: đọc IP thẳng từ MongoDB (không qua cache) khi check collision
- `cogs/invite.py` — `_check_ip_collision` và `_register_ip` chuyển thành `async`, đọc/ghi MongoDB trực tiếp
- `cogs/invite.py` — `.checkip` và `.ipstats` đọc thẳng MongoDB thay vì in-memory cache
- `cogs/invite.py` — Lệnh `.backfillip [số]` (admin): đọc lại lịch sử kênh log general, parse IP từ `INVITE_VERIFY`/`INVITE_FAKE`, backfill vào `_ip_records` (mặc định 2000 msg, idempotent)
- `cogs/admin.py` — Cập nhật `.help invite` thêm `.checkip`, `.ipstats`, `.backfillip`

### 🔧 Thay đổi kỹ thuật
- Key IP trong MongoDB đổi từ `"1.2.3.4"` → `"1_2_3_4"` (dấu `.` → `_`) để tương thích MongoDB field name

---

## [v4.2.0] — 2026-06-08

### ✨ Tính năng mới
- `cogs/invite.py` — Role `UNVERIFY` gán ngay khi join, không xem được kênh nào
- `cogs/invite.py` — Sau khi verify: tự động gán role `VERIFY`, xóa `UNVERIFY`
- `cogs/invite.py` — Trùng IP: vẫn verify được nhưng lưu `_shared_ip` data, tài khoản thứ 2+ bị chặn giveaway
- `cogs/invite.py` — Bot gửi DM giải thích rõ tình trạng cho cả tài khoản primary lẫn bị chặn
- `cogs/invite.py` — Auto-kick sau **24h** nếu member vẫn còn role UNVERIFY (chưa verify)
- `cogs/invite.py` — Lệnh `.checkip @user` (admin): xem toàn bộ tài khoản chung IP, ai được/bị chặn giveaway
- `cogs/giveaway.py` — Chặn tham gia giveaway nếu IP bị blocked, hiển thị ephemeral giải thích lý do

### 🔧 Cấu hình role (trong `invite.py`)
```
UNVERIFY_ROLE_ID = 1500512964065755288
VERIFY_ROLE_ID   = 1464411190808805540
VERIFY_GUILDS    = {1500513085096726528, 1500512893139943455}
```

---

## [v4.1.0] — 2026-06-08

### 🗑️ Xoá tính năng
- `cogs/banking.py` — Xoá toàn bộ cog banking (webhook SePay, log GD, `.banktoday`, `.banksearch`, v.v.)
- `bot.py` — Xoá `"cogs.banking"` khỏi danh sách COGS
- `core/data.py` — Xoá `_col_banktxs`, `MAX_TX_HISTORY_CACHE`, `banking_cfg` trong `_default_data()`, và block load `banking_txs` trong `init_data_cache()`
- `cogs/logger.py` — Xoá `BANK_TXNS` khỏi `LOG_ICONS` + `LOG_ROUTES`, xoá field **🏦 Ngân hàng** trong daily report, xoá block thu thập data banking

---

## [v4.0.0] — 2026-06-02

### 🔒 Bảo mật
- `core/data.py` — Xoá hoàn toàn hardcode fallback `ADMIN_IDS`. Nếu env `ADMIN_IDS` chưa set, bot log `CRITICAL` và không ai có quyền admin cho đến khi cài đúng env

### ⚡ Cải tiến hiệu năng
- `core/data.py` + `cogs/banking.py` — Tách `banking_txs` ra collection MongoDB riêng (`tuytam_bot.banking_txs`). Mỗi GD là 1 document độc lập, không còn ghi đè toàn bộ main document mỗi lần có giao dịch mới
- `cogs/banking.py` — Cache 500 GD gần nhất vào memory khi khởi động, đọc từ cache thay vì query MongoDB mỗi request

### 🧹 Refactor
- `cogs/admin.py` → tách UI Views/Modals (~1544 dòng) ra `cogs/admin_views.py`. `admin.py` còn ~771 dòng, dễ maintain hơn
- `cogs/ticket.py` + `cogs/mod.py` — Thêm `import logging`, thay 27 bare `except: pass` → `except Exception` (typed), những chỗ Discord API giữ silent, những chỗ logic khác log debug

### 📖 Help & Docs
- `cogs/admin.py` — `.help` cập nhật đầy đủ:
  - **Ticket**: thêm `.setpanel`, `.orderbase`, `.setsl`/`.removesl`/`.listsl` (stock limit)
  - **Banking**: thêm `.banktoday`, `.banksearch`, alias `.bstats`
  - **Log**: thêm `.baocao`, cập nhật nhóm log (thêm `banking`, bỏ `balance`)
  - **AI Chat**: thêm mục mới `.aireset`, `.mychat`
  - Overview embed: thêm field AI Chat

### 🗑️ Xoá tính năng
- `cogs/balance.py` — Xoá toàn bộ hệ thống balance (cộng/trừ số dư kênh)
- Xoá mọi references đến balance system trong `bot.py`, `core/data.py`, `cogs/admin.py`, `cogs/logger.py`, `cogs/ai_chat.py`, `cogs/ticket.py`

---

## [v3.9.5] — 2026-06-01

### ✨ Tính năng mới
- `giveaway.py` — Thêm lệnh `.gwstatus`: xem toàn bộ giveaway đang chạy và đã kết thúc trong data
  - 🟢 Đang chạy: GW ID, phần thưởng, thời gian còn lại, số người tham gia, kênh, message ID
  - 🔴 Đã kết thúc: GW ID, phần thưởng, winner, số người tham gia, kênh, message ID
- `admin.py` — Cập nhật `.help giveaway` thêm lệnh `.gwstatus`

---

## [v3.9.4] — 2026-05-23

### ✨ Tính năng mới
- `admin.py` — Cập nhật `.help` toàn bộ (ticket/point/ai/invite/dichvu/giveaway/mod/banking/log/admin)
- `bot.py` — Cập nhật `CHANGELOG_CHANNEL_ID`, parse CHANGELOG.md khi khởi động, hiển thị entry mới nhất

---

## [v3.8.1] — 2026-05-29

### 🔧 Sửa lỗi / Cải tiến
- `ticket.py` — Ticket **Order Base** ping thêm role `BUILDER_BASE_ROLE_ID` (1484158340849205308) khi tạo kênh

---

## [v3.8.0] — 2026-05-22

### 🔧 Sửa lỗi
- `ticket.py` — Xóa `.mkchannel` trùng → fix `CommandRegistrationError` (admin.py không load được)

---

## [v3.7.9] — 2026-05-22

### 🔧 Sửa lỗi / Cải tiến
- `core/data.py` — Thêm `get_or_fetch_channel()` (cache → fetch_channel)
- `admin/ticket/giveaway/bot` — Thay toàn bộ `bot.get_channel()` → `get_or_fetch_channel()`
- `.backfill` + auto-backfill: xử lý đúng thứ tự cũ→mới, thả ✅ + đổi tên kênh +1

---

## [v3.7.8] — 2026-05-22

### ✨ Tính năng mới
- `admin.py` — `.backfill [số]`: quét kênh legit, thả ✅ cho tin +1legit bị bỏ sót (mặc định 25, max 100)

---

## [v3.7.7] — 2026-05-22

### ✨ Tính năng mới
- `admin.py` — `.help` overview + `.help <mục>` chi tiết, alias tiếng Việt

---

## [v3.7.6] — 2026-05-22

### 🔧 Cải tiến
- `giveaway.py` — Embed giveaway giữ nguyên sau khi kết thúc, disable nút + gửi tin winner riêng

---

## [v3.7.5] — 2026-05-22

### 🔧 Sửa lỗi
- `admin.py` — Xóa `.qr` prefix trùng với `ticket.py`
- `ticket.py` — `.mkchannel` → `.sellerchannel`/`.sch`; `.done` chỉ ADMIN_IDS
- `core/data.py` — Thêm `get_seller_qr`, `save_seller_qr`, `get_all_seller_qr`

---

## [v3.7.4] — 2026-05-20

### 🔧 Cải tiến
- `core/data.py` — `BUILDER_BASE_ROLE_ID`, cập nhật `is_staff_member()`
- `ticket.py` — Builder Base tự động vào overwrites khi tạo ticket

---

## [v3.7.3] — 2026-05-18

### ✨ Tính năng mới
- `backend/main.py` — LootLabs postback → Discord webhook embed (mã/point/hạn/unique_id)

---

## [v3.7.2] — 2026-05-18

### 🔧 Cải tiến
- `point.py` — Redeem thành công + `.gencode` → log embed vào `CODE_GEN_LOG_CHANNEL_ID`

---

## [v3.7.1] — 2026-05-17

### ✨ Tính năng mới
- `.setpoint <ID> <số>`, `.pointall`/`.allpoints`/`.pointlist` (top 20, tổng point)

---

## [v3.7.0] — 2026-05-17

### ✨ Tính năng mới
- Bầu Cua nhiều người: `.bc open/cancel`, `.setbaucua`, 4-6 người, 30s, tỉ lệ x1→+0.9pt
- Xóa: Nối Từ, Vua Tiếng Việt

---

## [v3.4.x – v3.6.x] — 2026-05-14 đến 2026-05-16

### ✨ Tính năng mới
- Point system đầy đủ, FastAPI/Render, Linkvertise, `.shop .exchange .addreward .delreward .clearshop`
- Cá cược point minigame (WIN_RATE 0.9x), `.rank`, `.mgstats`
- `mod.py` Ban/Kick/Mute/Warn/Automod; `logger.py`; slash commands
- Tách bot.py 6000 dòng → cấu trúc Cog, MongoDB + cache
