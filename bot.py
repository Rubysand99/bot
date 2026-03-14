import discord
from discord.ext import commands
from discord.ui import Button, View
import datetime
import os

TOKEN = os.getenv("TOKEN")

ADMIN_ROLE_ID = 1325342802061688862
STATUS_CHANNEL_ID = 1482233794512556223
LOG_CHANNEL_ID = 1482234024868053083

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== LOẠI TICKET =====

ticket_types = [
    "selling ske",
    "selling monkey",
    "buying ske",
    "buying money",
    "hỗ trợ",
    "bảo hành"
]

# ===== MODAL NHẬP TÊN =====

class MinecraftNameModal(discord.ui.Modal, title="Nhập thông tin"):
    
    mc_name = discord.ui.TextInput(
        label="Tên tài khoản Minecraft",
        placeholder="Ví dụ: quannmc",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):

        view = TicketTypeView(self.mc_name.value)
        await interaction.response.send_message(
            "Chọn loại ticket:",
            view=view,
            ephemeral=True
        )

# ===== CHỌN LOẠI TICKET =====

class TicketTypeView(View):

    def __init__(self, mc_name):
        super().__init__(timeout=None)
        self.mc_name = mc_name

        for t in ticket_types:
            self.add_item(TicketButton(t, mc_name))

class TicketButton(Button):

    def __init__(self, ticket_type, mc_name):
        super().__init__(label=ticket_type, style=discord.ButtonStyle.primary)
        self.ticket_type = ticket_type
        self.mc_name = mc_name

    async def callback(self, interaction: discord.Interaction):

        if "selling" in self.ticket_type or "buying" in self.ticket_type:

            modal = QuantityModal(self.ticket_type, self.mc_name)
            await interaction.response.send_modal(modal)

        else:

            await create_ticket(interaction, self.ticket_type, self.mc_name, None)

# ===== MODAL SỐ LƯỢNG =====

class QuantityModal(discord.ui.Modal, title="Số lượng giao dịch"):

    quantity = discord.ui.TextInput(
        label="Số lượng muốn mua/bán",
        placeholder="Ví dụ: 10",
        required=True
    )

    def __init__(self, ticket_type, mc_name):
        super().__init__()
        self.ticket_type = ticket_type
        self.mc_name = mc_name

    async def on_submit(self, interaction: discord.Interaction):

        await create_ticket(
            interaction,
            self.ticket_type,
            self.mc_name,
            self.quantity.value
        )

# ===== TẠO TICKET =====

async def create_ticket(interaction, ticket_type, mc_name, quantity):

    guild = interaction.guild

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.get_role(ADMIN_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    channel_name = f"ticket-{interaction.user.name}-{ticket_type.replace(' ','-')}"

    channel = await guild.create_text_channel(
        name=channel_name,
        overwrites=overwrites
    )

    embed = discord.Embed(
        title="📩 Ticket mới",
        color=discord.Color.green()
    )

    embed.add_field(name="Khách hàng", value=interaction.user.mention)
    embed.add_field(name="Minecraft", value=mc_name)
    embed.add_field(name="Loại", value=ticket_type)

    if quantity:
        embed.add_field(name="Số lượng", value=quantity)

    view = TicketControlView()

    await channel.send(
        f"<@&{ADMIN_ROLE_ID}> ơi, có {interaction.user.mention} cần **{ticket_type}**",
        embed=embed,
        view=view
    )

    await interaction.response.send_message(
        f"✅ Ticket của bạn đã được tạo: {channel.mention}",
        ephemeral=True
    )

# ===== NÚT TRONG TICKET =====

class TicketControlView(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Hoàn thành đơn", style=discord.ButtonStyle.success)
    async def complete(self, interaction: discord.Interaction, button: Button):

        if ADMIN_ROLE_ID not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message("Chỉ admin dùng được.", ephemeral=True)
            return

        status_channel = bot.get_channel(STATUS_CHANNEL_ID)

        await status_channel.send(
            f"✅ Đơn trong {interaction.channel.name} đã hoàn thành."
        )

        await interaction.response.send_message("Đã đánh dấu hoàn thành.")

    @discord.ui.button(label="Đóng ticket", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: Button):

        if ADMIN_ROLE_ID not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message("Chỉ admin đóng được.", ephemeral=True)
            return

        messages = []

        async for msg in interaction.channel.history(limit=None, oldest_first=True):
            messages.append(f"{msg.author}: {msg.content}")

        filename = f"{interaction.channel.name}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(messages))

        log_channel = bot.get_channel(LOG_CHANNEL_ID)

        await log_channel.send(
            f"📁 Transcript {interaction.channel.name}",
            file=discord.File(filename)
        )

        os.remove(filename)

        await interaction.channel.delete()

# ===== LỆNH TẠO PANEL =====

@bot.command()
async def panel(ctx):

    view = View()

    button = Button(
        label="🎫 Tạo Ticket",
        style=discord.ButtonStyle.green
    )

    async def create(interaction):
        await interaction.response.send_modal(MinecraftNameModal())

    button.callback = create
    view.add_item(button)

    embed = discord.Embed(
        title="🎫 𝙩𝙪𝙮𝙩𝙖𝙢 𝙨𝙩𝙤𝙧𝙚✨",
        description="Nhấn nút bên dưới để tạo ticket mua bán hoặc hỗ trợ."
    )

    await ctx.send(embed=embed, view=view)

# ===== READY =====

@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")

bot.run(TOKEN)
