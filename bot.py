import discord
from discord.ext import commands
from discord.ui import Button, View
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

shop_name = "𝙩𝙪𝙮𝙩𝙖𝙢 𝙨𝙩𝙤𝙧𝙚✨"

order_id = 1000


class TicketButtons(View):

    def __init__(self, status_message):
        super().__init__(timeout=None)
        self.status_message = status_message

    async def update_status(self, interaction, text):
        embed = self.status_message.embeds[0]
        embed.set_field_at(3, name="📊 Trạng thái", value=text, inline=False)
        await self.status_message.edit(embed=embed)
        await interaction.response.send_message("Đã cập nhật trạng thái.", ephemeral=True)

    @discord.ui.button(label="💳 Đã thanh toán", style=discord.ButtonStyle.primary)
    async def paid(self, interaction: discord.Interaction, button: Button):
        await self.update_status(interaction, "💳 Đã thanh toán")

    @discord.ui.button(label="📦 Đang xử lý", style=discord.ButtonStyle.secondary)
    async def processing(self, interaction: discord.Interaction, button: Button):
        await self.update_status(interaction, "📦 Đang xử lý")

    @discord.ui.button(label="✅ Hoàn thành", style=discord.ButtonStyle.success)
    async def done(self, interaction: discord.Interaction, button: Button):
        await self.update_status(interaction, "✅ Hoàn thành")

    @discord.ui.button(label="❌ Huỷ đơn", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await self.update_status(interaction, "❌ Đã huỷ")

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.delete()


class CreateTicket(View):

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.success)
    async def create_ticket(self, interaction: discord.Interaction, button: Button):

        await interaction.response.send_message("Nhập **tên Minecraft** của bạn:", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        msg = await bot.wait_for("message", check=check)
        mc_name = msg.content.lower()

        await interaction.followup.send(
            "Chọn loại ticket:\n1️⃣ Mua Item / Money\n2️⃣ Bán Item\n3️⃣ Hỗ trợ / Bảo hành",
            ephemeral=True
        )

        msg2 = await bot.wait_for("message", check=check)

        types = {
            "1": ("Mua Item / Money", "mua"),
            "2": ("Bán Item", "ban"),
            "3": ("Hỗ trợ / Bảo hành", "hotro")
        }

        ticket_type, short = types.get(msg2.content, ("Khác", "khac"))

        global order_id
        order_id += 1

        guild = interaction.guild

        category = discord.utils.get(guild.categories, name="TICKETS")
        admin_role = discord.utils.get(guild.roles, name="Admin")

        channel = await guild.create_text_channel(
            f"ticket-{mc_name}-{short}",
            category=category
        )

        embed = discord.Embed(
            title=f"📦 ORDER #{order_id}",
            color=0x2ecc71
        )

        embed.add_field(name="👤 Khách", value=interaction.user.mention)
        embed.add_field(name="🎮 Minecraft username", value=mc_name)
        embed.add_field(name="📂 Loại", value=ticket_type)
        embed.add_field(name="📊 Trạng thái", value="⏳ Chưa xử lý", inline=False)

        await channel.send(admin_role.mention, embed=embed)

        status_channel = discord.utils.get(guild.text_channels, name="status")

        status_msg = await status_channel.send(embed=embed)

        view = TicketButtons(status_msg)

        await channel.send("Quản lý đơn hàng:", view=view)

        await interaction.followup.send(
            f"Ticket của bạn: {channel.mention}",
            ephemeral=True
        )


@bot.command()
async def panel(ctx):

    embed = discord.Embed(
        title=shop_name,
        description="Nhấn nút để tạo ticket mua bán."
    )

    await ctx.send(embed=embed, view=CreateTicket())


bot.run(TOKEN)
