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

# 🔴 TikTok config
TIKTOK_USERNAME = "tuytam156"
LIVE_CHANNEL_ID = 1486967511839801414
PING_ROLE_ID = 1464411190808805540

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

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

# ================= LIVE SAVE =================
def load_live():
    try:
        with open("live.json", "r") as f:
            return json.load(f)
    except:
        return {"live": False}

def save_live(data):
    with open("live.json", "w") as f:
        json.dump(data, f)

# ================= API LIVE =================
async def get_live_data():
    try:
        async with session.get(f"https://tiktok-live-checker.onrender.com/live/{TIKTOK_USERNAME}") as res:
            data = await res.json()
            return {
                "live": data.get("live", False),
                "title": data.get("title", "Đang livestream...")
            }
    except:
        pass

    try:
        async with session.get(f"https://tiktok-api.vercel.app/live/{TIKTOK_USERNAME}") as res:
            data = await res.json()
            return {
                "live": data.get("live", False),
                "title": data.get("title", "Đang livestream...")
            }
    except:
        pass

    return {"live": False, "title": ""}

# ================= EMBED =================
def create_live_embed(title):
    embed = discord.Embed(
        title="🔴 LIVESTREAM ĐANG DIỄN RA!",
        description=f"**{TIKTOK_USERNAME} đang phát trực tiếp**\n\n🎯 {title}",
        color=discord.Color.red()
    )

    embed.add_field(
        name="📺 Xem ngay",
        value=f"[👉 Click vào đây để xem LIVE](https://www.tiktok.com/@{TIKTOK_USERNAME}/live)",
        inline=False
    )

    embed.add_field(name="🔥 Trạng thái", value="Đang trực tiếp 🔴")
    embed.add_field(name="👤 Creator", value=f"@{TIKTOK_USERNAME}")

    embed.set_thumbnail(url=f"https://unavatar.io/tiktok/{TIKTOK_USERNAME}")
    embed.set_footer(text="🚀 Nhấn để tham gia ngay!")

    return embed

# ================= TIKTOK CHECK =================
async def check_tiktok_live():
    await bot.wait_until_ready()

    data_live = load_live()
    is_live = data_live.get("live", False)

    while not bot.is_closed():
        try:
            data = await get_live_data()
            live_now = data["live"]
            title = data["title"]

            channel = bot.get_channel(LIVE_CHANNEL_ID)

            if live_now and not is_live:
                is_live = True
                save_live({"live": True})

                if channel:
                    embed = create_live_embed(title)
                    await channel.send(content=f"<@&{PING_ROLE_ID}> 🔔", embed=embed)

            elif not live_now and is_live:
                is_live = False
                save_live({"live": False})

                if channel:
                    embed = discord.Embed(
                        title="⛔ Livestream đã kết thúc",
                        description=f"{TIKTOK_USERNAME} đã offline.",
                        color=discord.Color.dark_gray()
                    )
                    await channel.send(embed=embed)

        except Exception as e:
            print("TikTok error:", e)

        await asyncio.sleep(60)

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
    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green)
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(MinecraftModal())

# ================= COMMAND =================
@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    await ctx.send("🎫 Tạo ticket", view=TicketPanel())

# 🧪 TEST COMMAND
@bot.command()
async def test(ctx):
    embed = create_live_embed("Đây là test livestream 🔥")
    await ctx.send(content=f"<@&{PING_ROLE_ID}> 🔔", embed=embed)

# ================= READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()

    bot.add_view(TicketPanel())
    bot.loop.create_task(check_tiktok_live())

    print(f"Bot online: {bot.user}")

# ================= RUN =================
bot.run(TOKEN)
