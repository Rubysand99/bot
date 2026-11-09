"""
cogs/shop_admin.py — Shop-domain admin: .sv/.giaset (bảng giá dịch vụ), .sold (toggle
auto-sold), handle_sold() (auto move kênh sold + tính doanh số), luồng DM hỏi giá/người
mua khi bot không tự đọc được giá từ tên kênh, nút Shop Orders/Lời Cảm Ơn Hoá Đơn trong
`.st`.

MỚI TÁCH từ cogs/admin.py (session tách bot Shop — xem CHANGELOG.md). AdminCog (giữ ở
cogs/admin.py) vẫn `from cogs.shop_admin import ShopOrdersToggleButton,
ReceiptMessageButton` để 2 nút này hiển thị trong `.st` — `.st` là dashboard CHUNG mọi
domain (Core hiển thị cả trạng thái Shop/Ticket), không phải dấu hiệu Shop chưa tách
sạch.

Load bởi bot.py (pilot — vẫn load đủ, xem COGS) VÀ bot_shop.py (entry point riêng).
handle_sold()/resume_pending_sold_views() được gọi từ on_message/on_ready của BẤT KỲ
bot nào load cog này — xem cách bot.py và bot_shop.py wire 2 hàm này trong on_message/
on_ready của chính chúng.
"""

import re as _re
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ui import Button, TextInput

from cogs.logger import send_log
from cogs.seller import is_active_seller
from core.data import (
    TUYTAM_NOTIFY_ID, ADMIN_RUBY_ID,
    get_cfg_stock_category, get_cfg_sold_category, is_stock_channel,
    get_cfg_sold_detection_enabled, set_cfg_sold_detection_enabled,
    get_guild_prefix, is_admin, _uname_plain,
    parse_amount, fmt_amount,
    set_current_guild,
    add_seller_sale, add_user_spent,
    add_pending_sold_price, get_pending_sold_price, get_all_pending_sold_price,
    remove_pending_sold_price, set_pending_sold_dm, mark_pending_sold_escalated,
    mark_pending_sold_resolved, get_resolved_sold_price,
    add_pending_sold_buyer, get_pending_sold_buyer, get_all_pending_sold_buyer,
    remove_pending_sold_buyer, set_pending_sold_buyer_dm, mark_pending_sold_buyer_escalated,
    get_cfg_shop_orders_enabled, set_cfg_shop_orders_enabled,
    get_cfg_receipt_thankyou, set_cfg_receipt_thankyou,
    get_cfg_done_role, get_price_sections,
    GuildContextView as View, GuildContextModal as Modal,
)
from cogs.admin_views import PriceManagerView, build_sv_embed, _DEFAULT_PRICE_SECTIONS


class ShopAdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── .sv / .giaset ──
    @commands.command(name="sv", aliases=["dichvu", "service"])
    async def sv_cmd(self, ctx):
        await ctx.send(embed=build_sv_embed())

    # FIX (UX): gộp "giaset2"/"priceset2" (trước là 1 command RIÊNG chỉ để forward
    # sang giaset_cmd) vào thẳng danh sách alias bên dưới — 1 tính năng không cần 2
    # command riêng biệt để làm cùng 1 việc.
    @commands.command(name="giaset", aliases=["setgia", "pricemanager", "priceset", "giaset2", "priceset2"])
    async def giaset_cmd(self, ctx):
        if not is_admin(ctx.author): return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        embed = discord.Embed(title="⚙️  Quản Lý Bảng Giá — .sv", description=f"Hiện có **{len(sections)} mục** trong bảng giá.\nChọn mục từ dropdown để **sửa**, hoặc dùng nút bên dưới.\n\n" + "\n".join(f"`{i+1}.` {s['name']}" for i, s in enumerate(sections)), color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="💡 Hướng dẫn", value="Hỗ trợ đầy đủ **Discord markdown**:\n› `**bold**`, `~~gạch~~`, `> blockquote`\n› Emoji server: `<:tên:id>`\n› `### Tiêu đề nhỏ`", inline=False)
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Timeout 2 phút")
        await ctx.reply(embed=embed, view=PriceManagerView())

    @commands.command(name="sold")
    async def sold_toggle_cmd(self, ctx, mode: str = None):
        """`.sold on` / `.sold off` — bật/tắt auto nhận diện "sold" trong kênh
        stock (xem handle_sold() bên dưới). Gõ trơ trọi `.sold` (không kèm
        on/off) để xem trạng thái hiện tại, không đổi gì cả."""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")

        mode = (mode or "").strip().lower()
        if mode not in ("on", "off"):
            cur = get_cfg_sold_detection_enabled()
            return await ctx.reply(
                f"ℹ️ Auto-sold hiện đang **{'BẬT 🟢' if cur else 'TẮT 🔴'}**. "
                f"Dùng `.sold on` hoặc `.sold off` để đổi."
            )

        new_state = (mode == "on")
        set_cfg_sold_detection_enabled(new_state)
        status_text = "🟢 BẬT" if new_state else "🔴 TẮT"

        await ctx.send(f"✅ Auto-sold (kênh stock) đã chuyển sang **{status_text}**.")

        # Dọn dòng lệnh cho gọn kênh (yêu cầu Ruby) — không chặn gì nếu bot thiếu
        # quyền Manage Messages ở kênh đó, chỉ là không dọn được thôi.
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        await send_log(
            ctx.bot, "SETTINGS", f"Auto-sold (kênh stock) → {status_text}",
            fields=[("👤 Admin", f"{ctx.author}", True)],
            user=ctx.author, guild_id=ctx.guild.id if ctx.guild else None,
        )

