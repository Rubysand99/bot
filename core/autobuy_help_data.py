"""
core/autobuy_help_data.py — Nội dung hướng dẫn `.help autobuy` (thuần dữ liệu, không import discord để test được).

7 trang, mỗi trang là 1 embed (giới hạn Discord: field ≤ 1024 ký tự, tên field ≤ 256, tổng embed ≤ 6000, ≤ 25 field).
Giữ nội dung KHỚP với hành vi thật của cogs/autobuy.py — sửa cog thì sửa lại cả file này
(tests/test_autobuy_help.py kiểm tra giới hạn độ dài và các lệnh nhắc tới có thật).
"""

PAGE_ORDER = ["tongquan", "setup", "ban", "mua", "thanhtoan", "quanly", "loi"]

# alias gõ sau `.help autobuy <trang>`
PAGE_ALIASES = {
    "tongquan": "tongquan", "tong-quan": "tongquan", "overview": "tongquan", "main": "tongquan", "1": "tongquan",
    "setup": "setup", "caidat": "setup", "cai-dat": "setup", "install": "setup", "2": "setup",
    "ban": "ban", "sell": "ban", "dang": "ban", "dangban": "ban", "staff": "ban", "3": "ban",
    "mua": "mua", "buy": "mua", "khach": "mua", "customer": "mua", "4": "mua",
    "thanhtoan": "thanhtoan", "thanh-toan": "thanhtoan", "pay": "thanhtoan", "giao": "thanhtoan", "giaohang": "thanhtoan", "5": "thanhtoan",
    "quanly": "quanly", "quan-ly": "quanly", "admin": "quanly", "abset": "quanly", "config": "quanly", "6": "quanly",
    "loi": "loi", "faq": "loi", "fix": "loi", "suco": "loi", "su-co": "loi", "help": "loi", "7": "loi",
}

