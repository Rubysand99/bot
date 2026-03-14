import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os
import io

TOKEN = os.getenv("TOKEN")

ADMIN_ROLE_ID = 1464961078042689588
CATEGORY_ID = 123456789012345678  # ID category ticket
STATUS_CHANNEL_ID = 1482233794512556223
LOG_CHANNEL_ID = 1482234024868053083

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


# =========================
# MODAL NHẬP THÔNG TIN
# =========================
class MinecraftModal(Modal):

    def __init__(self):
        super().__init__(title="Tuytam Store | Thông tin đơn hàng")

        self.mc_name = TextInput(
            label="Tên tài khoản Minecraft",
            placeholder="Ví dụ: QuannMC",
            required=True
        )

        self.amount = TextInput(
            label="Số lượng ske / money",
            placeholder="Ví dụ: 10 ske hoặc 5m money",
            required=False
        )

        self.add_item(self.mc_name)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):

        view = TicketTypeSelect(self.mc_name.value, self.amount.value)

        await interaction.response.send_message(
            "Chọn loại ticket:",
            view=view,
            ephemeral=True
        )


# =========================
# CHỌN LOẠI TICKET
# =========================
class TicketTypeSelect(View):

    def __init__(self, mc_name, amount):
        super().__init__(timeout=None)
        self.mc_name = mc_name
        self.amount = amount

        select = Select(
            placeholder="Chọn loại ticket",
            options=[
                discord.SelectOption(label="selling ske", value="selling-ske"),
                discord.SelectOption(label="selling money", value="selling-money"),
                discord.SelectOption(label="buying ske", value="buying-ske"),
                discord.SelectOption(label="buying money", value="buying-money"),
                discord.SelectOption(label="hỗ trợ", value="support"),
                discord.SelectOption(label="bảo hành", value="warranty"),
            ]
        )

        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):

        ticket_type = interaction.data["values"][0]

        guild = interaction.guild
        category = guild.get_channel(CATEGORY_ID)
        admin_role = guild.get_role(ADMIN_ROLE_ID)

        channel_name = f"ticket-{interaction.user.name}-{ticket_type}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            admin_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title="🧾 Ticket mới",
            color=0x2f3136
        )

        embed.add_field(name="Buyer", value=interaction.user.mention)
        embed.add_field(name="Minecraft", value=self.mc_name)
        embed.add_field(name="Số lượng", value=self.amount if self.amount else "Không ghi")
        embed.add_field(name="Loại ticket", value=ticket_type)

        await channel.send(
            f"<@&{ADMIN_ROLE_ID}> ơi, có {interaction.user.mention} cần **{ticket_type}**"
        )

        await channel.send(embed=embed, view=TicketButtons())

        # gửi status
        status_channel = guild.get_channel(STATUS_CHANNEL_ID)

        embed_status = discord.Embed(
            title="🟡 Đơn mới",
            color=0xffcc00
        )

        embed_status.add_field(name="Buyer", value=interaction.user.mention)
        embed_status.add_field(name="Minecraft", value=self.mc_name)
        embed_status.add_field(name="Số lượng", value=self.amount if self.amount else "Không ghi")
        embed_status.add_field(name="Loại ticket", value=ticket_type)
        embed_status.add_field(name="Trạng thái", value="Đang chờ xử lý")

        await status_channel.send(embed=embed_status)

        await interaction.response.send_message(
            f"✅ Ticket của bạn: {channel.mention}",
            ephemeral=True
        )


# =========================
# NÚT TRONG TICKET
# =========================
class TicketButtons(View):

    @discord.ui.button(label="✅ Hoàn thành đơn", style=discord.ButtonStyle.green)
    async def complete_ticket(self, interaction: discord.Interaction, button: Button):

        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)

        if admin_role not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ Chỉ admin mới dùng được",
                ephemeral=True
            )
            return

        status_channel = interaction.guild.get_channel(STATUS_CHANNEL_ID)

        embed = discord.Embed(
            title="🟢 Đơn đã hoàn thành",
            color=0x00ff00
        )

        embed.add_field(name="Ticket", value=interaction.channel.name)
        embed.add_field(name="Hoàn thành bởi", value=interaction.user.mention)

        await status_channel.send(embed=embed)

        await interaction.response.send_message("✅ Đã đánh dấu hoàn thành")

    @discord.ui.button(label="🔒 Đóng Ticket", style=discord.ButtonStyle.red)
    async def close_ticket(self, interaction: discord.Interaction, button: Button):

        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)

        if admin_role not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ Chỉ admin mới đóng được",
                ephemeral=True
            )
            return

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)

        transcript = []

        async for msg in interaction.channel.history(limit=None, oldest_first=True):

            content = msg.content

            if msg.attachments:
                content += " " + " ".join(a.url for a in msg.attachments)

            transcript.append(f"[{msg.created_at}] {msg.author}: {content}")

        transcript_text = "\n".join(transcript)

        file = discord.File(
            io.BytesIO(transcript_text.encode()),
            filename=f"{interaction.channel.name}.txt"
        )

        embed = discord.Embed(
            title="🧾 Ticket Transcript",
            color=0xff0000
        )

        embed.add_field(name="Ticket", value=interaction.channel.name)
        embed.add_field(name="Đóng bởi", value=interaction.user.mention)

        await log_channel.send(embed=embed, file=file)

        await interaction.channel.delete()


# =========================
# PANEL TẠO TICKET
# =========================
class CreateTicket(View):

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green)

    async def create_ticket(self, interaction: discord.Interaction, button: Button):

        await interaction.response.send_modal(MinecraftModal())


# =========================
# LỆNH PANEL
# =========================
@bot.command()

async def ticket(ctx):

    embed = discord.Embed(
        title="🎫 Tuytam Store",
        description="Nhấn nút bên dưới để tạo ticket giao dịch / hỗ trợ",
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
