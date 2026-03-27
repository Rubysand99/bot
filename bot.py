import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import aiohttp
import os

TOKEN = os.getenv("TOKEN")

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
    1438384178755276923
]

ADMIN_PING = 846332174734983219

LOG_ADMIN_CHANNEL = 1464524557657440396
CODE_CHANNEL_ID = 1486967511839801414

API = "https://website-kiemtien.onrender.com"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

session = None

# ================= API =================

async def api_get(url):
    async with session.get(url) as res:
        return await res.json()

async def api_post(url, data):
    async with session.post(url, json=data) as res:
        return await res.json()

async def get_points(user_id):
    return await api_get(f"{API}/points/{user_id}")

async def add_points(user_id, amount):
    return await api_post(f"{API}/add-point", {
        "discordId": str(user_id),
        "amount": amount
    })

async def remove_points(user_id, amount=None):
    return await api_post(f"{API}/remove-point", {
        "discordId": str(user_id),
        "amount": amount
    })

async def get_leaderboard():
    return await api_get(f"{API}/leaderboard")

# ================= MODAL RÚT =================

class WithdrawModal(Modal, title="Rút Point"):

    amount = TextInput(label="Nhập số point muốn rút")

    async def on_submit(self, interaction: discord.Interaction):

        try:
            amount = int(self.amount.value)
        except:
            return await interaction.response.send_message(
                "❌ Số không hợp lệ",
                ephemeral=True
            )

        if amount < 5:
            return await interaction.response.send_message(
                "❌ Tối thiểu 5 point",
                ephemeral=True
            )

        data = await get_points(interaction.user.id)
        current = data.get("points", 0)

        if amount > current:
            return await interaction.response.send_message(
                "❌ Không đủ point",
                ephemeral=True
            )

        # ✅ trừ point
        await remove_points(interaction.user.id, amount)

        # ✅ gửi log
        log = bot.get_channel(LOG_ADMIN_CHANNEL)
        if log:
            await log.send(
                f"💸 <@{ADMIN_PING}> | {interaction.user} rút {amount} point"
            )

        await interaction.response.send_message(
            f"✅ Đã rút {amount} point",
            ephemeral=True
        )

# ================= BUTTON =================

class WithdrawView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="💸 Rút point",
        style=discord.ButtonStyle.green,
        custom_id="withdraw_point"
    )
    async def withdraw(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WithdrawModal())

# ================= READY =================

@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()
    bot.add_view(WithdrawView())
    print("Bot online:", bot.user)

# ================= ON MESSAGE =================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip().lower()

    # ================= CODE CHANNEL =================
    if message.channel.id == CODE_CHANNEL_ID:

        # ===== POINT =====
        if content == "point":

            data = await get_points(message.author.id)
            points = data.get("points", 0)

            embed = discord.Embed(
                title="💰 Thông tin point",
                color=discord.Color.gold()
            )
            embed.add_field(name="👤 User", value=message.author.mention)
            embed.add_field(name="💎 Point", value=str(points))

            await message.reply(embed=embed, view=WithdrawView())
            return

        # ===== LEADERBOARD =====
        if content == "point lb":

            data = await get_leaderboard()

            if not data:
                return await message.reply("❌ lỗi server")

            text = ""
            for i, user in enumerate(data[:10], start=1):
                if user["points"] > 0:
                    text += f"{i}. <@{user['discordId']}> - {user['points']} point\n"

            embed = discord.Embed(
                title="🏆 Leaderboard",
                description=text or "Không có dữ liệu",
                color=discord.Color.green()
            )

            await message.reply(embed=embed)
            return

        # ===== CODE =====
        if message.content.startswith("EP-"):

            data = await api_post(f"{API}/check-code", {
                "code": message.content,
                "discordId": str(message.author.id)
            })

            if not data:
                return await message.reply("❌ lỗi server")

            if data.get("status") == "ok":
                await message.reply(
                    f"✅ +1 point | Tổng: {data.get('points', 0)}"
                )
            elif data.get("status") == "expired":
                await message.reply("⏱️ code hết hạn")
            elif data.get("status") == "used":
                await message.reply("❌ code đã dùng")
            else:
                await message.reply("❌ code không hợp lệ")

        return

    # ================= ADMIN CHANNEL =================
    if message.channel.id == LOG_ADMIN_CHANNEL:

        if content.startswith("gp ") or content.startswith("xp "):

            if message.author.id not in ADMIN_IDS:
                return await message.reply("❌ Không có quyền")

            parts = message.content.split()
            username = parts[1]

            member = discord.utils.find(
                lambda m: m.name.lower() == username.lower(),
                message.guild.members
            )

            if not member:
                return await message.reply("❌ Không tìm thấy user")

            if content.startswith("gp"):
                amount = int(parts[2])
                await add_points(member.id, amount)
                await message.reply(f"✅ +{amount} point {member.mention}")

            elif content.startswith("xp"):
                amount = int(parts[2]) if len(parts) > 2 else None
                await remove_points(member.id, amount)
                await message.reply("🗑️ Đã xử lý")

        return

# ================= CLOSE =================

@bot.event
async def on_close():
    if session:
        await session.close()

# ================= RUN =================

bot.run(TOKEN)
