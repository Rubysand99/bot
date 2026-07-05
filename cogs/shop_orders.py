"""
cogs/shop_orders.py — QR thanh toán VietQR động + hàng đợi xử lý đơn, gắn vào lệnh .done có sẵn.

⚠️ TÍNH NĂNG THỬ NGHIỆM: mọi hàm đều no-op nếu get_cfg_shop_orders_enabled() == False.
Bật/tắt qua nút trong `.st` (do cogs/admin.py quản lý).

Cách hoạt động:
1. Admin cấu hình 1 lần:
   `.shopbank "Vietinbank" vietinbank 0123456789 "Nguyen Van A" "Thanh toan don hang"`
   `.setqueue #hang-doi`
2. Khi staff gõ `.done <số tiền>` trong ticket (cogs/ticket.py), nếu tính năng đang bật:
   - gửi kèm embed QR thanh toán (build_payment_qr_embed)
   - gửi thêm 1 embed "Đơn hàng chờ xử lý" vào kênh hàng đợi (send_to_queue)
3. Seller nhận được tiền, làm việc xong thì bấm nút ✅ "Hoàn thành" ngay trên embed đó
   trong kênh hàng đợi — embed được giữ lại, chỉ đổi màu + trạng thái, không xóa/chuyển kênh.
"""

import shlex
from urllib.parse import quote
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core.data import (
    ADMIN_IDS, fmt_amount, is_staff_member, get_or_fetch_channel,
    get_cfg_shop_orders_enabled,
    get_shop_orders_config, save_shop_orders_config,
    get_cfg_queue_channel, save_cfg_queue_channel,
    GuildContextView,
)
from cogs.logger import send_log

COLOR_QR = 0x5865F2
COLOR_QUEUE_PENDING = 0xF1C40F
COLOR_QUEUE_DONE = 0x2ECC71


def build_payment_qr_embed(amount: int) -> discord.Embed | None:
    """Trả về embed QR VietQR cho số tiền `amount`, dùng nội dung CK mặc định đã cấu hình.
    Trả về None nếu tính năng đang tắt hoặc chưa cấu hình đủ ngân hàng."""
    if not get_cfg_shop_orders_enabled():
        return None

    cfg = get_shop_orders_config()
    bank_code = cfg.get("bank_code")
    account_number = cfg.get("account_number")
    if not bank_code or not account_number:
        return None

    template = cfg.get("template", "compact2")
    account_holder = cfg.get("account_holder", "")
    default_content = cfg.get("default_content", "") or ""

    qr_url = (
        f"https://img.vietqr.io/image/{bank_code}-{account_number}-{template}.png"
        f"?amount={amount}&addInfo={quote(default_content)}&accountName={quote(account_holder)}"
    )

    e = discord.Embed(title="🏦 Quét mã để thanh toán", color=COLOR_QR)
    e.add_field(name="Ngân hàng", value=cfg.get("bank_name", "?"), inline=True)
    e.add_field(name="Số tài khoản", value=account_number, inline=True)
    e.add_field(name="Chủ tài khoản", value=account_holder or "?", inline=False)
    e.add_field(name="Số tiền", value=f"**{fmt_amount(amount)}**", inline=True)
    if default_content:
        e.add_field(name="Nội dung CK", value=f"`{default_content}`", inline=True)
    e.set_image(url=qr_url)
    e.set_footer(text="🧪 Shop Orders (thử nghiệm) — QR tự tạo qua VietQR")
    return e


def build_queue_embed(buyer: discord.abc.User, ticket_channel: discord.abc.GuildChannel, amount: int) -> discord.Embed:
    e = discord.Embed(
        title=f"{buyer.display_name} | Đơn hàng chờ xử lý",
        color=COLOR_QUEUE_PENDING,
        timestamp=datetime.now(timezone.utc),
    )
    e.set_thumbnail(url=buyer.display_avatar.url)
    e.add_field(name="👤 Khách", value=buyer.mention, inline=True)
    e.add_field(name="🎫 Ticket", value=ticket_channel.mention if ticket_channel else "*(không rõ)*", inline=True)
    e.add_field(name="💰 Số tiền", value=fmt_amount(amount), inline=True)
    e.add_field(name="📌 Trạng thái", value="🟡 Đang xử lý", inline=False)
    return e


