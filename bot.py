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

# ================= CONFIG =================
CODE_CHANNEL_ID = 1486967511839801414
LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

# ===== EarnPoint API =====
API = "https://website-kiemtien.onrender.com"

# ================= BOT SETUP =================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

session = None

# ================= DATABASE (Ticket) =================
def load_data():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except:
        return {"ticket": 0}

def save_data(data):
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

async def get_ticket_number(guild):
    data = load_data()
    data["ticket"] += 1
    save_data(data)
    return f"{data['ticket']:03d"}

async def has_ticket(guild, user):
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic:
            return True
    return False

def parse_money(value):
    value = value.lower().replace(" ", "")
    if value.isdigit():
        return int(value)
    if value.endswith("k") and value[:-1].isdigit():
        return int(value[:-1]) * 1000
    if value.endswith("m") and value[:-1].isdigit():
        return int(value[:-1]) * 1000000
    return None

def format_money(num):
    return f"{num:,}"

# ================= API =================
async def api_get(url):
    try:
        async with session.get(url) as res:
            if res.status == 200:
                return await res.json()
            print(f"[API ERROR] Status {res.status} for {url}")
            return None
    except Exception as e:
        print(f"[API ERROR] {e} for {url}")
        return None

async def api_post(url, data):
    try:
        async with session.post(url, json=data) as res:
            if res.status == 200:
                return await res.json()
            print(f"[API ERROR] Status {res.status} for {url}")
            return None
    except Exception as e:
        print(f"[API ERROR] {e} for {url}")
        return None

async def get_points(user_id):
    data = await api_get(f"{API}/points/{user_id}")
    if data is None:
        print(f"[DEBUG] get_points({user_id}) returned None")
        return {"points": 0}
    points = data.get("points", 0)
    print(f"[DEBUG] User {user_id} has {points} points")
    return data

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

# ================= WITHDRAW SYSTEM (ĐÃ BỔ SUNG) =================
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

        await api_post(f"{API}/remove-point", {
            "discordId": str(interaction.user.id),
            "amount": amount
        })

        await interaction.response.send_message(f"✅ Đã rút {amount} point thành công!", ephemeral=True)

class WithdrawView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💸 Rút point", style=discord.ButtonStyle.green, custom_id="withdraw_point")
    async def withdraw(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WithdrawModal())

# ================= TICKET VIEWS (giữ nguyên) =================
# ... (TicketPanel, MinecraftModal, TicketTypeView, TypeSelect, AmountModal, create_ticket, TicketButtons) ...

# (Để code không quá dài, tôi rút gọn phần Ticket. Bạn copy phần Ticket từ code trước đó vào đây)

# ================= COMMANDS =================
@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng lệnh này")
    embed = discord.Embed(title="🏪 tuytam store", description="Nhấn nút bên dưới để tạo ticket", color=discord.Color.gold())
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465005765478584404/1482629221149966356/shop.gif")
    await ctx.send(embed=embed, view=TicketPanel())

@bot.command()
async def point(ctx, subcommand: str = None):
    if subcommand is None or subcommand.lower() in ["", "me"]:
        data = await get_points(ctx.author.id)
        points = data.get("points", 0)
        embed = discord.Embed(title="💰 Thông tin Point", color=discord.Color.gold())
        embed.add_field(name="👤 User", value=ctx.author.mention, inline=False)
        embed.add_field(name="💎 Point", value=str(points), inline=False)
        await ctx.reply(embed=embed, view=WithdrawView())
    elif subcommand.lower() == "lb":
        await ctx.reply("⏳ Đang tải leaderboard...")
        lb = await build_leaderboard(ctx.guild)
        text = "\n".join([f"{i}. {member.mention} - {points} point" for i, (member, points) in enumerate(lb, start=1)])
        embed = discord.Embed(title="🏆 Leaderboard", description=text or "Không có dữ liệu", color=discord.Color.green())
        await ctx.send(embed=embed)
    else:
        await ctx.reply("❌ Sử dụng: `.point` hoặc `.point lb`")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📋 Danh sách lệnh", description="Prefix: **`.`**", color=discord.Color.blue())
    embed.add_field(name="Các lệnh", value="`.help` - Danh sách lệnh\n`.point` - Xem point cá nhân\n`.point lb` - Xem leaderboard\n`.panel` - Tạo panel ticket (admin)", inline=False)
    await ctx.reply(embed=embed)

# ================= ON READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()
    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    bot.add_view(WithdrawView())
    print(f"Bot online: {bot.user}")

# ================= ON MESSAGE =================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    original_content = message.content.strip()

    if message.channel.id == CODE_CHANNEL_ID:
        if original_content.startswith("EP-"):
            data = await api_post(f"{API}/check-code", {
                "code": original_content,
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
                await message.reply(f"code hợp lệ ✔️ +1 point\n💰 Tổng: {data.get('points', 0)}")
        return

    await bot.process_commands(message)

# ================= RUN =================
bot.run(TOKEN)
