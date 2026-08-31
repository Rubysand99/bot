"""
cogs/listings.py — Đăng sản phẩm dạng Forum HOẶC kênh chat thường (kiểu ảnh mẫu ViceVN) + nút 🛒 Mua.

Cách hoạt động:
1. Staff/seller/role Auto Buy gõ `.addlisting #kênh "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]`
   — #kênh có thể là kênh Forum (tạo thread mới) HOẶC kênh Text thường (gửi thẳng tin nhắn).
   Trong cùng tin nhắn có thể đính kèm 1 ảnh preview (không bắt buộc).
2. Bot đăng embed sản phẩm + 2 nút:
   - 🟢 Chưa bán / 🔴 Đã bán  — toggle, chỉ staff/seller/role Auto Buy bấm được
   - 🛒 Mua                   — khách bấm để tạo ticket mua (dùng lại luồng ticket.py),
                                thông tin sản phẩm được copy sẵn vào ticket.
3. ListingView KHÔNG gắn ID sản phẩm vào custom_id (giống QueueOrderView ở shop_orders.py) —
   view chỉ đọc/ghi trực tiếp embed của message được bấm, nên chỉ cần đăng ký 1 persistent
   view duy nhất lúc cog_load, không cần lưu danh sách listing vào Mongo.
4. Quyền đăng/sửa listing: `is_staff_member()` (ADMIN + support role + seller role) HOẶC có 1 trong
   các role được gán ở `.st` → Vai trò ticket → nhóm "🤖 Auto Buy" (key Mongo: "listing_manage").
"""

import shlex
import logging
from typing import Union
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.data import (
    is_staff_member, _uname_plain, ADMIN_IDS,
    get_ticket_role_ids, GuildContextView,
)
from cogs.logger import send_log
from cogs.ticket import (
    create_listing_ticket, create_stockpost_ticket,
    create_direct_order_ticket, create_accpre_ticket, create_build_ticket,
)

log = logging.getLogger(__name__)

COLOR_LISTING_AVAILABLE = 0x2ECC71
COLOR_LISTING_SOLD = 0xE74C3C


def can_manage_listing(member: discord.Member) -> bool:
    """Staff/seller (is_staff_member) HOẶC role được gán riêng cho Auto Buy (.st → Vai trò ticket → 🤖 Auto Buy)."""
    if is_staff_member(member):
        return True
    allowed_ids = get_ticket_role_ids("listing_manage")
    if not allowed_ids:
        return False
    if member.id in allowed_ids:
        return True
    member_role_ids = {r.id for r in member.roles}
    return any(rid in member_role_ids for rid in allowed_ids if rid not in ADMIN_IDS)


