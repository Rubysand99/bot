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
            if res.status == 200:
                return await res.json()
            return None
    except:
        return None

async def api_post(url, data):
    try:
        async with session.post(url, json=data) as res:
            if res.status == 200:
                return await res.json()
            return None
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
            return await interaction.response.send_message("❌ Số không hợp lệ", ephemeral=True)

        if amount < 5:
            return await interaction.response.send_message("❌ Tối thiểu 5 point", ephemeral=True)

        data = await get_points(interaction.user.id)
        current = data.get("points", 0) if data is not None else 0

        if amount > current:
            return await interaction.response.send_message("❌ Không đủ point", ephemeral=True)

        await remove_points(interaction.user.id, amount)

        log = bot.get_channel(LOG_ADMIN_CHANNEL)
        if log:
            await log.send(f"💸 <@{ADMIN_PING}> | {interaction.user} rút {amount} point")

        await interaction.response.send_message(f"✅ Đã rút {amount} point", ephemeral=True)

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

# ================= LEADERBOARD =================
async def build_leaderboard(guild):
    results = []
    for member in guild.members:
        if member.bot:
            continue
        data = await get_points(member.id)
        if data and (points := data.get("points", 0)) > 0:
            results.append((member, points))

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

        # ===== POINT + LEADERBOARD =====
        if content.startswith("point"):
            parts = content.split()

            # Leaderboard
            if len(parts) >= 2 and parts[1] == "lb":
                await message.reply("⏳ Đang tải leaderboard...")
                lb = await build_leaderboard(message.guild)

                text = "\n".join([f"{i}. {member.mention} - {points} point" 
                                for i, (member, points) in enumerate(lb, start=1)])

                embed = discord.Embed(
                    title="🏆 Leaderboard",
                    description=text or "Không có dữ liệu",
                    color=discord.Color.green()
                )
                await message.channel.send(embed=embed)
                return

            # ===== Xem point cá nhân =====
            data = await get_points(message.author.id)
            points = data.get("points", 0) if data is not None else 0

            embed = discord.Embed(
                title="💰 Thông tin point",
                color=discord.Color.gold()
            )
            embed.add_field(name="👤 User", value=message.author.mention, inline=False)
            embed.add_field(name="💎 Point", value=str(points), inline=False)

            await message.reply(embed=embed, view=WithdrawView())
            return

        # ===== Nhập code EP- =====
        if message.content.startswith("EP-"):
            data = await api_post(f"{API}/check-code", {
                "code": message.content,
                "discordId": str(message.author.id)
            })

            if not data:
                return await message.reply("❌ Lỗi server")

            status = data.get("status")
            if status == "ok":
                await message.reply(f"✅ +1 point | Tổng: {data.get('points', 0)}")
            elif status == "expired":
                await message.reply("⏱️ Code hết hạn")
            elif status == "used":
                await message.reply("❌ Code đã dùng")
            else:
                await message.reply("❌ Code không hợp lệ")
            return

    # ================= ADMIN CHANNEL =================
    if message.channel.id == LOG_ADMIN_CHANNEL:
        if content.startswith(("gp ", "xp ")):
            if message.author.id not in ADMIN_IDS:
                return await message.reply("❌ Không có quyền")

            parts = message.content.split()
            if len(parts) < 2:
                return

            username = parts[1]
            member = discord.utils.find(
                lambda m: m.name.lower() == username.lower() or str(m.id) == username,
                message.guild.members
            )

            if not member:
                return await message.reply("❌ Không tìm thấy user")

            if content.startswith("gp "):
                try:
                    amount = int(parts[2])
                    await api_post(f"{API}/add-point", {
                        "discordId": str(member.id),
                        "amount": amount
                    })
                    await message.reply(f"✅ Đã cộng +{amount} point cho {member.mention}")
                except:
                    await message.reply("❌ Số point không hợp lệ")

            elif content.startswith("xp "):
                try:
                    amount = int(parts[2]) if len(parts) > 2 else None
                    await remove_points(member.id, amount)
                    await message.reply(f"🗑️ Đã xử lý trừ point cho {member.mention}")
                except:
                    await message.reply("❌ Số point không hợp lệ")
        return

    # Xử lý command prefix nếu có
    await bot.process_commands(message)


# ================= READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()
    bot.add_view(WithdrawView())
    print(f"Bot online: {bot.user}")


# ================= CLOSE =================
@bot.event
async def on_close():
    if session:
        await session.close()


# ================= RUN =================
bot.run(TOKEN)
