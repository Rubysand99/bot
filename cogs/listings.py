"""
cogs/listings.py — Đăng sản phẩm dạng Forum (kiểu ảnh mẫu ViceVN) + nút 🛒 Mua.

Cách hoạt động:
1. Staff/seller gõ `.addlisting #forum-channel "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]`
   trong cùng tin nhắn có thể đính kèm 1 ảnh preview (không bắt buộc).
2. Bot tạo 1 thread mới trong kênh forum đó với embed sản phẩm + 2 nút:
   - 🟢 Chưa bán / 🔴 Đã bán  — toggle, chỉ staff/seller bấm được
   - 🛒 Mua                   — khách bấm để tạo ticket mua (dùng lại luồng ticket.py),
                                thông tin sản phẩm được copy sẵn vào ticket.
3. ListingView KHÔNG gắn ID sản phẩm vào custom_id (giống QueueOrderView ở shop_orders.py) —
   view chỉ đọc/ghi trực tiếp embed của message được bấm, nên chỉ cần đăng ký 1 persistent
   view duy nhất lúc cog_load, không cần lưu danh sách listing vào Mongo.
"""

import shlex
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core.data import (
    is_staff_member, _uname_plain,
    GuildContextView,
)
from cogs.logger import send_log
from cogs.ticket import create_listing_ticket

log = logging.getLogger(__name__)

COLOR_LISTING_AVAILABLE = 0x2ECC71
COLOR_LISTING_SOLD = 0xE74C3C


class ListingView(GuildContextView):
    """Persistent view gắn trên mỗi bài đăng sản phẩm."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 Chưa bán", style=discord.ButtonStyle.success, custom_id="shop_listing_toggle")
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Chỉ seller/staff mới đổi được trạng thái sản phẩm.", ephemeral=True)

        embed = interaction.message.embeds[0]
        currently_sold = bool(embed.color and embed.color.value == COLOR_LISTING_SOLD)

        if currently_sold:
            button.label = "🟢 Chưa bán"
            button.style = discord.ButtonStyle.success
            embed.color = COLOR_LISTING_AVAILABLE
        else:
            button.label = "🔴 Đã bán"
            button.style = discord.ButtonStyle.danger
            embed.color = COLOR_LISTING_SOLD

        for item in self.children:
            if getattr(item, "custom_id", None) == "shop_listing_buy":
                item.disabled = not currently_sold  # đang chuyển SANG đã bán → khóa nút Mua

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🛒 Mua", style=discord.ButtonStyle.primary, custom_id="shop_listing_buy")
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        if embed.color and embed.color.value == COLOR_LISTING_SOLD:
            return await interaction.response.send_message("❌ Sản phẩm này đã được bán rồi.", ephemeral=True)

        ign   = next((f.value for f in embed.fields if f.name == "👤 IGN"), "?")
        price = next((f.value for f in embed.fields if f.name == "💰 Giá"), "?")
        cape  = next((f.value for f in embed.fields if f.name == "👕 Cape"), "")
        note  = next((f.value for f in embed.fields if f.name == "📝 Thông tin thêm"), "")

        await interaction.response.defer(ephemeral=True)
        source_thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        await create_listing_ticket(interaction, ign, price, cape, note, source_thread)


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


class ListingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Đăng ký lại persistent view để nút Mua / trạng thái sống sau khi bot restart.
        self.bot.add_view(ListingView())

    @commands.command(name="addlisting", aliases=["sanpham", "listing"])
    async def addlisting_cmd(self, ctx: commands.Context, channel: discord.ForumChannel = None, *, args: str = None):
        """Dùng: .addlisting #forum "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]
        Đính kèm ảnh preview vào cùng tin nhắn nếu muốn (không bắt buộc)."""
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Chỉ staff/seller mới có quyền đăng sản phẩm.")
        if not channel or not args:
            return await ctx.reply(
                '❌ Dùng: `.addlisting #forum "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]`\n'
                'Ví dụ: `.addlisting #stock "test" "999K" "common, pan, copper" "Unban All"`\n'
                '💡 Đính kèm ảnh preview vào tin nhắn nếu muốn (không bắt buộc).'
            )
        if not isinstance(channel, discord.ForumChannel):
            return await ctx.reply("❌ Kênh đích phải là 1 Forum Channel (kênh chỉ có chủ đề).")

        try:
            parts = shlex.split(args)
        except ValueError:
            return await ctx.reply("❌ Cú pháp lỗi, kiểm tra lại dấu ngoặc kép.")
        if len(parts) < 3:
            return await ctx.reply(
                '❌ Thiếu tham số. Dùng: `.addlisting #forum "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]`'
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
            kwargs = {"name": f"{ign} | {price}"[:100], "embed": embed, "view": ListingView()}
            if file:
                kwargs["file"] = file
            result = await channel.create_thread(**kwargs)
        except discord.Forbidden:
            return await ctx.reply("❌ Bot thiếu quyền tạo bài trong kênh forum này.")
        except Exception as e:
            return await ctx.reply(f"❌ Lỗi khi tạo listing: `{e}`")

        thread = result.thread if hasattr(result, "thread") else result
        await ctx.reply(f"✅ Đã đăng sản phẩm: {thread.mention}")

        await send_log(
            ctx.bot, "SHOP_LISTING_CREATE", "Sản phẩm mới được đăng",
            fields=[
                ("📦 Sản phẩm", ign, True),
                ("💰 Giá", price, True),
                ("🧑 Người đăng", _uname_plain(ctx.author), True),
                ("🧵 Thread", thread.mention, True),
            ],
            user=ctx.author, guild_id=ctx.guild.id,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ListingsCog(bot))
