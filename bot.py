import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import aiohttp
import os

TOKEN = os.getenv("TOKEN")

ADMIN_IDS = [
    846332174734983219
]

CODE_CHANNEL_ID = 1486967511839801414
LOG_CHANNEL = 1482234024868053083

API = "https://website-kiemtien.onrender.com"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

session = None

# ================= API =================
async def api_get(url):
    async with session.get(url) as res:
        return await res.json()

async def api_post(url, data):
    async with session.post(url, json=data) as res:
        return await res.json()

async def get_points(user_id):
    data = await api_get(f"{API}/points/{user_id}")
    return data.get("points", 0)

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

        current = await get_points(interaction.user.id)

        if amount > current:
            return await interaction.response.send_message("❌ Không đủ point", ephemeral=True)

        data = await api_post(f"{API}/remove-point", {
            "discordId": str(interaction.user.id),
            "amount": amount
        })

        if data.get("status") != "ok":
            return await interaction.response.send_message("❌ Lỗi server", ephemeral=True)

        # LOG
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

# ================= LEADERBOARD =================
async def build_lb(guild):
    result = []
    for m in guild.members:
        if m.bot:
            continue
        p = await get_points(m.id)
        if p > 0:
            result.append((m, p))
    result.sort(key=lambda x: x[1], reverse=True)
    return result[:10]

# ================= COMMAND =================
@bot.command()
async def point(ctx, sub=None):
    if sub == "lb":
        await ctx.reply("⏳ Đang tải...")
        lb = await build_lb(ctx.guild)

        text = "\n".join([
            f"{i}. {m.mention} - {p}"
            for i,(m,p) in enumerate(lb,1)
        ])

        embed = discord.Embed(title="🏆 Leaderboard", description=text or "Không có dữ liệu")
        return await ctx.send(embed=embed)

    p = await get_points(ctx.author.id)

    embed = discord.Embed(title="💰 Point", color=discord.Color.gold())
    embed.add_field(name="User", value=ctx.author.mention)
    embed.add_field(name="Point", value=str(p))

    await ctx.reply(embed=embed, view=WithdrawView())

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="📋 Lệnh bot",
        description="""
💰 .point → xem point  
🏆 .point lb → leaderboard  
🎁 nhập code → gửi trực tiếp EP-XXXXX  
        """,
        color=discord.Color.blue()
    )
    await ctx.reply(embed=embed)

# ================= CODE =================
@bot.event
async def on_message(msg):
    if msg.author.bot:
        return

    content = msg.content.strip()

    if content.startswith("EP-"):
        data = await api_post(f"{API}/check-code", {
            "code": content,
            "discordId": str(msg.author.id)
        })

        if not data:
            return await msg.reply("❌ lỗi server")

        if data["status"] == "invalid":
            await msg.reply("❌ Code sai")
        elif data["status"] == "ok":
            await msg.reply(f"✔️ +1 point | Tổng: {data['points']}")

    await bot.process_commands(msg)

# ================= ERROR FIX =================
@bot.event
async def on_command_error(ctx, error):
    from discord.ext.commands import CommandNotFound

    if isinstance(error, CommandNotFound):
        return

    print("ERROR:", error)

# ================= READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()

    bot.add_view(WithdrawView())

    print(f"Bot online: {bot.user}")

# ================= RUN =================
bot.run(TOKEN)
