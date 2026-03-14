import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput, Select
import os

TOKEN = os.getenv("TOKEN")

ADMIN_ID = 1464961078042689588
CATEGORY_ID = 123456789012345678  # ID category ticket (bạn sửa)
STATUS_CHANNEL_ID = 123456789012345678  # kênh status (bạn sửa)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


# =========================
# FORM NHẬP TÊN MINECRAFT
# =========================
class MinecraftModal(Modal):
    def __init__(self):
        super().__init__(title="Nhập thông tin")

        self.mc_name = TextInput(
            label="Tên tài khoản Minecraft",
            placeholder="Ví dụ: QuannMC",
            required=True
        )

        self.add_item(self.mc_name)

    async def on_submit(self, interaction: discord.Interaction):

        view = TicketTypeSelect(self.mc_name.value)

        await interaction.response.send_message(
            "Chọn loại ticket:",
            view=view,
            ephemeral=True
        )


# =========================
# CHỌN LOẠI TICKET
# =========================
class TicketTypeSelect(View):

    def __init__(self, mc_name):
        super().__init__(timeout=None)
        self.mc_name = mc_name

        select = Select(
            placeholder="Chọn loại ticket",
            options=[
                discord.SelectOption(label="Mua Item", value="buy_item"),
                discord.SelectOption(label="Mua Money", value="buy_money"),
                discord.SelectOption(label="Hỗ trợ", value="support"),
                discord.SelectOption(label="Bảo hành", value="warranty"),
            ]
        )

        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):

        ticket_type = interaction.data["values"][0]

        guild = interaction.guild
        category = guild.get_channel(CATEGORY_ID)

        channel_name = f"ticket-quannmc-{ticket_type}-{interaction.user.name}"

        channel = await guild.create_text_channel(
            channel_name,
            category=category
        )

        admin = guild.get_member(ADMIN_ID)

        embed = discord.Embed(
            title="📦 Ticket mới",
            color=0x2f3136
        )

        embed.add_field(name="Khách hàng", value=interaction.user.mention)
        embed.add_field(name="Minecraft", value=self.mc_name)
        embed.add_field(name="Loại ticket", value=ticket_type)

        await channel.send(
            f"<@{ADMIN_ID}> ơi, có {interaction.user.mention} cần **{ticket_type}**"
        )

        await channel.send(embed=embed)

        await interaction.response.send_message(
            f"✅ Ticket của bạn đã được tạo: {channel.mention}",
            ephemeral=True
        )


# =========================
# NÚT TẠO TICKET
# =========================
class CreateTicket(View):

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green)
    async def create_ticket(self, interaction: discord.Interaction, button: Button):

        modal = MinecraftModal()
        await interaction.response.send_modal(modal)


# =========================
# LỆNH TẠO PANEL
# =========================
@bot.command()
async def ticket(ctx):

    embed = discord.Embed(
        title="🎫 Tuytam Store Support",
        description=(
            "Nhấn nút bên dưới để tạo ticket\n\n"
            "• Mua item\n"
            "• Mua money\n"
            "• Hỗ trợ\n"
            "• Bảo hành"
        ),
        color=0x5865F2
    )

    await ctx.send(embed=embed, view=CreateTicket())


# =========================
# BOT READY
# =========================
@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")


bot.run(TOKEN)
