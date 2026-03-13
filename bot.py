import discord
from discord.ext import commands
from discord.ui import View, Select, Button, Modal, TextInput

TOKEN = "BOT_TOKEN_HERE"

ADMIN_ID = 1464961078042689588
TICKET_CATEGORY_ID = 123456789
STATUS_CHANNEL_ID = 123456789

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


class MinecraftModal(Modal):

    def __init__(self):
        super().__init__(title="Nhập thông tin")

        self.mc_name = TextInput(
            label="Tên tài khoản Minecraft",
            placeholder="Ví dụ: quannmc",
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


class TicketTypeSelect(View):

    def __init__(self, mc_name):
        super().__init__(timeout=None)
        self.mc_name = mc_name

        select = Select(
            placeholder="Chọn loại ticket",
            options=[
                discord.SelectOption(label="Mua item / money", emoji="💰"),
                discord.SelectOption(label="Hỗ trợ", emoji="❓"),
                discord.SelectOption(label="Bảo hành", emoji="🛠️"),
            ]
        )

        async def callback(interaction: discord.Interaction):

            ticket_type = select.values[0]
            guild = interaction.guild
            category = guild.get_channel(TICKET_CATEGORY_ID)

            channel_name = f"ticket-{self.mc_name}-{ticket_type}".replace(" ", "-").lower()

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }

            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites
            )

            await channel.send(
                f"<@{ADMIN_ID}> ơi, có {interaction.user.mention} cần {ticket_type}"
            )

            embed = discord.Embed(
                title="🧾 Ticket mới",
                color=0x5865F2
            )

            embed.add_field(name="Buyer", value=interaction.user.mention, inline=False)
            embed.add_field(name="Minecraft", value=self.mc_name, inline=False)
            embed.add_field(name="Loại ticket", value=ticket_type, inline=False)
            embed.add_field(name="Thanh toán", value="Ngân hàng TMCP Quân Đội", inline=False)

            await channel.send(embed=embed, view=TicketButtons())

            await interaction.response.send_message(
                f"✅ Ticket đã tạo: {channel.mention}",
                ephemeral=True
            )

        select.callback = callback
        self.add_item(select)


class TicketButtons(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: Button):

        await interaction.channel.send("🔒 Ticket đã đóng.")
        await interaction.channel.edit(locked=True)

    @discord.ui.button(label="Complete", style=discord.ButtonStyle.green)
    async def complete(self, interaction: discord.Interaction, button: Button):

        status_channel = interaction.guild.get_channel(STATUS_CHANNEL_ID)

        embed = discord.Embed(
            title="✅ Đơn hàng hoàn thành",
            description=f"{interaction.channel.name}",
            color=0x00ff00
        )

        await status_channel.send(embed=embed)

        await interaction.channel.send("🎉 Đơn hàng đã hoàn thành.")


class TicketPanel(View):

    @discord.ui.button(label="Tạo ticket", style=discord.ButtonStyle.green, emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):

        await interaction.response.send_modal(MinecraftModal())


@bot.command()
async def panel(ctx):

    embed = discord.Embed(
        title="🎫 Tuytam Store",
        description=(
            "Mở ticket để mua hàng hoặc hỗ trợ.\n\n"
            "**Server:** DonutSMP\n"
            "**Thanh toán:** Ngân hàng TMCP Quân Đội"
        ),
        color=0x5865F2
    )

    await ctx.send(embed=embed, view=TicketPanel())


@bot.event
async def on_ready():
    print(f"Bot đã online: {bot.user}")


bot.run(TOKEN)
