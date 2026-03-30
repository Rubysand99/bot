import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import aiohttp
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

API = "https://website-kiemtien.onrender.com"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

session = None

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

# ================= API =================
async def api_get(url):
    async with session.get(url) as res:
        return await res.json()

async def api_post(url, data):
    async with session.post(url, json=data) as res:
        return await res.json()

async def get_points(user_id):
    data = await api_get(f"{API}/points/{user_id}")
    return data if data else {"points": 0}

# ================= WITHDRAW =================
class WithdrawModal(Modal, title="Rút Point"):
    amount = TextInput(label="Nhập số point", placeholder="Tối thiểu 2")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
        except:
            return await interaction.response.send_message("❌ Số không hợp lệ", ephemeral=True)

        if amount < 2:
            return await interaction.response.send_message("❌ Tối thiểu 2 point", ephemeral=True)

        data = await get_points(interaction.user.id)
        if amount > data["points"]:
            return await interaction.response.send_message("❌ Không đủ point", ephemeral=True)

        await api_post(f"{API}/remove-point", {
            "discordId": str(interaction.user.id),
            "amount": amount
        })

        log = bot.get_channel(LOG_CHANNEL)
        if log:
            await log.send(f"💸 {interaction.user} rút {amount} point")

        await interaction.response.send_message(f"✅ Đã rút {amount} point", ephemeral=True)

class WithdrawView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💸 Rút point", style=discord.ButtonStyle.green, custom_id="withdraw_btn")
    async def withdraw(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WithdrawModal())

# ================= TICKET =================
class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
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

        embed = discord.Embed(
            title=f"🎫 Ticket #{number}",
            description=f"{interaction.user.mention} đã tạo ticket",
            color=discord.Color.green()
        )

        await channel.send(
            f"<@&{SUPPORT_ROLE_ID}>",
            embed=embed,
            view=TicketButtons()
        )

class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Đóng ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Không có quyền", ephemeral=True)

        await interaction.response.defer()

        messages = []
        async for msg in interaction.channel.history(limit=None):
            messages.append(f"<p><b>{msg.author}</b>: {msg.content}</p>")

        html = f"<html><body>{''.join(messages[::-1])}</body></html>"

        file = discord.File(io.BytesIO(html.encode()), filename="transcript.html")

        log = bot.get_channel(LOG_CHANNEL)
        if log:
            await log.send(f"📄 Transcript {interaction.channel.name}", file=file)

        await interaction.channel.delete()

# ================= COMMAND =================
@bot.command()
async def point(ctx):
    data = await get_points(ctx.author.id)

    embed = discord.Embed(title="💰 Point", color=discord.Color.gold())
    embed.add_field(name="User", value=ctx.author.mention)
    embed.add_field(name="Point", value=data["points"])

    await ctx.reply(embed=embed, view=WithdrawView())

@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return

    embed = discord.Embed(title="🎫 Tạo Ticket", color=discord.Color.blue())
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

    file = discord.File(io.BytesIO(html.encode()), filename="transcript.html")

    log = bot.get_channel(LOG_CHANNEL)
    if log:
        await log.send(f"📄 Transcript {ctx.channel.name}", file=file)

    await ctx.channel.delete()

# ================= ON MESSAGE =================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == CODE_CHANNEL_ID:
        if message.content.startswith("EP-"):
            data = await api_post(f"{API}/check-code", {
                "code": message.content,
                "discordId": str(message.author.id)
            })

            if not data:
                return await message.reply("❌ lỗi server")

            if data.get("status") == "ok":
                await message.reply(f"✔️ +1 point\n💰 Tổng: {data.get('points', 0)}")
            else:
                await message.reply("❌ code sai")

    await bot.process_commands(message)

# ================= READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()

    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    bot.add_view(WithdrawView())

    print(f"Bot online: {bot.user}")

# ================= RUN =================
bot.run(TOKEN)
