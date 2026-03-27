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

LOG_CHANNEL = 1482234024868053083
LOG_ADMIN_CHANNEL = 1464524557657440396
LOG_CODE_CHANNEL_ID = 1482234024868053083

TICKET_CATEGORY_ID = 1464426174611456195
CODE_CHANNEL_ID = 1486967511839801414  # ✅ đã đổi

API = "https://website-kiemtien.onrender.com"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= SESSION =================
session = None

@bot.event
async def on_ready():
    global session
    if session is None:
        session = aiohttp.ClientSession()
    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    print("Bot online:", bot.user)

@bot.event
async def on_close():
    global session
    if session:
        await session.close()

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

async def get_ticket_number(guild):
    data = load_data()
    data["ticket"] += 1
    save_data(data)
    return f"{data['ticket']:03d}"

async def has_ticket(guild, user):
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic:
            return True
    return False

# ================= MONEY =================
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

def find_member(guild, username):
    username = username.lower()
    for member in guild.members:
        if member.name.lower() == username:
            return member
    return None

# ================= PANEL =================
class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create(self, interaction: discord.Interaction, button: Button):
        if await has_ticket(interaction.guild, interaction.user):
            return await interaction.response.send_message("❌ Bạn đã có ticket", ephemeral=True)
        await interaction.response.send_modal(MinecraftModal())

class MinecraftModal(Modal, title="Thông tin khách hàng"):
    mc = TextInput(label="Tên Minecraft", placeholder="Ví dụ: quannmc")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Chọn dịch vụ",
            view=TicketTypeView(self.mc.value),
            ephemeral=True
        )

class TicketTypeView(View):
    def __init__(self, mc):
        super().__init__(timeout=60)
        options = [
            discord.SelectOption(label="selling ske"),
            discord.SelectOption(label="selling money"),
            discord.SelectOption(label="buying ske"),
            discord.SelectOption(label="buying money"),
            discord.SelectOption(label="order vật phẩm"),
            discord.SelectOption(label="thuê dịch vụ"),
            discord.SelectOption(label="hỗ trợ"),
            discord.SelectOption(label="bảo hành")
        ]
        self.add_item(TypeSelect(options, mc))

class TypeSelect(Select):
    def __init__(self, options, mc):
        super().__init__(placeholder="Chọn dịch vụ", options=options)
        self.mc = mc

    async def callback(self, interaction: discord.Interaction):
        ticket_type = self.values[0]
        if "selling" in ticket_type or "buying" in ticket_type:
            await interaction.response.send_modal(
                AmountModal(self.mc, ticket_type)
            )
        else:
            await create_ticket(interaction, self.mc, ticket_type, "không có")

class AmountModal(Modal, title="Nhập số lượng"):
    amount = TextInput(label="Số lượng", placeholder="100k, 2m hoặc 500000")

    def __init__(self, mc, ticket_type):
        super().__init__()
        self.mc = mc
        self.ticket_type = ticket_type

    async def on_submit(self, interaction: discord.Interaction):
        value = self.amount.value.lower().replace(" ", "")
        if "money" in self.ticket_type:
            parsed = parse_money(value)
            if parsed is None:
                return await interaction.response.send_message("❌ Sai định dạng money", ephemeral=True)
            display = format_money(parsed)
        else:
            if not value.isdigit():
                return await interaction.response.send_message("❌ Số phải là số", ephemeral=True)
            display = value

        await create_ticket(interaction, self.mc, self.ticket_type, display)

async def create_ticket(interaction, mc, ticket_type, amount):
    guild = interaction.guild
    number = await get_ticket_number(guild)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True)
    }

    for admin in ADMIN_IDS:
        member = guild.get_member(admin)
        if member:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True)

    category = discord.utils.get(guild.categories, id=TICKET_CATEGORY_ID)

    channel = await guild.create_text_channel(
        name=f"ticket-{number}",
        overwrites=overwrites,
        category=category
    )

    embed = discord.Embed(title="Ticket mới", color=discord.Color.green())
    embed.add_field(name="User", value=interaction.user.mention)
    embed.add_field(name="MC", value=mc)
    embed.add_field(name="Type", value=ticket_type)
    embed.add_field(name="Amount", value=amount)

    await channel.send(embed=embed, view=TicketButtons())
    await interaction.response.send_message(f"✅ {channel.mention}", ephemeral=True)

class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Đóng", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Không có quyền", ephemeral=True)

        messages = []
        async for msg in interaction.channel.history(limit=None):
            messages.append(f"<p><b>{msg.author}</b>: {msg.content}</p>")

        html = f"<html><body>{''.join(messages[::-1])}</body></html>"

        file = discord.File(io.BytesIO(html.encode()), filename="log.html")
        log = bot.get_channel(LOG_CHANNEL)
        await log.send(file=file)

        await interaction.channel.delete()

# ================= COMMAND =================
@bot.command()
async def panel(ctx):
    embed = discord.Embed(title="🎫 Ticket", description="Nhấn để tạo", color=discord.Color.gold())
    await ctx.send(embed=embed, view=TicketPanel())

# ================= MESSAGE =================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    # ===== ADMIN =====
    if content.startswith("gp ") or content.startswith("xp "):
        if message.author.id not in ADMIN_IDS:
            return await message.reply("❌ Không có quyền")

        parts = content.split()
        member = find_member(message.guild, parts[1])
        if not member:
            return await message.reply("❌ Không tìm thấy user")

        if parts[0] == "gp":
            amount = int(parts[2])
            await add_points(member.id, amount)
            await message.reply(f"+{amount} point")

        if parts[0] == "xp":
            amount = int(parts[2]) if len(parts) > 2 else None
            await remove_points(member.id, amount)
            await message.reply(f"-point")

    # ===== CODE =====
    if message.channel.id == CODE_CHANNEL_ID:
        if not content.startswith("EP-"):
            return  # ✅ bỏ qua hoàn toàn

        data = await api_post(f"{API}/check-code", {
            "code": content,
            "discordId": str(message.author.id)
        })

        if not data:
            return await message.reply("❌ lỗi server")

        status = data.get("status")
        log_channel = bot.get_channel(LOG_CODE_CHANNEL_ID)

        if status == "ok":
            await message.reply(f"✅ +1 | Tổng: {data.get('points', 1)}")
        elif status == "expired":
            await message.reply("⏱️ hết hạn")
        else:
            await message.reply("❌ không hợp lệ")

        if log_channel:
            await log_channel.send(f"{message.author}: {content} → {status}")

    await bot.process_commands(message)

# ================= RUN =================
bot.run(TOKEN)
