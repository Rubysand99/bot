import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import io
import os
import json

TOKEN = os.getenv("TOKEN")

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
    1438384178755276923
]

LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

CODE_CHANNEL_ID = 1486967511839801414

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ================= DATA =================
def load_data():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except:
        return {"ticket": 0}

def save_data(data):
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

def get_ticket_number():
    data = load_data()
    data["ticket"] += 1
    save_data(data)
    return f"{data['ticket']:03d}"

# ================= CHECK TICKET =================
async def has_ticket(guild, user):
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic:
            return True
    return False

# ================= MODAL =================
class MinecraftModal(Modal, title="Nhập thông tin"):
    mc_name = TextInput(label="Tên Minecraft", placeholder="Ví dụ: quannmc")

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild

        if await has_ticket(guild, interaction.user):
            return await interaction.response.send_message(
                "❌ Bạn đã có ticket rồi", ephemeral=True
            )

        number = get_ticket_number()

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True)
        }

        for admin_id in ADMIN_IDS:
            member = guild.get_member(admin_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True)

        category = discord.utils.get(guild.categories, id=TICKET_CATEGORY_ID)

        channel = await guild.create_text_channel(
            name=f"ticket-{number}",
            overwrites=overwrites,
            category=category
        )

        channel.topic = f"{interaction.user.id}|{self.mc_name.value}"

        embed = discord.Embed(
            title=f"🎫 Ticket #{number}",
            color=discord.Color.green()
        )

        embed.add_field(name="👤 User", value=interaction.user.mention, inline=False)
        embed.add_field(name="🎮 Minecraft", value=self.mc_name.value, inline=False)

        await channel.send(
            f"<@&{SUPPORT_ROLE_ID}>",
            embed=embed,
            view=TicketButtons()
        )

        await interaction.response.send_message("✅ Đã tạo ticket!", ephemeral=True)

# ================= TICKET PANEL =================
class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎫 Tạo Ticket",
        style=discord.ButtonStyle.green,
        custom_id="create_ticket"
    )
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(MinecraftModal())

# ================= TICKET BUTTONS =================
class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Đóng ticket",
        style=discord.ButtonStyle.red,
        custom_id="close_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message(
                "❌ Không có quyền", ephemeral=True
            )

        await interaction.response.defer()

        messages = []
        async for msg in interaction.channel.history(limit=None):
            messages.append(f"<p><b>{msg.author}</b>: {msg.content}</p>")

        html = f"<html><body>{''.join(messages[::-1])}</body></html>"

        file = discord.File(
            io.BytesIO(html.encode()),
            filename="transcript.html"
        )

        log = bot.get_channel(LOG_CHANNEL)
        if log:
            await log.send(
                f"📄 Transcript {interaction.channel.name}",
                file=file
            )

        await interaction.channel.delete()

# ================= COMMANDS =================
@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return

    embed = discord.Embed(
        title="🎫 Tạo Ticket",
        color=discord.Color.blue()
    )

    await ctx.send(embed=embed, view=TicketPanel())

@bot.command()
async def close(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Bạn không có quyền")

    if not ctx.channel.name.startswith("ticket"):
        return await ctx.reply("❌ Không phải kênh ticket")

    messages = []
    async for msg in ctx.channel.history(limit=None):
        messages.append(f"<p><b>{msg.author}</b>: {msg.content}</p>")

    html = f"<html><body>{''.join(messages[::-1])}</body></html>"

    file = discord.File(
        io.BytesIO(html.encode()),
        filename="transcript.html"
    )

    log = bot.get_channel(LOG_CHANNEL)
    if log:
        await log.send(
            f"📄 Transcript {ctx.channel.name}",
            file=file
        )

    await ctx.channel.delete()

# ================= ON READY =================
@bot.event
async def on_ready():
    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    print(f"Bot online: {bot.user}")

# ================= RUN =================
bot.run(TOKEN)
