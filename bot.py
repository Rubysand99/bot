import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
import aiohttp
import asyncio
import json
import os
import io
import websockets

TOKEN = os.getenv("TOKEN")

# ===== CONFIG =====
ADMIN_IDS = [846332174734983219]
LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

LIVE_CHANNEL_ID = 1486967511839801414
PING_ROLE_ID = 1464411190808805540

TIKTOK_USER = "tuytam156"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

session = None

# ===== WEBSOCKET =====
clients = set()

async def ws_handler(websocket):
    clients.add(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        clients.remove(websocket)

async def send_ws(data):
    if clients:
        await asyncio.gather(*[c.send(data) for c in clients])

async def start_ws():
    server = await websockets.serve(ws_handler, "0.0.0.0", 8765)
    print("WebSocket chạy port 8765")

# ===== DATA =====
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

# ===== CHECK TICKET =====
async def has_ticket(guild, user):
    for ch in guild.text_channels:
        if ch.topic and str(user.id) in ch.topic:
            return True
    return False

# ===== TICKET =====
class MinecraftModal(Modal, title="Nhập thông tin"):
    mc_name = TextInput(label="Tên Minecraft")

    async def on_submit(self, interaction: discord.Interaction):
        if await has_ticket(interaction.guild, interaction.user):
            return await interaction.response.send_message("❌ Đã có ticket", ephemeral=True)

        number = get_ticket_number()

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True)
        }

        for admin in ADMIN_IDS:
            member = interaction.guild.get_member(admin)
            if member:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True)

        category = discord.utils.get(interaction.guild.categories, id=TICKET_CATEGORY_ID)

        channel = await interaction.guild.create_text_channel(
            f"ticket-{number}",
            overwrites=overwrites,
            category=category
        )

        await channel.edit(topic=f"{interaction.user.id}|{self.mc_name.value}")

        embed = discord.Embed(title=f"🎫 Ticket #{number}", color=0x00ffff)
        embed.add_field(name="User", value=interaction.user.mention)
        embed.add_field(name="Minecraft", value=self.mc_name.value)

        await channel.send(f"<@&{SUPPORT_ROLE_ID}>", embed=embed, view=TicketButtons())
        await interaction.response.send_message("✅ Đã tạo ticket", ephemeral=True)

class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green, custom_id="ticket_btn")
    async def create(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(MinecraftModal())

class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Đóng", style=discord.ButtonStyle.red, custom_id="close_btn")
    async def close(self, interaction: discord.Interaction, button: Button):
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

# ===== COMMAND =====
@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    embed = discord.Embed(title="🎫 Ticket", color=0x00ffff)
    await ctx.send(embed=embed, view=TicketPanel())

@bot.command()
async def close(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return

    messages = []
    async for msg in ctx.channel.history(limit=None):
        messages.append(f"<p><b>{msg.author}</b>: {msg.content}</p>")

    html = f"<html><body>{''.join(messages[::-1])}</body></html>"
    file = discord.File(io.BytesIO(html.encode()), filename="transcript.html")

    log = bot.get_channel(LOG_CHANNEL)
    if log:
        await log.send(f"📄 Transcript {ctx.channel.name}", file=file)

    await ctx.channel.delete()

@bot.command()
async def ping(ctx):
    await ctx.reply(f"🏓 {round(bot.latency*1000)}ms")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📜 Command", color=0x00ffff)
    embed.add_field(name=".panel", value="Tạo ticket")
    embed.add_field(name=".close", value="Đóng ticket")
    embed.add_field(name=".ping", value="Ping bot")
    await ctx.send(embed=embed)

# ===== TIKTOK CHECK (GIẢ LẬP DEMO) =====
is_live = False

@tasks.loop(seconds=10)
async def check_live():
    global is_live

    # ⚠️ demo (bạn thay API thật)
    import random
    live = random.choice([True, False])
    viewer = random.randint(10, 200)

    channel = bot.get_channel(LIVE_CHANNEL_ID)

    if live:
        await send_ws(json.dumps({
            "live": True,
            "viewer": viewer
        }))

        if not is_live:
            is_live = True
            embed = discord.Embed(
                title="🔴 ĐANG LIVE",
                description=f"👀 {viewer} viewer",
                color=0x00ffff
            )
            embed.add_field(name="Xem ngay", value=f"https://tiktok.com/@{TIKTOK_USER}")

            await channel.send(f"<@&{PING_ROLE_ID}>", embed=embed)

    else:
        await send_ws(json.dumps({
            "live": False,
            "viewer": 0
        }))

        if is_live:
            is_live = False
            await channel.send("⚫ Đã offline")

# ===== READY =====
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()

    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())

    bot.loop.create_task(start_ws())
    check_live.start()

    print(f"Bot online: {bot.user}")

bot.run(TOKEN)
