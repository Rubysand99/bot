# CHANGELOG — TuyTam Bot (Rudeus Bot)

## [v4.37.1] — 2026-08-22

### 🐛 Sửa lỗi — mã CK không khớp Cấu trúc mã thanh toán của SePay
`gen_transfer_code()` (v4.37.0) sinh mã dạng `<tên khách>-<6 ký tự chữ+số>` — không khớp
kiểu **<tiền tố CỐ ĐỊNH 2-5 ký tự chữ><hậu tố cùng loại ký tự, không dấu ngăn cách>** mà
SePay dùng để tự bóc tách trường `code` từ nội dung CK (Cấu hình Công ty › Cấu hình chung
› Cấu trúc mã thanh toán). Tên khách dài/đổi được không thể là "tiền tố cố định", nên
trường `code` phía SePay sẽ luôn rỗng với mã kiểu cũ — nếu bật thêm "Bỏ qua nếu không có
mã thanh toán" bên SePay thì webhook sẽ ÂM THẦM không bắn cho các đơn này.

- Đổi format: `DH` + 6 chữ số ngẫu nhiên, KHÔNG dấu ngăn cách (vd `DH482917`) — khớp
  đúng ví dụ mẫu trong docs SePay (`DH111111`). `DH` (Đơn Hàng) chọn trung lập, không
  gắn tên riêng TuyTam — đổi ở đây thì phải đổi Y HỆT bên cấu hình SePay.
- Bỏ luôn việc nhúng tên khách vào mã (không cần thiết — tên khách đã hiện riêng ở
  field "👤 Khách" của mọi embed liên quan rồi).
- Không gian mã nhỏ hơn bản trước (10^6 thay vì 36^6) nên thêm vòng kiểm tra trùng với
  đơn đang chờ trước khi lưu (`get_pending_shop_order`), tối đa 5 lần thử lại.
- `_handle_sepay_webhook`: ưu tiên tra thẳng theo field `code` SePay tự bóc tách (giờ
  đáng tin cậy vì khớp cấu trúc) trước khi fallback dò substring trong `content` thô —
  nhanh và chính xác hơn cho các webhook mới, vẫn tương thích ngược cho trường hợp cũ.

**Việc cần làm bên SePay dashboard:** vào Cấu hình Công ty › Cấu hình chung › Cấu trúc
mã thanh toán, đặt Tiền tố = `DH`, Hậu tố = 6 ký tự, loại **Số nguyên**.

---

## [v4.37.0] — 2026-08-22

### ✨ Tính năng mới — Shop Orders: multi-seller bank + tự nhận thanh toán qua SePay
Đại tu hẳn tính năng Shop Orders (thử nghiệm), theo yêu cầu riêng:

- **`.shopbank`/`.listbank` — mỗi seller 1 bank riêng.** Trước đây 1 bank DUY NHẤT dùng
  chung cho cả guild, chỉ admin cài được. Giờ admin HOẶC seller (`has_ticket_access` —
  có role xem được ít nhất 1 loại ticket, KHÔNG có nghĩa xem được TẤT CẢ loại ticket)
  tự `.shopbank` đăng ký bank CỦA RIÊNG mình (upsert theo `ctx.author.id`, gõ lại là
  cập nhật đúng bank của chính họ). `.listbank` xem toàn bộ bank đã đăng ký.
- **`.done` dùng ĐÚNG bank của người gõ lệnh.** QR giờ luôn theo `ctx.author`/
  `interaction.user` — tiền vào thẳng TK người xử lý đơn, không qua 1 TK chung. Seller
  chưa `.shopbank` thì báo rõ ngay (không im lặng bỏ qua như trường hợp tính năng tắt
  hẳn), phần còn lại của `.done` (spent/role) vẫn chạy bình thường.
- **Nội dung CK tự sinh riêng theo từng đơn** (`gen_transfer_code`, vd `TENKHACH-A1B2C3`)
  thay vì 1 chuỗi cố định dùng chung cho mọi đơn như trước — phục vụ đối soát, không
  phải để che giấu giao dịch. Mã này lưu vào pending order (GLOBAL, không tách theo
  guild — webhook thanh toán gọi vào không có guild context sẵn, giống lý do
  `_pending_sold_price` cũng phải để global) để webhook tự đối chiếu.
- **`verify_server.py`: route `/webhook/sepay` mới** — nhận báo có tiền vào từ SePay
  (auth bằng API Key, env var `SEPAY_WEBHOOK_API_KEY` mới), luôn trả `{"success": true}`
  theo đúng contract bắt buộc của SePay (chậm/sai format là bị tính lỗi và retry
  Fibonacci tối đa 7 lần/5 tiếng). File này CỐ TÌNH vẫn không import core.data/discord
  như trước giờ — auth + đọc payload xong giao hết cho `PAYMENT_CALLBACK` (đăng ký từ
  `cogs/shop_orders.py`), xử lý Mongo/Discord nằm hết bên đó.
- **`cogs/shop_orders.py`: `_handle_sepay_webhook()`** — dedup theo `id` webhook (SePay
  hay bắn trùng lúc retry), khớp `content` trả về với ref_code đang chờ (so khớp dạng
  substring, không đòi khớp tuyệt đối vì ngân hàng có thể thêm/bớt khoảng trắng quanh
  nội dung), đối chiếu thêm số TK nhận cho chắc, rồi tự thông báo **trong đúng ticket**
  + gửi embed hàng đợi.
- **Hàng đợi ("Đơn hàng đang xử lý") giờ CHỈ gửi SAU KHI webhook xác nhận đã thanh
  toán thật** — trước đây gửi NGAY lúc `.done` (trước khi biết khách đã trả tiền hay
  chưa). Đổi tên field/tiêu đề từ "chờ xử lý" → "đang xử lý" cho khớp đúng trạng thái.
  **Ngoại lệ:** nếu seller chưa `.shopbank` (không có QR nên không có webhook nào tự
  xác nhận được) thì GIỮ hành vi cũ — gửi hàng đợi ngay, staff tự bấm "Hoàn thành" tay,
  tránh đơn "biến mất" khỏi hàng đợi.
- **Hóa đơn công khai (kênh proof) hiện ĐÚNG mã CK thật đã in trên QR** — đọc lại từ
  field "📝 Mã CK" của embed hàng đợi, không tự sinh mã mới không liên quan gì tới giao
  dịch bank thật như trước. Có fallback sinh mã mới cho đơn hàng đợi gửi TRƯỚC bản cập
  nhật này (chưa có field đó), tránh lỗi khi bấm Hoàn thành trên đơn cũ còn tồn đọng.

**Việc CẦN làm bên phía Railway/SePay (không code được):** thêm env var
`SEPAY_WEBHOOK_API_KEY` (tự đặt), tạo Webhook trên dashboard SePay trỏ về
`{VERIFY_BASE_URL}/webhook/sepay` với đúng API Key đó.

**Chưa đụng tới / để dành quyết định sau:**
- Đối chiếu số TK (`accountNumber` từ SePay) hiện so sánh string trực tiếp với số đã
  lưu qua `.shopbank` — CHƯA test thực tế SePay có normalize khác đi không (bớt số 0
  đầu, thêm khoảng trắng...). Nếu về sau thấy log cảnh báo "LỆCH số TK" dù đúng TK thật,
  cần nới lỏng cách so khớp ở đây.
- `.automod addrole/delrole` (mod.py) vẫn còn bug ping-nhầm-role y hệt `.addrole` cũ
  (đã nêu ở v4.36.0) — chưa sửa.

---

## [v4.36.0] — 2026-08-21

### 🐛 Sửa lỗi
- `cogs/admin.py: .addrole` / `.removerole` — **ping nhầm cả role khi gõ lệnh.** Cú
  pháp cũ `.addrole @user @role` bắt buộc gõ role dạng `@mention` để `discord.Role`
  converter parse được (converter có hỗ trợ gõ ID hoặc tên chính xác thay vì mention,
  nhưng thực tế hầu như ai cũng gõ `@` rồi bấm chọn gợi ý của Discord) → Discord tự
  phát thông báo ping cho **TẤT CẢ member đang có role đó** ngay khi tin nhắn được gửi
  đi. Việc này xảy ra ở phía Discord, TRƯỚC khi bot kịp xử lý bất kỳ điều gì, nên
  không có cách nào "gỡ" ping sau khi tin nhắn đã gửi.
  - Sửa bằng cách bỏ hẳn tham số role khỏi lệnh gõ tay — giờ chỉ `.addrole @user` /
    `.removerole @user`, bot trả lời kèm dropdown chọn role
    (`RoleAssignSelectView`, `cogs/admin_views.py`, dùng `discord.ui.RoleSelect` —
    component chọn role NATIVE của Discord). Chọn qua dropdown không gõ chữ nên
    không thể tạo ra mention thật, cũng không bị giới hạn 25 role như Select thường.
  - Nhân tiện đồng bộ 1 điểm lệch nhỏ giữa 2 lệnh: `.addrole` vốn có check "role cao
    hơn role bot" nhưng `.removerole` thì KHÔNG (dựa hẳn vào `discord.Forbidden`
    không bắt được) — giờ cả 2 dùng chung `RoleAssignSelectView` nên được check như
    nhau, báo lỗi rõ ràng thay vì để exception rơi tự do.
  - **Chưa đụng tới:** `.automod addrole/delrole @role` (`cogs/mod.py`) có cùng dạng
    bug (role cũng là tham số `discord.Role` gõ tay) nhưng là lệnh cấu hình whitelist
    automod, tần suất dùng thấp hơn hẳn `.addrole` hàng ngày — để nguyên, báo lại để
    quyết định có cần sửa tương tự không.

---

## [v4.35.0] — 2026-08-10

### 🔍 Rà soát toàn bộ codebase — Phần 8/~10: AI (`cogs/ai_chat.py`, `core/ai_*.py`, `core/rag.py`) + rà lại `cogs/giveaway.py`