async def send_to_queue(bot, buyer: discord.abc.User, ticket_channel: discord.abc.GuildChannel, amount: int) -> None:
    """Gửi embed đơn hàng vào kênh hàng đợi (nếu đã cấu hình + tính năng đang bật).
    Gọi hàm này ngay sau khi build_payment_qr_embed() ở cogs/ticket.py."""
    if not get_cfg_shop_orders_enabled():
        return
    queue_channel_id = get_cfg_queue_channel()
    if not queue_channel_id:
        return
    queue_channel = await get_or_fetch_channel(bot, queue_channel_id)
    if not queue_channel:
        return

    embed = build_queue_embed(buyer, ticket_channel, amount)
    await queue_channel.send(embed=embed, view=QueueOrderView())


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

        embed.color = COLOR_QUEUE_DONE
        for i, field in enumerate(embed.fields):
            if field.name == "📌 Trạng thái":
                embed.set_field_at(i, name=field.name, value=f"✅ Đã hoàn thành bởi {interaction.user.mention}", inline=False)
                break

        button.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

        await send_log(
            interaction.client, "SHOP_QUEUE_DONE", "Đơn hàng đợi đã hoàn thành",
            fields=[("🧑 Seller", interaction.user.mention, True)],
            user=interaction.user, guild_id=interaction.guild_id,
        )


class ShopOrdersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Đăng ký lại persistent view để nút "Hoàn thành" sống sau khi bot restart.
        self.bot.add_view(QueueOrderView())

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

    @commands.command(name="shopbank")
    async def shopbank_cmd(self, ctx: commands.Context, *, args: str = None):
        """Dùng: .shopbank "<tên hiển thị>" <bank_code_vietqr> <số TK> "<chủ TK>" ["<nội dung CK mặc định>"] [template]
        bank_code_vietqr: mã ngân hàng theo VietQR, vd vietinbank, mbbank, vietcombank, tpbank...
        Danh sách mã: https://api.vietqr.io/v2/banks
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền.")
        if not args:
            cfg = get_shop_orders_config()
            return await ctx.reply(
                "**Cấu hình ngân hàng hiện tại:**\n"
                f"› Tên hiển thị: `{cfg.get('bank_name', '(chưa cài)')}`\n"
                f"› Mã VietQR: `{cfg.get('bank_code', '(chưa cài)')}`\n"
                f"› Số TK: `{cfg.get('account_number', '(chưa cài)')}`\n"
                f"› Chủ TK: `{cfg.get('account_holder', '(chưa cài)')}`\n"
                f"› Nội dung CK mặc định: `{cfg.get('default_content', '(chưa cài)')}`\n"
                f"› Template: `{cfg.get('template', 'compact2')}`\n\n"
                'Cài lại: `.shopbank "Vietinbank" vietinbank 0123456789 "Nguyen Van A" "Thanh toan don hang"`'
            )
        try:
            parts = shlex.split(args)
        except ValueError:
            return await ctx.reply("❌ Cú pháp lỗi, kiểm tra lại dấu ngoặc kép.")
        if len(parts) < 4:
            return await ctx.reply(
                '❌ Dùng: `.shopbank "<tên hiển thị>" <bank_code_vietqr> <số TK> "<chủ TK>" ["<nội dung CK mặc định>"] [template]`\n'
                'Ví dụ: `.shopbank "Vietinbank" vietinbank 0123456789 "Nguyen Van A" "Thanh toan don hang"`'
            )

        bank_name, bank_code, account_number, account_holder = parts[0], parts[1], parts[2], parts[3]
        default_content = parts[4] if len(parts) > 4 else ""
        template = parts[5] if len(parts) > 5 else "compact2"
        save_shop_orders_config(
            bank_name=bank_name, bank_code=bank_code.lower(),
            account_number=account_number, account_holder=account_holder,
            default_content=default_content, template=template,
        )
        await ctx.reply(
            f"✅ Đã lưu: **{bank_name}** (`{bank_code}`) — `{account_number}` — {account_holder}\n"
            f"› Nội dung CK mặc định: `{default_content or '(để trống)'}`\n"
            f"QR mẫu: https://img.vietqr.io/image/{bank_code.lower()}-{account_number}-{template}.png"
            f"?amount=100000&addInfo={quote(default_content)}"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopOrdersCog(bot))