SOLD_ESCALATE_AFTER_SECONDS = 24 * 3600  # 24h không ai xử lý → escalate sang Ruby
# FIX: đã xoá STOCK_CATEGORY_ID/SOLD_CATEGORY_ID/DONE_ROLE_ID hardcode ở đây — dead code
# (2 cái đầu không hề được dùng ở đâu trong file, handle_sold() dùng get_cfg_stock_category()/
# get_cfg_sold_category() từ core/data.py) và DONE_ROLE_ID là hằng số CHUNG cho mọi guild dù
# role ID là duy nhất theo guild trên Discord — sang guild khác role này không tồn tại, tính
# năng tặng role "Đã Mua Hàng" im lặng không chạy. Giờ dùng get_cfg_done_role() (per-guild,
# xem core/data.py) — cấu hình qua `.st` → nút "🎖️ Done Role" (cogs/admin_views.py:
# SettingsView), không còn hardcode ID nào trong code nữa.

# ══════════════════════════════════════════
# SOLD-STOCK — parse giá từ tên kênh
# ══════════════════════════════════════════
def _parse_price_from_channel_name(name: str) -> int | None:
    """
    Bóc giá ở đầu tên kênh stock, vd: ✅𝟏𝟑𝟎𝐤-𝐧𝐨𝐧-𝟏𝐜𝐚𝐩𝐞 → 130000.
    Bỏ font Unicode + ký tự không phải chữ/số ở đầu trước khi parse.
    """
    from cogs.admin_views import _strip_unicode_font
    clean = _strip_unicode_font(name)
    # Bỏ mọi ký tự đầu không phải chữ/số (✅, •, -, khoảng trắng...)
    clean = _re.sub(r"^[^a-zA-Z0-9]+", "", clean)
    # Lấy token đầu tiên trước dấu '-' hoặc '_'
    m = _re.match(r"^([a-zA-Z0-9.]+)", clean)
    if not m:
        return None
    token = m.group(1)
    return parse_amount(token)