class ListingView(GuildContextView):
    """Persistent view gắn trên mỗi bài đăng sản phẩm."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Chưa bán", style=discord.ButtonStyle.success, custom_id="shop_listing_toggle")
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_manage_listing(interaction.user):
            return await interaction.response.send_message("❌ Chỉ seller/staff/role Auto Buy mới đổi được trạng thái sản phẩm.", ephemeral=True)

        # CHỈ đổi label/màu nút — KHÔNG đụng embed/ảnh/attachment (né hoàn toàn nhóm lỗi
        # Discord tách/mất ảnh khi edit embed có ảnh đính kèm).
        #
        # Vì đây là persistent view dùng CHUNG cho mọi bài đăng sản phẩm, `self`/`button` là
        # object dùng lại giữa các tin nhắn khác nhau — KHÔNG được suy trạng thái hiện tại từ
        # `button.style`, phải đọc đúng trạng thái thật của tin nhắn bị bấm qua
        # `interaction.message.components`.
        currently_sold = False
        for row in interaction.message.components:
            for comp in row.children:
                if getattr(comp, "custom_id", None) == "shop_listing_toggle":
                    currently_sold = (comp.style == discord.ButtonStyle.danger)

        if currently_sold:
            button.label = "🟢 Chưa bán"
            button.style = discord.ButtonStyle.success
        else:
            button.label = "🔴 Đã bán"
            button.style = discord.ButtonStyle.danger

        for item in self.children:
            if getattr(item, "custom_id", None) == "shop_listing_buy":
                item.disabled = not currently_sold  # đang chuyển SANG đã bán → khóa nút Mua

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="🛒 Mua", style=discord.ButtonStyle.primary, custom_id="shop_listing_buy")
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Đọc trạng thái thật từ tin nhắn (lý do xem comment ở toggle_btn) thay vì embed.color
        # (không còn đổi màu embed theo trạng thái nữa — xem toggle_btn).
        for row in interaction.message.components:
            for comp in row.children:
                if getattr(comp, "custom_id", None) == "shop_listing_toggle" and comp.style == discord.ButtonStyle.danger:
                    return await interaction.response.send_message("❌ Sản phẩm này đã được bán rồi.", ephemeral=True)

        embed = interaction.message.embeds[0]
        ign   = next((f.value for f in embed.fields if f.name == "👤 IGN"), "?")
        price = next((f.value for f in embed.fields if f.name == "💰 Giá"), "?")
        cape  = next((f.value for f in embed.fields if f.name == "👕 Cape"), "")
        note  = next((f.value for f in embed.fields if f.name == "📝 Thông tin thêm"), "")

        await interaction.response.defer(ephemeral=True)
        # Kênh Forum (thread) → mention thread. Kênh Text thường → link thẳng tới tin nhắn listing gốc.
        if isinstance(interaction.channel, discord.Thread):
            source_link = interaction.channel.mention
        else:
            source_link = interaction.message.jump_url
        await create_listing_ticket(interaction, ign, price, cape, note, source_link)


def build_listing_embed(ign: str, price: str, cape: str, note: str, author: discord.abc.User) -> discord.Embed:
    e = discord.Embed(
        title=f"🎮 Tài khoản Minecraft: {ign}",
        color=COLOR_LISTING_AVAILABLE,
        timestamp=datetime.now(timezone.utc),
    )
    e.add_field(name="👤 IGN", value=ign, inline=False)
    e.add_field(name="💰 Giá", value=price, inline=False)
    e.add_field(name="👕 Cape", value=cape or "*(không có)*", inline=False)
    if note:
        e.add_field(name="📝 Thông tin thêm", value=note, inline=False)
    e.set_footer(text=f"Đăng bởi {author.display_name}")
    return e


# ══════════════════════════════════════════
# /post — đăng tin tuỳ chọn embed/ảnh/nội dung/trạng thái Stock-Sold vào 1 kênh bất kỳ.
# Dùng cho các kênh 「stock」「sold」 — không cần bấm nút ở panel Ticket để tạo ticket
# mua, khách bấm thẳng 🛒 Mua Ngay trên bài đăng. Cùng cơ chế đọc-trạng-thái-từ-live-
# message như ListingView ở trên (view dùng chung cho nhiều tin nhắn, KHÔNG lưu ID sản
# phẩm vào custom_id/Mongo).
# ══════════════════════════════════════════
STATUS_BADGE = {
    "stock": "📦 **CÒN HÀNG**",
    "sold":  "✅ **ĐÃ BÁN**",
}

# Nút "🛒 Mua Ngay" trên bài /post trước đây LUÔN tạo ticket chung (create_stockpost_ticket)
# — không phân biệt món hàng thuộc server/loại nào, staff phải tự phân loại thủ công trong
# ticket. Giờ hỏi người đăng ngay lúc /post (xem _StockPostTicketAskView) muốn nút Mua Ngay
# dẫn thẳng tới loại ticket nào, rồi LƯU lựa chọn vào field "🏷️ Loại" của embed (đọc lại ở
# buy_btn) — theo đúng cơ chế "đọc trạng thái từ message" đã dùng cho Trạng thái/toggle, KHÔNG
# lưu Mongo riêng. Chỉ chọn được các loại có hàm tạo ticket "thẳng" (không cần chọn item/con
# số bổ sung nào khác) — donut/kingmc/ff/accpre/build; rubyshop/giveaway/support/middleman
# không đưa vào đây vì không phải ticket "mua món hàng đang rao".
STOCKPOST_TICKET_TYPES = {
    "donut":   "🍩 DonutSMP",
    "kingmc":  "👑 KingMC",
    "ff":      "🔥 Free Fire",
    "accpre":  "🎭 Acc Pre",
    "build":   "🏗️ Build",
    "generic": "🛒 Ticket chung (không phân loại)",
}
_STOCKPOST_LABEL_TO_KEY = {label: key for key, label in STOCKPOST_TICKET_TYPES.items()}


async def _create_stockpost_dest_ticket(interaction: discord.Interaction, type_key: str | None, content: str, source_link: str):
    """Bấm 🛒 Mua Ngay → tạo đúng loại ticket đã chọn lúc /post (STOCKPOST_TICKET_TYPES).
    type_key=None: bài đăng CŨ (trước khi có tính năng này, không có field "🏷️ Loại")
    hoặc đăng ở chế độ text thường (không embed, không có chỗ lưu lựa chọn) → giữ NGUYÊN
    hành vi cũ, tạo ticket chung — KHÔNG đổi hành vi bài đăng có sẵn."""
    if type_key in ("donut", "kingmc", "ff"):
        await create_direct_order_ticket(interaction, type_key)
    elif type_key == "accpre":
        await create_accpre_ticket(interaction, "buy")
    elif type_key == "build":
        await create_build_ticket(interaction, "buy")
    else:
        await create_stockpost_ticket(interaction, content, source_link)


def build_stockpost_embed(content: str | None, status: str, author: discord.abc.User, ticket_type_label: str | None = None) -> discord.Embed:
    color = COLOR_LISTING_SOLD if status == "sold" else COLOR_LISTING_AVAILABLE
    e = discord.Embed(description=content or None, color=color, timestamp=datetime.now(timezone.utc))
    if status in STATUS_BADGE:
        e.add_field(name="Trạng thái", value=STATUS_BADGE[status], inline=True)
    if ticket_type_label:
        e.add_field(name="🏷️ Loại", value=ticket_type_label, inline=True)
    e.set_footer(text=f"Đăng bởi {author.display_name}")
    return e


def build_stockpost_text(content: str | None, status: str) -> str | None:
    lines = []
    if status in STATUS_BADGE:
        lines.append(STATUS_BADGE[status])
    if content:
        lines.append(content)
    return "\n\n".join(lines) if lines else None


class StockPostView(GuildContextView):
    """Persistent view gắn trên bài đăng từ `/post` khi có chọn trạng thái Còn hàng/Đã
    bán. Giống hệt cơ chế ListingView ở trên — đọc trạng thái thật từ component của
    message bị bấm (KHÔNG suy từ self/button, vì view này dùng chung cho mọi bài /post)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📦 Còn Hàng", style=discord.ButtonStyle.success, custom_id="stockpost_toggle")
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_manage_listing(interaction.user):
            return await interaction.response.send_message("❌ Chỉ seller/staff/role Auto Buy mới đổi được trạng thái.", ephemeral=True)

        currently_sold = False
        for row in interaction.message.components:
            for comp in row.children:
                if getattr(comp, "custom_id", None) == "stockpost_toggle":
                    currently_sold = (comp.style == discord.ButtonStyle.danger)

        new_status = "stock" if currently_sold else "sold"

        if currently_sold:
            button.label, button.style = "📦 Còn Hàng", discord.ButtonStyle.success
        else:
            button.label, button.style = "✅ Đã Bán", discord.ButtonStyle.danger

        for item in self.children:
            if getattr(item, "custom_id", None) == "stockpost_buy":
                item.disabled = not currently_sold  # đang chuyển SANG đã bán → khoá nút Mua

        # Đồng bộ lại badge "Trạng thái" trong embed/nội dung theo trạng thái mới — trước
        # đây chỉ đổi label/màu NÚT, embed/nội dung vẫn giữ nguyên "📦 CÒN HÀNG" mãi mãi dù
        # đã bấm "Đã Bán" (bug thật: đơn hàng xong, admin toggle nút nhưng bài đăng vẫn
        # hiện còn hàng). MUTATE TRỰC TIẾP embed đã có sẵn trên message (không dựng
        # discord.Embed mới, không gọi set_image()/đụng file đính kèm) để né đúng bug
        # Discord tách/mất ảnh khi edit embed kèm attachment mới — xem comment tương tự ở
        # ListingView.toggle_btn phía trên.
        kwargs = {"view": self}
        if interaction.message.embeds:
            embed = interaction.message.embeds[0]
            embed.colour = COLOR_LISTING_SOLD if new_status == "sold" else COLOR_LISTING_AVAILABLE
            for i, f in enumerate(embed.fields):
                if f.name == "Trạng thái":
                    embed.set_field_at(i, name="Trạng thái", value=STATUS_BADGE[new_status], inline=f.inline)
                    break
            kwargs["embed"] = embed
        elif interaction.message.content:
            # Tin thường (không embed) — badge nằm ở dòng đầu content (build_stockpost_text),
            # bóc dòng badge cũ ra rồi build lại với trạng thái mới để tránh nhân đôi/kẹt badge cũ.
            raw = interaction.message.content
            first, _, rest = raw.partition("\n\n")
            remainder = rest if first in STATUS_BADGE.values() else raw
            kwargs["content"] = build_stockpost_text(remainder or None, new_status)

        await interaction.response.edit_message(**kwargs)

    @discord.ui.button(label="🛒 Mua Ngay", style=discord.ButtonStyle.primary, custom_id="stockpost_buy")
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for row in interaction.message.components:
            for comp in row.children:
                if getattr(comp, "custom_id", None) == "stockpost_toggle" and comp.style == discord.ButtonStyle.danger:
                    return await interaction.response.send_message("❌ Sản phẩm này đã được bán rồi.", ephemeral=True)

        msg = interaction.message
        content = msg.embeds[0].description if msg.embeds else (msg.content or "")

        # Đọc lựa chọn loại ticket từ field "🏷️ Loại" của CHÍNH message bị bấm (không có
        # ở bài đăng cũ / bài đăng dạng text thường) → _create_stockpost_dest_ticket tự
        # fallback ticket chung nếu None, xem docstring hàm đó.
        type_label = next((f.value for f in msg.embeds[0].fields if f.name == "🏷️ Loại"), None) if msg.embeds else None
        type_key = _STOCKPOST_LABEL_TO_KEY.get(type_label)

        await interaction.response.defer(ephemeral=True)
        await _create_stockpost_dest_ticket(interaction, type_key, content or "", msg.jump_url)