### 🐛 Sửa lỗi
- `core/ai_tools.py: _invoke_cmd()` — **lỗi hồi quy do chính đợt sửa prefix trước đây
  (v4.29.0) gây ra.** Hàm này (dùng bởi HẦU HẾT tool admin của `.ai` — tạo/xoá/đổi tên
  kênh, tạo/xoá role, ban/kick/mute/warn, purge, đóng ticket, reset giveaway...) hardcode
  prefix `.` khi dựng message giả lập để gọi lại lệnh gốc. Từ khi prefix trở thành cấu
  hình riêng theo từng guild (`.st` → "Đặt Prefix Bot"), guild nào đổi sang prefix khác
  "." sẽ khiến `get_context()` KHÔNG nhận ra nội dung hardcode "." là lệnh hợp lệ nữa
  (prefix không khớp) → mọi tool admin qua `.ai` cho guild đó im lặng hỏng (chạy với
  argument rỗng/sai thay vì báo lỗi rõ ràng). Đã sửa dùng đúng `get_guild_prefix()` của
  guild hiện tại thay vì hardcode.

### ✅ Đã rà soát kỹ, xác nhận KHÔNG có bug
- `cogs/ai_chat.py: AIConfirmView` dùng `discord.ui.View` thường (không phải
  `GuildContextView`) — nhưng xác nhận AN TOÀN: chỉ tạo ra SAU khi `.ai` đã tự check
  `ADMIN_IDS`, và nút Xác nhận/Huỷ tự kiểm tra đúng người đã gõ lệnh
  (`interaction.user.id != ctx.author.id`) — 2 lớp bảo vệ độc lập, không phải kiểu hổng
  như `admin_views.py` ở Phần 4 (nơi CẢ VIEW LẪN LỆNH GỐC đều thiếu check).
- `handle_ai_message()` (auto-trả lời trong kênh AI, mọi user dùng được) CHỈ dùng agent
  "support" với `QUERY_TOOL_SCHEMAS` (tool chỉ đọc) — tool nguy hiểm
  (`ADMIN_TOOL_SCHEMAS`, agent "ops") chỉ reachable qua lệnh `.ai` đã check admin ngay
  từ đầu, không có đường nào để user thường chạm được tool nguy hiểm.
- `core/ai_tools.py` — mọi query-tool handler (check ticket/seller/invite/lịch sử mua)
  đều dùng đúng `ctx.guild`/`ctx.author`, không có ID hardcode nào.
- `core/rag.py` — `search_rag()`/`_keyword_fallback_search()`/vector search pipeline đều
  lọc đúng theo `guild_id` (cả nhánh Mongo `$vectorSearch` filter lẫn fallback từ khoá
  thô) — thiết kế multi-guild đúng ngay từ đầu, không có gì cần sửa.
- Rà lại `cogs/giveaway.py` (đã sửa nhiều ở Phần 1/2 + hotfix riêng) — `_h_giveaway_reset`
  ở `core/ai_tools.py` gọi qua `_invoke_cmd(ctx, "gwreset", ...)` nên tự động thừa hưởng
  toàn bộ fix trước đó của `.gwreset` (v4.28.1) lẫn fix prefix vừa sửa ở trên, không cần
  sửa thêm gì riêng.

---

## [v4.34.0] — 2026-08-10

### ✨ Tính năng mới
- Lệnh `.undone <tiền>` (alias `.donesub`/`.trutien`, admin only) — trừ tiền đã tiêu của
  user cho các trường hợp lỡ `.done` nhầm (nhầm người, nhầm số tiền). Cùng cú pháp linh
  hoạt như `.done`: dùng `.undone 50k` trong kênh ticket (tự đọc buyer từ topic) hoặc
  `.undone @user 50k` ở bất kỳ đâu.
  - Trừ đúng cả 2 nơi `.done` đã cộng: tổng chung (`user_total_spent`) VÀ tổng theo
    server nếu ticket có server_key (`user_spent_by_server`) — thêm
    `subtract_user_spent()`/`subtract_user_spent_server()` ở `core/data.py`, đối xứng
    với `add_user_spent()`/`add_user_spent_server()` đã có. Không cho âm (floor ở 0),
    báo rõ nếu số tiền yêu cầu trừ nhiều hơn tổng hiện có.
  - **Tự đồng bộ lại buy-role**: gọi lại `auto_give_buy_roles()` với tổng MỚI sau khi
    trừ — hàm này vốn đã tự add đúng tier VÀ remove tier không còn đạt, nên role mua
    hàng luôn khớp đúng tổng thực tế, không cần thao tác tay.
  - **Tự mở lại ticket**: nếu chạy trong đúng kênh ticket của buyer đó (không mention),
    tự xoá cờ `completed_{channel_id}` để `.done` chạy lại được với số tiền đúng, không
    cần tạo ticket mới.
  - Log đầy đủ qua `send_log()` với event type mới `TICKET_UNDONE` (thêm vào
    `cogs/logger.py`, cùng nhóm kênh "ticket" như `TICKET_DONE`) — có audit trail rõ
    ràng ai sửa, sửa bao nhiêu, sửa cho ai.
  - Cập nhật `.help` để lệnh hiện ra khi tra cứu.

---

## [v4.33.0] — 2026-08-10

### 🔍 Rà soát toàn bộ codebase — Phần 7/~10: `cogs/mod.py`

### 🐛 Sửa lỗi
- `cogs/mod.py` — **`_spam_cache`/`_image_cache`/`_warn_cooldown` không phân biệt theo
  guild**, chỉ key theo `user_id` (hoặc `(mod_id, target_id)`). Cùng lớp bug với
  `_open_tickets` đã sửa ở Phần 5: 1 user hoạt động cùng lúc ở 2 guild bot đang phục vụ
  (đúng mục đích multi-guild) có thể bị **tính gộp tin nhắn/ảnh từ CẢ HAI guild vào
  chung 1 bộ đếm** → bị auto-mod xoá tin/mute NHẦM vì "spam" dù mỗi guild riêng lẻ đều
  dưới ngưỡng. Tương tự, `_warn_cooldown` khiến 2 mod ở 2 guild khác nhau (hoặc 1 mod
  cảnh cáo cùng 1 user ở 2 guild vì 2 lỗi riêng biệt) bị chặn nhầm bởi cooldown của
  guild kia. Đã đổi toàn bộ key cache sang có `guild_id` — mỗi guild theo dõi độc lập,
  cập nhật cả 4 hàm + 10 chỗ gọi liên quan (`.warn`, `/warn`, automod text/ảnh).
- `cogs/mod.py` — Auto-mod embed cảnh báo hardcode footer "TuyTam Store • Auto-Mod" —
  hiện sai tên cho mọi guild khác. Đổi sang hiện đúng tên server đang chạy.

### 📌 Phát hiện thêm (chưa sửa — cần bạn quyết định phạm vi)
- Tìm thấy **44 chỗ** hardcode chuỗi "TuyTam Store" (chủ yếu ở footer embed) rải khắp
  TOÀN BỘ codebase, không riêng `mod.py`. Đây là vấn đề **thẩm mỹ** (branding hiện sai
  tên cho guild khác), không phải bug chức năng — không xử lý gộp vào phần này vì phạm
  vi quá rộng so với 1 file. Nếu muốn dọn toàn bộ, đây nên là 1 phần audit riêng (hoặc
  cân nhắc thêm "Tên Store" làm 1 mục cấu hình qua `.st`, tương tự prefix).

### ✅ Đã rà soát kỹ, xác nhận KHÔNG có bug
- `cog_load()` (resume tempban sau restart) dùng đúng lifecycle hook của discord.py —
  chạy 1 LẦN DUY NHẤT khi cog được load, KHÔNG refire mỗi lần reconnect như `on_ready()`
  (khác bug đã sửa ở Phần 2) — an toàn.
- `_get_mod_data()`/`_save_mod_data()` dùng pattern đọc-sửa-ghi không khoá, nhưng đã xác
  nhận an toàn: không có `await` nào xen giữa lúc đọc và lúc ghi trong bất kỳ luồng gọi
  nào (asyncio single-thread, không có điểm yield thì không thể bị chèn ngang) — khác
  với bug đã sửa ở `get_ticket_number()` (Phần 1), nơi có 1 `await` Mongo thật sự nằm
  giữa.
- `add_tempban()` đã đúng — nhận `guild_id` tường minh dù bảng tempban intentionally
  dùng chung toàn bộ bot (chống multi-acc/VPN xuyên guild — xem Phần 1).

---

## [v4.32.0] — 2026-08-10

### 🔍 Rà soát toàn bộ codebase — Phần 6/~10: `cogs/invite.py`
Tiếp tục dọn nốt các chỗ hardcode ID còn sót (đúng chủ đề đợt sửa v4.31.0), lần này ở
file quản lý invite/verify.

### 🐛 Sửa lỗi
- `cogs/invite.py` — **`MEMBER_ROLE_IDS`** (list 4 role tự động gán kèm khi verify: ping
  Stock/Notification/Member/ping media) hardcode dùng chung cho MỌI guild — cùng lớp bug
  với `DONE_ROLE_ID`/`TRANSCRIPT_CHANNEL_ID` đã sửa ở Phần 3/5. Đã chuyển thành
  `cfg_verify_extra_roles` (list, per-guild) — migrate giữ nguyên cho TuyTam Community
  (không đổi hành vi hiện tại), cấu hình qua `.st` → nút mới "🎁 Verify Extra Roles"
  (chọn được nhiều role cùng lúc trong 1 dropdown — thêm `MultiRoleConfigSelect` dùng
  chung cho các cấu hình dạng danh sách sau này nếu cần).
- `cogs/invite.py` — **`WELCOME_GUILDS`** (dict hardcode 1 guild_id → 1 channel_id, ping
  chào mừng member mới join). Rà kỹ phát hiện guild_id trong dict này (`950363132679831642`)
  **không khớp** `LEGACY_MAIN_GUILD_ID` (ID thật của TuyTam Community,
  `1464407860640219189`) — tính năng này thực ra đã âm thầm KHÔNG chạy ở TuyTam từ
  trước giờ, không phải bị đợt sửa này làm hỏng thứ đang hoạt động. Đã chuyển thành
  `cfg_welcome_channel` (per-guild) — KHÔNG migrate giá trị cũ cho TuyTam (vì nó chưa
  từng đúng với server này), cấu hình qua `.st` → nút mới "👋 Welcome Channel".

### ✅ Đã rà soát kỹ, xác nhận KHÔNG có bug
- `_get_shared_ip()`/`_check_ip_collision()` (hệ thống chống đa tài khoản qua IP, quyết
  định ai được ưu tiên tham gia giveaway) CỐ Ý dùng chung toàn bộ bot, không tách theo
  guild — đã có sẵn comment giải thích đây là thiết kế có chủ đích (IP không thuộc về
  guild cụ thể nào), không phải sai sót cần sửa.