# ══════════════════════════════════════════
# SOLD-STOCK — Modal admin TuyTam/Ruby điền giá thủ công
# ══════════════════════════════════════════
class _SoldPriceModal(Modal, title="💰 Nhập giá đơn sold"):
    price_input = TextInput(label="Giá (vd: 130k, 1m2, 1tr5)", placeholder="130k", max_length=20)

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        amount = parse_amount(self.price_input.value)
        if amount is None or amount <= 0:
            return await interaction.response.send_message(
                f"❌ Giá `{self.price_input.value}` không hợp lệ. Dùng dạng: `130k`, `1m2`, `1tr5`.",
                ephemeral=True,
            )
        pending = get_pending_sold_price(self.channel_id)
        if not pending:
            resolved = get_resolved_sold_price(self.channel_id)
            if resolved:
                resolver = f"<@{resolved['resolved_by']}>"
                return await interaction.response.edit_message(
                    content=(
                        f"ℹ️ Đơn này đã được {resolver} xử lý — "
                        f"giá **{fmt_amount(resolved['amount'])}** (kênh cũ: `{resolved['old_name']}`)."
                    ),
                    embed=None, view=None,
                )
            return await interaction.response.send_message(
                "❌ Đơn này đã được xử lý hoặc không còn tồn tại.", ephemeral=True,
            )

        # ⚠️ Interaction này chạy trong DM admin — interaction.guild_id LUÔN None nên
        # GuildContextModal.interaction_check KHÔNG set được context. pending["guild_id"]
        # (đọc từ global data, không cần context) mới là nguồn đúng để set context ở đây,
        # TRƯỚC khi gọi add_seller_sale/add_pending_sold_buyer (data theo-guild).
        guild_id = pending.get("guild_id")
        if guild_id:
            set_current_guild(guild_id)

        seller_id = pending["seller_id"]
        add_seller_sale(seller_id, amount, pending["channel_name"], self.channel_id)
        mark_pending_sold_resolved(self.channel_id, amount, interaction.user.id, pending["old_name"])
        remove_pending_sold_price(self.channel_id)

        bot_ref = interaction.client
        await send_log(bot_ref, "INFO", "Sold-stock — điền giá thủ công",
            fields=[
                ("👤 Seller",  f"<@{seller_id}>",              True),
                ("💰 Giá",     fmt_amount(amount),              True),
                ("🎫 Kênh cũ", f"`{pending['old_name']}`",       True),
                ("✍️ Điền bởi", _uname_plain(interaction.user),   True),
            ],
            user=interaction.user, guild_id=guild_id)

        # Báo cho admin còn lại biết đơn đã được xử lý (nếu đã escalate sang cả 2)
        await _notify_other_admin(bot_ref, self.channel_id, interaction.user.id, amount, pending)

        # Đã có giá — giờ hỏi tiếp admin buyer là tài khoản Discord nào để cộng tiền
        # (giống lệnh .done), thay vì dừng lại ở đây như trước.
        if guild_id:
            add_pending_sold_buyer(
                self.channel_id, seller_id, amount, pending["channel_name"], pending["old_name"], guild_id,
            )
            await interaction.response.edit_message(
                content=(
                    f"✅ Đã ghi nhận **{fmt_amount(amount)}** cho <@{seller_id}> "
                    f"(kênh cũ: `{pending['old_name']}`).\n\n"
                    f"👉 Bấm nút bên dưới để cho biết **tài khoản Discord nào đã mua** — "
                    f"bot sẽ cộng tiền cho đúng người đó như lệnh `.done`."
                ),
                embed=None, view=_SoldBuyerView(self.channel_id),
            )
        else:
            await interaction.response.edit_message(
                content=(
                    f"✅ Đã ghi nhận **{fmt_amount(amount)}** cho <@{seller_id}> "
                    f"(kênh cũ: `{pending['old_name']}`).\n\n"
                    f"⚠️ Không xác định được guild của đơn này nên bot KHÔNG hỏi buyer tiếp — "
                    f"nếu cần cộng tiền cho khách, dùng lệnh `.done` trực tiếp trong ticket."
                ),
                embed=None, view=None,
            )


async def _notify_other_admin(bot, channel_id: int, resolved_by: int, amount: int, pending: dict):
    """Sau khi 1 admin điền giá, báo cho admin còn lại (nếu họ cũng có DM cho đơn này)."""
    other_id = None
    if resolved_by == TUYTAM_NOTIFY_ID and ADMIN_RUBY_ID and pending.get("ruby_message_id"):
        other_id = ADMIN_RUBY_ID
    elif resolved_by == ADMIN_RUBY_ID and TUYTAM_NOTIFY_ID and pending.get("tuytam_message_id"):
        other_id = TUYTAM_NOTIFY_ID

    if not other_id:
        return
    try:
        other_user = bot.get_user(other_id) or await bot.fetch_user(other_id)
        if other_user:
            await other_user.send(
                f"ℹ️ Đơn sold kênh `{pending['old_name']}` đã được <@{resolved_by}> "
                f"xử lý — giá **{fmt_amount(amount)}**."
            )
    except discord.Forbidden:
        pass


class _SoldPriceView(View):
    """Nút trong DM admin TuyTam/Ruby — nhấn để mở Modal nhập giá."""
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="💰 Nhập giá", style=discord.ButtonStyle.primary, custom_id="sold_price_input")
    async def input_price(self, interaction: discord.Interaction, button: Button):
        pending = get_pending_sold_price(self.channel_id)
        if not pending:
            for item in self.children:
                item.disabled = True
            resolved = get_resolved_sold_price(self.channel_id)
            if resolved:
                content = (
                    f"ℹ️ Đơn này đã được <@{resolved['resolved_by']}> xử lý — "
                    f"giá **{fmt_amount(resolved['amount'])}**."
                )
            else:
                content = "ℹ️ Đơn này đã được xử lý rồi."
            return await interaction.response.edit_message(content=content, view=self)
        await interaction.response.send_modal(_SoldPriceModal(self.channel_id))