class _StockPostTicketSelect(discord.ui.Select):
    """Dropdown chọn loại ticket — theo đúng pattern Select-subclass-override-callback đã
    dùng ở ItemSelect/_TradeModeSelect/_RubyShopOptionSelect trong cogs/ticket.py."""

    def __init__(self):
        options = [discord.SelectOption(label=label, value=key) for key, label in STOCKPOST_TICKET_TYPES.items()]
        super().__init__(placeholder="Chọn loại Ticket cho nút Mua Ngay…", options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.view.finish(interaction, self.values[0])


class _StockPostTicketAskView(GuildContextView):
    """Hỏi loại Ticket cho nút 🛒 Mua Ngay TRƯỚC KHI đăng bài thật (chỉ dùng nội bộ trong
    post_cmd — KHÔNG persistent/không add_view ở cog_load, timeout ngắn vì chỉ dùng 1 lần
    ngay lúc /post, khác StockPostView vốn timeout=None vì gắn trên bài đăng vĩnh viễn)."""

    def __init__(self, *, channel: discord.TextChannel, content: str | None, image: discord.Attachment | None, status_val: str):
        super().__init__(timeout=180)
        self.channel = channel
        self.content = content
        self.image = image
        self.status_val = status_val
        self.add_item(_StockPostTicketSelect())

    async def finish(self, interaction: discord.Interaction, type_key: str):
        type_label = STOCKPOST_TICKET_TYPES[type_key]

        file = None
        if self.image:
            try:
                file = await self.image.to_file()
            except Exception as e:
                return await interaction.response.edit_message(content=f"❌ Không đọc được ảnh: `{e}`", view=None)

        embed = build_stockpost_embed(self.content, self.status_val, interaction.user, ticket_type_label=type_label)
        if file:
            embed.set_image(url=f"attachment://{file.filename}")

        view = StockPostView()
        if self.status_val == "sold":
            for item in view.children:
                if getattr(item, "custom_id", None) == "stockpost_toggle":
                    item.label, item.style = "✅ Đã Bán", discord.ButtonStyle.danger
                if getattr(item, "custom_id", None) == "stockpost_buy":
                    item.disabled = True

        kwargs = {"embed": embed, "view": view, "file": file} if file else {"embed": embed, "view": view}

        try:
            target_msg = await self.channel.send(**kwargs)
        except discord.Forbidden:
            return await interaction.response.edit_message(content="❌ Bot thiếu quyền đăng bài trong kênh này.", view=None)
        except Exception as e:
            return await interaction.response.edit_message(content=f"❌ Lỗi khi đăng bài: `{e}`", view=None)

        await interaction.response.edit_message(
            content=f"✅ Đã đăng: {target_msg.jump_url}\n🏷️ Mua Ngay sẽ tạo ticket: **{type_label}**", view=None,
        )

        await send_log(
            interaction.client, "SHOP_LISTING_CREATE", "Đăng bài /post",
            fields=[
                ("📍 Kênh", self.channel.mention, True),
                ("🧑 Người đăng", _uname_plain(interaction.user), True),
                ("📦 Trạng thái", self.status_val, True),
                ("🏷️ Loại ticket", type_label, True),
            ],
            user=interaction.user, guild_id=interaction.guild_id,
        )


class ListingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Đăng ký lại persistent view để nút Mua / trạng thái sống sau khi bot restart.
        self.bot.add_view(ListingView())
        self.bot.add_view(StockPostView())

    @commands.command(name="addlisting", aliases=["sanpham", "listing"])
    async def addlisting_cmd(
        self, ctx: commands.Context,
        channel: Union[discord.ForumChannel, discord.TextChannel] = None,
        *, args: str = None,
    ):
        """Dùng: .addlisting #kênh "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]
        #kênh có thể là kênh Forum (tạo thread mới) hoặc kênh Text thường (gửi thẳng tin nhắn).
        Đính kèm ảnh preview vào cùng tin nhắn nếu muốn (không bắt buộc)."""
        if not can_manage_listing(ctx.author):
            return await ctx.reply("❌ Chỉ staff/seller hoặc role được cấp quyền Auto Buy mới có quyền đăng sản phẩm.")
        if not channel or not args:
            return await ctx.reply(
                '❌ Dùng: `.addlisting #kênh "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]`\n'
                '#kênh có thể là kênh Forum (tạo thread) hoặc kênh Text thường (gửi thẳng tin nhắn).\n'
                'Ví dụ: `.addlisting #stock "test" "999K" "common, pan, copper" "Unban All"`\n'
                '💡 Đính kèm ảnh preview vào tin nhắn nếu muốn (không bắt buộc).'
            )

        try:
            parts = shlex.split(args)
        except ValueError:
            return await ctx.reply("❌ Cú pháp lỗi, kiểm tra lại dấu ngoặc kép.")
        if len(parts) < 3:
            return await ctx.reply(
                '❌ Thiếu tham số. Dùng: `.addlisting #kênh "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]`'
            )

        ign, price, cape = parts[0], parts[1], parts[2]
        note = parts[3] if len(parts) > 3 else ""

        embed = build_listing_embed(ign, price, cape, note, ctx.author)

        file = None
        if ctx.message.attachments:
            try:
                file = await ctx.message.attachments[0].to_file()
                embed.set_image(url=f"attachment://{file.filename}")
            except Exception as e:
                log.warning(f"[LISTINGS] ⚠️ Không đọc được ảnh đính kèm: {e}")

        try:
            if isinstance(channel, discord.ForumChannel):
                kwargs = {"name": f"{ign} | {price}"[:100], "embed": embed, "view": ListingView()}
                if file:
                    kwargs["file"] = file
                result = await channel.create_thread(**kwargs)
                target = result.thread if hasattr(result, "thread") else result
            else:
                kwargs = {"embed": embed, "view": ListingView()}
                if file:
                    kwargs["file"] = file
                target = await channel.send(**kwargs)
        except discord.Forbidden:
            return await ctx.reply("❌ Bot thiếu quyền đăng bài trong kênh này.")
        except Exception as e:
            return await ctx.reply(f"❌ Lỗi khi tạo listing: `{e}`")

        await ctx.reply(f"✅ Đã đăng sản phẩm: {target.mention}")

        await send_log(
            ctx.bot, "SHOP_LISTING_CREATE", "Sản phẩm mới được đăng",
            fields=[
                ("📦 Sản phẩm", ign, True),
                ("💰 Giá", price, True),
                ("🧑 Người đăng", _uname_plain(ctx.author), True),
                ("📍 Vị trí", target.mention, True),
            ],
            user=ctx.author, guild_id=ctx.guild.id,
        )

    @app_commands.command(name="post", description="[Staff] Đăng tin vào 1 kênh — tuỳ chọn embed/ảnh/nội dung/trạng thái Còn hàng-Đã bán")
    @app_commands.describe(
        channel="Kênh sẽ đăng tin vào",
        content="Nội dung tin nhắn (bỏ trống nếu chỉ gửi ảnh)",
        image="Ảnh đính kèm (bỏ trống nếu chỉ gửi chữ)",
        use_embed="Gửi dạng embed hay tin nhắn thường (mặc định: Embed)",
        status="Hiện trạng thái + nút 🛒 Mua Ngay (bỏ trống = tin thường, không có nút)",
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="📦 Còn hàng (có nút Mua Ngay)", value="stock"),
        app_commands.Choice(name="✅ Đã bán (khoá nút Mua Ngay)", value="sold"),
    ])
    async def post_cmd(
        self, interaction: discord.Interaction, channel: discord.TextChannel,
        content: str = None, image: discord.Attachment = None,
        use_embed: bool = True, status: app_commands.Choice[str] = None,
    ):
        if not can_manage_listing(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ staff/seller hoặc role được cấp quyền Auto Buy mới có quyền đăng bài.", ephemeral=True
            )
        if not content and not image:
            return await interaction.response.send_message("❌ Cần ít nhất nội dung hoặc ảnh.", ephemeral=True)

        status_val = status.value if status else "none"

        # Có nút "🛒 Mua Ngay" (status stock/sold) VÀ dùng embed (nơi duy nhất lưu được
        # lựa chọn loại ticket, field "🏷️ Loại" — xem STOCKPOST_TICKET_TYPES) → hỏi loại
        # Ticket TRƯỚC khi đăng thật, việc đăng bài chuyển vào _StockPostTicketAskView.finish().
        # Tin thường (status bỏ trống) hoặc tắt embed → đăng ngay, đường cũ bên dưới
        # (không có nút Mua, hoặc không có field embed nào để lưu lựa chọn).
        if status_val in ("stock", "sold") and use_embed:
            ask_view = _StockPostTicketAskView(channel=channel, content=content, image=image, status_val=status_val)
            return await interaction.response.send_message(
                "🎯 **Bấm \"🛒 Mua Ngay\" trên bài này sẽ tạo Ticket loại nào?**",
                view=ask_view, ephemeral=True,
            )

        file = None
        if image:
            try:
                file = await image.to_file()
            except Exception as e:
                return await interaction.response.send_message(f"❌ Không đọc được ảnh: `{e}`", ephemeral=True)

        # Chỉ gắn view (toggle + nút Mua Ngay) khi có chọn trạng thái — tin thường
        # (status bỏ trống) thì không có nút gì, đúng như 1 tin thông báo bình thường.
        view = None
        if status_val in ("stock", "sold"):
            view = StockPostView()
            if status_val == "sold":
                for item in view.children:
                    if getattr(item, "custom_id", None) == "stockpost_toggle":
                        item.label, item.style = "✅ Đã Bán", discord.ButtonStyle.danger
                    if getattr(item, "custom_id", None) == "stockpost_buy":
                        item.disabled = True

        kwargs = {"view": view} if view else {}
        if use_embed:
            embed = build_stockpost_embed(content, status_val, interaction.user)
            if file:
                embed.set_image(url=f"attachment://{file.filename}")
                kwargs["file"] = file
            kwargs["embed"] = embed
        else:
            text = build_stockpost_text(content, status_val)
            if text:
                kwargs["content"] = text
            if file:
                kwargs["file"] = file

        try:
            target_msg = await channel.send(**kwargs)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Bot thiếu quyền đăng bài trong kênh này.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Lỗi khi đăng bài: `{e}`", ephemeral=True)

        await interaction.response.send_message(f"✅ Đã đăng: {target_msg.jump_url}", ephemeral=True)

        await send_log(
            interaction.client, "SHOP_LISTING_CREATE", "Đăng bài /post",
            fields=[
                ("📍 Kênh", channel.mention, True),
                ("🧑 Người đăng", _uname_plain(interaction.user), True),
                ("📦 Trạng thái", status_val, True),
            ],
            user=interaction.user, guild_id=interaction.guild_id,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ListingsCog(bot))
