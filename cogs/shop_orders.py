"""
cogs/shop_orders.py — QR thanh toán VietQR động + hàng đợi xử lý đơn, gắn vào lệnh .done có sẵn.

⚠️ TÍNH NĂNG THỬ NGHIỆM: mọi hàm đều no-op nếu get_cfg_shop_orders_enabled() == False.
Bật/tắt qua nút trong `.st` (do cogs/admin.py quản lý).

KIẾN TRÚC MULTI-SELLER (mỗi seller 1 bank riêng, không còn 1 bank chung cho cả guild):
1. Admin HOẶC seller (has_ticket_access — có role xem được ít nhất 1 loại ticket) tự
   đăng ký bank CỦA RIÊNG mình, gõ lại là cập nhật đúng bank của chính họ:
   `.shopbank "Vietinbank" vietinbank 0123456789 "Nguyen Van A"`
   `.listbank` — xem toàn bộ bank các seller đã đăng ký.
   `.setqueue #hang-doi` — admin cấu hình kênh hàng đợi (không đổi so với trước).
2. Khi staff gõ `.done <số tiền>` trong ticket (cogs/ticket.py), nếu tính năng đang bật:
   - QR dùng ĐÚNG bank của người gõ `.done` (ctx.author) — tiền vào thẳng TK người xử lý
     đơn, không qua 1 TK chung. Nếu người đó chưa `.shopbank` thì báo rõ, KHÔNG chặn phần
     còn lại của `.done` (spent/role vẫn lưu bình thường).
   - Nội dung CK (addInfo) KHÔNG còn là 1 chuỗi cố định chung nữa — mỗi đơn tự sinh 1 mã
     tham chiếu riêng (gen_transfer_code), mã này được lưu vào pending order (GLOBAL, xem
     core/data.py) để webhook thanh toán sau này tự đối chiếu — xem Phần 2 (chưa làm ở
     bản này: verify_server.py route nhận webhook SePay + tự động khớp + báo trong ticket).
   - gửi thêm 1 embed "Đơn hàng chờ xử lý" vào kênh hàng đợi (send_to_queue) — TẠM THỜI
     vẫn gửi NGAY lúc `.done` như cũ; đổi thành "chỉ gửi sau khi xác nhận đã thanh toán"
     sẽ làm cùng lúc với Phần 2 (webhook), để title/hành vi luôn khớp nhau.
3. Seller nhận được tiền, làm việc xong thì bấm nút ✅ "Hoàn thành" ngay trên embed đó
   trong kênh hàng đợi — embed được giữ lại, chỉ đổi màu + trạng thái, không xóa/chuyển kênh.
   Hóa đơn công khai (kênh proof) hiện ĐÚNG mã CK thật đã dùng trên QR (không sinh mã mới
   không liên quan như trước).
"""

import io
import re
import random
import string
import shlex
import asyncio
import logging
from urllib.parse import quote
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands
from discord.ui import TextInput

from core.vietqr import (MAX_IMAGE_BYTES, QRDecoderMissing, bank_name_from_bin, bank_problem, decode_qr_texts,
                         normalize_account, normalize_holder, pick_vietqr, validate_bank)

from core.qr_image import fetch_qr_image

from core.data import is_admin
from core.data import (
    ADMIN_IDS, fmt_amount, is_staff_member, get_or_fetch_channel, _uname_plain,
    set_current_guild, is_data_cache_ready,
    get_cfg_shop_orders_enabled,
    get_shop_orders_bank, save_shop_orders_bank, get_all_shop_orders_banks, delete_shop_orders_bank,
    has_ticket_access,
    save_pending_shop_order, get_pending_shop_order, find_pending_shop_order_by_content, pop_pending_shop_order,
    is_webhook_id_processed, mark_webhook_id_processed,
    get_cfg_queue_channel, save_cfg_queue_channel,
    get_cfg_proof_channel,
    get_next_shop_order_number, set_shop_order_counter,
    get_cfg_receipt_thankyou,
    load_data,
    GuildContextView, GuildContextModal,
)
from cogs.logger import send_log

log = logging.getLogger(__name__)

COLOR_QR = 0x5865F2
COLOR_QUEUE_PENDING = 0xF1C40F
COLOR_QUEUE_DONE = 0x2ECC71


def _extract_mention_id(text: str) -> int | None:
    m = re.search(r"<@!?(\d+)>", text or "")
    return int(m.group(1)) if m else None


def _extract_amount_digits(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def fmt_vnd(amount: int) -> str:
    """Định dạng đầy đủ '150,000 VNĐ' — KHÔNG rút gọn như fmt_amount() ('150k'/'1.5tr').
    Dùng cho mọi field embed mà sau này bị đọc lại bằng _extract_amount_digits() (hàng đợi →
    hóa đơn), vì fmt_amount() rút gọn sẽ làm mất số 0 khi strip ký tự không phải chữ số
    (vd '150k' → chỉ còn '150' → hóa đơn hiện sai 150đ thay vì 150,000đ). Cũng khớp đúng
    định dạng hóa đơn mẫu (ảnh gốc): 'Số tiền: 150,000 VNĐ'."""
    return f"{amount:,} VNĐ"


PAYMENT_CODE_PREFIX = "DH"  # 2-5 ký tự CHỮ, khớp "Tiền tố" cấu hình trong SePay ›
                             # Cấu hình Công ty › Cấu hình chung › Cấu trúc mã thanh toán.
                             # "DH" (Đơn Hàng) trung lập, không gắn tên riêng TuyTam — bot
                             # multi-guild, guild khác dùng chung 1 SePay account (nếu có)
                             # vẫn ra mã hợp lệ. Đổi ở đây thì phải đổi Y HỆT bên SePay.
PAYMENT_CODE_SUFFIX_LEN = 6  # khớp "Hậu tố" = 6 ký tự, loại Số nguyên, cấu hình bên SePay.
# Dò mã CK dạng DH123456 trong nội dung giao dịch — dùng để phát hiện "tiền đã vào nhưng
# không có đơn chờ khớp" (đơn hết hạn/đã bị xoá) và báo admin thay vì bỏ qua im lặng.
_PAYMENT_CODE_RE = re.compile(re.escape(PAYMENT_CODE_PREFIX) + r"\d{" + str(PAYMENT_CODE_SUFFIX_LEN) + r"}", re.IGNORECASE)


def gen_transfer_code() -> str:
    """Sinh mã CK dạng <PREFIX><6 chữ số ngẫu nhiên>, vd DH482917 — khớp ĐÚNG cấu trúc
    <tiền tố><hậu tố Số nguyên, không dấu ngăn cách> mà SePay dùng để tự bóc tách trường
    `code` từ nội dung chuyển khoản (xem Cấu hình mã thanh toán trên SePay dashboard).
    KHÔNG còn nhúng tên khách như bản trước (tên khách đã hiện riêng ở field "👤 Khách"
    của mọi embed liên quan rồi, không cần nhúng lại vào mã) — đổi vì cấu trúc SePay
    yêu cầu tiền tố CỐ ĐỊNH 2-5 ký tự chữ, không hợp với tên khách dài/thay đổi được."""
    digits = "".join(random.choices(string.digits, k=PAYMENT_CODE_SUFFIX_LEN))
    return f"{PAYMENT_CODE_PREFIX}{digits}"


async def _resolve_member(guild: discord.Guild, user_id: int | None):
    """Cache trước, fetch_member() fallback — né gọi API dư khi member đã có sẵn trong
    cache (đa số trường hợp vì buyer/seller vừa tương tác trong ticket/queue xong)."""
    if not user_id:
        return None
    member = guild.get_member(user_id)
    if member:
        return member
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.HTTPException):
        return None


