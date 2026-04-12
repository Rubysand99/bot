import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import io
import os
import json
import asyncio
import aiohttp
import time
import matplotlib.pyplot as plt

TOKEN = os.getenv("TOKEN")

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
    1438384178755276923
]

LOG_CHANNEL = 1482234024868053083
LIVE_LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

TIKTOK_USERNAME = "tuytam156"
LIVE_CHANNEL_ID = 1486967511839801414
PING_ROLE_ID = 1464411190808805540

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

session = None
live_message_id = None

viewer_history = []
time_history = []

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
            data = await res.json()
            return {
                "live": data.get("live", False),
                "title": data.get("title", "Đang livestream..."),
                "viewers": data.get("viewers", 0)
            }
    except:
        pass

    try:
        async with session.get(f"https://tiktok-api.vercel.app/live/{TIKTOK_USERNAME}") as res:
            data = await res.json()
            return {
                "live": data.get("live", False),
                "title": data.get("title", "Đang livestream..."),
                "viewers": data.get("viewers", 0)
            }
    except:
        pass

    return {"live": False, "title": "", "viewers": 0}

# ================= EMBED =================
def create_live_embed(title, viewers):
    embed = discord.Embed(
        title="🔴 LIVESTREAM ĐANG DIỄN RA!",
        description=f"🎯 {title}",
        color=discord.Color.red()
    )

    embed.add_field(name="👀 Người xem", value=str(viewers))
    embed.add_field(
        name="📺 Xem ngay",
        value=f"https://www.tiktok.com/@{TIKTOK_USERNAME}/live",
        inline=False
    )

    embed.set_thumbnail(url=f"https://unavatar.io/tiktok/{TIKTOK_USERNAME}")
    embed.set_footer(text="Auto update mỗi 10s")

    return embed

# ================= LIVE =================
async def check_tiktok_live():
    global live_message_id

    await bot.wait_until_ready()

    data_live = load_live()
    is_live = data_live.get("live", False)

    while not bot.is_closed():
        await process_live_check(is_live)
        data_live = load_live()
        is_live = data_live.get("live", False)
        await asyncio.sleep(10)

async def process_live_check(is_live):
    global live_message_id

    data = await get_live_data()
    channel = bot.get_channel(LIVE_CHANNEL_ID)
    log_channel = bot.get_channel(LIVE_LOG_CHANNEL)

    live_now = data["live"]
    title = data["title"]
    viewers = data["viewers"]

    # START LIVE
    if live_now and not is_live:
        save_live({"live": True})

        embed = create_live_embed(title, viewers)
        msg = await channel.send(content=f"<@&{PING_ROLE_ID}> 🔔", embed=embed)
        live_message_id = msg.id

        if log_channel:
            await log_channel.send(f"🔴 START LIVE\nTitle: {title}")

    # UPDATE
    elif live_now and is_live and live_message_id:
        viewer_history.append(viewers)
        time_history.append(int(time.time()))

        try:
            msg = await channel.fetch_message(live_message_id)
            embed = create_live_embed(title, viewers)
            await msg.edit(embed=embed)
        except:
            pass

    # OFFLINE
    elif not live_now and is_live:
        save_live({"live": False})

        await channel.send(embed=discord.Embed(
            title="⛔ Livestream đã kết thúc",
            color=discord.Color.dark_gray()
        ))

        # chart
        try:
            plt.figure()
            plt.plot(viewer_history)
            plt.xlabel("Time (10s)")
            plt.ylabel("Viewer")
            plt.title("Viewer Chart")

            file_path = "chart.png"
            plt.savefig(file_path)
            plt.close()

            if log_channel:
                await log_channel.send(file=discord.File(file_path))
        except Exception as e:
            print("Chart error:", e)

        viewer_history.clear()
        time_history.clear()
        live_message_id = None

# ================= COMMAND =================
@bot.command()
async def test(ctx):
    embed = create_live_embed("Test livestream", 999)
    await ctx.send(content=f"<@&{PING_ROLE_ID}> 🔔", embed=embed)

@bot.command()
async def status(ctx):
    data = await get_live_data()
    await ctx.send(f"Live: {data['live']}\nViewer: {data['viewers']}\nTitle: {data['title']}")

@bot.command()
async def forcecheck(ctx):
    await process_live_check(load_live().get("live", False))
    await ctx.send("✅ Checked")

@bot.command()
async def chart(ctx):
    if os.path.exists("chart.png"):
        await ctx.send(file=discord.File("chart.png"))
    else:
        await ctx.send("❌ Chưa có dữ liệu")

# ================= READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()
    bot.loop.create_task(check_tiktok_live())
    print(f"Bot online: {bot.user}")

# ================= RUN =================
bot.run(TOKEN)
