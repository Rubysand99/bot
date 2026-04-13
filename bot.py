import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import io
import os
import json
import asyncio
import aiohttp
import requests

TOKEN = os.getenv("TOKEN")

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
    1438384178755276923
]

LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

TIKTOK_USERNAME = "tuytam156"
LIVE_CHANNEL_ID = 1486967511839801414
PING_ROLE_ID = 1464411190808805540

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

session = None
live_message_id = None
viewer_history = []

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

def load_live():
    try:
        with open("live.json", "r") as f:
            return json.load(f)
    except:
        return {"live": False}

def save_live(data):
    with open("live.json", "w") as f:
        json.dump(data, f)

# ================= API =================
async def get_live_data():
    try:
        async with session.get(f"https://tiktok-live-checker.onrender.com/live/{TIKTOK_USERNAME}") as res:
            return await res.json()
    except:
        return {"live": False}

# ================= CHART =================
def create_chart_url():
    if len(viewer_history) < 2:
        return None

    data = {
        "type": "line",
        "data": {
            "labels": list(range(len(viewer_history))),
            "datasets": [{
                "label": "Viewer",
                "data": viewer_history
            }]
        }
    }

    return f"https://quickchart.io/chart?c={json.dumps(data)}"

# ================= EMBED =================
def create_live_embed(title, viewers):
    embed = discord.Embed(
        title="🔴 LIVESTREAM ĐANG DIỄN RA!",
        description=f"🎯 {title}",
        color=discord.Color.red()
    )

    embed.add_field(name="👀 Người xem", value=str(viewers))

    chart_url = create_chart_url()
    if chart_url:
        embed.set_image(url=chart_url)

    embed.add_field(
        name="📺 Xem ngay",
        value=f"https://www.tiktok.com/@{TIKTOK_USERNAME}/live",
        inline=False
    )

    embed.set_footer(text="Update mỗi 10s")
    return embed

# ================= TICKET =================
async def has_ticket(guild, user):
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic:
            return True
    return False

class MinecraftModal(Modal, title="Nhập thông tin"):
    mc_name = TextInput(label="Tên Minecraft")

    async def on_submit(self, interaction: discord.Interaction):
        if await has_ticket(interaction.guild, interaction.user):
            return await interaction.response.send_message("❌ Bạn đã có ticket", ephemeral=True)

        number = get_ticket_number()

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True)
        }

        category = discord.utils.get(interaction.guild.categories, id=TICKET_CATEGORY_ID)

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{number}",
            overwrites=overwrites,
            category=category
        )

        channel.topic = str(interaction.user.id)

        await channel.send(f"<@&{SUPPORT_ROLE_ID}> Ticket mới!")
        await interaction.response.send_message("✅ Đã tạo ticket", ephemeral=True)

class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(MinecraftModal())

# ================= LIVE =================
async def process_live():
    global live_message_id

    data = await get_live_data()
    channel = bot.get_channel(LIVE_CHANNEL_ID)

    live = data.get("live", False)
    title = data.get("title", "Livestream")
    viewers = data.get("viewers", 0)

    saved = load_live()

    print(f"[LIVE] {live} | {title} | {viewers}")

    if live and not saved.get("live"):
        save_live({
            "live": True,
            "title": title,
            "viewers": viewers
        })

        viewer_history.clear()

        msg = await channel.send(
            content=f"<@&{PING_ROLE_ID}> 🔔",
            embed=create_live_embed(title, viewers)
        )
        live_message_id = msg.id

    elif live and saved.get("live"):
        save_live({
            "live": True,
            "title": title,
            "viewers": viewers
        })

        viewer_history.append(viewers)

        try:
            msg = await channel.fetch_message(live_message_id)
            await msg.edit(embed=create_live_embed(title, viewers))
        except:
            pass

    elif not live and saved.get("live"):
        save_live({
            "live": False,
            "title": "",
            "viewers": 0
        })

        await channel.send(embed=discord.Embed(
            title="⛔ Livestream đã kết thúc",
            color=discord.Color.dark_gray()
        ))

        viewer_history.clear()
        live_message_id = None

async def live_loop():
    await bot.wait_until_ready()
    while True:
        await process_live()
        await asyncio.sleep(10)

# ================= COMMAND =================
@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! `{latency}ms`")

@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.send("❌ Không có quyền")
    await ctx.send("🎫 Tạo ticket", view=TicketPanel())

@bot.command()
async def close(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Không có quyền")

    if not ctx.channel.name.startswith("ticket"):
        return await ctx.reply("❌ Không phải ticket")

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
async def test(ctx):
    await ctx.send(
        content=f"<@&{PING_ROLE_ID}> 🔔",
        embed=create_live_embed("Test livestream", 999)
    )

@bot.command()
async def check(ctx):
    await process_live()
    await ctx.send("✅ Checked")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📖 Help", color=discord.Color.blue())
    embed.add_field(name=".ping", value="Xem độ trễ bot", inline=False)
    embed.add_field(name=".panel", value="Tạo ticket", inline=False)
    embed.add_field(name=".close", value="Đóng ticket + lưu transcript", inline=False)
    embed.add_field(name=".test", value="Test live", inline=False)
    embed.add_field(name=".check", value="Check live", inline=False)
    await ctx.send(embed=embed)

# ================= READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()

    bot.add_view(TicketPanel())

    bot.loop.create_task(live_loop())

    print(f"Bot online: {bot.user}")

# ================= RUN =================
bot.run(TOKEN)