def _fmt_receipt_person(member, fallback_id: int | None) -> str:
    if member:
        return f"{member.mention}\n`{member.name}`"
    return f"<@{fallback_id}>" if fallback_id else "*(không rõ)*"


async def build_receipt_embed(order_number: str, buyer_id: int, product: str, amount: int,
                               approver: discord.abc.User, transfer_code: str,
                               guild: discord.Guild, seller_id: int | None = None) -> discord.Embed:
    """Hóa đơn công khai — gửi vào kênh proof khi đơn hàng đợi được đánh dấu Hoàn thành.
    Layout theo mẫu ảnh admin gửi (26/8): lời cảm ơn kèm tên shop lên đầu (config được,
    xem cfg_receipt_thankyou/.st), field gọn theo cặp mention + username thô, giờ hiển
    thị theo VN (UTC+7). Mã CK + người duyệt vẫn giữ lại (không có trong ảnh mẫu nhưng
    cần cho đối soát) — đưa xuống field/footer để không phá layout chính.
    `transfer_code` là mã CK THẬT đã in trên QR (đọc lại từ field "📝 Mã CK" của embed
    hàng đợi) — KHÔNG sinh mã mới không liên quan."""
    buyer  = await _resolve_member(guild, buyer_id)
    seller = await _resolve_member(guild, seller_id)

    thankyou = get_cfg_receipt_thankyou().replace("{shop}", guild.name)
    now_vn = datetime.now(timezone(timedelta(hours=7)))

    e = discord.Embed(
        title=f"🧾 HÓA ĐƠN THANH TOÁN • #{order_number}",
        description=thankyou,
        color=COLOR_QUEUE_DONE,
    )
    e.add_field(name="👤 Khách Hàng", value=_fmt_receipt_person(buyer, buyer_id), inline=True)
    e.add_field(name="🏪 Bán Bởi",   value=_fmt_receipt_person(seller, seller_id), inline=True)
    e.add_field(name="💳 Phương Thức", value="`VietQR`", inline=True)
    e.add_field(name="💰 Tổng Thanh Toán", value=f"**{fmt_vnd(amount)}**", inline=True)
    e.add_field(name="📦 Trạng Thái", value="🟢 Đã bàn giao", inline=True)
    e.add_field(name="⏰ Thời Gian", value=now_vn.strftime("%d/%m/%Y %H:%M:%S"), inline=True)
    e.add_field(name="🛒 Sản Phẩm & Dịch Vụ", value=product or "*(không rõ)*", inline=False)
    e.add_field(name="📝 Mã Chuyển Khoản", value=f"`{transfer_code}`", inline=False)
    e.set_footer(text=f"Hoá đơn #{order_number} • Xử lý bởi {approver}")
    return e