- `_get_invite_counts()`/`_save_invite_counts()`/`_get_alltime_counts()` — số liệu mời
  đã đúng per-guild từ trước (qua `load_data()`/`save_data()` theo contextvar).
- `ACC1_ID`/`ACC2_ID` trong lệnh `.testip` chỉ là dữ liệu giả để test UI thống kê IP,
  không phải cấu hình thật — không cần sửa.

---

## [v4.31.0] — 2026-08-10

### 🏗️ Thay đổi kiến trúc — KHÔNG còn ID nào hardcode trong code, tất cả qua `.st`
Theo yêu cầu: gỡ bỏ hoàn toàn việc lưu ID role/kênh/category cụ thể trong code làm giá
trị mặc định. Trước đây nhiều nơi (constants ở `core/data.py`, hoặc tệ hơn là hardcode
cục bộ trong từng file) coi ID của TuyTam Community là "mặc định" cho MỌI guild — dù
comment ghi rõ "chỉ đúng cho server chính". Cách này không đáng tin cậy (đã tìm ra 3 lần
bị vi phạm ở Phần 3 và Phần 5: `DONE_ROLE_ID`, `TRANSCRIPT_CHANNEL_ID`, `BUILDER_BASE_ROLE_ID`
hoàn toàn không qua hệ thống `cfg_*`, im lặng không chạy ở guild khác).

**Giờ:**
- `core/data.py: _default_data()` — KHÔNG còn ID nào hardcode. Mọi guild (kể cả TuyTam
  Community) bắt đầu ở trạng thái "chưa cài" (0) cho: Ticket Category, Support Role,
  Seller Role, Builder Role, Legit Channel, Proof Channel, Stock/Sold Category, Done
  Role, Transcript Channel.
- **TuyTam Community được bảo toàn cấu hình cũ tự động, 1 lần duy nhất**: thêm
  `_TUYTAM_LEGACY_CFG_MIGRATION` (dict riêng, chỉ dùng cho việc migrate, KHÔNG phải
  default cho ai khác) + `_mongo_load()` tự backfill các field còn trống (0) của
  **đúng 1 document** `guild_<TuyTam ID>` khi bot load lần kế tiếp — admin không cần
  làm gì, server hiện tại không bị gián đoạn. Field nào ĐÃ có giá trị (kể cả do admin
  từng đổi qua `.st`) sẽ KHÔNG bị ghi đè.
- Toàn bộ 9 mục trên giờ cấu hình **duy nhất qua `.st`** (nút bấm — chọn role/kênh/
  category trực tiếp từ dropdown Discord, không cần nhớ cú pháp lệnh): thêm 3 nút mới
  "🔨 Builder Role", "🎖️ Done Role", "📄 Transcript Channel" vào `SettingsView`
  (`cogs/admin_views.py`) — dùng chung helper `_send_role_select`/`_send_channel_select`
  đã có sẵn cho các mục khác, không phải code mới từ đầu.
- **Xoá 2 lệnh riêng** `.donerole` và `.transcriptchannel` (thêm ở Phần 3/5) — đã gộp
  hoàn toàn vào `.st`, tránh có 2 cách làm 1 việc. Dọn `.help` theo.
- `.st` — embed hiển thị cũng bỏ luôn 2 chỗ hardcode ID fallback còn sót (Support Role,
  Proof Channel hiện "Chưa cài" đúng nghĩa thay vì hiện nhầm mention của TuyTam ở guild
  khác), thêm 3 field hiển thị mới (Builder/Done Role, Transcript Channel), và sửa luôn
  title embed hardcode "TuyTam Store" → hiện đúng tên server đang chạy lệnh.
- `core/data.py: is_staff_member()` — hàm dùng CHUNG toàn bộ bot cũng dính hardcode
  `BUILDER_BASE_ROLE_ID` trực tiếp, không qua `cfg_*` — đã sửa theo.

---

## [v4.30.0] — 2026-08-10

### 🔍 Rà soát toàn bộ codebase — Phần 5/~10: `cogs/ticket.py`

### 🐛 Sửa lỗi
- `cogs/ticket.py` — **`_open_tickets` (cache "user nào đang có ticket mở") không phân
  biệt theo guild**, chỉ key theo `user_id`. Với 1 user là member của NHIỀU guild bot
  đang phục vụ (đúng mục đích multi-guild) — có ticket mở ở guild A, rồi thử mở ticket
  ở guild B: `has_ticket(guild_B, user)` tra nhầm `channel_id` của guild A, guild_B
  không tìm thấy kênh đó (đúng — nó thuộc guild khác) → tưởng nhầm "ticket không còn
  tồn tại" → **TỰ XOÁ LUÔN cache của guild A dù ticket ở đó vẫn đang mở bình thường**.
  User sau đó mở được ticket THỨ 2 ở guild A dù ticket đầu chưa đóng — phá vỡ luật
  "1 ticket/user". Đã đổi key cache thành `(guild_id, user_id)` — mỗi guild theo dõi
  độc lập, cập nhật cả 9 chỗ gọi liên quan.
- `core/data.py` + `cogs/ticket.py` — **`TRANSCRIPT_CHANNEL_ID` (kênh lưu transcript khi
  đóng ticket) là hằng số hardcode dùng chung cho MỌI guild** — cùng lớp bug với
  `DONE_ROLE_ID` đã sửa ở Phần 3 (v4.28.0), lần này chưa từng được đưa vào hệ thống
  `cfg_*` per-guild. Guild khác TuyTam Community chắc chắn không có kênh ID này →
  transcript đóng ticket **im lặng không được lưu**, không lỗi không log. Đã thêm
  `cfg_transcript_channel` (per-guild, default = ID cũ nên TuyTam không đổi hành vi) +
  `get_cfg_transcript_channel()`/`set_cfg_transcript_channel()`, cùng lệnh
  `.transcriptchannel [#kênh]` (admin, alias `.settranscript`) để mỗi server tự cấu
  hình. `FEEDBACK_CHANNEL_ID` cùng khu vực constants nhưng xác nhận là dead code —
  không được dùng ở bất kỳ đâu trong toàn bộ codebase, không cần sửa.
- `cogs/ticket.py: .done` — Dòng báo lỗi "Không tìm thấy role" khi role tặng chưa cấu
  hình đúng còn sót hardcode số ID CŨ (`1515393691206811901`) từ TRƯỚC khi
  `DONE_ROLE_ID` được chuyển sang `cfg_done_role` ở Phần 3 — guild khác cấu hình role
  khác thì lỗi vẫn hiện đúng số ID đó, không liên quan gì role họ thật sự đã đặt. Giờ
  hiện đúng ID đang cấu hình cho guild đang chạy lệnh, kèm gợi ý `.donerole @role`.

### ✅ Đã rà soát kỹ, xác nhận KHÔNG có bug
- Không có `interaction_check()` override nào trong file này — mọi View dùng chung base
  `GuildContextView` (đúng, vì hầu hết View trong `ticket.py` CỐ Ý cho member thường
  dùng, ví dụ mở ticket). Các action admin-only (đóng ticket, hoàn thành đơn, bật/tắt
  nút panel) đều tự kiểm tra `ADMIN_IDS`/`is_staff_member()` + `ephemeral=True` đúng
  cách ở từng callback — quét toàn bộ 0 chỗ nào thiếu (khác hẳn `admin_views.py` ở
  Phần 4, nơi cả object View thiếu check hoàn toàn).

---

## [v4.29.0] — 2026-08-10 — 🔴 SECURITY

### 🔍 Rà soát toàn bộ codebase — Phần 4/~10: `cogs/admin_views.py`

### 🚨 Lỗi nghiêm trọng nhất tìm được trong toàn bộ đợt rà soát — leo thang đặc quyền
Sau khi admin gõ `.setup`, 4 nhánh chính — **Kênh / Danh mục / Role / Server** — đều:
1. Được gửi ra kênh **CÔNG KHAI** (không `ephemeral=True`) — ai trong kênh cũng thấy.
2. Bản thân 4 View đó (`SetupChannelView`, `SetupCategoryView`, `SetupRoleView`,
   `SetupServerView`) **KHÔNG có check admin riêng** — chỉ kế thừa
   `GuildContextView.interaction_check()` gốc, vốn CHỈ kiểm tra server đã ủy quyền hay
   chưa, KHÔNG kiểm tra người bấm có phải admin không.

Kết hợp lại: trong tối đa 180 giây sau khi 1 admin bấm vào 1 trong 4 nhánh này, **BẤT KỲ
member nào nhìn thấy tin nhắn đó** (không cần là admin) đều có thể bấm nút và:
- Tạo / xoá / đổi tên / clone kênh, đổi font toàn bộ kênh & category trong server.
- Tạo / xoá category, di chuyển kênh giữa các category.
- **Tạo / xoá role, và đặc biệt — tự GÁN ROLE CHO CHÍNH MÌNH** qua nút "✅ Gán role"
  (`AssignRoleModal action="give"`) — đây là leo thang đặc quyền thật sự, không chỉ
  xem/sửa nhầm cấu hình.
- Đổi kênh welcome/goodbye/log, role tự động gán khi member mới join, prefix bot.

Rà soát kỹ hơn phát hiện lỗi này lan rộng khắp toàn bộ cây `.setup`, không riêng 4 view
chính — tổng cộng **25 chỗ** gửi tin nhắn kèm nút bấm/menu chọn mà thiếu `ephemeral=True`
(mọi Select con: xoá/đổi tên/clone kênh, xoá/đổi tên category, xoá role, xoá buy-role
tier, xoá mục giá, chọn kênh welcome/goodbye/log...).

**Đã sửa:**
- Thêm `ephemeral=True` cho toàn bộ **25 chỗ** gửi tin nhắn kèm `view=` — đây là lớp bảo
  vệ CHÍNH: tin nhắn ephemeral chỉ người bấm tự thấy/tự bấm được, Discord đảm bảo ở tầng
  nền tảng, không phụ thuộc logic Python có đúng hay không.
- Thêm `interaction_check()` (check admin, giống hệt `SetupMainView` — đã sửa ở
  v4.25.3) cho cả 4 view `SetupChannelView`/`SetupCategoryView`/`SetupRoleView`/
  `SetupServerView` — lớp bảo vệ THỨ 2, phòng trường hợp 1 thay đổi code sau này lỡ gửi
  lại 1 trong các view này mà quên `ephemeral=True`.