async def _send_sold_price_dm(bot, target_user_id: int, channel_id: int, old_name: str, seller_mention: str) -> int | None:
    """Gửi DM hỏi giá cho 1 admin, trả về message_id nếu gửi thành công."""
    target_user = bot.get_user(target_user_id) or await bot.fetch_user(target_user_id)
    if not target_user:
        return None
    embed = discord.Embed(
        title="💰 Cần nhập giá đơn sold",
        description=(
            f"Seller {seller_mention} vừa sold kênh `{old_name}` nhưng bot không đọc "
            f"được giá từ tên kênh.\n\nNhấn nút bên dưới để nhập giá thủ công."
        ),
        color=0xF0A500,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🎫 Kênh cũ", value=f"`{old_name}`", inline=True)
    embed.add_field(name="👤 Seller", value=seller_mention, inline=True)
    try:
        msg = await target_user.send(embed=embed, view=_SoldPriceView(channel_id))
        return msg.id
    except discord.Forbidden:
        return None


# ══════════════════════════════════════════
# SOLD-STOCK — hỏi admin TuyTam/Ruby "tài khoản Discord nào mua" để cộng tiền
# cho buyer (giống lệnh .done: add_user_spent + auto_give_buy_roles + role "Đã Mua Hàng")
# ══════════════════════════════════════════
class _SoldBuyerModal(Modal, title="🧑 Người mua đơn sold"):
    buyer_input = TextInput(
        label="ID hoặc @mention người mua",
        placeholder="vd: 123456789012345678 hoặc @tên",
        max_length=100,
    )

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        pending = get_pending_sold_buyer(self.channel_id)
        if not pending:
            return await interaction.response.edit_message(
                content="ℹ️ Đơn này đã được xử lý hoặc không còn tồn tại.", embed=None, view=None,
            )

        # Bóc ID từ dạng "<@123>", "<@!123>" hoặc số thuần
        raw = self.buyer_input.value.strip()
        digits = _re.sub(r"[^0-9]", "", raw)
        if not digits:
            return await interaction.response.send_message(
                f"❌ Không đọc được ID từ `{raw}`. Nhập ID số hoặc @mention người mua.",
                ephemeral=True,
            )
        buyer_id = int(digits)

        # ⚠️ Chạy trong DM admin — set_current_guild() thủ công từ guild_id đã lưu trong
        # pending (đọc từ global data, không cần context) TRƯỚC khi gọi add_user_spent/
        # auto_give_buy_roles (data + role theo-guild).
        # FIX: dùng .get() thay vì pending["guild_id"] — mọi nơi TẠO record buyer-pending
        # hiện tại đều truyền guild_id nên rủi ro rất thấp, nhưng lỡ có record cũ/tương lai
        # thiếu field này thì .get() báo lỗi rõ ràng cho admin thay vì crash KeyError im lặng
        # (Discord chỉ hiện "Tương tác thất bại" chung chung, không rõ nguyên nhân).
        guild_id = pending.get("guild_id")
        if not guild_id:
            return await interaction.response.send_message(
                "❌ Đơn này thiếu thông tin server (guild_id) — không thể xác định nơi cộng tiền. "
                "Báo cho dev kiểm tra lại record này.",
                ephemeral=True,
            )
        set_current_guild(guild_id)

        bot_ref = interaction.client
        guild = bot_ref.get_guild(guild_id)
        if not guild:
            return await interaction.response.send_message(
                "❌ Bot không thấy server của đơn này (có thể đã rời server).", ephemeral=True,
            )

        try:
            buyer = guild.get_member(buyer_id) or await guild.fetch_member(buyer_id)
        except discord.NotFound:
            buyer = None
        except discord.HTTPException:
            buyer = None

        if not buyer:
            return await interaction.response.send_message(
                f"❌ Không tìm thấy thành viên `{buyer_id}` trong server. Kiểm tra lại ID/mention rồi thử lại.",
                ephemeral=True,
            )

        amount = pending["amount"]
        new_total = add_user_spent(buyer_id, amount)

        from cogs.admin_views import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(guild, buyer, new_total)

        done_role = guild.get_role(get_cfg_done_role())
        done_role_given = False
        if done_role:
            try:
                if done_role not in buyer.roles:
                    await buyer.add_roles(done_role, reason=f"Sold-stock — cộng tiền qua DM bởi {_uname_plain(interaction.user)}")
                done_role_given = True
            except Exception as _e:
                log_msg = f"[SOLD] Không thể give role {get_cfg_done_role()} cho {buyer}: {_e}"
                print(log_msg)

        remove_pending_sold_buyer(self.channel_id)

        content = (
            f"✅ Đã cộng **{fmt_amount(amount)}** cho {buyer.mention} "
            f"(tổng hiện tại: **{fmt_amount(new_total)}**) — kênh cũ: `{pending['old_name']}`."
        )
        if role_cfg:
            content += f"\n🏆 Role hiện tại: **{role_cfg.get('label', '?')}**"
        if done_role:
            content += f"\n🎖️ Role tặng: {done_role.mention} {'✅' if done_role_given else '*(đã có sẵn)*'}"
        await interaction.response.edit_message(content=content, embed=None, view=None)

        await send_log(bot_ref, "INFO", "💰 Sold-stock — đã cộng tiền cho buyer qua DM",
            fields=[
                ("👤 Buyer",   buyer.mention,                    True),
                ("💰 Giá",     fmt_amount(amount),                True),
                ("🎫 Kênh cũ", f"`{pending['old_name']}`",        True),
                ("✍️ Nhập bởi", _uname_plain(interaction.user),  True),
            ],
            user=buyer, guild_id=guild_id)


class _SoldBuyerView(View):
    """Nút trong DM admin TuyTam/Ruby — nhấn để mở Modal nhập tài khoản buyer."""
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="🧑 Nhập người mua", style=discord.ButtonStyle.primary, custom_id="sold_buyer_input")
    async def input_buyer(self, interaction: discord.Interaction, button: Button):
        pending = get_pending_sold_buyer(self.channel_id)
        if not pending:
            for item in self.children:
                item.disabled = True
            return await interaction.response.edit_message(
                content="ℹ️ Đơn này đã được xử lý hoặc không còn tồn tại.", view=self,
            )
        await interaction.response.send_modal(_SoldBuyerModal(self.channel_id))


