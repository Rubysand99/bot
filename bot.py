import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import os
import io

TOKEN = os.getenv("TOKEN")

ADMIN_ID = 1464961078042698588

CATEGORY_ID = 148223350000000000
STATUS_CHANNEL_ID = 1482233794512556223
LOG_CHANNEL_ID = 1482234024868053083

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# MODAL NHẬP TÊN MINECRAFT
# =========================

class MinecraftModal(Modal):
    def __init__(self, ticket_type):
        super().__init__(title="Thông tin Minecraft")
        self.ticket_type = ticket_type

        self.mc_name = TextInput(
            label="Tên tài khoản Minecraft",
            placeholder="Ví dụ: QuanMC",
            required=True
        )

        self.add_item(self.mc_name)

    async def on_submit(self, interaction: discord.Interaction):

        # nếu là mua/bán thì hỏi số lượng
        if "selling" in self.ticket_type or "buying" in self.ticket_type:
            await interaction.response.send_modal(AmountModal(self.ticket_type, self.mc_name.value))
        else:
            await create_ticket(interaction, self.ticket_type, self.mc_name.value, None)


# =========================
# MODAL NHẬP SỐ LƯỢNG
# =========================

class AmountModal(Modal):
    def __init__(self, ticket_type, mc_name):
        super().__init__(title="Số lượng")

        self.ticket_type = ticket_type
        self.mc_name = mc_name

        self.amount = TextInput(
            label="Số lượng muốn mua/bán",
            placeholder="Ví dụ: 10",
            required=True
        )

        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):

        await create_ticket(
            interaction,
            self.ticket_type,
            self.mc_name,
            self.amount.value
        )


# =========================
# TẠO TICKET
# =========================

async def create_ticket(interaction, ticket_type, mc_name, amount):

    guild = interaction.guild
    category = guild.get_channel(CATEGORY_ID)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.get_member(ADMIN_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        category=category,
        overwrites=overwrites
    )

    embed = discord.Embed(
        title="Ticket đã tạo",
        color=0x2F3136
    )

    embed.add_field(name="Người tạo", value=interaction.user.mention)
    embed.add_field(name="Minecraft", value=mc_name)
    embed.add_field(name="Loại", value=ticket_type)

    if amount:
        embed.add_field(name="Số lượng", value=amount)

    await channel.send(
        interaction.user.mention,
        embed=embed,
        view=TicketButtons()
    )

    # status
    status_channel = guild.get_channel(STATUS_CHANNEL_ID)

    await status_channel.send(
        f"📩 Ticket mới: {channel.mention} | {ticket_type}"
    )

    await interaction.response.send_message(
        f"Ticket đã tạo: {channel.mention}",
        ephemeral=True
    )


# =========================
# NÚT TRONG TICKET
# =========================

class TicketButtons(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Hoàn thành đơn", style=discord.ButtonStyle.green)
    async def complete(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id != ADMIN_ID:
            return await interaction.response.send_message(
                "Chỉ admin được dùng nút này",
                ephemeral=True
            )

        await interaction.channel.send("✅ Đơn hàng đã hoàn thành.")

    @discord.ui.button(label="Đóng ticket", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id != ADMIN_ID:
            return await interaction.response.send_message(
                "Chỉ admin được đóng ticket",
                ephemeral=True
            )

        await save_transcript(interaction.channel)

        await interaction.channel.delete()


# =========================
# LƯU TRANSCRIPT
# =========================

async def save_transcript(channel):

    messages = []

    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(f"{msg.author}: {msg.content}")

    text = "\n".join(messages)

    file = discord.File(
        io.BytesIO(text.encode()),
        filename=f"{channel.name}.txt"
    )

    log_channel = channel.guild.get_channel(LOG_CHANNEL_ID)

    await log_channel.send(
        f"📁 Transcript {channel.name}",
        file=file
    )


# =========================
# SELECT LOẠI TICKET
# =========================

class TicketSelect(Select):

    def __init__(self):

        options = [

            discord.SelectOption(label="selling ske"),
            discord.SelectOption(label="selling monkey"),

            discord.SelectOption(label="buying ske"),
            discord.SelectOption(label="buying monkey"),

            discord.SelectOption(label="hỗ trợ"),
            discord.SelectOption(label="bảo hành"),
        ]

        super().__init__(
            placeholder="Chọn loại ticket",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):

        await interaction.response.send_modal(
            MinecraftModal(self.values[0])
        )


class TicketView(View):

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# =========================
# LỆNH TẠO PANEL
# =========================

@bot.command()
async def panel(ctx):

    embed = discord.Embed(
        title="🎫 Tạo Ticket",
        description="Chọn loại ticket bên dưới"
    )

    await ctx.send(embed=embed, view=TicketView())


# =========================
# BOT READY
# =========================

@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")


bot.run(TOKEN)
