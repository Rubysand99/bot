# cogs/ticket.py — Ticket system, Seller management
from config import *

class RatingModal(Modal):
    def __init__(self, ticket_name: str, user_id: int):
        super().__init__(title="⭐ Đánh Giá Dịch Vụ")
        self.ticket_name = ticket_name
        self.user_id = user_id

    stars_input = TextInput(
        label="Số sao (1-5)",
        placeholder="Nhập số từ 1 đến 5",
        min_length=1,
        max_length=1
    )
    comment = TextInput(
        label="Nhận xét (tuỳ chọn)",
        placeholder="Dịch vụ tốt, staff nhiệt tình...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars = int(self.stars_input.value)
            if stars < 1 or stars > 5:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Số sao không hợp lệ! Nhập từ 1 đến 5.", ephemeral=True
            )

        save_rating(self.ticket_name, self.user_id, stars)
        star_display = "⭐" * stars + "☆" * (5 - stars)

        log = bot.get_channel(FEEDBACK_CHANNEL_ID)
        if log:
            embed = discord.Embed(
                title="⭐ Đánh Giá Mới",
                color=0xF1C40F,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Ticket", value=f"`{self.ticket_name}`", inline=True)
            embed.add_field(name="User", value=f"<@{self.user_id}>", inline=True)
            embed.add_field(name="Đánh giá", value=star_display, inline=True)
            if self.comment.value:
                embed.add_field(name="Nhận xét", value=self.comment.value, inline=False)
            await log.send(embed=embed)

        await interaction.response.send_message(
            f"✅ Cảm ơn bạn đã đánh giá! {star_display}", ephemeral=True
        )

class RatingView(View):
    def __init__(self, ticket_name: str, user_id: int):
        super().__init__(timeout=300)
        self.ticket_name = ticket_name
        self.user_id = user_id

    @discord.ui.button(label="⭐ Đánh giá dịch vụ", style=discord.ButtonStyle.blurple)
    async def rate(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Chỉ người tạo ticket mới được đánh giá.", ephemeral=True)
        await interaction.response.send_modal(RatingModal(self.ticket_name, self.user_id))

# ================= ADD STAFF MODAL =================
class AddStaffModal(Modal):
    def __init__(self):
        super().__init__(title="📎 Thêm Staff vào Ticket")

    user_id_input = TextInput(
        label="ID của Staff",
        placeholder="Nhập User ID (click chuột phải → Copy ID)",
        min_length=15,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
            member = interaction.guild.get_member(uid)
            if not member:
                return await interaction.response.send_message("❌ Không tìm thấy member này.", ephemeral=True)

            overwrite = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )
            await interaction.channel.set_permissions(member, overwrite=overwrite)
            await interaction.response.send_message(
                f"✅ Đã thêm {member.mention} vào ticket!", ephemeral=False
            )
        except ValueError:
            await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

# ================= NOTE MODAL =================
class NoteModal(Modal):
    def __init__(self, channel_id: int):
        super().__init__(title="📝 Thêm Ghi Chú Nội Bộ")
        self.channel_id = channel_id

    note_input = TextInput(
        label="Nội dung ghi chú",
        placeholder="Ghi chú chỉ staff thấy...",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        add_ticket_note(self.channel_id, str(interaction.user), self.note_input.value)
        embed = discord.Embed(
            title="📝 Ghi Chú Nội Bộ",
            description=self.note_input.value,
            color=0xFEE75C,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Bởi {interaction.user} • Chỉ staff thấy")
        await interaction.response.send_message(embed=embed)

# ================= ORDER MODAL =================
async def create_service_ticket(interaction: discord.Interaction, service_key: str):
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send(
                "❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True
            )

        info = SERVICE_TABLE[service_key]
        number = await get_next_ticket_number()
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
        }
        for admin_id in ADMIN_IDS:
            m = guild.get_member(admin_id)
            if m:
                overwrites[m] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True
                )
        support_role = guild.get_role(get_cfg_support_role())
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )
        seller_role = guild.get_role(get_cfg_seller_role())
        if seller_role:
            overwrites[seller_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True,
                attach_files=True, embed_links=True,
                manage_channels=True, manage_permissions=True
            )

        category = discord.utils.get(guild.categories, id=get_cfg_category())
        channel = await guild.create_text_channel(
            name=f"ticket-{number}",
            overwrites=overwrites,
            category=category,
            topic=f"{interaction.user.id}||service|{service_key}|open"
        )

        embed = discord.Embed(
            title=f"{info['type_label']}  •  #{number}",
            description=(
                f"Xin chào {interaction.user.mention}! 👋\n"
                f"Staff sẽ hỗ trợ bạn sớm nhất có thể.\n"
                f"🟡 **Trạng thái:** Đang chờ staff nhận"
            ),
            color=info["color"],
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="📦  Dịch vụ",   value=info["label"],             inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(
            text="TuyTam Store  •  Ticket System",
            icon_url=guild.icon.url if guild.icon else None
        )

        await channel.send(
            f"<@&{get_cfg_support_role()}> | {interaction.user.mention}",
            embed=embed,
            view=TicketButtons()
        )

        await interaction.followup.send(
            f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True
        )

    except Exception as e:
        try:
            await interaction.followup.send(
                f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`\nVui lòng thử lại hoặc liên hệ admin.", ephemeral=True
            )
        except:
            pass

class OrderModal(Modal):
    def __init__(self, trade_type: str, item_key: str):
        item_info = PRICE_TABLE[trade_type][item_key]
        action = "Mua" if trade_type == "sell" else "Bán"
        super().__init__(title=f"{action} {item_info['label']}")
        self.trade_type = trade_type
        self.item_key = item_key

        self.mc_name = TextInput(
            label="Tên Minecraft của bạn",
            placeholder="Ví dụ: quannmc",
            min_length=2, max_length=32
        )
        self.add_item(self.mc_name)
        self.amount = TextInput(
            label="Số lượng",
            placeholder="Ví dụ: 10m / 5 cái / 100",
            min_length=1, max_length=50
        )
        self.add_item(self.amount)
        self.payment = TextInput(
            label="Phương thức thanh toán",
            placeholder="MB Bank / Thẻ cào / Thẻ Viettel (+18% thuế) / Ingame",
            min_length=2, max_length=100
        )
        self.add_item(self.payment)
        self.note = TextInput(
            label="Ghi chú (tuỳ chọn)",
            placeholder="Ví dụ: cần gấp, giao hàng online...",
            style=discord.TextStyle.paragraph,
            required=False, max_length=200
        )
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        try:
            if await has_ticket(guild, interaction.user):
                return await interaction.response.send_message(
                    "❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.",
                    ephemeral=True
                )

            number = await get_next_ticket_number()
            item_info = PRICE_TABLE[self.trade_type][self.item_key]
            created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

            if self.trade_type == "sell":
                color = 0x57F287
                type_label = "🛒 MUA HÀNG"
            else:
                color = 0xFEE75C
                type_label = "💸 BÁN HÀNG"

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )
            }
            for admin_id in ADMIN_IDS:
                m = guild.get_member(admin_id)
                if m:
                    overwrites[m] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True,
                        read_message_history=True, manage_messages=True
                    )
            support_role = guild.get_role(get_cfg_support_role())
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True
                )
            seller_role = guild.get_role(get_cfg_seller_role())
            if seller_role:
                overwrites[seller_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True,
                    attach_files=True, embed_links=True,
                manage_channels=True, manage_permissions=True
                )

            category = discord.utils.get(guild.categories, id=get_cfg_category())
            channel = await guild.create_text_channel(
                name=f"ticket-{number}",
                overwrites=overwrites,
                category=category,
                topic=f"{interaction.user.id}|{self.mc_name.value}|{self.trade_type}|{self.item_key}|open"
            )

            embed = discord.Embed(
                title=f"{type_label}  •  {item_info['label']}  •  #{number}",
                description=(
                    f"Xin chào {interaction.user.mention}! 👋\n"
                    f"Staff sẽ xử lý giao dịch sớm nhất có thể.\n"
                    f"🟡 **Trạng thái:** Đang chờ staff nhận"
                ),
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="👤  Người dùng",    value=interaction.user.mention,  inline=True)
            embed.add_field(name="🎮  Tên Minecraft", value=f"`{self.mc_name.value}`", inline=True)
            embed.add_field(name="🕐  Thời gian",     value=created_at,                inline=True)
            embed.add_field(name="📦  Item",          value=item_info["label"],        inline=True)
            embed.add_field(name="🔢  Số lượng",      value=self.amount.value,         inline=True)
            embed.add_field(name="💳  Thanh toán",    value=self.payment.value,        inline=True)
            if "viettel" in self.payment.value.lower():
                embed.add_field(
                    name="⚠️  Lưu ý Viettel",
                    value="Thẻ Viettel bị trừ thêm **18% thuế**, giá thực tế sẽ cao hơn!",
                    inline=False
                )
            if self.note.value:
                embed.add_field(name="📝  Ghi chú", value=self.note.value, inline=False)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(
                text="TuyTam Store  •  Ticket System",
                icon_url=guild.icon.url if guild.icon else None
            )

            await channel.send(
                f"<@&{get_cfg_support_role()}> | {interaction.user.mention}",
                embed=embed,
                view=TicketButtons()
            )

            await interaction.response.send_message(
                f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True
            )

        except Exception as e:
            try:
                await interaction.response.send_message(
                    f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`\nVui lòng thử lại hoặc liên hệ admin.",
                    ephemeral=True
                )
            except:
                pass

async def create_order_ticket(interaction: discord.Interaction, trade_type: str,
                              item_key: str = "other", item_label: str = "📦 Khác",
                              seller_id: int | None = None, seller_name: str = "staff"):
    """Tạo ticket mua/bán. Interaction đã được defer trước."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send(
                "❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True
            )

        number     = await get_next_ticket_number()
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        _key_slug = {"money": "money", "skeleton": "skeleton", "other": "khac"}
        channel_name = f"{_key_slug.get(item_key, 'ticket')}-{number}"

        if trade_type == "sell":
            color      = 0x57F287
            type_label = "🛒 MUA HÀNG"
        else:
            color      = 0xFEE75C
            type_label = "💸 BÁN HÀNG"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user:   discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
        }
        for admin_id in ADMIN_IDS:
            m = guild.get_member(admin_id)
            if m:
                overwrites[m] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True
                )
        if seller_id:
            seller_member = guild.get_member(seller_id)
            if seller_member:
                overwrites[seller_member] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True
                )
        seller_role = guild.get_role(get_cfg_seller_role())
        if seller_role:
            overwrites[seller_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True,
                attach_files=True, embed_links=True,
                manage_channels=True, manage_permissions=True
            )

        category = discord.utils.get(guild.categories, id=get_cfg_category())
        channel  = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            category=category,
            topic=f"{interaction.user.id}||{trade_type}|{item_key}|open"
        )

        embed = discord.Embed(
            title=f"{type_label}  •  {item_label}  •  #{number}",
            description=(
                f"Xin chào {interaction.user.mention}! 👋\n"
                f"Staff sẽ xử lý giao dịch sớm nhất có thể.\n"
                f"🟡 **Trạng thái:** Đang chờ staff nhận"
            ),
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="📦  Loại hàng",  value=item_label,               inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(
            text="TuyTam Store  •  Ticket System",
            icon_url=guild.icon.url if guild.icon else None
        )

        ping_target = f"<@{seller_id}>" if seller_id else f"<@&{get_cfg_support_role()}>"
        await channel.send(
            f"{ping_target} | {interaction.user.mention}",
            embed=embed,
            view=TicketButtons()
        )

        await interaction.followup.send(
            f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True
        )

    except Exception as e:
        try:
            await interaction.followup.send(
                f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`\nVui lòng thử lại hoặc liên hệ admin.",
                ephemeral=True
            )
        except:
            pass

# ================= SELECT ITEM TYPE =================
_ITEM_OPTIONS = [
    discord.SelectOption(
        label="💰 Money",
        value="money",
        description="Giao dịch tiền tệ trong game",
        emoji="💰",
    ),
    discord.SelectOption(
        label="💀 Skeleton",
        value="skeleton",
        description="Giao dịch skeleton",
        emoji="💀",
    ),
    discord.SelectOption(
        label="📦 Khác",
        value="other",
        description="Item / dịch vụ khác — ghi rõ trong ticket",
        emoji="📦",
    ),
]

_ITEM_LABEL = {
    "money":    "💰 Money",
    "skeleton": "💀 Skeleton",
    "other":    "📦 Khác",
}

class ItemSelect(Select):
    def __init__(self, trade_type: str):
        self.trade_type = trade_type
        action = "mua" if trade_type == "sell" else "bán"
        super().__init__(
            placeholder=f"Bạn muốn {action} loại nào?",
            options=_ITEM_OPTIONS,
            custom_id=f"item_select_{trade_type}",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            item_key   = self.values[0]
            item_label = _ITEM_LABEL.get(item_key, item_key)
            await interaction.response.defer(ephemeral=True)
            await create_order_ticket(
                interaction,
                trade_type=self.trade_type,
                item_key=item_key,
                item_label=item_label,
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

class ItemSelectView(View):
    def __init__(self, trade_type: str):
        super().__init__(timeout=60)
        self.add_item(ItemSelect(trade_type))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# ================= LỆNH QUẢN LÝ SELLER =================

@bot.command(name="addseller")
async def addseller_cmd(ctx: commands.Context, user_id: str = None, *, username: str = None):
    """
    Thêm seller vào danh sách chọn trong ticket.
    Cú pháp: .addseller <ID> <tên hiển thị>
    Ví dụ:   .addseller 846332174734983219 TuyTam
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
    if not user_id or not username:
        return await ctx.reply(
            "❌ Thiếu thông tin!\n"
            "Cú pháp: `.addseller <ID> <tên hiển thị>`\n"
            "Ví dụ: `.addseller 846332174734983219 TuyTam`"
        )
    try:
        seller_id = int(user_id.strip())
    except ValueError:
        return await ctx.reply("❌ ID không hợp lệ! Phải là dãy số.")

    sellers = get_sellers()
    for s in sellers:
        if s["id"] == seller_id:
            return await ctx.reply(f"❌ Seller ID `{seller_id}` đã có trong danh sách rồi!")

    member = ctx.guild.get_member(seller_id)
    display = f"{member.mention} ({member.name})" if member else f"ID: `{seller_id}`"

    sellers.append({"id": seller_id, "label": username.strip()})
    save_sellers(sellers)

    embed = discord.Embed(
        title="✅ Đã Thêm Seller",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 User",          value=display,                  inline=True)
    embed.add_field(name="🏷️ Tên hiển thị", value=f"**{username.strip()}**", inline=True)
    embed.add_field(name="📋 Tổng sellers",  value=f"**{len(sellers)}** người", inline=True)
    embed.add_field(
        name="📝 Danh sách hiện tại",
        value="\n".join(f"`{i+1}.` **{s['label']}** — `{s['id']}`" for i, s in enumerate(sellers)) or "—",
        inline=False
    )
    embed.set_footer(text=f"Thêm bởi {ctx.author}")
    await ctx.reply(embed=embed)

@bot.command(name="removeseller", aliases=["delseller", "xoaseller"])
async def removeseller_cmd(ctx: commands.Context, *, target: str = None):
    """
    Xoá seller khỏi danh sách.
    Cú pháp: .removeseller <ID hoặc tên>
    Ví dụ:   .removeseller 846332174734983219
             .removeseller TuyTam
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
    if not target:
        return await ctx.reply("❌ Cú pháp: `.removeseller <ID hoặc tên hiển thị>`")

    sellers = get_sellers()
    target  = target.strip()

    found = None
    for s in sellers:
        if str(s["id"]) == target or s["label"].lower() == target.lower():
            found = s
            break

    if not found:
        return await ctx.reply(
            f"❌ Không tìm thấy seller `{target}` trong danh sách.\n"
            f"Dùng `.listseller` để xem danh sách hiện tại."
        )

    sellers.remove(found)
    save_sellers(sellers)

    embed = discord.Embed(
        title="🗑️ Đã Xoá Seller",
        color=0xED4245,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏷️ Seller đã xoá", value=f"**{found['label']}** (`{found['id']}`)", inline=False)
    embed.add_field(
        name=f"📋 Còn lại ({len(sellers)} người)",
        value="\n".join(f"`{i+1}.` **{s['label']}** — `{s['id']}`" for i, s in enumerate(sellers)) or "*(trống)*",
        inline=False
    )
    embed.set_footer(text=f"Xoá bởi {ctx.author}")
    await ctx.reply(embed=embed)

@bot.command(name="listseller", aliases=["sellers", "danhsachseller"])
async def listseller_cmd(ctx: commands.Context):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

    sellers = get_sellers()
    embed = discord.Embed(
        title="📋 Danh Sách Seller",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    if sellers:
        lines = []
        for i, s in enumerate(sellers):
            member = ctx.guild.get_member(s["id"])
            mention = member.mention if member else f"`{s['id']}`"
            lines.append(f"`{i+1}.` **{s['label']}** — {mention}")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Tổng: {len(sellers)} seller  •  .addseller <ID> <tên> để thêm")
    else:
        embed.description = (
            "*(Chưa có seller nào)*\n\n"
            "Thêm seller bằng lệnh:\n"
            "`.addseller <ID> <tên hiển thị>`\n"
            "Ví dụ: `.addseller 846332174734983219 TuyTam`"
        )
    await ctx.reply(embed=embed)

# ================= SERVICE SELECT =================
class ServiceSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=info["label"],
                value=key,
                description=info["note"],
                emoji=info["label"].split()[0]
            )
            for key, info in SERVICE_TABLE.items()
        ]
        super().__init__(
            placeholder="Chọn dịch vụ bạn cần...",
            options=options,
            custom_id="service_select"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_service_ticket(interaction, self.values[0])
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

class ServiceSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(ServiceSelect())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# ================= PANEL VIEW =================
class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Mua hàng",
        emoji="🛒",
        style=discord.ButtonStyle.green,
        custom_id="panel_buy"
    )
    async def buy(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "🛒 **Bạn muốn mua loại nào?**",
                view=ItemSelectView(trade_type="sell"),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Bán hàng",
        emoji="💸",
        style=discord.ButtonStyle.blurple,
        custom_id="panel_sell"
    )
    async def sell(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "💸 **Bạn muốn bán loại nào?**",
                view=ItemSelectView(trade_type="buy"),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Dịch Vụ",
        emoji="🎮",
        style=discord.ButtonStyle.grey,
        custom_id="panel_service"
    )
    async def service(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "🎮 **Bạn cần dịch vụ nào?**",
                view=ServiceSelectView(),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

# ================= TICKET BUTTONS =================
class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Mua",
        emoji="🛒",
        style=discord.ButtonStyle.blurple,
        custom_id="claim_ticket"
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            for item in self.children:
                if item.custom_id == "claim_ticket":
                    item.disabled = True
                    item.label = f"Claimed: {_uname_plain(interaction.user)}"
                    item.emoji = "✅"
                    break
            await interaction.response.defer()
            await interaction.message.edit(view=self)
            await interaction.followup.send(f"✅ {interaction.user.mention} đã nhận ticket này!")
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Add Staff",
        emoji="📎",
        style=discord.ButtonStyle.grey,
        custom_id="add_staff"
    )
    async def add_staff(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            await interaction.response.send_modal(AddStaffModal())
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Ghi chú",
        emoji="📝",
        style=discord.ButtonStyle.grey,
        custom_id="add_note"
    )
    async def add_note(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            await interaction.response.send_modal(NoteModal(interaction.channel.id))
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Đóng ticket",
        emoji="🔒",
        style=discord.ButtonStyle.red,
        custom_id="close_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Không có quyền.", ephemeral=True)
        try:
            await interaction.response.defer()
            await _close_ticket(interaction.channel, bot, closer=interaction.user)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi khi đóng ticket: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Hoàn thành đơn",
        emoji="✅",
        style=discord.ButtonStyle.green,
        custom_id="complete_order"
    )
    async def complete_order(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            await interaction.response.defer(ephemeral=True)
            await _complete_order(interaction)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Gửi QR",
        emoji="📱",
        style=discord.ButtonStyle.green,
        custom_id="send_qr"
    )
    async def send_qr(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            qr_path = get_qr_path()
            if not qr_path or not os.path.exists(qr_path):
                return await interaction.response.send_message(
                    "❌ Chưa có QR! Admin cài QR qua `.settings` trước.", ephemeral=True
                )
            file = discord.File(qr_path, filename="qr.png")
            embed = discord.Embed(
                title="📱  Mã QR Thanh Toán",
                description=(
                    "> 🏦 **MB Bank** — `0702557706` — HOVANBUT\n"
                    "> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n"
                    "> ⚠️ Ghi rõ nội dung: `[tên MC] mua [item]`"
                ),
                color=0x57F287,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_image(url="attachment://qr.png")
            embed.set_footer(text=f"Gửi bởi {_uname_plain(interaction.user)}")
            await interaction.response.send_message(embed=embed, file=file)
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

# ================= HOÀN THÀNH ĐƠN (GIVE ROLE) =================
async def _complete_order(interaction: discord.Interaction):
    """
    Staff nhấn nút 'Hoàn thành đơn' trong ticket.
    Bot đọc buyer từ topic kênh → +1 đơn → give role phù hợp.
    Chỉ hoạt động với ticket loại mua hàng (sell/buy), không áp dụng cho service/support.
    """
    channel = interaction.channel
    guild   = interaction.guild

    if not channel.topic or "|" not in channel.topic:
        return await interaction.followup.send("❌ Đây không phải kênh ticket.", ephemeral=True)

    parts = channel.topic.split("|")
    try:
        user_id = int(parts[0]) if parts[0].isdigit() else None
    except Exception:
        user_id = None

    if not user_id:
        return await interaction.followup.send("❌ Không đọc được thông tin buyer từ ticket.", ephemeral=True)

    trade_type = parts[2] if len(parts) > 2 else None

    if trade_type not in ("sell", "buy"):
        return await interaction.followup.send(
            "ℹ️ Ticket dịch vụ / hỗ trợ không tính vào đơn mua hàng.", ephemeral=True
        )

    buyer = guild.get_member(user_id)
    if not buyer:
        return await interaction.followup.send(
            f"❌ Không tìm thấy buyer (ID: `{user_id}`) trong server — họ có thể đã rời.", ephemeral=True
        )

    data = load_data()
    completed_key = f"completed_{channel.id}"
    if data.get(completed_key):
        total = get_user_total_spent(user_id)
        return await interaction.followup.send(
            f"⚠️ Đơn này đã được đánh dấu hoàn thành rồi!\n"
            f"Buyer: {buyer.mention} — tổng đã mua: **{fmt_amount(total)}**",
            ephemeral=True
        )

    await interaction.followup.send("💵 Vui lòng nhập số tiền của đơn này:", ephemeral=True, view=None)
    await interaction.channel.send(
        f"⚠️ {interaction.user.mention} — hãy dùng lệnh `.done <số tiền>` để hoàn thành đơn.\n"
        f"Ví dụ: `.done 50k`, `.done 1tr5`, `.done 200000`",
        delete_after=20
    )

# ================= CLOSE LOGIC =================
async def _close_ticket(channel, bot_instance, closer: discord.Member = None):
    user_id    = None
    mc_name    = None
    trade_type = None
    item_key   = None
    ticket_name = channel.name

    if channel.topic:
        parts = channel.topic.split("|")
        try: user_id    = int(parts[0]) if parts[0].isdigit() else None
        except: pass
        mc_name    = parts[1] if len(parts) > 1 and parts[1] not in ("service", "") else None
        trade_type = parts[2] if len(parts) > 2 else None
        item_key   = parts[3] if len(parts) > 3 else None

    guild = channel.guild
    creator: discord.Member | None = guild.get_member(user_id) if user_id else None

    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    created_at_str = messages[0].created_at.strftime("%d/%m/%Y %H:%M:%S UTC") if messages else "Không rõ"

    item_label = None
    if item_key and trade_type:
        try:
            item_label = PRICE_TABLE[trade_type][item_key]["label"]
        except (KeyError, TypeError):
            pass
    if not item_label and item_key:
        svc = SERVICE_TABLE.get(item_key)
        item_label = svc["label"] if svc else item_key

    type_map = {"sell": "🛒 Mua Hàng", "buy": "💸 Bán Hàng", "service": "🎮 Dịch Vụ"}
    ticket_type_label = type_map.get(trade_type, trade_type or "Ticket")

    info = {
        "created_by_name":   str(creator) if creator else (f"ID:{user_id}" if user_id else "Không rõ"),
        "created_by_id":     str(user_id) if user_id else "",
        "created_by_avatar": creator.display_avatar.url if creator else "",
        "closed_by_name":    str(closer) if closer else "Hệ thống",
        "closed_by_id":      str(closer.id) if closer else "",
        "ticket_type":       ticket_type_label,
        "mc_name":           mc_name,
        "item":              item_label,
        "trade_type":        trade_type,
        "created_at":        created_at_str,
    }

    html = build_transcript_html(channel.name, messages, info)
    file = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")

    transcript_ch = bot_instance.get_channel(TRANSCRIPT_CHANNEL_ID)
    close_time = datetime.now(timezone.utc)
    if messages:
        duration = close_time - messages[0].created_at.replace(tzinfo=timezone.utc)
        total_sec = int(duration.total_seconds())
        h, m, s = total_sec // 3600, (total_sec % 3600) // 60, total_sec % 60
        duration_str = f"{h}g {m}p {s}s" if h else f"{m}p {s}s"
    else:
        duration_str = "Không rõ"

    embed = discord.Embed(
        title="📄 Ticket Đã Đóng",
        color=0xED4245,
        timestamp=close_time
    )
    embed.add_field(name="🎫 Ticket",        value=f"`{ticket_name}`",                                    inline=True)
    embed.add_field(name="🏷️ Loại",          value=ticket_type_label,                                     inline=True)
    embed.add_field(name="💬 Tin nhắn",       value=f"**{len(messages)}**",                                inline=True)
    embed.add_field(name="👤 Người tạo",      value=str(creator) if creator else f"`ID:{user_id}`",        inline=True)
    embed.add_field(name="🔒 Người đóng",     value=closer.mention if closer else "Hệ thống",              inline=True)
    embed.add_field(name="⏱️ Thời lượng",     value=duration_str,                                          inline=True)
    embed.add_field(name="🕐 Thời gian tạo",  value=created_at_str,                                        inline=True)
    embed.add_field(name="🕑 Thời gian đóng", value=close_time.strftime("%d/%m/%Y %H:%M:%S UTC"),          inline=True)
    if mc_name:
        embed.add_field(name="🎮 Minecraft",  value=f"`{mc_name}`",                                        inline=True)
    if item_label:
        embed.add_field(name="📦 Item",       value=item_label,                                            inline=True)
    if creator:
        embed.set_thumbnail(url=creator.display_avatar.url)
    embed.set_footer(text="TuyTam Store • Ticket System")

    if transcript_ch:
        file2 = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")
        await transcript_ch.send(embed=embed, file=file2)

    notes = get_ticket_note(channel.id)
    if notes and transcript_ch:
        note_text = "\n".join([f"**{n['author']}:** {n['note']}" for n in notes])
        note_embed = discord.Embed(
            title="📝 Ghi Chú Nội Bộ",
            description=note_text,
            color=0xFEE75C,
            timestamp=datetime.now(timezone.utc)
        )
        note_embed.set_footer(text=f"Ticket: {ticket_name}")
        await transcript_ch.send(embed=note_embed)

    await channel.delete()

    if creator:
        try:
            rate_embed = discord.Embed(
                title="⭐ Đánh Giá Dịch Vụ",
                description=(
                    f"Ticket `{ticket_name}` của bạn đã được đóng.\n"
                    f"Hãy đánh giá dịch vụ để giúp chúng tôi cải thiện!"
                ),
                color=0xF1C40F,
                timestamp=datetime.now(timezone.utc)
            )
            await creator.send(embed=rate_embed, view=RatingView(ticket_name, creator.id))
        except discord.Forbidden:
            pass

# ================= COMMANDS =================
