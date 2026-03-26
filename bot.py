import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import io
import os
import json
import requests

TOKEN = os.getenv("TOKEN")

ADMIN_ID = 846332174734983219
LOG_ADMIN_CHANNEL = 1464524557657440396

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
    1438384178755276923
]

LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195

API = "https://website-kiemtien.onrender.com"
CODE_CHANNEL_ID = 1464428982857634044
LOG_CODE_CHANNEL_ID = 1482234024868053083

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

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

# ================= POINT API =================

def get_points(discord_id):
    try:
        res = requests.get(API + f"/points/{discord_id}")
        return res.json()
    except:
        return None

def add_points(discord_id, amount):
    try:
        res = requests.post(API + "/add-point", json={
            "discordId": str(discord_id),
            "amount": amount
        })
        return res.json()
    except:
        return None

def remove_points(discord_id, amount=None):
    try:
        res = requests.post(API + "/remove-point", json={
            "discordId": str(discord_id),
            "amount": amount
        })
        return res.json()
    except:
        return None

# ================= FIND USER =================

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
    mc = TextInput(label="Tên Minecraft")

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
        await create_ticket(interaction, self.mc, ticket_type, "không có")

# ================= CREATE =================

async def create_ticket(interaction, mc, ticket_type, amount):
    guild = interaction.guild
    number = await get_ticket_number(guild)
    name = f"ticket-{number}"

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
        name=name,
        overwrites=overwrites,
        category=category
    )

    channel.topic = f"{interaction.user.id}|{mc}|{ticket_type}|{amount}"

    await channel.send(f"🎫 Ticket của {interaction.user.mention}")

    await interaction.response.send_message(
        f"✅ Ticket: {channel.mention}",
        ephemeral=True
    )

# ================= POINT COMMAND =================

@bot.command()
async def point(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = get_points(member.id)
    if not data:
        return await ctx.send("❌ Lỗi server")
    await ctx.send(f"💰 {member.mention}: {data.get('points', 0)} point")

# ================= ON MESSAGE =================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # ===== GP / XP TEXT COMMAND =====
    if message.content.startswith("gp ") or message.content.startswith("xp "):

        if message.author.id != ADMIN_ID:
            return await message.reply("❌ Bạn không có quyền")

        parts = message.content.split()
        cmd = parts[0]
        username = parts[1]

        member = find_member(message.guild, username)

        if not member:
            return await message.reply("❌ Không tìm thấy user")

        log_channel = bot.get_channel(LOG_ADMIN_CHANNEL)

        if cmd == "gp":
            if len(parts) < 3:
                return await message.reply("❌ Thiếu số point")

            try:
                amount = int(parts[2])
            except:
                return await message.reply("❌ Số không hợp lệ")

            add_points(member.id, amount)

            await message.reply(f"✅ +{amount} point cho {member.mention}")

            if log_channel:
                await log_channel.send(f"➕ {message.author} → {member} (+{amount})")

        elif cmd == "xp":
            amount = None

            if len(parts) >= 3:
                try:
                    amount = int(parts[2])
                except:
                    return await message.reply("❌ Số không hợp lệ")

            remove_points(member.id, amount)

            if amount is None:
                await message.reply(f"🗑️ Xoá hết point {member.mention}")
            else:
                await message.reply(f"🗑️ -{amount} point {member.mention}")

            if log_channel:
                await log_channel.send(f"➖ {message.author} → {member} ({amount})")

    # ===== EARN CODE =====
    if message.channel.id == CODE_CHANNEL_ID:
        code = message.content.strip()

        if not code.startswith("EP-"):
            return await message.reply("❌ code sai")

        try:
            res = requests.post(API + "/check-code", json={
                "code": code,
                "discordId": str(message.author.id)
            })

            data = res.json()

            if data["status"] == "ok":
                await message.reply(f"✅ +1 point | Tổng: {data['points']}")
            else:
                await message.reply("❌ code lỗi")

        except:
            await message.reply("❌ lỗi server")

    await bot.process_commands(message)

# ================= READY =================

@bot.event
async def on_ready():
    print("Bot online:", bot.user)

bot.run(TOKEN)
