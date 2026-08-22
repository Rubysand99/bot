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

import re
import random
import string
import shlex
import logging
from urllib.parse import quote
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ui import TextInput

from core.data import (
    ADMIN_IDS, fmt_amount, is_staff_member, get_or_fetch_channel, _uname_plain,
    set_current_guild,
    get_cfg_shop_orders_enabled,
    get_shop_orders_bank, save_shop_orders_bank, get_all_shop_orders_banks,
    has_ticket_access,
    save_pending_shop_order, find_pending_shop_order_by_content, pop_pending_shop_order,
    is_webhook_id_processed, mark_webhook_id_processed,
    get_cfg_queue_channel, save_cfg_queue_channel,
    get_cfg_proof_channel,
    get_next_shop_order_number, set_shop_order_counter,
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


def gen_transfer_code(name: str) -> str:
    """Sinh nội dung CK kiểu <tên>-<mã random 6 ký tự>. Giờ dùng làm addInfo THẬT của QR
    (không chỉ để trang trí hóa đơn như trước) nên phải: chỉ chữ/số (bank không làm hỏng
    dấu/khoảng trắng lạ), đủ ngắn (đa số app ngân hàng giới hạn nội dung CK), đủ random để
    không trùng 2 đơn cùng lúc (36^6 ≈ 2.1 tỷ tổ hợp)."""
    safe_name = re.sub(r"[^A-Za-z0-9_]", "", name or "")[:20] or "KHACH"
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{safe_name}-{rand}"


def build_receipt_embed(order_number: str, buyer_mention: str, product: str, amount: int,
                         approver: discord.abc.User, transfer_code: str,
                         seller_mention: str = "") -> discord.Embed:
    """Hóa đơn công khai kiểu ảnh mẫu — gửi vào kênh proof khi đơn hàng đợi được đánh dấu
    Hoàn thành. `transfer_code` giờ là mã CK THẬT đã in trên QR (đọc lại từ field
    "📝 Mã CK" của embed hàng đợi) — KHÔNG còn sinh mã mới không liên quan như trước."""
    e = discord.Embed(
        title=f"🧾 HÓA ĐƠN THANH TOÁN MUA HÀNG #{order_number}",
        description="Giao dịch đã được xác nhận hoàn tất thành công bởi Admin!",
        color=COLOR_QUEUE_DONE,
        timestamp=datetime.now(timezone.utc),
    )
    e.add_field(name="👤 Khách hàng", value=buyer_mention, inline=False)
    if seller_mention:
        e.add_field(name="🧑 Người bán", value=seller_mention, inline=False)
    e.add_field(name="📦 Sản phẩm", value=product or "*(không rõ)*", inline=False)
    e.add_field(name="💰 Số tiền", value=f"**{fmt_vnd(amount)}**", inline=True)
    e.add_field(name="🧑 Người duyệt", value=approver.mention, inline=True)
    e.add_field(name="📝 Nội dung CK", value=f"`{transfer_code}`", inline=False)
    e.add_field(name="🚀 Trạng thái", value="🟢 Đã giao hàng", inline=False)
    e.set_footer(text="Cảm ơn bạn đã tin tưởng!")
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
            f'`.shopbank "Tên NH" ma_bank SoTK "Chủ TK"` để lần `.done` sau tự có QR.'
        )

    bank_code      = bank.get("bank_code")
    account_number = bank.get("account_number")
    if not bank_code or not account_number:
        return None, None, f"⚠️ Bank của {seller.mention} thiếu mã ngân hàng hoặc số TK — `.shopbank` lại đầy đủ."

    template       = bank.get("template") or "compact2"
    account_holder = bank.get("account_holder", "")

    ref_code = gen_transfer_code(getattr(buyer, "display_name", None) or str(buyer))
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
        buyer_member  = interaction.guild.get_member(buyer_id) if buyer_id else None
        name_for_code = buyer_member.name if buyer_member else "KHACH"
        transfer_code = code_field.strip("`") if code_field else gen_transfer_code(name_for_code)

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

        receipt = build_receipt_embed(
            order_number=order_number, buyer_mention=buyer_mention,
            product=product, amount=amount, approver=interaction.user,
            transfer_code=transfer_code, seller_mention=seller_mention,
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


class ShopOrdersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Đăng ký lại persistent view để nút "Hoàn thành" sống sau khi bot restart.
        self.bot.add_view(QueueOrderView())
        # Đăng ký callback nhận webhook thanh toán SePay — xem verify_server.py
        # (route /webhook/sepay) + _handle_sepay_webhook() bên dưới.
        from verify_server import register_payment_callback
        register_payment_callback(self._handle_sepay_webhook)

    async def _handle_sepay_webhook(self, payload: dict) -> None:
        """Callback đăng ký với verify_server.py — nhận payload THÔ từ SePay (đã lọc sẵn
        transferType == "in" ở route), tự lo dedup + khớp đơn đang chờ + thông báo. Chạy
        trong event loop CHUNG với bot (cùng process, xem docstring verify_server.py)
        nhưng KHÔNG có guild context sẵn — set_current_guild() SAU KHI tra được
        order["guild_id"] từ pending order, cùng pattern với _pending_sold_price
        (core/data.py) vốn cũng phải xử lý ngoài context guild bình thường."""
        webhook_id = payload.get("id")
        if webhook_id is not None and is_webhook_id_processed(webhook_id):
            return  # SePay tự retry cùng 1 giao dịch — đã xử lý rồi thì bỏ qua
        if webhook_id is not None:
            mark_webhook_id_processed(webhook_id)

        content = payload.get("content") or payload.get("description") or ""
        order = find_pending_shop_order_by_content(content)
        if not order:
            log.info(f"[SEPAY] ℹ️ Không khớp đơn đang chờ nào — content: {content!r}")
            return

        account_number = str(payload.get("accountNumber") or "")
        if order.get("account_number") and account_number and str(order["account_number"]) != account_number:
            log.warning(
                f"[SEPAY] ⚠️ Khớp content nhưng LỆCH số TK nhận — bỏ qua để an toàn "
                f"(order={order.get('account_number')} / webhook={account_number})."
            )
            return

        ref_code = order["ref_code"]
        # Claim ngay bằng pop — trả None nghĩa là đã có 1 lần gọi khác xử lý mất rồi
        # (trùng lặp/race hiếm gặp), tránh gửi thông báo/hàng đợi 2 lần cho cùng 1 đơn.
        order = pop_pending_shop_order(ref_code)
        if not order:
            return

        set_current_guild(order["guild_id"])
        guild = self.bot.get_guild(order["guild_id"])
        if not guild:
            log.warning(f"[SEPAY] ⚠️ Bot không còn ở guild {order['guild_id']} — không thông báo được order {ref_code}.")
            return
        channel = await get_or_fetch_channel(self.bot, order["channel_id"])
        seller  = guild.get_member(order["seller_id"])
        buyer   = guild.get_member(order["buyer_id"])
        if not (channel and seller and buyer):
            log.warning(f"[SEPAY] ⚠️ Thiếu channel/seller/buyer để thông báo order {ref_code}.")
            return

        try:
            await channel.send(
                f"✅ **Đã nhận thanh toán** — {fmt_vnd(order['amount'])} từ {buyer.mention}, "
                f"mã CK `{ref_code}`. {seller.mention} xử lý đơn nhé!"
            )
        except Exception as e:
            log.warning(f"[SEPAY] ⚠️ Không gửi được thông báo vào ticket {order['channel_id']}: {e}")

        await send_to_queue(self.bot, seller, buyer, channel, order["amount"], ref_code)

    @commands.command(name="setqueue")
    async def setqueue_cmd(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Dùng: .setqueue #kênh — đặt kênh hàng đợi đơn hàng."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền.")
        if not channel:
            current_id = get_cfg_queue_channel()
            current = f"<#{current_id}>" if current_id else "*(chưa cài)*"
            return await ctx.reply(f"Kênh hàng đợi hiện tại: {current}\nDùng: `.setqueue #kênh` để đổi.")
        save_cfg_queue_channel(channel.id)
        await ctx.reply(f"✅ Đã đặt kênh hàng đợi: {channel.mention}")

    @commands.command(name="bxh", aliases=["leaderboard", "top"])
    async def leaderboard_cmd(self, ctx: commands.Context):
        """Dùng: .bxh — Bảng xếp hạng top 10 chi tiêu nhiều nhất trong server."""
        spent = load_data().get("user_total_spent", {})
        ranking = sorted(
            ((uid, amt) for uid, amt in spent.items() if amt > 0),
            key=lambda kv: kv[1], reverse=True,
        )[:10]

        if not ranking:
            return await ctx.reply("📭 Chưa có ai chi tiêu gì trong server này cả.")

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, amount) in enumerate(ranking):
            icon = medals[i] if i < 3 else "✨"
            member = ctx.guild.get_member(int(uid))
            name = member.mention if member else f"<@{uid}>"
            lines.append(f"{icon} **Top {i + 1}:** {name} — Đã chi: **{fmt_amount(amount)}**")

        embed = discord.Embed(
            title="🏆 BẢNG XẾP HẠNG CHI TIÊU",
            description="\n".join(lines),
            color=0xF1C40F,
            timestamp=datetime.now(timezone.utc),
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.set_footer(text=f"{ctx.guild.name} • Cập nhật lúc")
        await ctx.reply(embed=embed)

    @commands.command(name="shoporderno")
    async def shoporderno_cmd(self, ctx: commands.Context, number: int = None):
        """Dùng: .shoporderno <số> — chỉnh số hóa đơn kế tiếp (vd để khớp hệ thống cũ)."""
        if ctx.author.id not in ADMIN_IDS:
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
        """Dùng: .shopbank "<tên hiển thị>" <bank_code_vietqr> <số TK> "<chủ TK>" ["<ghi chú>"] [template]
        Đăng ký/cập nhật bank CỦA BẠN — mỗi seller 1 bank riêng, .done bạn gõ dùng đúng bank này.
        bank_code_vietqr: mã ngân hàng theo VietQR, vd vietinbank, mbbank, vietcombank, tpbank...
        Danh sách mã: https://api.vietqr.io/v2/banks
        """
        if not (ctx.author.id in ADMIN_IDS or has_ticket_access(ctx.author)):
            return await ctx.reply("❌ Chỉ admin hoặc seller mới dùng được lệnh này.")

        if not args:
            bank = get_shop_orders_bank(ctx.author.id)
            if not bank:
                return await ctx.reply(
                    "📭 Bạn chưa đăng ký bank nào.\n"
                    'Đăng ký: `.shopbank "Vietinbank" vietinbank 0123456789 "Nguyen Van A"`'
                )
            return await ctx.reply(
                "**Bank của bạn hiện tại:**\n"
                f"› Tên hiển thị: `{bank.get('bank_name', '?')}`\n"
                f"› Mã VietQR: `{bank.get('bank_code', '?')}`\n"
                f"› Số TK: `{bank.get('account_number', '?')}`\n"
                f"› Chủ TK: `{bank.get('account_holder', '?')}`\n"
                f"› Ghi chú: `{bank.get('default_content') or '(không có)'}`\n"
                f"› Template: `{bank.get('template', 'compact2')}`\n\n"
                'Cập nhật: `.shopbank "Vietinbank" vietinbank 0123456789 "Nguyen Van A"`'
            )

        try:
            parts = shlex.split(args)
        except ValueError:
            return await ctx.reply("❌ Cú pháp lỗi, kiểm tra lại dấu ngoặc kép.")
        if len(parts) < 4:
            return await ctx.reply(
                '❌ Dùng: `.shopbank "<tên hiển thị>" <bank_code_vietqr> <số TK> "<chủ TK>" ["<ghi chú>"] [template]`\n'
                'Ví dụ: `.shopbank "Vietinbank" vietinbank 0123456789 "Nguyen Van A"`'
            )

        bank_name, bank_code, account_number, account_holder = parts[0], parts[1], parts[2], parts[3]
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

    @commands.command(name="listbank")
    async def listbank_cmd(self, ctx: commands.Context):
        """Dùng: .listbank — liệt kê toàn bộ bank các seller đã đăng ký qua .shopbank."""
        if not (ctx.author.id in ADMIN_IDS or has_ticket_access(ctx.author)):
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


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopOrdersCog(bot))
