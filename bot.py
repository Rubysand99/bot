import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
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

CODE_CHANNEL_ID = 1486967511839801414
LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

API = "https://website-kiemtien.onrender.com"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

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
    data = await api_get(f"{API}/points/{user_id}")
    return data if data else {"points": 0}

# ================= LEADERBOARD =================
async def build_leaderboard(guild):
    data = await api_get(f"{API}/leaderboard")
    results = []

    if not data:
        return results

    for user in data:
        member = guild.get_member(int(user["userId"]))
        if member:
            results.append((member, user["points"]))

    return results[:10]

# ================= WITHDRAW =================
class WithdrawModal(Modal, title="Rút Point"):
    amount = TextInput(label="Nhập số point muốn rút", placeholder="Tối thiểu 5")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
        except:
            return await interaction.response.send_message("❌ Số không hợp lệ", ephemeral=True)

        if amount < 5:
            return await interaction.response.send_message("❌ Tối thiểu 5 point", ephemeral=True)

        data = await get_points(interaction.user.id)
        current = data.get("points", 0)

        if amount > current:
            return await interaction.response.send_message("❌ Không đủ point", ephemeral=True)

        result = await api_post(f"{API}/remove-point", {
            "discordId": str(interaction.user.id),
            "amount": amount
        })

        if not result or result.get("status") != "ok":
            return await interaction.response.send_message("❌ Lỗi server khi rút point", ephemeral=True)

        # ===== LOG =====
        log = bot.get_channel(LOG_CHANNEL)
        if log:
            await log.send(
                f"💸 {interaction.user} đã rút {amount} point <@846332174734983219>"
            )

        await interaction.response.send_message(
            f"✅ Đã rút {amount} point thành công!",
            ephemeral=True
        )

class WithdrawView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="💸 Rút point",
        style=discord.ButtonStyle.green,
        custom_id="withdraw_point"  # 🔥 BẮT BUỘC
    )
    async def withdraw(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WithdrawModal())

# ================= COMMAND =================
@bot.command()
async def point(ctx, sub=None):
    if not sub:
        data = await get_points(ctx.author.id)
        embed = discord.Embed(title="💰 Point", color=discord.Color.gold())
        embed.add_field(name="User", value=ctx.author.mention)
        embed.add_field(name="Point", value=data.get("points", 0))
        await ctx.reply(embed=embed, view=WithdrawView())

    elif sub == "lb":
        await ctx.reply("⏳ Đang tải leaderboard...")
        lb = await build_leaderboard(ctx.guild)

        text = "\n".join([
            f"{i}. {m.mention} - {p} point"
            for i, (m, p) in enumerate(lb, 1)
        ])

        embed = discord.Embed(
            title="🏆 Leaderboard",
            description=text or "Không có dữ liệu",
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)

# ================= CODE CHECK =================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    if message.channel.id == CODE_CHANNEL_ID:
        if content.startswith("EP-"):
            data = await api_post(f"{API}/check-code", {
                "code": content,
                "discordId": str(message.author.id)
            })

            if not data:
                return await message.reply("❌ lỗi server")

            status = data.get("status")

            if status in ["invalid", "used"]:
                await message.reply("code không hợp lệ ❌")
            elif status == "expired":
                await message.reply("⏱️ code hết hạn")
            elif status == "ok":
                await message.reply(
                    f"code hợp lệ ✔️ +1 point\n💰 Tổng: {data.get('points', 0)}"
                )

            return

    # ✅ LỆNH CHẠY MỌI KÊNH
    await bot.process_commands(message)

# ================= READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()
    bot.add_view(WithdrawView())
    print("Bot online:", bot.user)

# ================= RUN =================
bot.run(TOKEN)