### 🐛 Sửa lỗi khác
- `core/data.py` + `bot.py` + `cogs/admin_views.py: SetPrefixModal` — **Đổi prefix bot
  không có tác dụng gì dù báo thành công.** `SetPrefixModal` lưu `cfg_prefix` và báo
  "✅ Prefix đã đổi", nhưng `bot.py` hardcode `command_prefix="."` (chuỗi tĩnh) — không
  có gì từng đọc lại `cfg_prefix`. Đã thêm `get_guild_prefix()` (đọc trực tiếp cache,
  không qua contextvar vì đây là hàm chạy sớm nhất trong pipeline xử lý message) +
  chuyển `bot.py` sang dùng prefix CALLABLE theo từng guild. `SetPrefixModal` giờ cảnh
  báo thêm: help text nơi khác trong bot vẫn hiển thị `.` cứng, chưa tự cập nhật theo.
- `cogs/admin_views.py` — **5 chỗ** khác còn sót `"❌ Chỉ admin."` thiếu `ephemeral=True`
  (Part 1 — v4.25.3 — chỉ bắt được biến thể 1 dòng, bỏ sót biến thể xuống dòng riêng).
  Đã quét lại toàn bộ file bằng script thay vì sửa tay từng dòng, xác nhận hết sạch.

---

## [v4.28.1] — 2026-08-10 — HOTFIX

### 🐛 Sửa lỗi (do chính bản vá trước gây ra — xin lỗi vì lỗi này)
- `cogs/giveaway.py: end_giveaway()` — **giveaway kết thúc mà KHÔNG có bất kỳ thông báo
  nào** (không random winner, không edit embed, không gửi "🎊 Chúc mừng...", không cả
  "❌ không ai tham gia"). Nguyên nhân: fix chống trùng lặp thêm ở v4.27.0 kiểm tra field
  `"ended"` ngay đầu hàm — nhưng CẢ 3 nơi gọi `end_giveaway()` (`_giveaway_timer_task`
  khi hết giờ tự nhiên, `/gend`, dropdown "Kết thúc" trong `/gwlist`) đều TỰ
  `gw["ended"]=True` NGAY TRƯỚC KHI gọi hàm này (coi đó là bước "claim" của riêng họ,
  để hủy task timer đang chờ) — nên field đó LUÔN thấy `True` ngay từ lần gọi đầu tiên,
  hàm return ngay lập tức, 100% mọi giveaway kết thúc đều không thông báo. Đã đổi sang
  dùng marker RIÊNG `"_announce_done"` — chỉ do chính `end_giveaway()` ghi/đọc, không
  đụng cờ `"ended"` mà 3 nơi gọi trên tự quản lý, nhưng vẫn giữ được mục đích gốc: chặn
  2 caller khác nhau lọt qua do có `await` xen giữa lúc check và lúc set ở phía họ.
- `cogs/giveaway.py: .gwreset` — Cũng cập nhật: reset thêm `_announce_done=False`
  (nếu không, giveaway bị stuck do lỗi trên vẫn tiếp tục không thông báo được kể cả sau
  `.gwreset`). **Quan trọng hơn**: trước đây `.gwreset` từ chối thẳng nếu giveaway đã
  quá giờ kết thúc ("❌ ... không thể khôi phục") — nhưng giveaway bị lỗi trên LUÔN đã
  quá giờ (đó chính là lúc bug xảy ra), nên bản cũ không bao giờ cứu được đúng giveaway
  nó sinh ra để cứu. Giờ nếu đã quá giờ, `.gwreset` kích hoạt lại NGAY LẬP TỨC thay vì
  từ chối — giveaway sẽ tự công bố kết quả trong giây lát.
- `cogs/giveaway.py: .gwstatus` — Thêm dấu ⚠️ riêng cho giveaway "ended nhưng có người
  tham gia mà chưa có winner" (nghi bị stuck) — phân biệt rõ với 🔴 (kết thúc bình
  thường), kèm dòng gợi ý `.gwreset <gw_id>` ở phần tổng quan nếu có GW nào đang stuck.

### 📋 Cần làm sau khi cập nhật
Nếu có giveaway nào đã kết thúc (đúng lúc/sau khi v4.27.0 chạy) mà không thấy thông báo
— chạy `.gwstatus`, tìm dòng có dấu ⚠️, rồi chạy `.gwreset <gw_id>` cho từng cái để công
bố lại kết quả đúng.

---

## [v4.28.0] — 2026-08-10

### 🔍 Rà soát toàn bộ codebase — Phần 3/~10: `cogs/admin.py`

