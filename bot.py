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
    try:
        async with session.get(url) as res:
            return await res.json()
    except:
        return None

async def api_post(url, data):
    try:
        async with session.post(url, json=data) as res:
            return await res.json()
    except:
        return None

async def get_points(user_id):
    return await api_get(f"{API}/points/{user_id}")

async def remove_points(user_id, amount=None):
    return await api_post(f"{API}/remove-point", {
        "discordId": str(user_id),
        "amount": amount
    })

# ================= MODAL =================

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

        await remove_points(interaction.user.id, amount)

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

# ================= LEADERBOARD REALTIME =================

async def build_leaderboard(guild):

    results = []

    for member in guild.members:

        if member.bot:
            continue

        data = await get_points(member.id)

        if not data:
            continue

        points = data.get("points", 0)

        if points > 0:
            results.append((member, points))

    # sort giảm dần
    results.sort(key=lambda x: x[1], reverse=True)

    return results[:10]

# ================= ON MESSAGE =================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip().lower()

    # ================= CODE CHANNEL =================
    if message.channel.id == CODE_CHANNEL_ID:

        # ===== POINT + LB =====
        if content.startswith("point"):

            parts = content.split()

            # ===== LEADERBOARD =====
            if len(parts) >= 2 and parts[1] == "lb":

                await message.reply("⏳ Đang tải leaderboard...")

                lb = await build_leaderboard(message.guild)

                text = ""
                for i, (member, points) in enumerate(lb, start=1):
                    text += f"{i}. {member.mention} - {points} point\n"

                embed = discord.Embed(
                    title="🏆 Leaderboard",
                    description=text or "Không có dữ liệu",
                    color=discord.Color.green()
                )

                await message.channel.send(embed=embed)
                return

            # ===== POINT =====
            # Trong on_message
async def on_message(self, message):
    if message.author.bot:  # Bỏ qua tin nhắn của bot
        return

    # ... code xử lý lệnh của bạn ...

    try:
        # Phần code lấy data từ API hoặc DB của hệ thống EarnPoint
        data = await get_points_data(...)  # hàm bạn đang gọi

        if data is None:
            # Xử lý trường hợp không có data (có thể log hoặc bỏ qua)
            print(f"[DEBUG] Data is None for message: {message.content}")
            return  # hoặc await message.channel.send("Không tìm thấy dữ liệu...")

        points = data.get("points", 0)
        # ... tiếp tục code của bạn

    except Exception as e:
        print(f"[ERROR] Lỗi xử lý on_message: {e}")
        # Không raise lại để bot không crash
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
                await api_post(f"{API}/add-point", {
                    "discordId": str(member.id),
                    "amount": amount
                })
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