def build_payment_qr_embed(seller: discord.abc.User, buyer: discord.abc.User, amount: int,
                            guild_id: int, channel_id: int) -> tuple[discord.Embed | None, str | None, str | None]:
    """Tạo QR VietQR dùng ĐÚNG bank của `seller` (người gõ .done) — tiền vào thẳng TK
    người xử lý đơn. Nội dung CK là mã tham chiếu SINH RIÊNG cho đơn này (gen_transfer_code),
    lưu lại qua save_pending_shop_order() để webhook thanh toán tự đối chiếu sau này.

    Trả về (embed, ref_code, None)   nếu tạo QR bình thường — ref_code cần truyền tiếp
                                       cho send_to_queue() để hàng đợi/hóa đơn sau này
                                       hiện ĐÚNG mã đã in trên QR (không tự parse lại
                                       field embed, tránh phụ thuộc ngầm giữa 2 file).
    Trả về (None, None, None)        nếu tính năng đang tắt hẳn — im lặng bỏ qua như cũ.
    Trả về (None, None, "<cảnh báo>") nếu seller CHƯA `.shopbank` — cần báo rõ ngay cho
                                       staff biết vì sao không có QR, khác với tắt hẳn."""
    if not get_cfg_shop_orders_enabled():
        return None, None, None

    bank = get_shop_orders_bank(seller.id)
    if not bank:
        return None, None, (
            f"⚠️ {seller.mention} chưa đăng ký ngân hàng nhận tiền — gõ "
            f'`.shopbank` kèm ảnh QR ngân hàng (hoặc nhập tay {BANK_TYPED_EXAMPLE}) để lần `.done` sau tự có QR.'
        )

    problem = bank_problem(bank)
    if problem:                                   # dữ liệu sai (vd số TK = "ma_bank") → KHÔNG dựng QR hỏng, báo rõ lý do
        return None, None, (f"⚠️ Bank của {seller.mention} đang lưu **sai** — {problem}. "
                            "Gõ `.shopbank` kèm **ảnh QR ngân hàng** để đăng ký lại.")
    bank_code      = bank.get("bank_code")
    account_number = normalize_account(bank.get("account_number"))

    template       = bank.get("template") or "compact2"
    account_holder = bank.get("account_holder", "")

    ref_code = gen_transfer_code()
    for _ in range(5):  # không gian mã nhỏ hơn bản cũ (10^6 thay vì 36^6) — kiểm tra
                         # trùng với đơn ĐANG chờ trước khi lưu, phòng hờ dù xác suất thấp.
        if not get_pending_shop_order(ref_code):
            break
        ref_code = gen_transfer_code()
    save_pending_shop_order(
        ref_code,
        guild_id=guild_id, channel_id=channel_id,
        seller_id=seller.id, buyer_id=buyer.id, amount=amount,
        account_number=account_number,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    qr_url = (
        f"https://img.vietqr.io/image/{bank_code}-{account_number}-{template}.png"
        f"?amount={amount}&addInfo={quote(ref_code)}&accountName={quote(account_holder)}"
    )

    e = discord.Embed(title="🏦 Quét mã để thanh toán", color=COLOR_QR)
    e.add_field(name="Người nhận", value=seller.mention, inline=True)
    e.add_field(name="Ngân hàng", value=bank.get("bank_name", "?"), inline=True)
    e.add_field(name="Số tài khoản", value=account_number, inline=True)
    e.add_field(name="Chủ tài khoản", value=account_holder or "?", inline=False)
    e.add_field(name="Số tiền", value=f"**{fmt_amount(amount)}**", inline=True)
    e.add_field(name="Nội dung CK", value=f"`{ref_code}`", inline=True)
    e.set_image(url=qr_url)
    e.set_footer(text="🧪 Shop Orders (thử nghiệm) — ghi ĐÚNG nội dung CK để hệ thống tự nhận thanh toán")
    return e, ref_code, None


async def attach_qr_image(embed: discord.Embed, **log_ctx) -> list:
    """Tải ảnh QR của embed (do build_payment_qr_embed dựng, đang trỏ link img.vietqr.io) về phía bot rồi đính kèm file.

    Trả về danh sách file để truyền vào `send(..., files=...)` — và ĐỔI embed sang `attachment://qr.<đuôi>`.
    Vì sao: img.vietqr.io có thể trả SVG (Discord không hiển thị được) → bot tự đổi sang PNG, xem core/qr_image.py.
    Không làm được (mạng lỗi, thiếu thư viện đổi SVG…) → trả [] và GIỮ NGUYÊN embed dùng link như cũ.
    ⚠️ Gọi SAU khi đã `interaction.response.defer()` (tải ảnh có thể mất vài giây, quá 3s là hết hạn tương tác).
    Mọi chỗ gửi embed QR phải truyền `files=` kèm theo — gửi embed đã đổi mà thiếu file thì ảnh không hiện."""
    url = getattr(getattr(embed, "image", None), "url", None)
    if not url:
        return []
    try:
        got = await fetch_qr_image(url, ctx=log_ctx)
    except Exception:                      # fetch_qr_image không ném lỗi — chốt chặn cuối, QR không được làm hỏng .done
        log.exception("[QR] attach_qr_image lỗi bất ngờ")
        return []
    if not got:
        return []
    data, ext = got
    name = f"qr.{ext}"
    embed.set_image(url=f"attachment://{name}")
    return [discord.File(io.BytesIO(data), filename=name)]


def build_queue_embed(seller: discord.abc.User, buyer: discord.abc.User,
                       ticket_channel: discord.abc.GuildChannel, amount: int,
                       ref_code: str) -> discord.Embed:
    e = discord.Embed(
        title=f"{buyer.display_name} | Đơn hàng đang xử lý",
        color=COLOR_QUEUE_PENDING,
        timestamp=datetime.now(timezone.utc),
    )
    e.set_thumbnail(url=buyer.display_avatar.url)
    e.add_field(name="👤 Khách", value=buyer.mention, inline=True)
    e.add_field(name="🧑 Seller", value=seller.mention, inline=True)
    e.add_field(name="🎫 Ticket", value=ticket_channel.mention if ticket_channel else "*(không rõ)*", inline=True)
    e.add_field(name="💰 Số tiền", value=fmt_vnd(amount), inline=True)
    e.add_field(name="📝 Mã CK", value=f"`{ref_code}`" if ref_code else "*(không có)*", inline=True)
    e.add_field(name="📌 Trạng thái", value="🟡 Đang xử lý", inline=False)
    return e


def build_payment_confirmed_embed(seller: discord.abc.User, buyer: discord.abc.User,
                                   amount: int, ref_code: str) -> discord.Embed:
    """Embed báo trong ticket ngay khi webhook SePay xác nhận tiền đã vào TK — gửi SAU
    khi tiền đã thực sự chuyển vào tài khoản ngân hàng qua QR (không phải lúc .done)."""
    e = discord.Embed(
        title="✅ Đã nhận thanh toán",
        description="SePay đã xác nhận tự động — tiền đã vào tài khoản ngân hàng qua QR.",
        color=COLOR_QUEUE_DONE,
        timestamp=datetime.now(timezone.utc),
    )
    e.add_field(name="👤 Khách", value=buyer.mention, inline=True)
    e.add_field(name="🧑 Seller", value=seller.mention, inline=True)
    e.add_field(name="💰 Số tiền", value=fmt_vnd(amount), inline=True)
    e.add_field(name="📝 Mã CK", value=f"`{ref_code}`", inline=True)
    e.set_footer(text="🧪 Shop Orders — xác nhận tự động qua webhook SePay")
    return e


async def send_to_queue(bot, seller: discord.abc.User, buyer: discord.abc.User,
                         ticket_channel: discord.abc.GuildChannel, amount: int,
                         ref_code: str = "") -> None:
    """Gửi embed đơn hàng vào kênh hàng đợi (nếu đã cấu hình + tính năng đang bật).
    Gọi hàm này ngay sau khi build_payment_qr_embed() ở cogs/ticket.py.
    TẠM THỜI vẫn gọi NGAY lúc .done như hành vi cũ — xem docstring đầu file."""
    if not get_cfg_shop_orders_enabled():
        return
    queue_channel_id = get_cfg_queue_channel()
    if not queue_channel_id:
        return
    queue_channel = await get_or_fetch_channel(bot, queue_channel_id)
    if not queue_channel:
        return

    embed = build_queue_embed(seller, buyer, ticket_channel, amount, ref_code)
    await queue_channel.send(embed=embed, view=QueueOrderView())


class ReceiptProductModal(GuildContextModal, title="🧾 Hoàn thành đơn hàng"):
    """Hỏi tên/mã sản phẩm trước khi dựng hóa đơn công khai gửi vào kênh proof."""

    def __init__(self, message: discord.Message, default_product: str = ""):
        super().__init__()
        self.message = message
        self.product_input = TextInput(
            label="Tên / mã sản phẩm",
            placeholder="vd: PANJA_ATIG123",
            default=default_product[:100] if default_product else None,
            max_length=100,
            required=False,
        )
        self.add_item(self.product_input)

    async def on_submit(self, interaction: discord.Interaction):
        embed = self.message.embeds[0]
        if embed.color and embed.color.value == COLOR_QUEUE_DONE:
            return await interaction.response.send_message("Đơn này đã được đánh dấu hoàn thành rồi.", ephemeral=True)

        buyer_field  = next((f.value for f in embed.fields if f.name == "👤 Khách"), "")
        seller_field = next((f.value for f in embed.fields if f.name == "🧑 Seller"), "")
        amount_field = next((f.value for f in embed.fields if f.name == "💰 Số tiền"), "")
        code_field   = next((f.value for f in embed.fields if f.name == "📝 Mã CK"), "")
        buyer_id     = _extract_mention_id(buyer_field)
        seller_id    = _extract_mention_id(seller_field)
        amount       = _extract_amount_digits(amount_field)
        buyer_mention  = f"<@{buyer_id}>" if buyer_id else "*(không rõ)*"
        seller_mention = f"<@{seller_id}>" if seller_id else ""

        # FIX: trước đây LUÔN sinh mã CK mới ở đây, không liên quan gì tới mã THẬT đã in
        # trên QR gửi cho khách (2 hệ thống tách rời nhau). Giờ đọc lại đúng mã đã dùng
        # (field "📝 Mã CK" của embed hàng đợi) — hóa đơn phản ánh đúng giao dịch bank thật.
        # Fallback sinh mã mới CHỈ áp dụng cho đơn hàng đợi gửi TRƯỚC bản cập nhật này
        # (chưa có field "📝 Mã CK"), tránh lỗi khi bấm Hoàn thành trên đơn cũ còn tồn đọng.
        transfer_code = code_field.strip("`") if code_field else gen_transfer_code()

        product        = self.product_input.value.strip()
        order_number   = get_next_shop_order_number()

        embed.color = COLOR_QUEUE_DONE
        for i, field in enumerate(embed.fields):
            if field.name == "📌 Trạng thái":
                embed.set_field_at(
                    i, name=field.name,
                    value=f"✅ Đã hoàn thành bởi {interaction.user.mention} • Hóa đơn #{order_number}",
                    inline=False,
                )
                break

        view = QueueOrderView()
        view.done_btn.disabled = True

        try:
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception:
            await self.message.edit(embed=embed, view=view)
            await interaction.response.send_message("✅ Đã hoàn thành đơn hàng.", ephemeral=True)

        receipt = await build_receipt_embed(
            order_number=order_number, buyer_id=buyer_id,
            product=product, amount=amount, approver=interaction.user,
            transfer_code=transfer_code, guild=interaction.guild, seller_id=seller_id,
        )
        proof_ch_id = get_cfg_proof_channel()
        if proof_ch_id:
            proof_channel = await get_or_fetch_channel(interaction.client, proof_ch_id)
            if proof_channel:
                try:
                    await proof_channel.send(embed=receipt)
                except Exception as e:
                    log.warning(f"[SHOP] ⚠️ Không gửi được hóa đơn vào kênh proof: {e}")
        else:
            log.warning("[SHOP] ⚠️ Chưa cấu hình kênh proof (Proof Channel trong .st) — bỏ qua gửi hóa đơn công khai.")

        await send_log(
            interaction.client, "SHOP_QUEUE_DONE", "Đơn hàng đợi đã hoàn thành",
            fields=[
                ("🙋 Khách hàng", buyer_mention, True),
                ("🧑 Seller", seller_mention or _uname_plain(interaction.user), True),
                ("📦 Sản phẩm", product or "(không rõ)", True),
                ("🧾 Số hóa đơn", f"#{order_number}", True),
            ],
            user=interaction.user, guild_id=interaction.guild_id,
        )


class QueueOrderView(GuildContextView):
    """Persistent view — không gắn order_code, chỉ sửa trực tiếp embed của message được bấm."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Hoàn thành", emoji="✅", style=discord.ButtonStyle.success, custom_id="shop_queue_done")
    async def done_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền bấm nút này.", ephemeral=True)

        embed = interaction.message.embeds[0]
        if embed.color and embed.color.value == COLOR_QUEUE_DONE:
            return await interaction.response.send_message("Đơn này đã được đánh dấu hoàn thành rồi.", ephemeral=True)

        ticket_field = next((f.value for f in embed.fields if f.name == "🎫 Ticket"), "")
        default_product = ""
        m = re.search(r"<#(\d+)>", ticket_field or "")
        if m:
            ch = interaction.guild.get_channel(int(m.group(1)))
            if ch:
                default_product = ch.name

        await interaction.response.send_modal(ReceiptProductModal(interaction.message, default_product))


_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

SETBANK_USAGE = (
    "**`.setbank` — admin gán bank cho seller** (mỗi dòng = 1 seller, tối đa 25 dòng):\n"
    "`.setbank <@seller|ID> <mã NH hoặc BIN> <số TK> [tên chủ TK]`\n"
    "Ví dụ: `.setbank 123456789012345678 970422 0123456789 NGUYEN VAN A`\n"
    "› Mã BIN thường gặp: MB `970422` · Vietcombank `970436` · VietinBank `970415` · BIDV `970418` · Techcombank `970407` · "
    "ACB `970416` · TPBank `970423` · VPBank `970432` · Sacombank `970403`\n"
    "› Số TK lấy **số in trên ảnh QR/app ngân hàng** (một số ngân hàng như MB nhúng mã định danh vào QR nên bot không đọc được số TK)\n"
    "› Tên chủ TK có thể bỏ trống (tự IN HOA, bỏ dấu). Gán lại cho cùng seller sẽ ghi đè bank cũ."
)

# Ví dụ nhập tay dùng GIÁ TRỊ THẬT (không dùng chữ mẫu như `ma_bank` — người dùng hay copy nguyên văn)
BANK_TYPED_EXAMPLE = '`.shopbank "MB Bank" mbbank 0123456789 "NGUYEN VAN A"` (tên NH · mã NH · SỐ TK · tên chủ TK)'

QR_ERRORS = {
    "no_qr": "❌ Không đọc được mã QR trong ảnh. Gửi ảnh **nét, đủ sáng, không bị cắt viền** — chụp màn hình mã QR nhận tiền trong app ngân hàng.",
    "not_vietqr": "❌ Đây không phải mã **VietQR ngân hàng** (có thể là QR ví MoMo/ZaloPay hoặc link). Hãy dùng QR nhận tiền / QR tài khoản của app ngân hàng.",
    "bad_crc": "❌ Mã QR bị lỗi (sai mã kiểm tra) — ảnh có thể bị mờ hoặc chỉnh sửa. Chụp lại màn hình QR rồi gửi lại.",
    "card": "❌ Đây là QR **số thẻ**, bot cần QR **tài khoản**. Trong app ngân hàng chọn mã QR nhận tiền theo số tài khoản.",
    "bad_account": "❌ QR thiếu/sai mã ngân hàng hoặc số tài khoản — dùng QR nhận tiền chuẩn VietQR của app ngân hàng.",
}


async def _find_qr_attachment(ctx: commands.Context):
    """Ảnh QR: đính kèm ngay trong tin nhắn gõ lệnh, hoặc trong tin nhắn mà lệnh đang REPLY tới."""
    candidates = list(ctx.message.attachments)
    ref = ctx.message.reference
    if not candidates and ref:
        msg = ref.resolved if isinstance(ref.resolved, discord.Message) else None
        if msg is None and ref.message_id:
            try:
                msg = await ctx.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                msg = None
        if msg:
            candidates = list(msg.attachments)
    for a in candidates:
        if (a.content_type or "").startswith("image/") or (a.filename or "").lower().endswith(_IMAGE_EXT):
            return a
    return None


class ShopOrdersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Đăng ký lại persistent view để nút "Hoàn thành" sống sau khi bot restart.
        self.bot.add_view(QueueOrderView())
        # Đăng ký callback nhận webhook thanh toán SePay — xem verify_server.py
        # (route /webhook/sepay) + _handle_sepay_webhook() bên dưới.
        from verify_server import register_payment_callback
        register_payment_callback(self._handle_sepay_webhook, ready=is_data_cache_ready)

    # ── SePay: helper báo admin / resolve user ────────────────────────────
    async def _alert_admins(self, text: str) -> None:
        """DM cho ADMIN_IDS khi thanh toán rơi vào tình huống BẤT THƯỜNG cần người xử lý tay.
        FIX (v4.59.1): trước đây các nhánh này chỉ log.warning trên Railway → tiền đã vào
        nhưng không ai trong Discord biết."""
        log.warning(f"[SEPAY][ALERT] {text}")
        for admin_id in ADMIN_IDS:
            try:
                user = await self.bot.fetch_user(admin_id)
                await user.send(text[:1900])
            except Exception as e:
                log.warning(f"[SEPAY] Không DM được admin {admin_id}: {e}")

    async def _resolve_user(self, guild, user_id):
        """Member (cache/fetch) → nếu đã rời server thì fetch_user. None nếu không tìm được."""
        if not user_id:
            return None
        member = await _resolve_member(guild, user_id)
        if member:
            return member
        try:
            return await self.bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    @staticmethod
    def _payload_brief(payload: dict) -> str:
        content = str(payload.get("content") or payload.get("description") or "")[:150].replace("`", "'")
        return (f"id=`{payload.get('id')}` · số tiền=`{payload.get('transferAmount')}` · "
                f"TK nhận=`{payload.get('accountNumber')}` · nội dung=`{content}`")

    async def _handle_sepay_webhook(self, payload: dict) -> None:
        """Callback đăng ký với verify_server.py — nhận payload THÔ từ SePay (đã lọc sẵn
        transferType == "in" ở route). Mọi lỗi đều được báo admin qua DM (không còn nuốt im lặng)."""
        try:
            await self._process_sepay_payload(payload)
        except Exception as e:
            log.exception("[SEPAY] Lỗi không mong muốn khi xử lý webhook")
            await self._alert_admins(
                "🚨 **SePay — lỗi xử lý 1 giao dịch, cần kiểm tra tay.**\n"
                f"{self._payload_brief(payload)}\nLỗi: `{type(e).__name__}: {str(e)[:200]}`"
            )

    async def _process_sepay_payload(self, payload: dict) -> None:
        webhook_id = payload.get("id")
        if webhook_id is not None and is_webhook_id_processed(webhook_id):
            return  # SePay tự retry cùng 1 giao dịch — đã xử lý rồi thì bỏ qua

        content = str(payload.get("content") or payload.get("description") or "")
        # Ưu tiên field `code` SePay TỰ bóc tách (đã cấu hình khớp DH+6 số của gen_transfer_code()),
        # fallback dò chuỗi con trong `content` thô cho webhook cũ/trường hợp `code` rỗng.
        code = (payload.get("code") or "").strip().upper()
        order = get_pending_shop_order(code) if code else None
        if not order:
            order = find_pending_shop_order_by_content(content)
        if not order:
            log.info(f"[SEPAY] ℹ️ Không khớp đơn đang chờ nào — code: {code!r}, content: {content!r}")
            # Có mã dạng DHxxxxxx nhưng không có đơn chờ (đơn hết hạn / đã xử lý / bị xoá) → tiền
            # đã vào mà không ai biết: báo admin. Chuyển khoản không mã thì bỏ qua như cũ.
            if _PAYMENT_CODE_RE.search(f"{code} {content}"):
                await self._alert_admins(
                    "⚠️ **SePay — nhận tiền với mã CK nhưng KHÔNG có đơn chờ khớp** "
                    "(đơn hết hạn, đã xử lý hoặc bị xoá?). Cần đối chiếu tay.\n" + self._payload_brief(payload)
                )
                if webhook_id is not None:
                    mark_webhook_id_processed(webhook_id)
            return

        account_number = str(payload.get("accountNumber") or "")
        if order.get("account_number") and account_number and str(order["account_number"]) != account_number:
            await self._alert_admins(
                f"⚠️ **SePay — đơn `{order['ref_code']}` khớp mã nhưng LỆCH số TK nhận** "
                f"(đơn: `{order.get('account_number')}` / webhook: `{account_number}`). "
                "Không tự xác nhận, đơn vẫn chờ.\n" + self._payload_brief(payload)
            )
            if webhook_id is not None:
                mark_webhook_id_processed(webhook_id)
            return

        # BẮT BUỘC so `transferAmount` (số tiền THẬT SePay báo đã nhận) với order["amount"].
        transfer_amount = payload.get("transferAmount")
        try:
            transfer_amount = int(transfer_amount)
        except (TypeError, ValueError):
            transfer_amount = None
        expected_amount = int(order.get("amount", 0))
        if transfer_amount is None or transfer_amount < expected_amount:
            # FIX: trước đây chỉ log.warning; giờ báo admin và đánh dấu webhook đã xử lý (tránh
            # báo lặp). Đơn vẫn nằm trong _shop_pending_orders để admin đối chiếu/xử lý tay.
            await self._alert_admins(
                f"⚠️ **SePay — số tiền LỆCH** cho đơn `{order['ref_code']}`: cần **{expected_amount:,}**, "
                f"nhận **{transfer_amount}**. KHÔNG tự xác nhận — đơn vẫn chờ.\n" + self._payload_brief(payload)
            )
            if webhook_id is not None:
                mark_webhook_id_processed(webhook_id)
            return

        ref_code = order["ref_code"]
        # Claim bằng pop (đồng bộ, không có await giữa kiểm tra và xoá) — trả None nghĩa là đã có
        # 1 lần gọi khác xử lý rồi. Đánh dấu webhook ĐÃ XỬ LÝ ngay sau khi claim thành công
        # (không phải trước khi khớp đơn như bản cũ).
        order = pop_pending_shop_order(ref_code)
        if not order:
            return
        if webhook_id is not None:
            mark_webhook_id_processed(webhook_id)

        try:
            problems = await self._notify_paid_order(order, ref_code, transfer_amount, expected_amount)
        except Exception as e:
            log.exception(f"[SEPAY] Lỗi khi thông báo đơn {ref_code}")
            problems = [f"lỗi không mong muốn: {type(e).__name__}: {str(e)[:150]}"]

        if problems:
            # Đơn ĐÃ được thanh toán + đã bị lấy ra khỏi hàng chờ → admin phải biết để xử lý tay.
            await self._alert_admins(
                f"🚨 **SePay — đơn `{ref_code}` ĐÃ THANH TOÁN ({transfer_amount:,}đ) nhưng thông báo không đầy đủ:**\n"
                + "\n".join(f"• {x}" for x in problems)
                + f"\nServer `{order.get('guild_id')}` · kênh ticket `{order.get('channel_id')}` · "
                  f"buyer `{order.get('buyer_id')}` · seller `{order.get('seller_id')}`\n"
                + self._payload_brief(payload)
            )

    async def _notify_paid_order(self, order: dict, ref_code: str, transfer_amount: int,
                                 expected_amount: int) -> list[str]:
        """Gửi xác nhận vào ticket + hàng đợi. Trả về danh sách vấn đề (rỗng = xong trọn vẹn)."""
        problems: list[str] = []
        set_current_guild(order["guild_id"])
        guild = self.bot.get_guild(order["guild_id"])
        if not guild:
            return ["bot không còn ở server của đơn này"]

        # Đơn do AutoBuy (cogs/autobuy.py) tạo → TỰ GIAO tài khoản thay vì đẩy vào hàng đợi `.done`.
        if order.get("autobuy_username"):
            ab = self.bot.get_cog("AutoBuyCog")
            if not ab:
                return ["cog AutoBuy chưa load trên bot này — không tự giao được tài khoản"]
            return await ab.on_paid(order, transfer_amount, expected_amount)

        channel = await get_or_fetch_channel(self.bot, order["channel_id"])
        seller = await self._resolve_user(guild, order.get("seller_id"))
        buyer = await self._resolve_user(guild, order.get("buyer_id"))
        if not channel:
            problems.append("kênh ticket đã bị xoá / bot không truy cập được")
        if not seller:
            problems.append("không tìm thấy seller")
        if not buyer:
            problems.append("không tìm thấy buyer")
        if not (channel and seller and buyer):
            return problems

        if transfer_amount > expected_amount:
            log.info(f"[SEPAY] ℹ️ Order {ref_code} nhận THỪA ({transfer_amount} > {expected_amount}) — "
                     f"vẫn confirm bình thường, admin tự đối chiếu chênh lệch.")
        try:
            await channel.send(embed=build_payment_confirmed_embed(seller, buyer, order["amount"], ref_code))
        except Exception as e:
            problems.append(f"không gửi được xác nhận vào ticket: {e}")
        try:
            await send_to_queue(self.bot, seller, buyer, channel, order["amount"], ref_code)
        except Exception as e:
            problems.append(f"không gửi được vào hàng đợi: {e}")
        return problems

    @commands.command(name="setqueue")
    async def setqueue_cmd(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Dùng: .setqueue #kênh — đặt kênh hàng đợi đơn hàng."""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ Chỉ admin mới có quyền.")
        if not channel:
            current_id = get_cfg_queue_channel()
            current = f"<#{current_id}>" if current_id else "*(chưa cài)*"
            return await ctx.reply(f"Kênh hàng đợi hiện tại: {current}\nDùng: `.setqueue #kênh` để đổi.")
        save_cfg_queue_channel(channel.id)
        await ctx.reply(f"✅ Đã đặt kênh hàng đợi: {channel.mention}")

    # NOTE (v4.60.0): lệnh `.bxh` (bảng xếp hạng chi tiêu) đã chuyển sang cogs/leaderboard.py —
    # có nút "Thứ Hạng Của Tôi" / "Làm Mới" và bảng tự cập nhật. Đừng thêm lại ở đây (trùng tên lệnh).

    @commands.command(name="shoporderno")
    async def shoporderno_cmd(self, ctx: commands.Context, number: int = None):
        """Dùng: .shoporderno <số> — chỉnh số hóa đơn kế tiếp (vd để khớp hệ thống cũ)."""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ Chỉ admin mới có quyền.")
        if number is None:
            current = load_data().get("shop_order_counter", 0)
            return await ctx.reply(f"Số hóa đơn hiện tại: `#{current}` — hóa đơn tiếp theo sẽ là `#{current + 1}`.\nDùng: `.shoporderno <số>` để đổi.")
        set_shop_order_counter(number)
        await ctx.reply(f"✅ Đã đặt số hóa đơn — hóa đơn tiếp theo sẽ là `#{number + 1}`.")

    # ── .shopbank / .listbank ────────────────────────────────────────────────────
    # FIX kiến trúc: trước đây 1 bank DUY NHẤT dùng chung cho cả guild, chỉ admin cài
    # được. Giờ MỖI SELLER (admin hoặc has_ticket_access — có role xem được ít nhất 1
    # loại ticket, KHÔNG có nghĩa xem được TẤT CẢ loại ticket) tự đăng ký bank CỦA RIÊNG
    # mình — .done ai gõ thì QR dùng đúng bank người đó, tiền vào thẳng TK người xử lý
    # đơn thay vì qua 1 TK chung.

    @commands.command(name="shopbank")
    async def shopbank_cmd(self, ctx: commands.Context, *, args: str = None):
        """Dùng: .shopbank + ĐÍNH KÈM ẢNH QR ngân hàng (bot tự đọc) — hoặc nhập tay:
        .shopbank "<tên hiển thị>" <bank_code_vietqr> <số TK> "<chủ TK>" ["<ghi chú>"] [template]
        Đăng ký/cập nhật bank CỦA BẠN — mỗi seller 1 bank riêng, .done bạn gõ dùng đúng bank này.
        bank_code_vietqr: mã ngân hàng theo VietQR, vd vietinbank, mbbank, vietcombank, tpbank...
        Danh sách mã: https://api.vietqr.io/v2/banks
        """
        if not (is_admin(ctx.author) or has_ticket_access(ctx.author)):
            return await ctx.reply("❌ Chỉ admin hoặc seller mới dùng được lệnh này.")

        # 📷 Chỉ cần gửi ảnh QR ngân hàng: `.shopbank` + đính kèm ảnh (hoặc reply vào ảnh). Gõ đủ 4 tham số như cũ thì
        # giữ nguyên cách nhập tay; có ảnh mà tham số < 4 thì phần chữ (nếu có) được coi là TÊN CHỦ TK.
        # ✏️ `.shopbank name <TÊN CHỦ TK>` — chỉ đặt/sửa TÊN CHỦ TK của bank đã lưu (QR ngân hàng thường KHÔNG chứa tên)
        name_m = re.match(r"^(?:name|ten|tên)\s+(.+)$", (args or "").strip(), flags=re.I | re.S)
        qr_att = await _find_qr_attachment(ctx)
        if name_m and not qr_att:
            return await self._set_holder(ctx, name_m.group(1))
        if qr_att:
            typed_full = False
            if args and not name_m:
                try:
                    typed_full = len(shlex.split(args)) >= 4
                except ValueError:
                    typed_full = False
            if not typed_full:
                holder_arg = name_m.group(1) if name_m else (args or "")
                return await self._register_bank_from_qr(ctx, qr_att, holder_arg.strip().strip('"'))

        if not args:
            bank = get_shop_orders_bank(ctx.author.id)
            if not bank:
                return await ctx.reply(
                    "📭 Bạn chưa đăng ký bank nào.\n"
                    'Đăng ký nhanh: gõ `.shopbank` và **đính kèm ảnh QR nhận tiền** của ngân hàng (bot tự đọc).\n'
                    f'Hoặc nhập tay: {BANK_TYPED_EXAMPLE}'
                )
            problem = bank_problem(bank)
            warn = (f"⚠️ **Bank đang lưu bị lỗi — {problem}.** QR thanh toán sẽ không hiện cho tới khi sửa: "
                    "gõ `.shopbank` kèm ảnh QR ngân hàng để đăng ký lại.\n\n") if problem else ""
            if not problem and not bank.get("account_holder"):
                warn = ("ℹ️ Chưa có **tên chủ TK** (QR ngân hàng thường không chứa tên) — QR thanh toán vẫn dùng được. "
                        "Muốn hiện tên: `.shopbank name NGUYEN VAN A`\n\n")
            return await ctx.reply(
                warn + "**Bank của bạn hiện tại:**\n"
                f"› Tên hiển thị: `{bank.get('bank_name', '?')}`\n"
                f"› Mã VietQR: `{bank.get('bank_code', '?')}`\n"
                f"› Số TK: `{bank.get('account_number', '?')}`\n"
                f"› Chủ TK: `{bank.get('account_holder', '?')}`\n"
                f"› Ghi chú: `{bank.get('default_content') or '(không có)'}`\n"
                f"› Template: `{bank.get('template', 'compact2')}`\n\n"
                f'Cập nhật: {BANK_TYPED_EXAMPLE}'
            )

        try:
            parts = shlex.split(args)
        except ValueError:
            return await ctx.reply("❌ Cú pháp lỗi, kiểm tra lại dấu ngoặc kép.")
        if len(parts) < 4:
            return await ctx.reply(
                '❌ Dùng: `.shopbank "<tên hiển thị>" <bank_code_vietqr> <số TK> "<chủ TK>" ["<ghi chú>"] [template]`\n'
                f'Ví dụ: {BANK_TYPED_EXAMPLE}'
            )

        bank_name, bank_code, account_number, account_holder = parts[0], parts[1], parts[2], parts[3]
        err = validate_bank(bank_code, account_number, account_holder)
        if err:                                   # KHÔNG lưu dữ liệu sai (từng có bank lưu số TK = "ma_bank" → QR không hiện ảnh)
            return await ctx.reply(
                f"❌ Chưa lưu — {err}.\n"
                f"› Bot đọc được: Tên NH `{bank_name}` · Mã NH `{bank_code}` · Số TK `{account_number}` · Chủ TK `{account_holder}`\n"
                f"› Thứ tự đúng: {BANK_TYPED_EXAMPLE}\n"
                "› **Dễ nhất:** gõ `.shopbank` và đính kèm **ảnh QR nhận tiền** của ngân hàng — bot tự đọc, không cần nhập gì."
            )
        account_number = normalize_account(account_number)
        account_holder = normalize_holder(account_holder)
        default_content = parts[4] if len(parts) > 4 else ""
        template = parts[5] if len(parts) > 5 else "compact2"
        save_shop_orders_bank(
            ctx.author.id,
            bank_name=bank_name, bank_code=bank_code.lower(),
            account_number=account_number, account_holder=account_holder,
            default_content=default_content, template=template,
            registered_at=datetime.now(timezone.utc).isoformat(),
        )
        await ctx.reply(
            f"✅ Đã lưu bank **của bạn**: **{bank_name}** (`{bank_code}`) — `{account_number}` — {account_holder}\n"
            f"› Từ giờ `.done` do bạn gõ sẽ tự dùng bank này. Xem toàn bộ danh sách: `.listbank`\n"
            f"› Lưu ý: nội dung CK trên QR giờ TỰ SINH riêng theo từng đơn để đối soát — "
            f"tham số ghi chú ở trên chỉ để bạn tự nhớ, không còn in lên QR nữa."
        )

    async def _set_holder(self, ctx: commands.Context, raw: str) -> None:
        """`.shopbank name <tên>` — đặt tên chủ TK cho bank ĐÃ lưu (chuẩn hoá: in hoa, bỏ dấu)."""
        bank = get_shop_orders_bank(ctx.author.id)
        if bank_problem(bank):
            return await ctx.reply("❌ Bạn chưa có bank hợp lệ để đặt tên — gõ `.shopbank` kèm **ảnh QR ngân hàng** trước.")
        name = normalize_holder(raw)
        if not (2 <= len(name) <= 60) or normalize_account(name).isdigit():
            return await ctx.reply("❌ Tên chủ TK không hợp lệ — gõ ví dụ `.shopbank name NGUYEN VAN A` (chữ, không phải dãy số).")
        save_shop_orders_bank(ctx.author.id, account_holder=name)
        await ctx.reply(f"✅ Đã đặt tên chủ TK: **{name}** — QR thanh toán sẽ hiện tên này. Xem lại: `.shopbank`")

    async def _register_bank_from_qr(self, ctx: commands.Context, att: discord.Attachment, holder: str) -> None:
        """Đọc ảnh VietQR → lưu bank CỦA NGƯỜI GÕ LỆNH (giống `.shopbank` nhập tay, bank_code = mã BIN)."""
        if att.size and att.size > MAX_IMAGE_BYTES:
            return await ctx.reply("❌ Ảnh quá lớn (tối đa 8MB) — chụp màn hình QR rồi gửi lại.")
        try:
            data = await att.read()
            texts = await asyncio.to_thread(decode_qr_texts, data)
        except QRDecoderMissing as e:
            log.error(f"[SHOPBANK] {e}")
            return await ctx.reply("❌ Bot chưa cài thư viện đọc QR (`pip install zxing-cpp`) — nhờ admin cài, hoặc nhập tay: "
                                   f'{BANK_TYPED_EXAMPLE}')
        except Exception as e:
            log.warning(f"[SHOPBANK] không đọc được ảnh: {e}")
            return await ctx.reply("❌ Không mở được ảnh này — gửi lại ảnh PNG/JPG của mã QR.")

        info = pick_vietqr(texts)
        if not info["ok"]:
            if info["error"] == "alias":
                bin_ = info["bin"]
                return await ctx.reply(
                    f"❌ QR của **{bank_name_from_bin(bin_)}** (BIN `{bin_}`) dùng **mã định danh** thay cho số tài khoản nên bot "
                    "không lấy được số TK từ QR (số TK thật chỉ in trên hình, không nằm trong mã).\n"
                    f"› Nhập tay kèm **số TK in trên ảnh**: `.shopbank \"{bank_name_from_bin(bin_)}\" {bin_} <SỐ TK> \"TÊN CHỦ TK\"`\n"
                    f"› Hoặc nhờ admin gán giúp: `.setbank <@seller|ID> {bin_} <SỐ TK> <TÊN CHỦ TK>`")
            return await ctx.reply(QR_ERRORS.get(info["error"], QR_ERRORS["no_qr"]))

        old = get_shop_orders_bank(ctx.author.id) or {}
        bank_name = bank_name_from_bin(info["bin"])
        holder = normalize_holder(holder)
        account_holder = holder or normalize_holder(info["holder"]) or (old.get("account_holder") if old.get("account_number") == info["account_number"] else "") or ""
        save_shop_orders_bank(
            ctx.author.id,
            bank_name=bank_name, bank_code=info["bin"], account_number=info["account_number"],
            account_holder=account_holder, default_content=old.get("default_content", ""),
            template=old.get("template") or "compact2",
            registered_at=datetime.now(timezone.utc).isoformat(), source="qr",
        )
        lines = [
            f"✅ Đã đăng ký bank **của bạn** từ ảnh QR: **{bank_name}** (BIN `{info['bin']}`) — `{info['account_number']}` — "
            f"{account_holder or '*(QR không có tên chủ TK)*'}",
            "› Từ giờ QR thanh toán (`.done`, Auto Buy) dùng đúng bank này. Xem lại: `.shopbank` · toàn bộ: `.listbank`",
        ]
        if not account_holder:
            lines.append("› QR này không chứa tên chủ TK nên QR thanh toán sẽ không hiện tên (vẫn thanh toán bình thường). "
                         "Muốn hiện tên: gõ `.shopbank name NGUYEN TAN HOANG QUAN` (tên in trên ảnh QR, không cần gửi lại ảnh).")
        lines.append("› Nhớ kiểm tra số TK ở trên có ĐÚNG không — tiền khách chuyển sẽ vào đúng tài khoản này.")
        await ctx.reply("\n".join(lines))
        if att in ctx.message.attachments:        # ảnh QR do chính người gõ gửi → xoá cho gọn (tin trả lời ở trên đã giữ thông tin)
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

    @commands.command(name="setbank")
    async def setbank_cmd(self, ctx: commands.Context, *, args: str = None):
        """.setbank <@seller|ID> <mã NH|BIN> <số TK> [tên chủ TK] — ADMIN gán bank cho seller. Mỗi dòng = 1 seller."""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
        lines = [ln.strip() for ln in (args or "").replace("```", "").splitlines() if ln.strip()]
        if not lines:
            return await ctx.reply(SETBANK_USAGE)
        if len(lines) > 25:
            return await ctx.reply("❌ Tối đa 25 dòng (25 seller) mỗi lần.")
        out, ok = [], 0
        for n, line in enumerate(lines, 1):
            done, text = await self._setbank_line(ctx, line)
            ok += 1 if done else 0
            out.append(text if done else f"❌ Dòng {n}: {text}")
        head = f"**Gán bank xong: {ok}/{len(lines)} thành công**\n" if len(lines) > 1 else ""
        msg = head + "\n".join(out)
        await ctx.reply(msg[:1990], allowed_mentions=discord.AllowedMentions.none())

    async def _setbank_line(self, ctx: commands.Context, line: str) -> tuple[bool, str]:
        parts = line.split(None, 3)
        if len(parts) < 3:
            return False, f"thiếu thông tin — cần `<@seller|ID> <mã NH|BIN> <số TK> [tên chủ TK]`. Dòng: `{line[:70]}`"
        m = re.fullmatch(r"<@!?(\d{15,20})>|(\d{15,20})", parts[0])
        if not m:
            return False, f"`{parts[0][:30]}` không phải @mention/ID Discord hợp lệ (ID là dãy 17–20 chữ số)"
        uid = int(m.group(1) or m.group(2))
        member = ctx.guild.get_member(uid)
        if member is None:
            try:
                member = await ctx.guild.fetch_member(uid)
            except (discord.NotFound, discord.HTTPException):
                member = None
        if member is None:
            return False, f"không tìm thấy thành viên ID `{uid}` trong server này (gõ nhầm ID?)"

        code, account = parts[1], parts[2]
        holder = normalize_holder(parts[3]) if len(parts) > 3 else ""
        err = validate_bank(code, account, holder)
        if err:
            return False, f"{member.display_name}: {err}"
        account = normalize_account(account)
        old = get_shop_orders_bank(uid) or {}
        bank_name = bank_name_from_bin(code) if (code.isdigit() and len(code) == 6) else code.upper()
        save_shop_orders_bank(
            uid, bank_name=bank_name, bank_code=code.lower() if not code.isdigit() else code, account_number=account,
            account_holder=holder, default_content=old.get("default_content", ""),
            template=old.get("template") or "compact2",
            registered_at=datetime.now(timezone.utc).isoformat(), source="admin", set_by=ctx.author.id,
        )
        notes = []
        try:
            from cogs.seller import is_active_seller
            if not (is_admin(member) or is_active_seller(ctx.guild.id, uid)):
                notes.append("⚠️ chưa có gói seller (`.seller add`) nên chưa đăng bán Auto Buy được")
        except Exception:
            pass
        if old.get("account_number") and old.get("account_number") != account:
            notes.append(f"đã thay bank cũ …{str(old['account_number'])[-4:]}")
        if not holder:
            notes.append("chưa có tên chủ TK")
        return True, (f"✅ {member.mention} — **{bank_name}** (`{code}`) · `{account}` · {holder or '*(chưa có tên)*'}"
                      + (f" — {'; '.join(notes)}" if notes else ""))

    @commands.command(name="listbank")
    async def listbank_cmd(self, ctx: commands.Context):
        """Dùng: .listbank — liệt kê toàn bộ bank các seller đã đăng ký qua .shopbank."""
        if not (is_admin(ctx.author) or has_ticket_access(ctx.author)):
            return await ctx.reply("❌ Chỉ admin hoặc seller mới dùng được lệnh này.")

        banks = get_all_shop_orders_banks()
        if not banks:
            return await ctx.reply("📭 Chưa seller nào đăng ký bank. Dùng `.shopbank` để đăng ký.")

        lines = []
        for uid_str, bank in banks.items():
            member = ctx.guild.get_member(int(uid_str))
            name = member.mention if member else f"`ID:{uid_str}`"
            lines.append(
                f"**{name}** — {bank.get('bank_name', '?')} (`{bank.get('bank_code', '?')}`) — "
                f"`{bank.get('account_number', '?')}` — {bank.get('account_holder', '?')}"
            )

        chunks = [lines[i:i + 10] for i in range(0, len(lines), 10)]
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"🏦 Danh sách Bank đã đăng ký ({len(banks)}) — Trang {i + 1}/{len(chunks)}",
                description="\n".join(chunk),
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )
            await ctx.reply(embed=embed)

    @commands.command(name="delbank", aliases=["removebank"])
    async def delbank_cmd(self, ctx: commands.Context, member: discord.Member = None):
        """Dùng: .delbank [@seller] — xoá bank đã đăng ký (thêm nhầm/sai thông tin).
        Không truyền @seller = tự xoá bank CỦA BẠN. Truyền @seller = chỉ admin xoá được
        bank của NGƯỜI KHÁC (seller thường không được xoá bank của seller khác)."""
        if not (is_admin(ctx.author) or has_ticket_access(ctx.author)):
            return await ctx.reply("❌ Chỉ admin hoặc seller mới dùng được lệnh này.")

        target = member or ctx.author
        if target.id != ctx.author.id and not is_admin(ctx.author):
            return await ctx.reply("❌ Bạn chỉ xoá được bank CỦA CHÍNH BẠN — cần admin để xoá bank người khác.")

        bank = get_shop_orders_bank(target.id)
        if not bank:
            return await ctx.reply(f"📭 {target.mention} chưa đăng ký bank nào — không có gì để xoá.")

        delete_shop_orders_bank(target.id)
        await ctx.reply(
            f"✅ Đã xoá bank của {target.mention}: {bank.get('bank_name', '?')} "
            f"(`{bank.get('account_number', '?')}`).\n"
            f"› `.done` do {target.mention} gõ từ giờ sẽ báo chưa đăng ký bank cho tới khi `.shopbank` lại."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopOrdersCog(bot))