async def _send_sold_buyer_dm(bot, target_user_id: int, channel_id: int, old_name: str, amount: int, seller_mention: str) -> int | None:
    """Gửi DM hỏi 'tài khoản Discord nào mua' cho 1 admin, trả về message_id nếu gửi thành công."""
    target_user = bot.get_user(target_user_id) or await bot.fetch_user(target_user_id)
    if not target_user:
        return None
    embed = discord.Embed(
        title="🧑 Cần xác nhận người mua đơn sold",
        description=(
            f"Seller {seller_mention} vừa sold kênh `{old_name}` với giá **{fmt_amount(amount)}**.\n\n"
            f"Nhấn nút bên dưới và cho biết **tài khoản Discord nào đã mua** — bot sẽ cộng tiền "
            f"cho đúng người đó, y như lệnh `.done`."
        ),
        color=0xF0A500,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🎫 Kênh cũ", value=f"`{old_name}`", inline=True)
    embed.add_field(name="👤 Seller", value=seller_mention, inline=True)
    embed.add_field(name="💰 Giá", value=fmt_amount(amount), inline=True)
    try:
        msg = await target_user.send(embed=embed, view=_SoldBuyerView(channel_id))
        return msg.id
    except discord.Forbidden:
        return None


async def _escalate_pending_sold(bot, channel_id: int):
    """Sau 24h không ai xử lý → DM thêm cho Ruby, KHÔNG thu hồi nút bên TuyTam."""
    await asyncio.sleep(SOLD_ESCALATE_AFTER_SECONDS)
    pending = get_pending_sold_price(channel_id)
    if not pending or pending.get("escalated"):
        return  # Đã xử lý hoặc đã escalate rồi (resume sau restart)
    if not ADMIN_RUBY_ID:
        return

    seller_mention = f"<@{pending['seller_id']}>"
    msg_id = await _send_sold_price_dm(bot, ADMIN_RUBY_ID, channel_id, pending["old_name"], seller_mention)
    mark_pending_sold_escalated(channel_id)
    if msg_id:
        set_pending_sold_dm(channel_id, ruby_message_id=msg_id)
        bot.add_view(_SoldPriceView(channel_id), message_id=msg_id)

    await send_log(bot, "INFO", "⏰ Sold-stock — quá 24h, đã escalate sang admin Ruby",
        fields=[("👤 Seller", seller_mention, True), ("🎫 Kênh cũ", f"`{pending['old_name']}`", True)],
        guild_id=pending.get("guild_id"))


async def resume_pending_sold_views(bot):
    """Gọi từ bot.py on_ready — đăng ký lại persistent view cho mọi đơn pending còn tồn
    (giá lẫn buyer), và lên lịch escalate đúng theo thời gian còn lại (hoặc escalate ngay
    nếu đã quá 24h). [v4.18.0] Data đã chuyển sang global nên KHÔNG cần loop theo guild
    nữa — get_all_pending_sold_price()/get_all_pending_sold_buyer() đọc được ngay."""
    pending_price_all = get_all_pending_sold_price()
    for channel_id_str, pending in pending_price_all.items():
        channel_id = int(channel_id_str)

        tuytam_mid = pending.get("tuytam_message_id")
        if tuytam_mid:
            bot.add_view(_SoldPriceView(channel_id), message_id=tuytam_mid)

        ruby_mid = pending.get("ruby_message_id")
        if ruby_mid:
            bot.add_view(_SoldPriceView(channel_id), message_id=ruby_mid)

        if pending.get("escalated"):
            continue  # Đã escalate trước khi restart, không cần lên lịch lại

        try:
            created_at = datetime.fromisoformat(pending["time"])
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except Exception:
            created_at = datetime.now(timezone.utc)

        elapsed   = (datetime.now(timezone.utc) - created_at).total_seconds()
        remaining = SOLD_ESCALATE_AFTER_SECONDS - elapsed

        if remaining <= 0:
            asyncio.create_task(_escalate_pending_sold_now(bot, channel_id))
        else:
            asyncio.create_task(_escalate_pending_sold_after(bot, channel_id, remaining))

    # Đơn đang chờ xác định BUYER (không escalate — chỉ cần đăng ký lại nút bấm)
    pending_buyer_all = get_all_pending_sold_buyer()
    for channel_id_str, pending in pending_buyer_all.items():
        channel_id = int(channel_id_str)
        tuytam_mid = pending.get("tuytam_message_id")
        if tuytam_mid:
            bot.add_view(_SoldBuyerView(channel_id), message_id=tuytam_mid)
        ruby_mid = pending.get("ruby_message_id")
        if ruby_mid:
            bot.add_view(_SoldBuyerView(channel_id), message_id=ruby_mid)


async def _escalate_pending_sold_now(bot, channel_id: int):
    """Escalate ngay (dùng khi resume và đã quá 24h từ lúc tạo pending)."""
    pending = get_pending_sold_price(channel_id)
    if not pending or pending.get("escalated") or not ADMIN_RUBY_ID:
        return
    seller_mention = f"<@{pending['seller_id']}>"
    msg_id = await _send_sold_price_dm(bot, ADMIN_RUBY_ID, channel_id, pending["old_name"], seller_mention)
    mark_pending_sold_escalated(channel_id)
    if msg_id:
        set_pending_sold_dm(channel_id, ruby_message_id=msg_id)
        bot.add_view(_SoldPriceView(channel_id), message_id=msg_id)
    await send_log(bot, "INFO", "⏰ Sold-stock — quá 24h (resume sau restart), đã escalate sang admin Ruby",
        fields=[("👤 Seller", seller_mention, True), ("🎫 Kênh cũ", f"`{pending['old_name']}`", True)],
        guild_id=pending.get("guild_id"))


async def _escalate_pending_sold_after(bot, channel_id: int, delay_seconds: float):
    await asyncio.sleep(delay_seconds)
    await _escalate_pending_sold_now(bot, channel_id)


# "sold" nhận diện Ở BẤT KỲ ĐÂU trong tin nhắn (yêu cầu Ruby, trước đây chỉ nhận
# nếu tin BẮT ĐẦU bằng "sold"/"## sold"). Dùng \b (word boundary) chứ KHÔNG phải
# substring trần — "sold" phải đứng riêng thành 1 từ, để "unsold"/"consolidate"/
# tên kênh dạng "...-solder..." không bị tính nhầm. Không phân biệt hoa thường.
_SOLD_PATTERN = _re.compile(r"\bsold\b", _re.IGNORECASE)


async def handle_sold(bot, message: discord.Message):
    """Gọi từ bot.py on_message để xử lý auto-sold."""
    if message.author.bot or not message.guild:
        return

    channel = message.channel
    if not isinstance(channel, discord.TextChannel):
        return

    stock_cat_id = get_cfg_stock_category()
    sold_cat_id  = get_cfg_sold_category()

    # Kênh trong danh mục stock = kênh stock; NHƯNG kênh có chữ "ticket" trong tên (hoặc topic
    # ticket của bot) luôn là ticket, không bị auto-sold chuyển category dù nằm trong stock.
    if not is_stock_channel(channel):
        return

    if not get_cfg_sold_detection_enabled():
        return  # admin đã `.sold off` — bỏ qua hoàn toàn, không nhận diện gì cả

    # Bỏ qua MỌI tin nhắn dạng lệnh bot (bắt đầu bằng prefix của guild, mặc định
    # ".") TRƯỚC khi soi nội dung — BẮT BUỘC có bước này: giờ "sold" khớp ở bất kỳ
    # đâu trong câu, nên nếu thiếu guard này thì chính lệnh ".sold on"/".sold off"
    # cũng tự khớp luôn (nó CÓ chữ "sold"), gây chuyển nhầm kênh admin đang gõ lệnh
    # sang category sold ngay khi họ tắt/bật tính năng.
    prefix = get_guild_prefix(message.guild.id)
    if message.content.startswith(prefix):
        return

    if not _SOLD_PATTERN.search(message.content):
        return

    sold_category = message.guild.get_channel(sold_cat_id)
    if not sold_category or not isinstance(sold_category, discord.CategoryChannel):
        await message.add_reaction("⚠️")
        return

    old_name = channel.name

    # AutoBuy: tài khoản có card ở kênh này → đánh dấu SOLD + khoá nút BUY (không để khách mua nốt acc đã bán tay).
    try:
        _ab = bot.get_cog("AutoBuyCog")
        if _ab:
            await _ab.on_manual_sold(channel)
    except Exception as _e:
        print(f"[SOLD] ⚠️ AutoBuy on_manual_sold lỗi: {_e}")

    if "•" in old_name:
        new_name = "❌•" + old_name.split("•", 1)[-1]
    else:
        new_name = "❌•" + old_name

    try:
        await channel.edit(
            name=new_name,
            category=sold_category,
            reason=f"Sold bởi {message.author} — auto-move",
        )
        await message.add_reaction("✅")
        await send_log(bot, "INFO", f"Kênh sold: `{old_name}` → `{new_name}`",
            fields=[("Seller", _uname_plain(message.author), True), ("Kênh mới", f"<#{channel.id}>", True), ("Category", sold_category.name, True)],
            guild_id=message.guild.id)
    except discord.Forbidden:
        await message.add_reaction("⚠️")
        return
    except Exception as e:
        await message.add_reaction("❌")
        await channel.send(f"⚠️ Lỗi khi chuyển kênh: `{e}`", delete_after=10)
        return

    # ── Thống kê doanh số seller (chỉ tính nếu seller hợp lệ — .seller add còn hạn) ──
    seller_id = message.author.id
    if not is_active_seller(message.guild.id, seller_id):
        return  # Không phải seller hợp lệ → vẫn chuyển kênh nhưng không tính thống kê

    amount = _parse_price_from_channel_name(old_name)

    if amount is not None and amount > 0:
        add_seller_sale(seller_id, amount, old_name, channel.id)
        await send_log(bot, "INFO", "💰 Sold-stock — đã ghi nhận thống kê",
            fields=[
                ("👤 Seller",  _uname_plain(message.author),  True),
                ("💰 Giá",     fmt_amount(amount),       True),
                ("🎫 Kênh cũ", f"`{old_name}`",          True),
            ],
            user=message.author, guild_id=message.guild.id)

        # ── Giá đã có ngay — hỏi admin TuyTam tài khoản Discord nào mua để cộng
        # tiền cho đúng người (giống lệnh .done), KHÔNG chặn phần trên (kênh đã
        # chuyển, thống kê seller đã ghi xong dù DM này có gửi được hay không).
        add_pending_sold_buyer(channel.id, seller_id, amount, new_name, old_name, message.guild.id)
        if not TUYTAM_NOTIFY_ID:
            print(f"[SOLD] ⚠️ Không hỏi được người mua cho kênh `{old_name}` — chưa cài TUYTAM_NOTIFY_ID.")
            await send_log(bot, "INFO", "⚠️ Sold-stock — chưa cài TUYTAM_NOTIFY_ID, không hỏi được người mua",
                fields=[("👤 Seller", _uname_plain(message.author), True), ("🎫 Kênh cũ", f"`{old_name}`", True)],
                user=message.author, guild_id=message.guild.id)
            return
        msg_id = await _send_sold_buyer_dm(bot, TUYTAM_NOTIFY_ID, channel.id, old_name, amount, message.author.mention)
        if msg_id:
            set_pending_sold_buyer_dm(channel.id, tuytam_message_id=msg_id)
            bot.add_view(_SoldBuyerView(channel.id), message_id=msg_id)
        else:
            print(f"[SOLD] ⚠️ Không gửi được DM hỏi người mua cho admin TuyTam — kênh `{old_name}` (DM tắt?).")
            await send_log(bot, "INFO", "⚠️ Không gửi được DM hỏi người mua cho admin TuyTam (DM tắt)",
                fields=[("👤 Seller", _uname_plain(message.author), True), ("🎫 Kênh cũ", f"`{old_name}`", True)],
                user=message.author, guild_id=message.guild.id)
        return

    # ── Không parse được giá → lưu pending + DM admin TuyTam nhập tay ──
    # (sau khi admin nhập giá xong, _SoldPriceModal.on_submit sẽ TỰ hỏi tiếp người mua)
    add_pending_sold_price(channel.id, seller_id, new_name, old_name, message.guild.id)

    if not TUYTAM_NOTIFY_ID:
        print(f"[SOLD] ⚠️ Không đọc được giá từ tên kênh `{old_name}` & chưa cài TUYTAM_NOTIFY_ID — bỏ qua hỏi giá.")
        await send_log(bot, "INFO", "⚠️ Sold-stock — không parse được giá & chưa cài TUYTAM_NOTIFY_ID",
            fields=[("👤 Seller", _uname_plain(message.author), True), ("🎫 Kênh cũ", f"`{old_name}`", True)],
            user=message.author, guild_id=message.guild.id)
        return

    msg_id = await _send_sold_price_dm(bot, TUYTAM_NOTIFY_ID, channel.id, old_name, message.author.mention)
    if msg_id:
        set_pending_sold_dm(channel.id, tuytam_message_id=msg_id)
        bot.add_view(_SoldPriceView(channel.id), message_id=msg_id)
    else:
        await send_log(bot, "INFO", "⚠️ Không gửi được DM hỏi giá cho admin TuyTam (DM tắt)",
            fields=[("👤 Seller", _uname_plain(message.author), True), ("🎫 Kênh cũ", f"`{old_name}`", True)],
            user=message.author, guild_id=message.guild.id)

    # Sau 24h nếu chưa xử lý → escalate sang Ruby
    asyncio.create_task(_escalate_pending_sold(bot, channel.id))


# ══════════════════════════════════════════
# SHOP ORDERS — nút bật/tắt trong .st (tính năng đang thử nghiệm)
# ══════════════════════════════════════════
class ShopOrdersToggleButton(discord.ui.Button):
    def __init__(self):
        enabled = get_cfg_shop_orders_enabled()
        super().__init__(
            label="Tắt Shop Orders" if enabled else "Bật Shop Orders",
            emoji="🧪",
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền dùng nút này.", ephemeral=True)

        new_state = not get_cfg_shop_orders_enabled()
        set_cfg_shop_orders_enabled(new_state)

        embed = interaction.message.embeds[0]
        status_text = "🟢 Bật" if new_state else "🔴 Tắt"
        for i, field in enumerate(embed.fields):
            if field.name == "🧪 Shop Orders (thử nghiệm)":
                embed.set_field_at(i, name=field.name, value=status_text, inline=True)
                break

        self.label = "Tắt Shop Orders" if new_state else "Bật Shop Orders"
        self.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success

        await interaction.response.edit_message(embed=embed, view=self.view)
        await send_log(
            interaction.client, "SETTINGS", f"Shop Orders (thử nghiệm) → {status_text}",
            fields=[("👤 Admin", f"{interaction.user}", True)],
            user=interaction.user,
            guild_id=interaction.guild_id,
        )


# ══════════════════════════════════════════
# HOÁ ĐƠN — nút sửa lời cảm ơn trong .st (cfg_receipt_style="embed" giờ dùng bản này;
# "image" là Phần 2, sẽ thêm nút chọn kiểu ở đây khi làm xong — xem core/data.py)
# ══════════════════════════════════════════
class ReceiptMessageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Sửa Lời Cảm Ơn Hoá Đơn", emoji="🧾", style=discord.ButtonStyle.secondary, row=4)

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền dùng nút này.", ephemeral=True)
        await interaction.response.send_modal(ReceiptMessageModal())


class ReceiptMessageModal(Modal, title="🧾 Sửa Lời Cảm Ơn Hoá Đơn"):
    """Đổi phần mở đầu hóa đơn công khai (build_receipt_embed ở shop_orders.py) — admin
    tự viết lại theo ý mình thay vì bị hardcode 1 kiểu duy nhất."""

    def __init__(self):
        super().__init__()
        self.message_input = TextInput(
            label="Lời cảm ơn (đầu hóa đơn công khai)",
            style=discord.TextStyle.paragraph,
            placeholder="Dùng {shop} để tự chèn tên server. VD: Cảm ơn quý khách tại {shop}!",
            default=get_cfg_receipt_thankyou()[:300],
            max_length=300,
            required=True,
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        text = self.message_input.value.strip()
        set_cfg_receipt_thankyou(text)
        preview = "> " + text.replace("{shop}", interaction.guild.name).replace("\n", "\n> ")
        await interaction.response.send_message(
            f"✅ Đã cập nhật lời cảm ơn hoá đơn.\n\n**Xem trước:**\n{preview}",
            ephemeral=True,
        )
        await send_log(
            interaction.client, "SETTINGS", "Sửa lời cảm ơn hoá đơn",
            fields=[("👤 Admin", f"{interaction.user}", True)],
            user=interaction.user,
            guild_id=interaction.guild_id,
        )




async def setup(bot):
    await bot.add_cog(ShopAdminCog(bot))
