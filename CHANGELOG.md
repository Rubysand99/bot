# CHANGELOG — TuyTam Bot (Rudeus Bot)

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
