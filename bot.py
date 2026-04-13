import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import io
import os
import json
import asyncio
import aiohttp

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

last_live_state = None  # FIX: chống spam state
last_viewers = None     # FIX: chỉ update khi đổi view

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

# ================= API (FIXED) =================
async def get_live_data():
    global session
    try:
        async with session.get(
            f"https://tiktok-live-checker.onrender.com/live/{TIKTOK_USERNAME}"
        ) as res:
            if res.status != 200:
                return None  # FIX: không giả data
            return await res.json()
    except:
        return None  # FIX: lỗi thì skip hoàn toàn

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

    embed.set_footer(text="Update mỗi 10s (real data)")
    return embed

# ================= LIVE PROCESS (FIXED ANTI-SPAM) =================
async def process_live():
    global live_message_id, last_live_state, last_viewers

    data = await get_live_data()
    if not data:
        return  # FIX: API lỗi -> không làm gì

    channel = bot.get_channel(LIVE_CHANNEL_ID)

    live = data.get("live", False)
    title = data.get("title", "Livestream")
    viewers = data.get("viewers", None)

    if viewers is None:
        return  # FIX: không fake 0

    saved = load_live()

    # ================= LIVE START =================
    if live and not saved.get("live"):
        save_live({"live": True, "title": title, "viewers": viewers})

        viewer_history.clear()
        viewer_history.append(viewers)

        msg = await channel.send(
            content=f"<@&{PING_ROLE_ID}> 🔔 LIVE STARTED",
            embed=create_live_embed(title, viewers)
        )
        live_message_id = msg.id

        last_live_state = True
        last_viewers = viewers

    # ================= LIVE UPDATE =================
    elif live and saved.get("live"):
        # FIX: chỉ update nếu view thay đổi
        if viewers == last_viewers:
            return

        last_viewers = viewers
        viewer_history.append(viewers)

        save_live({"live": True, "title": title, "viewers": viewers})

        try:
            msg = await channel.fetch_message(live_message_id)
            await msg.edit(embed=create_live_embed(title, viewers))
        except:
            pass

    # ================= LIVE END =================
    elif not live and saved.get("live"):
        save_live({"live": False, "title": "", "viewers": 0})

        await channel.send(
            embed=discord.Embed(
                title="⛔ Livestream đã kết thúc",
                color=discord.Color.dark_gray()
            )
        )

        viewer_history.clear()
        live_message_id = None
        last_live_state = False
        last_viewers = None

# ================= LOOP =================
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

# ================= READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()

    bot.loop.create_task(live_loop())
    print(f"Bot online: {bot.user}")

# ================= RUN =================
bot.run(TOKEN)