PAGES = {
    # ─────────────────────────────────────────────
    "tongquan": {
        "emoji": "🧭", "label": "Tổng quan",
        "title": "Auto Buy — Tổng quan",
        "description": (
            "Bán **tài khoản Minecraft tự động**: staff đăng *card ảnh* có nút BUY → khách bấm → bot tạo ticket + QR → "
            "khách chuyển khoản → bot nhận tiền (SePay) và **tự giao** thông tin đăng nhập qua DM. "
            "Không cần ai trực ticket."
        ),
        "fields": [
            ("🧭 Quy trình 1 đơn hàng",
             "1️⃣ Staff/seller `/add_acc` — nạp thông tin đăng nhập vào kho\n"
             "2️⃣ `/stock acc` — đăng card ảnh + nút 🛒 BUY (thành kênh riêng trong danh mục Stock)\n"
             "3️⃣ Khách bấm BUY → ticket riêng + mã QR; card đổi thành ⏳ *Đang giao dịch*\n"
             "4️⃣ Khách chuyển khoản đúng nội dung → bot tự nhận tiền\n"
             "5️⃣ Bot DM thông tin acc cho khách; card → 🔒 SOLD; kênh → ❌ vào danh mục Sold; gửi bill\n"
             "6️⃣ Khách vouch trong ticket → bot đóng ticket"),
            ("👥 Ai làm được gì",
             "**Khách:** bấm 🛒 BUY / ℹ️ Cách mua\n"
             "**Seller còn hạn** (`.seller list`) **hoặc owner/admin — và đã `.shopbank`:** `/add_acc` `/stock acc` (nạp kho + đăng bán)\n"
             "**Staff, seller, người/role gán ở `.st` → Vai trò ticket → 🛒 Quản lý Auto Buy:** "
             "`/restock` `.abresend`, nút ✅ Confirm / 🔒 Close\n"
             "**Admin:** `.abset` `/ab_import` + cài đặt trong `.st`"),
            ("📚 Các trang hướng dẫn (gõ hoặc chọn ở menu bên dưới)",
             "`.help autobuy setup` — ⚙️ cài đặt lần đầu\n"
             "`.help autobuy ban` — 📦 đăng bán acc (`/add_acc`, `/stock acc`, `/restock`)\n"
             "`.help autobuy mua` — 🛒 khách mua như thế nào (có thể copy gửi khách)\n"
             "`.help autobuy thanhtoan` — 💳 thanh toán, giao hàng, Confirm/Close\n"
             "`.help autobuy quanly` — 🔧 `.abset`, `.abresend`, `/ab_import`, dữ liệu\n"
             "`.help autobuy loi` — 🩺 xử lý sự cố thường gặp"),
            ("🔗 Đừng nhầm với",
             "`.help listings` — đăng sản phẩm dạng **bài Forum** (khách mua qua ticket, staff xử lý tay, không tự giao)\n"
             "`.help shoporders` — QR `.done`, hóa đơn, bảng xếp hạng `.bxh` (Auto Buy dùng chung hạ tầng này)"),
        ],
    },
    # ─────────────────────────────────────────────
    "setup": {
        "emoji": "⚙️", "label": "Cài đặt lần đầu",
        "title": "Auto Buy — Cài đặt lần đầu (admin)",
        "description": "Làm lần lượt các bước dưới đây **một lần**. Bước 1–4 là đủ để bán (xác nhận tay); thêm bước 5 để bot **tự giao**.",
        "fields": [
            ("1️⃣ Danh mục Stock & Sold",
             "`.st` → cài **danh mục Stock** (mỗi acc đăng bán = 1 kênh mới trong đây) và **danh mục Sold** "
             "(kênh đã bán tự chuyển sang).\n"
             "Không cài Stock → `/stock acc` đăng card ngay kênh đang gõ lệnh. Không cài Sold → kênh đã bán chỉ đổi icon ❌."),
            ("2️⃣ Ai được đăng bán",
             "Chỉ **seller** có gói còn hạn — thêm bằng `.seller add @user <số ngày>`, xem `.seller list` — hoặc **owner/admin**. "
             "Người đăng **bắt buộc đã có bank** (bước 4: admin `.setbank` hoặc seller `.shopbank`), nếu không bot từ chối `/add_acc` và `/stock acc`.\n"
             "Role gán ở `.st` → **Vai trò ticket** → 🛒 **Quản lý Auto Buy** *không* cho đăng bán — chỉ cho vào ticket mua hàng, "
             "bấm Confirm/Close, `/restock`, `.abresend`."),
            ("3️⃣ Ticket & bill",
             "`.abset ticket <ID danh mục>` — danh mục chứa kênh ticket (không cài → ticket nằm ngoài danh mục)\n"
             "`.abset bill <#kênh>` — kênh nhận bill (ảnh card + người mua + giá) sau mỗi đơn\n"
             "Tuỳ chọn, hiện trong DM giao hàng: `.abset youtube|2fa|lock|vouch <#kênh>` "
             "(kênh hướng dẫn đổi thông tin / 2FA / lock acc / nơi vouch)\n"
             "Xem lại toàn bộ: `.abset`"),
            ("4️⃣ Bank nhận tiền của seller (bắt buộc trước khi đăng bán)",
             "**Cách 1 — Admin gán giúp** (khuyên dùng, ít lỗi nhất): `.setbank <@seller|ID> <mã NH|BIN> <số TK> [tên]` — "
             "mỗi dòng 1 seller; gõ `.setbank` để xem ví dụ + mã BIN.\n"
             "**Cách 2 — Seller tự gõ `.shopbank` kèm ảnh QR** nhận tiền (hoặc reply vào ảnh QR): bot tự đọc ngân hàng + số TK. "
             "Một số QR (vd **MB**) nhúng *mã định danh* thay số TK nên bot không đọc được số TK → dùng cách 1 với số TK in trên ảnh.\n"
             "**Cách 3 — Nhập tay:** `.shopbank \"MB Bank\" mbbank 0123456789 \"NGUYEN VAN A\"`\n"
             "Tên chủ TK không bắt buộc (QR không chứa tên): thêm bằng `.shopbank name NGUYEN VAN A`. "
             "Xem lại: `.shopbank` · danh sách: `.listbank`."),
            ("5️⃣ Thanh toán tự động (để bot tự giao)",
             "• Admin bật **Shop Orders** trong `.st`\n"
             "• Webhook SePay `/webhook/sepay` + biến môi trường `SEPAY_WEBHOOK_API_KEY` khớp API Key khai trên SePay "
             "(chi tiết: `.help shoporders`)\n"
             "Thiếu bank → *không đăng bán được*. Thiếu Shop Orders/SePay → vẫn bán được nhưng seller/staff phải bấm ✅ Confirm tay."),
            ("6️⃣ Quyền của bot",
             "Bot cần: **Manage Channels** (tạo kênh stock/ticket, đổi tên, chuyển danh mục), **Send Messages**, "
             "**Embed Links**, **Attach Files**, **Read Message History**. Thiếu → tạo ticket lỗi (bot tự hoàn tác, acc không bị kẹt)."),
            ("7️⃣ Có kho cũ từ bot autobuy Node?",
             "`/ab_import` + đính kèm `kho.json` → nhập kho, **giữ nguyên card cũ** (nút BUY cũ vẫn mua được). "
             "Nhớ **tắt bot Node** để 2 bot không cùng xử lý nút."),
            ("8️⃣ Chạy thử 1 đơn nhỏ",
             "`/add_acc` một acc test → `/stock acc username:<tên> price:1k` → dùng acc/tài khoản phụ bấm BUY → "
             "chuyển 1k (hoặc bấm ✅ Confirm) → kiểm tra DM, card SOLD, kênh Sold, bill."),
        ],
    },
    # ─────────────────────────────────────────────
    "ban": {
        "emoji": "📦", "label": "Đăng bán (staff)",
        "title": "Auto Buy — Đăng bán acc (staff/seller)",
        "description": "Hai bước: **nạp thông tin vào kho** (`/add_acc`) rồi **đăng card** (`/stock acc`). Người chạy `/add_acc` là **seller** của acc đó.",
        "fields": [
            ("🔐 Điều kiện để đăng bán",
             "• Là **seller còn hạn** (`.seller list`) hoặc **owner/admin**\n"
             "• Đã **`.shopbank`** — tiền khách chuyển sẽ vào bank này. Chưa có → bot từ chối và nhắc lệnh\n"
             "• `/stock acc`: bank của **seller của acc** (không nhất thiết là người đang gõ) cũng phải có — owner đăng hộ acc của seller thì seller đó phải đã `.shopbank`\n"
             "• Shop Orders đang tắt → vẫn đăng được nhưng bot sẽ cảnh báo: ticket không có QR, phải Confirm tay"),
            ("1️⃣ `/add_acc` — nạp kho",
             "Mở form, dán mỗi dòng `Nhãn: giá trị`:\n"
             "```\nUsername: \nCapes: \nRecovery Code: \nPrimary Email: \nSecurity Email: \nSecret Key: \nPassword: \n```"
             "Chỉ **Username** là bắt buộc. Thông tin đăng nhập chỉ nằm trong kho và gửi DM cho người mua.\n"
             "• Nạp lại acc *đang bán*: chỉ cập nhật thông tin, giữ nguyên card/giá/trạng thái\n"
             "• Nạp lại acc *đã SOLD*: coi như hàng mới → `/stock acc` để đăng lại"),
            ("2️⃣ `/stock acc` — đăng card",
             "`username` *(bắt buộc)* — tên Minecraft, dùng để lấy skin 3D\n"
             "`price` *(bắt buộc)* — `140k` · `140000` · `1.2M` · `1tr` · số <1000 tính là nghìn (`140` = 140k)\n"
             "`capes` — emoji cape (card hiện tối đa 7). Bỏ trống → lấy từ kho; kho trống → lấy emoji dán ở rank/stats\n"
             "`rank` — `VIP` `MVP` `MVP+` `NON`… (hiện dạng `MVP+-RANK`; bỏ trống = NON)\n"
             "`statshpx` — Hypixel: `Level, Achievements` vd `150, 4500`\n"
             "`statsdonut` — DonutSMP: `Playtime, Money, Shards` vd `120h, 50M, 1500`"),
            ("🖼️ Kết quả",
             "Card ảnh (skin, tên, giá, capes, rank, chỉ số; góc trên là **tên + icon server** của bạn) + dòng Seller + nút 🛒 **BUY** / ℹ️ **Cách mua**.\n"
             "Có danh mục Stock → tạo kênh `✅・140k・3-cape` (giá rút gọn + số cape), khách xem được nhưng không chat. "
             "Chưa cài → đăng ngay kênh đang gõ lệnh.\n"
             "Đăng lại cùng username → card mới. Acc đang có người mở đơn thì chưa đăng lại được."),
            ("📣 `/restock`",
             "Gửi bảng liệt kê **tất cả kênh trong danh mục Stock** vào kênh hiện tại — dùng để báo hàng mới."),
            ("✋ Bán tay ngoài bot",
             "Gõ `sold` trong kênh stock → chạy luồng sold có sẵn (chuyển kênh, hỏi người mua nếu tên kênh có giá) và acc cũng thành "
             "**SOLD**, nút BUY bị khoá nên không ai mua nốt acc đã bán."),
            ("💡 Mẹo",
             "• Seller của acc = người nhận tiền: QR dùng **bank của người này** (`.shopbank`), được ping trong ticket và được tính doanh số\n"
             "• Staff (không phải seller) không đăng bán được nhưng vẫn Confirm/Close ticket, `/restock`, `.abresend`"),
        ],
    },
    # ─────────────────────────────────────────────
    "mua": {
        "emoji": "🛒", "label": "Khách mua",
        "title": "Auto Buy — Khách mua như thế nào",
        "description": "Trang này viết cho **khách** — staff có thể copy gửi khách khi cần hỗ trợ.",
        "fields": [
            ("1️⃣ Bấm 🛒 BUY",
             "Dưới card tài khoản bạn thích (ℹ️ **Cách mua** để xem hướng dẫn nhanh). Bot tạo kênh `ticket-<tên acc>` "
             "chỉ bạn, seller và staff thấy. Card chuyển ⏳ *Đang giao dịch* — người khác không bấm mua trùng được."),
            ("2️⃣ Chuyển khoản theo QR",
             "Trong ticket có đơn hàng + **mã QR VietQR**. Quét bằng app ngân hàng và **giữ nguyên số tiền + nội dung chuyển khoản** "
             "(mã dạng `DH123456`, mỗi đơn một mã) — bot dựa vào mã này để khớp đơn. Chuyển **thiếu tiền** thì bot không tự giao."),
            ("3️⃣ Nhận tài khoản qua DM",
             "Tiền về → bot báo \"💰 Đã nhận thanh toán\" rồi gửi **DM**: Username, Password, Email, Recovery Code, Secret Key "
             "(kèm các kênh hướng dẫn đổi thông tin nếu shop đã cài). Hãy đổi thông tin bảo mật ngay."),
            ("⚠️ Bật DM trước khi trả tiền",
             "Bật *Cho phép tin nhắn trực tiếp từ thành viên máy chủ*. Lỡ tắt → báo seller/staff, họ gửi lại bằng `.abresend`."),
            ("4️⃣ Vouch",
             "Nhận xong hãy nhắn vouch ngay trong ticket (vd `+1 legit @seller mfa`) → bot ghi \"đã legit\" và đóng ticket sau 3 giây. "
             "Chưa nhắn → bot nhắc qua DM mỗi 5 phút (tối đa 2 giờ)."),
            ("🔄 Muốn huỷ / mua nhầm?",
             "Nhờ staff/seller bấm 🔒 **Close** — acc quay lại bán được và mã QR bị huỷ. "
             "**Đã chuyển khoản rồi thì đừng tự đóng/xoá ticket**, báo staff để được xử lý."),
            ("📭 Ticket không có QR?",
             "Seller chưa cài bank (hoặc tính năng tự động đang tắt). Làm theo hướng dẫn trong ticket, "
             "chuyển khoản cho seller rồi gửi ảnh bill — seller bấm ✅ Confirm là nhận acc ngay."),
        ],
    },
    # ─────────────────────────────────────────────
    "thanhtoan": {
        "emoji": "💳", "label": "Thanh toán & giao hàng",
        "title": "Auto Buy — Thanh toán & giao hàng",
        "description": "Có **2 cách** giao hàng — kết quả cuối giống hệt nhau, và dù cả hai xảy ra cùng lúc bot **chỉ giao 1 lần**.",
        "fields": [
            ("🤖 Cách 1 — Tự động (SePay)",
             "Điều kiện: Shop Orders bật + seller đã `.shopbank` + webhook SePay hoạt động (xem `.help autobuy setup`).\n"
             "Ticket hiện QR; khi SePay báo đã nhận **đủ hoặc dư** số tiền, đúng mã `DHxxxxxx` → bot tự giao. "
             "Lệch số TK nhận, thiếu tiền hoặc mã không có đơn → **không tự giao**, bot báo admin xử lý tay."),
            ("🔎 Bot biết đã có tiền bằng cách nào?",
             "Ảnh QR chỉ để khách quét — bot **không tự thấy tài khoản ngân hàng**. Việc nhận biết tiền về đến từ **SePay**: "
             "ngân hàng báo SePay → SePay gọi webhook `/webhook/sepay` của bot → bot khớp **mã `DHxxxxxx`** + số tiền + số TK rồi giao. "
             "Chưa nối SePay thì QR vẫn hiện nhưng bot không tự giao — dùng ✅ Confirm."),
            ("✋ Cách 2 — Confirm tay",
             "Dùng khi chưa có QR tự động (thiếu bank / Shop Orders tắt / giá thoả thuận). Ticket hiện hướng dẫn liên hệ seller "
             "(hoặc QR dự phòng `.abset qr`). Khách gửi bill → **staff hoặc seller của acc** bấm ✅ **Confirm** → giao ngay. "
             "Người khác bấm bị từ chối."),
            ("✅ Khi giao thành công",
             "1. Acc → **SOLD**\n2. DM thông tin đăng nhập cho người mua\n"
             "3. Card → 🔒 SOLD + dòng \"Acc đã được bán ❌\"; kênh đổi ❌ và chuyển sang danh mục Sold\n"
             "4. Gửi bill (ảnh card + người mua + giá) vào kênh bill\n"
             "5. Cộng chi tiêu vào `.bxh` và thống kê seller\n6. Ghi log hệ thống + nhắc khách vouch qua DM"),
            ("🔒 Close — huỷ đơn chưa giao",
             "Staff/seller bấm Close: acc về ✅ BUY được, mã QR bị huỷ, kênh tự xoá sau 5 giây. "
             "Xoá kênh ticket bằng tay cũng tự hoàn acc. Đơn **đã giao** thì Close chỉ đóng kênh, acc vẫn SOLD."),
            ("⚠️ Tiền về sau khi ticket đã đóng",
             "Bot **không giao nữa** (mã QR đã huỷ) mà báo admin: \"nhận tiền với mã CK nhưng không có đơn chờ khớp\" — "
             "admin hoàn tiền hoặc giao tay (nạp lại acc bằng `/add_acc`, mở đơn mới)."),
            ("📨 Khách tắt DM",
             "Acc vẫn tính **đã bán**; bot báo trong ticket và cho admin biết. Khi khách bật DM: `.abresend <username>`."),
        ],
    },
    # ─────────────────────────────────────────────
    "quanly": {
        "emoji": "🔧", "label": "Quản lý & dữ liệu",
        "title": "Auto Buy — Quản lý, cấu hình, dữ liệu",
        "description": "Các lệnh quản trị và nơi lưu dữ liệu của Auto Buy.",
        "fields": [
            ("⚙️ `.abset` (admin)",
             "`.abset` — xem cấu hình hiện tại\n"
             "`.abset ticket <ID danh mục>` — danh mục chứa ticket\n"
             "`.abset bill <#kênh>` — kênh bill\n"
             "`.abset youtube|2fa|lock|vouch <#kênh>` — kênh hướng dẫn/vouch hiện trong DM giao hàng\n"
             "`.abset qr <url ảnh>` — QR dự phòng khi seller chưa `.shopbank`\n"
             "`.abset <khoá> off` — xoá 1 mục\n"
             "-# Danh mục **Stock/Sold** dùng chung cài đặt `.st` — không cài trong `.abset`."),
            ("📨 `.abresend <username>` (staff)",
             "Gửi lại DM thông tin cho người đã mua acc đó (chỉ với acc **đã SOLD**) — dùng khi lần giao đầu khách tắt DM."),
            ("📥 `/ab_import` (admin)",
             "Đính kèm `kho.json` của bot autobuy Node → nhập kho. Acc trùng username bị bỏ qua (không ghi đè); "
             "acc đang ⏳ PROCESSING bên Node được đặt về AVAILABLE; **giữ nguyên card cũ**. Kết quả chỉ mình bạn thấy."),
            ("🗃️ Dữ liệu lưu ở đâu",
             "Trong dữ liệu server (MongoDB), theo từng server: kho acc, ticket đang mở, cấu hình `.abset`.\n"
             "⚠️ Thông tin đăng nhập acc lưu **dạng văn bản** (như bản Node lưu JSON): chỉ admin/DB đọc được — "
             "đừng chia sẻ bản dump database."),
            ("🔐 Giới hạn hệ thống",
             "• Mỗi acc chỉ 1 người mở đơn tại 1 thời điểm (chiếm ngay khi bấm BUY)\n"
             "• Acc đã bán vẫn nằm trong kho (để `.abresend`) và **không tự xoá** — nhớ giữ database an toàn\n"
             "• Nút BUY/Confirm/Close vẫn hoạt động sau khi bot restart"),
            ("🔷 Tất cả lệnh Auto Buy",
             "`/add_acc` `/stock acc` `/restock` `/ab_import` · `.abset` `.abresend` · nút 🛒 BUY, ✅ Confirm, 🔒 Close"),
        ],
    },
    # ─────────────────────────────────────────────
    "loi": {
        "emoji": "🩺", "label": "Sự cố thường gặp",
        "title": "Auto Buy — Sự cố thường gặp",
        "description": "Tra nhanh theo triệu chứng.",
        "fields": [
            ("`/add_acc` hoặc `/stock acc` báo \"Chỉ seller…\" / \"chưa đăng ký ngân hàng\"",
             "Bạn cần là **seller còn hạn** (`.seller list`, admin thêm bằng `.seller add`) hoặc owner/admin, và đã `.shopbank`. "
             "Owner đăng hộ acc của seller khác thì seller đó cũng phải đã `.shopbank`. Gõ `.shopbank` (không tham số) để xem bank đang lưu."),
            ("`.shopbank` + ảnh QR báo \"mã định danh\" (vd QR của MB)",
             "Ngân hàng đó nhúng mã định danh vào QR thay cho số tài khoản, bot chỉ biết ngân hàng (BIN) chứ không có số TK thật. "
             "Admin gán bằng số TK **in trên ảnh**: `.setbank <@seller|ID> 970422 <SỐ TK> <TÊN>` (hoặc seller nhập tay `.shopbank \"MB Bank\" 970422 <SỐ TK> \"TÊN\"`)."),
            ("`.shopbank` + ảnh QR báo không đọc được / không phải VietQR",
             "Dùng **mã QR nhận tiền theo số tài khoản** trong app ngân hàng (không phải QR ví MoMo/ZaloPay, không phải QR số thẻ). "
             "Chụp màn hình **nét, không cắt viền QR**. Vẫn lỗi → nhập tay: `.shopbank \"Vietinbank\" vietinbank 0123456789 \"Nguyen Van A\"`. "
             "Báo thiếu thư viện đọc QR → admin chạy `pip install zxing-cpp` trên VPS rồi restart bot."),
            ("Nút BUY báo \"đang có người mở đơn\" mãi",
             "Ticket cũ còn treo. Vào kênh `ticket-<tên acc>` bấm 🔒 **Close** (hoặc xoá kênh) → acc tự quay lại BUY được. "
             "Không thấy kênh ticket nữa mà nút vẫn kẹt → báo admin."),
            ("Ticket có khung \"Quét mã để thanh toán\" nhưng KHÔNG hiện ảnh QR",
             "Thường do **bank của seller lưu sai** (vd số TK là chữ `ma_bank`, hoặc số TK nằm nhầm ô tên chủ TK) nên ảnh QR không dựng được. "
             "Seller gõ `.shopbank` (không kèm gì) để xem đang lưu gì, rồi đăng ký lại bằng `.shopbank` + **ảnh QR ngân hàng**. "
             "Từ bản này bot chặn lưu bank sai và không còn gửi QR hỏng. Ticket cũ: bấm 🔒 **Close** rồi bấm BUY lại."),
            ("Ticket không có QR",
             "Seller của acc chưa `.shopbank`, Shop Orders đang tắt, hoặc giá không hợp lệ. "
             "Bán tay bằng ✅ Confirm, hoặc cài bank rồi mở đơn mới."),
            ("Chuyển khoản rồi nhưng bot không giao",
             "Kiểm tra: nội dung CK có đúng mã `DHxxxxxx`? chuyển đủ tiền? đúng số TK của QR? SePay đang gửi webhook? "
             "Bot sẽ **báo admin** các trường hợp lệch tiền/lệch TK/không có đơn. Xác nhận tiền đã về thật thì bấm ✅ Confirm."),
            ("Khách không nhận được DM",
             "Khách bật *tin nhắn riêng từ thành viên server* rồi staff chạy `.abresend <username>`."),
            ("`/stock acc` báo không tạo được kênh / ticket",
             "Bot thiếu **Manage Channels** hoặc danh mục đã đầy (giới hạn 50 kênh/danh mục của Discord). "
             "Acc không bị kẹt — bot tự hoàn về AVAILABLE khi tạo ticket lỗi."),
            ("Card không có ảnh skin",
             "Tên Minecraft sai hoặc các API skin đang lỗi — card vẫn đăng và bán bình thường. Đăng lại bằng `/stock acc` khi API ổn."),
            ("Lệnh slash không hiện",
             "Bot cần restart để đồng bộ lệnh mới (tự động khi khởi động). Server chưa được ủy quyền (`.as`) thì bot không chạy lệnh nào."),
            ("Hết cách?",
             "Gửi admin: tên acc, kênh ticket, giờ giao dịch. Log của bot (`journalctl -u tuytam-bot`) có tiền tố `[AUTOBUY]` và `[SEPAY]`."),
        ],
    },
}


def embed_size(page: dict) -> int:
    """Tổng ký tự Discord tính cho embed (title + description + field name/value + footer chừa ~100)."""
    n = len(page["title"]) + len(page["description"]) + 100
    return n + sum(len(name) + len(value) for name, value in page["fields"])