### 🐛 Sửa lỗi
- `core/data.py` + `cogs/admin.py` + `cogs/ticket.py` — **`DONE_ROLE_ID` (role "Đã Mua
  Hàng" tự động tặng cho buyer khi hoàn thành đơn) là hằng số hardcode DÙNG CHUNG cho
  MỌI guild**, trong khi role ID trên Discord là duy nhất theo từng server — vi phạm
  đúng nguyên tắc "mỗi server data riêng, không dùng chung". Mọi ID tương tự khác
  (`cfg_ticket_category`, `cfg_support_role`, `cfg_stock_category`...) đều đã được đưa
  vào hệ thống `cfg_*` per-guild từ trước — riêng `DONE_ROLE_ID` bị bỏ sót, tự định
  nghĩa CỤC BỘ giống hệt nhau ở cả `cogs/admin.py` (`_SoldBuyerModal`) LẪN
  `cogs/ticket.py` (`.done`). Hậu quả: với bất kỳ guild nào khác ngoài TuyTam Community,
  `guild.get_role(DONE_ROLE_ID)` luôn trả `None` → tính năng tặng role **im lặng không
  chạy**, không lỗi không log, admin server đó không có cách nào biết hay tự cấu hình.
  Đã thêm `cfg_done_role` (per-guild, default = ID cũ nên TuyTam không đổi hành vi) +
  `get_cfg_done_role()`/`set_cfg_done_role()` ở `core/data.py`, cập nhật cả 2 nơi dùng,
  và thêm lệnh `.donerole [@role]` (admin, alias `.setdonerole`) để mỗi server tự xem/
  đổi role riêng. Dọn luôn `STOCK_CATEGORY_ID`/`SOLD_CATEGORY_ID` khai báo cục bộ ở
  `cogs/admin.py` — dead code, không được dùng ở đâu (logic thật đã dùng đúng
  `get_cfg_stock_category()`/`get_cfg_sold_category()` từ lâu).
- `cogs/admin.py: .backfill` — Vòng lặp đổi tên kênh dùng `channel.edit()` trần + nuốt
  lỗi im lặng (`except Exception: pass`) thay vì cơ chế hàng đợi rate-limit đã có sẵn ở
  `bot.py` (`_next_rename_target`/`_queue_or_rename`, dùng cho +1 legit/vouch thường
  ngày). `.backfill` tồn tại ĐỂ xử lý NHIỀU tin nhắn bị bỏ sót cùng lúc — đúng kịch bản
  dễ dính rate limit Discord nhất (tối đa 2 lần đổi tên kênh / 10 phút). Code cũ khiến
  số đếm trên tên kênh bị hụt dù MỌI tin nhắn đều đã có ✅ (trông như xử lý xong hoàn
  chỉnh nhưng không phải). Đã chuyển sang dùng chung cơ chế hàng đợi, thêm ghi chú ở
  footer embed kết quả để admin biết nếu bị rate limit thì số sẽ tự cập nhật tiếp ở nền.
- `cogs/admin.py: _SoldBuyerModal.on_submit` — đọc `pending["guild_id"]` trực tiếp
  (crash `KeyError` nếu thiếu field, hiện lỗi chung chung "Tương tác thất bại" cho
  admin) thay vì `.get()` an toàn với thông báo rõ ràng như modal chị em
  `_SoldPriceModal.on_submit` đã làm — nay đồng bộ 2 nơi.

### ✅ Đã rà soát kỹ, xác nhận KHÔNG có bug
- Luồng khôi phục guild context trong DM (`_SoldPriceModal`/`_SoldBuyerModal` — cả 2
  đều chạy trong DM admin nên `GuildContextModal` không tự set được context) — đã có
  sẵn code đọc `guild_id` lưu trong pending record và `set_current_guild()` thủ công
  TRƯỚC khi gọi các hàm theo-guild, kèm comment giải thích rõ ràng.
- `add_seller_sale()` không cần tham số `guild_id` riêng vì dựa đúng vào contextvar đã
  được set từ `bot.py: on_message` trước khi gọi `handle_sold()`.
- Rủi ro tạo task escalate trùng lặp ở `resume_pending_sold_views()` (nêu ở v4.27.0)
  đã được đóng hoàn toàn nhờ fix `on_ready()` guard ở Phần 2 — không cần sửa thêm gì
  ở file này.

---

## [v4.27.0] — 2026-08-10

### 🔍 Rà soát toàn bộ codebase — Phần 2/~10: `bot.py` + `verify_server.py`

### 🐛 Sửa lỗi
- `bot.py: on_ready()` — **cùng gốc bệnh "refire mỗi lần reconnect" đã sửa ở
  `init_data_cache()` (v4.25.4), nhưng lần này gây hậu quả trực tiếp hơn nhiều: TẠO
  TASK TRÙNG LẶP.** `on_ready()` gọi hàng loạt hàm "resume 1 lần lúc khởi động" —
  nhưng chạy lại y hệt mỗi lần Discord gateway reconnect (rớt mạng, Railway restart
  container...). Hậu quả xác nhận:
  - `gw_cog.resume_active_giveaways()` tạo THÊM 1 task đếm giờ cho MỖI giveaway đang
    chạy mà không huỷ task cũ → khi hết giờ, **cả 2 task cùng gọi `end_giveaway()`,
    giveaway bị công bố kết thúc + random winner 2 LẦN (có thể ra 2 winner khác nhau)**.
  - `resume_pending_sold_views()` — tạo thêm task escalate cho đơn sold-stock đang chờ
    giá/buyer → ping Ruby trùng lặp.
  - Embed "🔄 Bot Khởi Động" gửi lại vào kênh changelog mỗi lần reconnect → spam.
  Fix: gom toàn bộ các bước "chỉ an toàn chạy 1 lần" vào khối `if first_boot:` (guard
  bằng cờ module-level `_on_ready_first_boot_done`) — chỉ chạy ở lần on_ready đầu tiên
  sau khi PROCESS khởi động, không phải lần đầu sau MỖI reconnect.
  `cache_invites()`/`sync_ticket_counter()` CỐ Ý vẫn chạy mỗi lần refire (an toàn/cần
  thiết — xem docstring trong code).
- `cogs/giveaway.py: end_giveaway()` — Thêm 1 lớp phòng thủ độc lập với fix trên: check
  `gw.get("ended")` NGAY ĐẦU hàm, TRƯỚC KHI set `ended=True` (không phải sau) — nếu
  giveaway đã ended từ trước (gọi lần 2, dù từ đâu tới) thì dừng ngay, không random lại
  winner / không gửi trùng thông báo. Bảo vệ luôn cả những đường gọi trùng khác trong
  tương lai, không riêng bug reconnect ở trên.
- `verify_server.py` + `cogs/invite.py` — **Rò rỉ bộ nhớ ở `_tokens`** (dict token verify
  trong RAM). Token chỉ được dọn khi user THỰC SỰ bấm link verify (`verify_page()` tự
  pop) — nếu user KHÔNG BAO GIỜ bấm (rất phổ biến: tắt DM, lười, offline...), entry nằm
  mãi trong RAM vì không có gì proactively dọn. `invite.py` đã tự dọn dict
  `VERIFY_CALLBACKS` của riêng nó khi hết hạn 10 phút hoặc DM gửi thất bại, nhưng QUÊN
  dọn `_tokens` ở `verify_server.py` — 2 dict lẽ ra cùng vòng đời bị lệch nhau, tích luỹ
  không giới hạn theo số lượt join không verify (bot không tự restart thường xuyên nên
  không tự "reset" định kỳ). Thêm `discard_token()` ở `verify_server.py`, gọi kèm ở cả
  2 chỗ `invite.py` dọn `VERIFY_CALLBACKS`.

### ⚠️ Rủi ro đã rà nhưng CHƯA sửa — cần bạn xác nhận trước khi đổi code
- `verify_server.py` dòng ~113: `ip = request.headers.get("x-forwarded-for", ...).split(",")[0]`
  — lấy IP client từ header `X-Forwarded-For`, vốn là header **client tự set được**
  trừ khi proxy phía trước ghi đè/lọc nó. Toàn bộ hệ thống chống gian lận của bot (chặn
  1 IP nhiều tài khoản, phát hiện VPN, ai được tham gia giveaway) dựa vào IP đọc từ đây
  — nếu header này bị giả mạo được, toàn bộ hệ thống chống gian lận bị vô hiệu hoá.
  Đã tra cứu kỹ (tài liệu chính thức Railway + nhiều thảo luận cộng đồng) nhưng **không
  tìm được câu trả lời chắc chắn** cho hành vi cụ thể hiện tại của Railway với header
  này — tài liệu chính thức không đề cập, các thảo luận cộng đồng MÂU THUẪN nhau (có
  nơi nói Railway lọc sạch giá trị client gửi lên, có nơi nói Railway CHỈ append vào
  cuối chuỗi chứ không lọc — 2 hành vi này cần cách đọc IP HOÀN TOÀN khác nhau, đọc sai
  chiều sẽ khiến verify hỏng thật sự chứ không chỉ là rủi ro lý thuyết). Sửa nhầm chiều
  còn tệ hơn giữ nguyên, nên chưa tự ý đổi code. Cách tự kiểm tra chắc chắn cho đúng
  server của bạn: gửi 1 request có sẵn header `X-Forwarded-For` giả (vd
  `curl -H "X-Forwarded-For: 1.2.3.4" https://<domain-bot-của-bạn>/verify?token=test`)
  rồi xem log của bot in ra IP nào — nếu ra đúng `1.2.3.4` (giá trị giả) thay vì IP thật
  của máy bạn, nghĩa là ĐANG bị giả mạo được, cần đổi sang lấy phần tử cuối
  (`.split(",")[-1]`) thay vì đầu.

---

## [v4.26.0] — 2026-08-10

### ✨ Tính năng mới
- Lệnh `.gwverify` (alias `.gwvr`/`.gwverifyreq`, admin only) — **bật/tắt** yêu cầu
  xác minh (role Verify) mới được bấm 🎉 Tham gia giveaway. Trước đây check này BẮT
  BUỘC, hardcode luôn bật trong `GiveawayView.join()` — giờ mỗi server tự chọn bật/tắt
  qua 1 lệnh, mặc định **giữ nguyên hành vi cũ (BẬT)** nên không phá server đang chạy.
  Lưu qua `cfg_giveaway_require_verify` trong data riêng của guild (không ảnh hưởng
  server khác) — `get_cfg_giveaway_require_verify()`/`set_cfg_giveaway_require_verify()`
  ở `core/data.py`. TẮT chỉ bỏ check verify — check IP trùng (chống 1 người nhiều tài
  khoản) vẫn giữ nguyên không đổi theo.
- `cogs/admin.py` — Cập nhật `.help giveaway` (embed lệnh) + mục `.help` tổng quan để
  liệt kê `.gwverify`.

---

## [v4.25.4] — 2026-08-10

### 🔍 Rà soát toàn bộ codebase — Phần 1/~10: `core/data.py`
Bắt đầu rà soát có hệ thống toàn bộ code (chia nhỏ theo từng phần, không dồn 1 lần).
Phần 1 là `core/data.py` — nền tảng cache/guild-isolation mà mọi cog khác phụ thuộc vào.

### 🐛 Sửa lỗi
- `core/data.py` — **`init_data_cache()` reset sạch cache mỗi lần `on_ready()` refire —
  ăn vào MỌI data, không riêng ủy quyền.** Cùng gốc với bug `.as` đã sửa ở v4.25.1, nhưng
  hoá ra nghiêm trọng hơn nhiều: `on_ready()` KHÔNG chỉ chạy 1 lần lúc khởi động — Discord
  gateway reconnect (rớt mạng, Railway restart, session bị Discord invalidate...) khiến nó
  refire bất cứ lúc nào. Bản cũ unconditionally reset `_data_cache`/`_global_cache`/
  `_giveaways_cache = {}` rồi load lại từ Mongo MỖI LẦN refire — bất kỳ `save_data()`/
  `save_global_data()` nào vừa update RAM xong nhưng task ghi Mongo nền chưa kịp hoàn tất
  (giá, danh sách seller, invite count, ticket note, QR...) đều bị xoá sạch khỏi cache nếu
  đúng lúc đó có 1 lần reconnect. Đã sửa: chỉ full-load ở lần gọi ĐẦU TIÊN; các lần refire
  sau chỉ nạp thêm guild MỚI (phòng bot được mời lúc mất kết nối), giữ nguyên cache cũ.
- `core/data.py` — **`get_ticket_number()` có thể sinh trùng số ticket dưới tải đồng thời.**
  Cache được cập nhật SAU `await col.update_one(...)` — trong lúc chờ Mongo (1 điểm yield),
  1 coroutine khác load_data() (đọc số ticket CŨ vì cache chưa kịp cập nhật) rồi save_data()
  sẽ ghi đè NGUYÊN cache guild đó bằng bản có số cũ, làm cache "tụt" lại → lần tạo ticket kế
  tiếp sinh trùng số. Đã chuyển việc cập nhật cache lên TRƯỚC điểm `await`, đóng cửa sổ race.
- `core/data.py` — `get_ticket_number()` dùng 1 `asyncio.Lock` DUY NHẤT cho MỌI guild, khiến
  2 server tạo ticket cùng lúc phải xếp hàng chờ nhau dù chẳng liên quan — đi ngược đúng mục
  tiêu multi-guild. Đổi sang 1 lock riêng mỗi guild (`_get_ticket_lock(guild_id)`), giống
  pattern `_save_locks` đã dùng cho việc ghi Mongo.

### 📌 Lưu ý cho phần sau (chưa sửa ở bản này)
- `bot.py: on_ready()` cũng chạy lại các bước "1 lần" khác mỗi lần refire (gửi lại embed
  "Bot Khởi Động" vào kênh changelog, `bot.add_view()` ×4, sync slash command...) — sẽ rà ở
  phần audit `bot.py` (Part 2), không sửa chung vào bản này để tránh 1 lần đổi quá nhiều file.

---

## [v4.25.3] — 2026-08-10

### 🐛 Sửa lỗi
- `cogs/admin_views.py` — **AUTH_GATE bị vô hiệu hoá ở đúng View quan trọng nhất: `.setup`
  (`SetupMainView`), `MkChannelView`, `_PageView`**. 3 class này TỰ OVERRIDE
  `interaction_check()` và gọi `set_current_guild()` trực tiếp thay vì gọi
  `super().interaction_check()` — nghĩa là chúng vô tình **che mất** luôn phần kiểm tra
  `is_guild_authorized()` vừa thêm ở `GuildContextView` (v4.25.2). Hậu quả: nếu `.setup`
  được mở lúc server còn ủy quyền, sau đó admin `.as` thu hồi ủy quyền trong lúc panel
  đó vẫn còn hiệu lực (chưa hết 180s timeout), các nút/select bên trong **vẫn bấm được
  bình thường** — xuyên thủng AUTH_GATE ngay tại panel setup chính. Đã sửa cả 3: gọi
  `await super().interaction_check(interaction)` TRƯỚC (set context + áp AUTH_GATE),
  chỉ cộng thêm điều kiện riêng (admin-only / đúng người gõ lệnh) sau khi super() pass.
  `EmbedPreviewView` (dòng ~2415) đã làm đúng kiểu này từ đầu, không cần sửa.
- `cogs/admin_views.py` — Dọn import `set_current_guild` không còn dùng tới (toàn bộ
  override giờ set context gián tiếp qua `super()`).
- `cogs/admin_views.py` — **7 chỗ** cảnh báo `"❌ Chỉ admin."` thiếu `ephemeral=True`,
  khiến tin nhắn từ chối quyền hiển thị **công khai cho cả kênh** thay vì chỉ người bấm
  thấy (không nhất quán — các cảnh báo tương tự khác trong cùng file đều đã ephemeral
  đúng). Gồm `SetupMainView.interaction_check()` (dòng ~762, đúng panel `.setup`),
  `PriceManagerView` (×3, nút Thêm/Xoá/Reset bảng giá), kênh-config select callback
  trong `SettingsView` (×1), và 2 chỗ khác cùng pattern. Đã thêm `ephemeral=True` cả 7.

### 📌 Bài học (ghi lại cho lần sau)
- BẤT KỲ View/Modal nào override `interaction_check()` (để thêm điều kiện riêng như
  admin-only, đúng người gõ lệnh...) **BẮT BUỘC** phải gọi
  `if not await super().interaction_check(interaction): return False` ĐẦU TIÊN, không
  được tự ý copy lại logic `set_current_guild()` rồi bỏ qua phần còn lại của lớp cha —
  lớp cha (`GuildContextView`/`GuildContextModal`) có thể được thêm logic quan trọng
  (như AUTH_GATE) sau này mà các override cũ sẽ không tự động thừa hưởng.

---

## [v4.25.2] — 2026-08-10

### 🐛 Sửa lỗi
- `core/data.py` — **Lỗi nghiêm trọng nhất trong đợt AUTH_GATE**: `GuildContextView`/
  `GuildContextModal` (dùng bởi `TicketPanel`, `TicketButtons`, `MiddlemanPanelView`,
  `GiveawayView`, toàn bộ UI `.st`/settings...) chỉ tự set guild context, **KHÔNG hề
  kiểm tra `is_guild_authorized()`**. Hậu quả: prefix command (`.command`) và slash
  command đã bị AUTH_GATE chặn đúng ở server chưa/hết ủy quyền, nhưng **nút bấm/select/
  modal của các panel đã đăng từ trước (persistent View, `bot.add_view()` ở `on_ready`)
  vẫn hoạt động bình thường** dù server đó bị `.as` thu hồi ủy quyền — vì Discord gửi
  thẳng interaction đến View đã đăng ký, không đi qua `bot.check`/`CommandTree.
  interaction_check` như lệnh gõ chữ/slash. Đã thêm kiểm tra `is_guild_authorized()`
  vào `interaction_check()` của cả 2 class — chặn + báo (ephemeral, chỉ admin) tương tự
  slash command khi server chưa ủy quyền.
- `bot.py` — Dọn tham chiếu chết tới lệnh `.aslist` (không còn tồn tại — đã gộp hiển thị
  trạng thái ủy quyền vào `.serverlist` từ v4.25.0) trong `AUTH_EXEMPT_COMMANDS` + docstring.

### ⚠️ Lưu ý (không phải bug, nhắc để tránh nhầm)
- `.as <id>` là lệnh **toggle** — gõ lần 2 trên cùng 1 server sẽ **THU HỒI** ủy quyền
  thay vì chạy lại/xác nhận lại. Muốn xem trạng thái hiện tại trước khi bấm, dùng
  `.serverlist` (hiện ✅/🔒 từng server) thay vì đoán rồi gõ `.as` lại cho chắc.

---

## [v4.25.1] — 2026-08-10

### 🐛 Sửa lỗi
- `core/data.py`, `cogs/admin.py` — `.as <guild_id>` báo ỦY QUYỀN thành công nhưng lệnh
  ngay sau đó vẫn bị chặn "chưa được ủy quyền". Nguyên nhân: `add_authorized_guild()`/
  `remove_authorized_guild()` ghi Mongo qua `save_global_data()` — chạy nền
  (`loop.create_task`, fire-and-forget). Discord gateway reconnect có thể khiến
  `on_ready()` refire bất cứ lúc nào (không chỉ 1 lần lúc khởi động) và
  `init_data_cache()` unconditionally RESET `_global_cache` từ Mongo — nếu refire xảy
  ra trước khi task ghi nền kịp hoàn tất, ủy quyền vừa bật bị mất dù bot đã báo
  thành công. Thêm `set_guild_authorized(guild_id, bool)` (async, `.as` giờ `await`
  hàm này) — ghi thẳng xuống Mongo và đợi xong TRƯỚC KHI gửi embed xác nhận, đảm bảo
  chắc chắn đã lưu, không còn phụ thuộc task nền.

---

## [v4.25.0] — 2026-08-10

### ✨ Tính năng mới
- `core/data.py` — Thêm hệ thống **ủy quyền server (AUTH_GATE)**: `get_authorized_guilds()`, `is_guild_authorized()`, `add_authorized_guild()`, `remove_authorized_guild()` — lưu ở global data (`_id: "main"`, key `_authorized_guilds`), không thuộc riêng guild nào.
- `cogs/admin.py` — Lệnh `.as <guild_id>` (alias `.authorize`/`.uyquyen`, admin only): **toggle** ủy quyền cho 1 server — không truyền `guild_id` thì áp dụng luôn cho server đang gõ lệnh. Dùng được cả qua DM bot (không cần đang ở trong server đó), tiện cho Ruby ủy quyền server mới chỉ bằng ID.
- `bot.py` — Server **CHƯA được ủy quyền** thì bot không chạy bất kỳ lệnh `.command`/slash command nào, cũng bỏ qua toàn bộ tính năng tự động (auto-sold, AI channel, legit/vouch) ở server đó:
  - `_global_guild_authorization_check()` — global `bot.check` chặn mọi lệnh prefix, trừ `.as`/`.aslist`.
  - `GuildContextTree.interaction_check()` — chặn slash command tương tự (báo ephemeral cho admin).
  - `on_message` — bỏ qua auto-sold/AI channel/legit-vouch nếu guild chưa ủy quyền.
  - `on_guild_join` — bot vẫn tự load cache riêng cho guild mới (không đổi), nhưng giờ DM ngay cho `ADMIN_IDS` báo server mới CHƯA được ủy quyền + hướng dẫn `.as <id>`.
- `cogs/invite.py`, `cogs/mod.py`, `cogs/ticket.py`, `cogs/ai_chat.py`, `cogs/message_search.py` — thêm gate `is_guild_authorized()` ở đầu các listener chạy Task riêng (`on_member_join`, `on_member_remove`, automod `on_message`, ticket relay `on_message`, AI forum-reply `on_message`, AI search-index `on_message`) — các listener này KHÔNG đi qua `bot.py: on_message` nên phải tự chặn riêng, tương tự cách chúng đã tự `set_current_guild()` (xem AI_CONTEXT.md mục Multi-guild).
- `cogs/invite.py` — `.serverlist`/`.servers`/`.guildlist` giờ hiển thị thêm trạng thái ✅ Đã ủy quyền / 🔒 CHƯA ủy quyền cho từng server, kèm tổng số server đã ủy quyền ở title.
- `cogs/admin.py` — Mục `.help invite` (phần "🌐 Quản lý server bot") — cập nhật mô tả `.serverlist` + thêm hướng dẫn lệnh `.as`.

---

## [v4.23.2] — 2026-08-05

### 🐛 Sửa lỗi
- `cogs/admin_views.py` — `.settings`/`.st` → nút "🎫 Ticket Roles" chưa có **Ruby Shop** trong danh sách chọn (chỉ `.setrole rubyshop @role` bằng lệnh gõ chữ mới gán được, UI bấm nút thì không thấy). Đã thêm `rubyshop` vào `_TICKET_GROUPS` (dropdown chọn loại ticket) và `_build_ticket_roles_embed` (bảng hiển thị role hiện tại) — giờ gán role Ruby Shop qua nút bấm trong `.st` cũng được, không bắt buộc phải gõ `.setrole` nữa.

---

## [v4.23.1] — 2026-08-05

### ✨ Cải tiến
- `cogs/ticket.py`, `core/data.py` — `.rubyoption`/`.rbopt`:
  - Thêm thao tác **`edit <tên cũ> -> <tên mới>`** để đổi tên 1 dịch vụ Ruby Shop mà không mất vị trí trong danh sách (chặn trùng tên với lựa chọn khác).
  - Hỗ trợ **gộp nhiều thao tác trong 1 lệnh**, phân tách bằng dấu phẩy: `.rbopt add A, add B, remove C, edit D -> E`. Mỗi thao tác báo kết quả riêng (✅/⚠️/❌/✏️/🗑️), lỗi ở 1 thao tác không chặn các thao tác còn lại.

---

## [v4.23.0] — 2026-08-05

### ✨ Tính năng mới
- `cogs/ticket.py`, `core/data.py` — Thêm loại ticket **💎 Ruby Shop** vào panel. Trước khi ticket được tạo, bot hỏi user cần hỗ trợ dịch vụ gì qua Select menu — danh sách lựa chọn **không hardcode trong code**, admin/staff tự quản lý bằng lệnh:
  - `.rubyoption add <tên>` (alias `.rbopt`) — thêm 1 lựa chọn (tối đa 25, giới hạn Select menu của Discord)
  - `.rubyoption remove <tên>` — xoá 1 lựa chọn
  - `.rubyoption list` — xem danh sách hiện tại
  - Nếu chưa có lựa chọn nào, bot báo cho user biết thay vì tạo ticket trống.
  - `.setrole rubyshop @role` — gán role xử lý ticket Ruby Shop (dùng chung hệ thống multi-role sẵn có, `.listroles` cũng hiển thị).
  - Ticket tạo ra ghi rõ dịch vụ user đã chọn trong embed + log audit (`TICKET_CREATE`).
  - Nút Ruby Shop có thể bật/tắt riêng qua `.panelbuttons` như các nút khác.

---

## [v4.22.0] — 2026-08-03

### ✨ Tính năng mới
- `cogs/admin.py`, `cogs/admin_views.py`, `core/data.py` — `.embed [#kênh] [everyone|here]` (alias `.thongbao`/`.announce`) và `/embed` — gửi thông báo dạng embed, nội dung (tiêu đề/mô tả/màu hex/ảnh lớn/thumbnail/footer) do người dùng tự nhập qua Modal ngay lúc dùng lệnh thay vì cố định trong code. `.embed` gửi kèm nút "📝 Soạn nội dung" (lệnh gõ chữ không có sẵn interaction để mở Modal thẳng), `/embed` mở Modal ngay lập tức.
  - Quyền: **staff** (`is_staff_member`) soạn/gửi được; ping `@everyone`/`@here` chỉ dành cho **ADMIN_IDS** (staff thường vẫn gửi được nhưng không kèm ping, có cảnh báo).
  - **Xem trước (preview)**: sau khi soạn, bot không gửi ngay mà hiện bản xem trước dạng ephemeral (chỉ người soạn thấy) kèm 3 nút — 📤 Gửi thật vào kênh / ✏️ Sửa lại (mở lại Modal, giữ nguyên nội dung cũ để chỉnh tiếp) / ❌ Huỷ. Chỉ người bấm nút mới thao tác được trên bản xem trước của chính mình. Áp dụng cho cả `.embeduse`/`/embeduse` (gửi mẫu) — sửa tạm trước khi gửi không ảnh hưởng tới mẫu đã lưu.
  - **`.embedimport`/`/embedimport`**: đính kèm 1 file `.json` dạng `{"tên_mẫu": {title, description, color, image, thumbnail, footer}}` — bot tự lưu thẳng vào MongoDB qua kết nối đang chạy sẵn (không cần restart, không cần script rời).
  - **Lưu mẫu**: sau khi bấm 📤 Gửi thành công, có nút "💾 Lưu làm mẫu" đặt tên và lưu lại nội dung vào DB theo server để dùng lại nhiều lần qua `.embeduse <tên>` / `/embeduse` (không cần soạn lại từ đầu). `.embedlist`/`/embedlist` xem danh sách, `.embeddel`/`/embeddel` xoá mẫu.
  - Có log audit vào kênh log nhóm `admin` mỗi lần gửi.

---

## [v4.21.0] — 2026-07-27

### ♻️ Thay đổi
- `cogs/listings.py: ListingView` — **Đổi hướng xử lý nút trạng thái sản phẩm** sau nhiều lần vá không dứt điểm được lỗi ảnh tách/mất khi edit embed có đính kèm ảnh (v4.20.1 → v4.20.6). Từ nay bấm 🟢 Chưa bán/🔴 Đã bán **chỉ đổi label + màu của nút** (và khoá/mở nút 🛒 Mua) — **không đụng tới embed hay ảnh đính kèm nữa** (trước đây còn đổi cả màu viền embed theo trạng thái). Vì không còn edit embed/attachment nên né hoàn toàn nhóm lỗi Discord tách/mất ảnh khi edit — đổi lại, embed không còn đổi màu xanh/đỏ theo trạng thái (chỉ còn nút thể hiện).
- `cogs/listings.py: toggle_btn/buy_btn` — Đọc đúng trạng thái "đã bán" từ `interaction.message.components` (dữ liệu thật của đúng tin nhắn bị bấm) thay vì từ `embed.color` hay từ `self.children`/`button` (object dùng CHUNG cho mọi bài đăng vì đây là persistent view — dùng sai sẽ lẫn trạng thái giữa các sản phẩm khác nhau khi có nhiều bài đăng cùng lúc).

---

## [v4.20.6] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/listings.py: ListingView.toggle_btn` — Xác nhận qua test trên Discord Mobile: lỗi dư 1 file đính kèm nằm phía TRÊN embed chỉ xảy ra ở lần bấm đầu, bấm lần 2 (chiều ngược lại) thì tự hết — cho thấy 2 bước edit (xoá trắng → gắn file mới, thêm ở v4.20.5) chạy quá sát nhau khiến Discord xử lý chưa kịp (race condition). Thêm `await asyncio.sleep(0.6)` giữa 2 bước để đảm bảo Discord xử lý xong việc xoá đính kèm cũ trước khi request gắn file mới được gửi.

---

## [v4.20.5] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/listings.py: ListingView.toggle_btn` — Xác nhận: sau khi đổi trạng thái, embed hiện ảnh đúng NHƯNG vẫn còn dư 1 file ảnh cũ nằm ngoài embed — tức `attachments=[file]` (v4.20.4) không thay thế sạch được attachment cũ như kỳ vọng. Sửa bằng cách ép edit **2 bước**: bước 1 gọi `edit_original_response(attachments=[])` xoá trắng toàn bộ đính kèm hiện có, bước 2 mới `edit_original_response(embed=..., attachments=[file mới])` để gắn ảnh vào — đảm bảo không thể còn sót file cũ vì đã bị xoá sạch trước khi thêm file mới.

---

## [v4.20.4] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/listings.py: ListingView.toggle_btn` — v4.20.3 vẫn còn tách ảnh dù đã re-upload lại file, dù log không báo lỗi gì. Nguyên nhân nghi vấn: `interaction.response.edit_message()` phải phản hồi trong 3 giây, nhưng bước `fetch_message()` + tải lại bytes ảnh (`to_file()`) rồi mới edit có thể vượt quá 3s (hoặc endpoint UPDATE_MESSAGE xử lý multipart upload không ổn định) → Discord fallback hiển thị sai mà không throw exception rõ ràng ở phía bot. Đổi sang `interaction.response.defer()` ack ngay lập tức, rồi `interaction.edit_original_response()` (endpoint followup, có thời gian xử lý dài hơn nhiều — token hợp lệ 15 phút thay vì 3 giây) để thực hiện phần tải/upload lại ảnh + đổi embed.

---

## [v4.20.3] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/listings.py: ListingView.toggle_btn` — Sửa đúng gốc lỗi ảnh tách ra ngoài embed (v4.20.1/v4.20.2 mới chỉ chặn được việc mất ảnh, chưa hết tách ảnh): Discord chỉ giữ ảnh "thuộc về" embed (không hiện thành file rời bên dưới) khi embed dùng `attachment://<file>` **và** file đó được **re-upload lại trong cùng request edit**. Bản trước chỉ giữ nguyên `Attachment` cũ (không kèm file mới) → Discord coi ảnh là 2 thứ tách biệt: link ảnh trong embed + file đính kèm cũ hiện riêng. Nay tải lại ảnh cũ qua `Attachment.to_file()` và up lại kèm mỗi lần bấm 🟢/🔴, đảm bảo ảnh luôn nằm đúng trong embed như lúc mới đăng.

---

## [v4.20.2] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/listings.py: ListingView.toggle_btn` — Fix v4.20.1 (`attachments=interaction.message.attachments`) gây **mất ảnh hoàn toàn** thay vì tách khỏi embed: `interaction.message` (lấy từ cache interaction) đôi khi trả về danh sách `attachments` rỗng dù ảnh vẫn tồn tại trên message thật, nên truyền `attachments=[]` rỗng khiến Discord xoá ảnh khi edit. Sửa bằng cách `fetch_message()` lại message đầy đủ trước khi edit để lấy đúng attachments thật, và chỉ truyền tham số `attachments` khi danh sách đó không rỗng (nếu rỗng thì bỏ qua tham số, để Discord tự giữ nguyên như mặc định thay vì ép xoá).

---

## [v4.20.1] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/listings.py: ListingView.toggle_btn` — Ảnh preview bị "tách" ra khỏi embed, hiện như file đính kèm rời bên dưới tin nhắn sau khi bấm nút 🟢/🔴 đổi trạng thái. Nguyên nhân: `interaction.response.edit_message()` không khai báo lại `attachments` hiện có, khiến Discord huỷ liên kết giữa ảnh và vị trí `image` trong embed dù ảnh không mất. Sửa bằng cách truyền `attachments=interaction.message.attachments` mỗi lần edit để giữ đúng liên kết.
- `cogs/ticket.py: create_listing_ticket` — Role gán ở `.st` → Vai trò ticket → nhóm **🤖 Auto Buy** (`listing_manage`) không tự động thấy được kênh ticket khi khách bấm 🛒 Mua, vì kênh ticket chỉ đọc role ở nhóm **🛒 Mua Sản Phẩm (Listing)** (`listing`) riêng biệt. Nay ticket cộng gộp role từ **cả 2 nhóm** — chỉ cần gán role ở 1 trong 2 mục (hoặc cả 2) đều được thấy ticket.

---

## [v4.20.0] — 2026-07-27

### ✨ Tính năng mới
- `cogs/admin_views.py` — Thêm nhóm role mới **"🤖 Auto Buy"** trong `.st` → Vai trò ticket (key Mongo `listing_manage`, dùng chung cơ chế `_RolePickerView` với role ticket) — admin gán role được phép **đăng/sửa listing** (tách riêng khỏi role nhận ping khi có ticket mua, vốn đã có ở nhóm `listing`).
- `cogs/listings.py` — `can_manage_listing()`: quyền đăng/toggle listing giờ = `is_staff_member()` **HOẶC** có 1 trong các role vừa gán ở mục Auto Buy — không còn giới hạn chỉ staff/seller mặc định.

### ♻️ Thay đổi
- `cogs/listings.py: addlisting_cmd` — `#kênh` giờ nhận cả **kênh Text thường** lẫn kênh Forum (trước đây bắt buộc Forum). Kênh Forum → vẫn tạo thread như cũ; kênh Text → gửi thẳng tin nhắn listing vào kênh.
- `cogs/ticket.py: create_listing_ticket` — đổi tham số `source_thread: Thread` → `source_link: str`, để ticket "🔗 Listing gốc" hiển thị đúng cả 2 trường hợp: mention thread (Forum) hoặc link tin nhắn gốc (Text, qua `jump_url`) thay vì bị bỏ trống khi đăng ở kênh Text.

---

## [v4.19.2] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/admin.py` — `.help` chưa liệt kê các lệnh mới của v4.19.0: `.bxh`/`.leaderboard`/`.top`, `.addlisting`, `.shoporderno`. Bổ sung vào mục `shoporders` (đổi tên hiển thị thành "Shop Orders (VietQR) & Bảng xếp hạng") và tạo mục mới `listings` (🛒 Sản phẩm) mô tả `.addlisting`, 2 nút trên bài đăng, và cách gán role ping riêng qua `.st`. Cập nhật cả embed tổng quan (`.help` không tham số) và alias (`.help bxh`, `.help listing`, `.help sanpham`, `.help forum` đều dẫn đúng mục).

---

## [v4.19.1] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/shop_orders.py` — **Hóa đơn công khai hiện sai số tiền.** `build_queue_embed()` ghi field "💰 Số tiền" bằng `fmt_amount()` (dạng rút gọn, vd `150000` → `"150k"`), sau đó `ReceiptProductModal.on_submit` đọc lại field đó bằng `_extract_amount_digits()` (strip mọi ký tự không phải chữ số) → chữ `k`/`tr` bị mất, `"150k"` chỉ còn lại `"150"` → hóa đơn gửi vào kênh proof hiện **150 VNĐ thay vì 150,000 VNĐ**. Thêm `fmt_vnd()` (định dạng đầy đủ `"150,000 VNĐ"`, không rút gọn — khớp đúng định dạng ảnh hóa đơn mẫu) và dùng nó ở cả `build_queue_embed()` lẫn `build_receipt_embed()` thay cho `fmt_amount()`, đảm bảo số tiền đọc lại từ embed luôn khớp 100% với số tiền gốc.

### ♻️ Thay đổi
- `cogs/admin_views.py` — Thêm loại ticket `listing` (🛒 Mua Sản Phẩm) vào danh sách gán role ping trong `.st` → Vai trò ticket, để admin cấu hình được role nhận ping khi khách bấm nút Mua trên 1 bài đăng sản phẩm (`cogs/listings.py`) — trước đó loại ticket này luôn fallback về support role mặc định, không cấu hình riêng được.

---

## [v4.19.0] — 2026-07-27

### ✨ Tính năng mới
- `cogs/shop_orders.py` — **Hóa đơn thanh toán công khai**: khi staff bấm ✅ Hoàn thành trên đơn hàng trong kênh hàng đợi, bot hỏi tên/mã sản phẩm qua modal rồi tự dựng hóa đơn (`build_receipt_embed`, có số hóa đơn tăng dần theo guild, nội dung CK tự sinh) và gửi vào kênh Proof Channel (cấu hình sẵn qua `.st`) — theo đúng format hóa đơn mẫu ViceVN.
- `cogs/shop_orders.py: leaderboard_cmd` — Lệnh `.bxh` (alias `.leaderboard`/`.top`): bảng xếp hạng top 10 chi tiêu nhiều nhất trong server, đọc từ `user_total_spent` đã có sẵn (được cộng dồn mỗi khi `.done`).
- `cogs/listings.py` (mới) — **Đăng sản phẩm dạng Forum**: lệnh `.addlisting #forum "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]` tạo 1 thread sản phẩm trong kênh forum kèm ảnh preview (nếu đính kèm) + 2 nút: 🟢 Chưa bán/🔴 Đã bán (toggle, staff/seller) và 🛒 Mua (khách bấm → tạo ticket mua qua `create_listing_ticket()` ở `cogs/ticket.py`, thông tin sản phẩm được copy sẵn vào ticket).

---

## [v4.18.0] — 2026-07-27

### 🐛 Sửa lỗi
- `cogs/ticket.py: done_cmd` + `/done` — `.done` từng CRASH ngay khi chạy (trước cả khi gửi embed xác nhận) do `from cogs.admin import auto_give_buy_roles` sai module — hàm thật nằm ở `cogs/admin_views.py`. Sửa lại đúng import ở cả 2 chỗ (prefix command + slash command)
- `core/data.py` — Luồng admin TuyTam/Ruby nhập giá đơn sold thủ công qua DM (`_SoldPriceModal`) không hoạt động đúng: `pending_sold_price`/`resolved_sold_price` lưu theo-guild nhưng Modal/View chạy trong DM luôn có `interaction.guild_id = None` nên không set được guild context → `load_data()` đọc nhầm/rỗng. Chuyển 2 bảng này (+ `pending_sold_buyer` mới) sang `load_global_data()`/`save_global_data()` — không cần guild context để đọc, nơi gọi tự `set_current_guild(pending["guild_id"])` khi cần thao tác data theo-guild (add_seller_sale, add_user_spent, auto_give_buy_roles...)

### ✨ Tính năng mới
- `cogs/shop_orders.py: build_payment_qr_embed` — Khi `.done` gọi mà ngân hàng CHƯA cấu hình đủ (thiếu `.shopbank`), bot vẫn bỏ qua gửi QR như trước nhưng giờ có in log console (`log.warning`) để admin biết vì sao QR không gửi. Giá đơn hàng vẫn được lưu bình thường, không phụ thuộc vào QR
- `cogs/admin.py` — Sold-stock (`stock` → `sold`) giờ hỏi thêm admin TuyTam **tài khoản Discord nào đã mua** để cộng tiền cho đúng buyer (giống hệt lệnh `.done`: `add_user_spent` + `auto_give_buy_roles` + tặng role "Đã Mua Hàng"), thay vì trước đây chỉ ghi thống kê doanh số cho seller:
  - Nếu đọc được giá từ tên kênh → ghi thống kê seller như cũ, sau đó DM ngay admin TuyTam hỏi người mua (`_SoldBuyerModal`/`_SoldBuyerView`)
  - Nếu KHÔNG đọc được giá từ tên kênh → vẫn DM admin TuyTam nhập giá thủ công như cũ (`_SoldPriceModal`); sau khi nhập giá xong, bot tự động hỏi tiếp người mua ngay trong cùng luồng
  - Đăng ký lại persistent view cho cả 2 loại DM (giá + buyer) sau khi bot restart (`resume_pending_sold_views`)

## [v4.17.0] — 2026-07-26

### 🐛 Sửa lỗi
- `bot.py: on_message` — Bot crash-log khi có người **nhắn DM** cho bot: `'DMChannel' object has no attribute 'name'` trong `_handle_legit()` + cảnh báo `load_data() KHÔNG có guild context` (do `set_current_guild()` không được gọi khi `message.guild` là None nhưng các handler auto-sold/AI-chat/legit/vouch vẫn chạy tiếp). Thêm `if not message.guild: return` ngay sau `process_commands()` — các tính năng chỉ dành cho server giờ tự bỏ qua DM, lệnh prefix trong DM vẫn hoạt động bình thường

### ✨ Tính năng mới
- `core/rag.py` — Fallback tìm kiếm khi **Voyage AI lỗi/hết quota (429)**: thêm `_keyword_fallback_search()` so khớp từ khoá thô trong Mongo (không cần Atlas Vector Index) khi `get_embedding()` trả `None`. `get_relevant_context()` nhận diện kết quả fallback (không cùng thang điểm với cosine similarity) và đưa cảnh báo vào prompt để Groq tự đánh giá độ liên quan trước khi dùng, thay vì AI chat mất hẳn khả năng tra RAG mỗi khi Voyage bị giới hạn rate

---

## [v4.16.0] — 2026-07-23

### 🐛 Sửa lỗi
- **Log messages ping nhầm user thật** — `send_log()` gửi dạng plain text (không phải embed), nên mọi field trước đây dùng `.mention` (user/member) thực chất LÀ ping thật, không chỉ hiển thị. Đổi toàn bộ sang username (`_uname_plain()`) trong 7 file: `admin.py`, `ai_chat.py`, `giveaway.py`, `mod.py`, `shop_orders.py`, `ticket.py`. Mention kênh (`#channel`) giữ nguyên vì không gây ping
- `cogs/logger.py` — thêm `_depinged()` làm lớp phòng vệ cuối: tự động vô hiệu hoá mention user/role còn sót lọt vào field log (chèn zero-width space sau `<@`/`<@&`), phòng trường hợp code sau này lỡ quên sửa

### ✨ Tính năng mới
- `.botinfo` — thêm uptime, health-check MongoDB (🟢/🔴), RAM đang dùng (`psutil`), số cogs/lệnh đã load
- `.serverinfo` — thêm boost level + số boost, verification level, tổng role, tổng emoji, tách kênh theo loại (text/voice/forum/thread)
- `.userinfo` — thêm role cao nhất, trạng thái boost server, trạng thái timeout, badge admin/staff/owner, cảnh báo tài khoản mới tạo <7 ngày (hữu ích soi invite ảo)
- `.invitetop` — field riêng cho Top 3 (breakdown đầy đủ verify/chờ/fake/rời), dòng tổng kết net toàn server ở đầu embed
- `.ipstats` — gộp thành 1 tin nhắn + nút ◀ ▶ phân trang (trang đầu là tóm tắt tổng quan), thay vì gửi nhiều embed rời rạc thành nhiều tin nhắn như trước

### ♻️ Thay đổi
- Thêm `psutil>=5.9.0` vào `requirements.txt` (cần cho RAM ở `.botinfo`)

---

## [v4.15.0] — 2026-07-22

### ✨ Tính năng mới — Multi-agent (ý #8 trong roadmap AI)
- `core/ai_agents.py` (mới) — đăng ký 3 "agent" AI chuyên biệt: `support` (tra cứu khách hàng), `ops` (điều hành server), `report` (báo cáo số liệu — stub, chờ ý #17). Mỗi agent chỉ mang system prompt + tool subset riêng thay vì nhồi hết tool vào 1 lần gọi model
- `.ai` — thêm 1 bước router nhẹ (1 lần gọi Groq, không kèm tool, temperature=0) phân loại yêu cầu admin vào đúng agent trước khi chạy tool-calling thật, giúp model chọn tool chính xác hơn khi số lượng tool tăng

### ♻️ Thay đổi
- `cogs/ai_chat.py` — `run_ai_tools_agent()` đổi signature: nhận thẳng `system_prompt` + `tools` thay vì cờ `is_admin`, dùng chung 1 vòng lặp cho mọi agent

---

## [v4.14.0] — 2026-07-22

### 🐛 Sửa lỗi
- Groq đã deprecate `llama-3.1-8b-instant` + `llama-3.3-70b-versatile` (shutdown 16/08/2026); `gemma2-9b-it` (fallback thứ 2 trong `GROQ_MODELS`) đã ngừng hoạt động từ 08/10/2025 — nghĩa là fallback cuối cùng thực ra không hoạt động từ lâu. Đổi `GROQ_MODELS` sang `openai/gpt-oss-20b` (chính) / `openai/gpt-oss-120b` (fallback) — cả 2 đều hỗ trợ native tool calling
- Xoá `AI_EXEC_SYSTEM`/`_call_groq_exec`/`_call_groq_clarify`/`_call_groq_fill`/`_run_action` trong `ai_chat.py` — hệ thống prompt-JSON tự chế cũ **chưa từng được gọi ở đâu** (dead code, không có lệnh nào trigger được nó) và một số action còn trỏ lệnh **không tồn tại** trong bot (`ticketpanel`, `gend`, `greroll`)

### ✨ Tính năng mới — Function calling (ý #1 trong roadmap AI)
- `core/ai_tools.py` (mới) — 19 tool cho AI dùng native tool calling của Groq: 4 query tool (khách hàng tự tra ticket/seller/invite/lịch sử mua hàng của chính họ) + 15 admin tool (kênh/role/mod/ticket/giveaway)
- Lệnh mới `.ai <yêu cầu>` (admin) — điều khiển bot bằng ngôn ngữ tự nhiên qua tool calling, có xác nhận bằng nút bấm cho hành động nguy hiểm (ban/kick/mute/xoá kênh/xoá role/purge)
- Kênh AI chat: khách hàng giờ có thể hỏi AI tự tra cứu ticket/seller/invite/lịch sử mua hàng của chính họ thay vì AI chỉ đoán

---

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
