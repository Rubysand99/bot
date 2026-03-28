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

ADMIN_PING = 846332174734983219
LOG_ADMIN_CHANNEL = 1464524557657440396
CODE_CHANNEL_ID = 1486967511839801414

# ===== Ticket Config =====
LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

# ===== EarnPoint API =====
API = "https://website-kiemtien.onrender.com"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

session = None

# ================= DATABASE =================
def load_data():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except:
        return {"ticket": 0}

def save_data(data):
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

# ================= TICKET COUNT =================
async def get_ticket_number(guild):
    data = load_data()
    data["ticket"] += 1
    save_data(data)
    return f"{data['ticket']:03d}"

# ================= CHECK EXISTING TICKET =================
async def has_ticket(guild, user):
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic:
            return True
    return False

# ================= MONEY HELPER =================
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

# ================= TICKET VIEWS & MODALS =================
class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create(self, interaction: discord.Interaction, button: Button):
        if await has_ticket(interaction.guild, interaction.user):
            return await interaction.response.send_message("❌ Bạn đã có ticket đang mở", ephemeral=True)
        await interaction.response.send_modal(MinecraftModal())

class MinecraftModal(Modal, title="Thông tin khách hàng"):
    mc = TextInput(label="Tên Minecraft", placeholder="Ví dụ: quannmc")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Chọn dịch vụ", view=TicketTypeView(self.mc.value), ephemeral=True)

class TicketTypeView(View):
    def __init__(self, mc):
        super().__init__(timeout=60)
        self.add_item(TypeSelect([
            discord.SelectOption(label="selling ske"),
            discord.SelectOption(label="selling money"),
            discord.SelectOption(label="buying ske"),
            discord.SelectOption(label="buying money"),
            discord.SelectOption(label="order vật phẩm"),
            discord.SelectOption(label="thuê dịch vụ"),
            discord.SelectOption(label="hỗ trợ"),
            discord.SelectOption(label="bảo hành")
        ], mc))

class TypeSelect(Select):
    def __init__(self, options, mc):
        super().__init__(placeholder="Chọn dịch vụ", options=options)
        self.mc = mc

    async def callback(self, interaction: discord.Interaction):
        ticket_type = self.values[0]
        if "selling" in ticket_type or "buying" in ticket_type:
            await interaction.response.send_modal(AmountModal(self.mc, ticket_type))
        else:
            await create_ticket(interaction, self.mc, ticket_type, "không có")

class AmountModal(Modal, title="Nhập số lượng"):
    amount = TextInput(label="Số lượng", placeholder="Ví dụ: 100k, 2m hoặc 500000")

    def __init__(self, mc, ticket_type):
        super().__init__()
        self.mc = mc
        self.ticket_type = ticket_type

    async def on_submit(self, interaction: discord.Interaction):
        value = self.amount.value.lower().replace(" ", "")
        if "money" in self.ticket_type:
            parsed = parse_money(value)
            if parsed is None:
                return await interaction.response.send_message("❌ Money chỉ được nhập dạng: 100k, 2m hoặc số", ephemeral=True)
            display = format_money(parsed)
        else:
            if not value.isdigit():
                return await interaction.response.send_message("❌ Số lượng phải là số", ephemeral=True)
            display = value

        await create_ticket(interaction, self.mc, self.ticket_type, display)

# ================= CREATE TICKET =================
async def create_ticket(interaction, mc, ticket_type, amount):
    guild = interaction.guild
    number = await get_ticket_number(guild)
    name = f"🎫-ticket-{number}"

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }

    for admin_id in ADMIN_IDS:
        member = guild.get_member(admin_id)
        if member:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    category = discord.utils.get(guild.categories, id=TICKET_CATEGORY_ID)
    if not category:
        return await interaction.response.send_message("❌ Không tìm thấy category Ticket", ephemeral=True)

    channel = await guild.create_text_channel(name=name, overwrites=overwrites, category=category)
    channel.topic = f"{interaction.user.id}|{mc}|{ticket_type}|{amount}"

    embed = discord.Embed(title="🛒 Ticket mới", color=discord.Color.green())
    embed.add_field(name="Buyer", value=interaction.user.mention)
    embed.add_field(name="Minecraft", value=mc)
    embed.add_field(name="Loại", value=ticket_type)
    embed.add_field(name="Số lượng", value=amount)

    await channel.send(f"<@&{SUPPORT_ROLE_ID}> có khách", embed=embed, view=TicketButtons())

    await interaction.response.send_message(f"✅ Ticket của bạn đã được tạo: {channel.mention}", ephemeral=True)

class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Đóng ticket", style=discord.ButtonStyle.red, custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Bạn không có quyền đóng ticket", ephemeral=True)

        messages = []
        async for msg in interaction.channel.history(limit=None):
            time = msg.created_at.strftime("%H:%M")
            messages.append(f"<p><b>[{time}] {msg.author}</b>: {msg.content}</p>")

        html = f"<html><body><h2>Transcript {interaction.channel.name}</h2>{''.join(messages[::-1])}</body></html>"

        file = discord.File(io.BytesIO(html.encode()), filename="transcript.html")
        log = bot.get_channel(LOG_CHANNEL)
        if log:
            await log.send(f"📄 Transcript {interaction.channel.name}", file=file)

        await interaction.channel.delete()

# ================= COMMANDS =================
@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng lệnh này")
    
    embed = discord.Embed(
        title="🏪 tuytam store",
        description="Nhấn nút bên dưới để tạo ticket",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465005765478584404/1482629221149966356/shop.gif")
    await ctx.send(embed=embed, view=TicketPanel())

# ================= ON READY =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()
    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    print(f"Bot online: {bot.user}")

# ================= ON MESSAGE - EarnPoint & System Commands =================
# ================= ON MESSAGE - EarnPoint & System Commands =================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip().lower()

    # ================= CODE CHANNEL - CHỈ XỬ LÝ CODE EP- =================
    if message.channel.id == CODE_CHANNEL_ID:
        if message.content.strip().startswith("EP-"):   # dùng message.content gốc để kiểm tra EP-
            data = await api_post(f"{API}/check-code", {
                "code": message.content.strip(),
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
            # Các tin nhắn khác → im lặng, không reply

        return   # ← Quan trọng: Kết thúc luôn, không xử lý gì thêm trong kênh code

    # ================= XỬ LÝ LỆNH HỆ THỐNG (point, point lb, !panel, ...) =================
    # point và point lb (không có dấu !)
    if content.startswith("point"):
        parts = content.split()

        # point lb
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

        # point (xem point cá nhân)
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

    # Nếu là lệnh có prefix "!" (như !panel) thì mới cho process_commands chạy
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
# ================= RUN =================
bot.run(TOKEN)
