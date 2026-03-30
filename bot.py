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
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

API = "https://website-kiemtien.onrender.com"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

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

# ================= POINT =================
async def get_points(user_id):
    data = await api_get(f"{API}/points/{user_id}")
    if not data:
        return 0
    return data.get("points", 0)

# ================= WITHDRAW =================
class WithdrawModal(Modal, title="Rút Point"):
    amount = TextInput(label="Nhập số point", placeholder=">= 5")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            amount = int(self.amount.value)
        except:
            return await interaction.followup.send("❌ Số không hợp lệ")

        if amount < 5:
            return await interaction.followup.send("❌ Tối thiểu 5")

        current = await get_points(interaction.user.id)

        if amount > current:
            return await interaction.followup.send("❌ Không đủ point")

        await api_post(f"{API}/remove-point", {
            "discordId": str(interaction.user.id),
            "amount": amount
        })

        log = bot.get_channel(LOG_CHANNEL)
        if log:
            await log.send(f"💸 {interaction.user} rút {amount} point")

        await interaction.followup.send(f"✅ Đã rút {amount} point")

class WithdrawView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💸 Rút point", style=discord.ButtonStyle.green, custom_id="withdraw_btn")
    async def withdraw(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WithdrawModal())

# ================= TICKET =================
async def has_ticket(guild, user):
    for c in guild.text_channels:
        if c.topic and str(user.id) in str(c.topic):
            return True
    return False

class TicketCloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Đóng Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Không có quyền", ephemeral=True)

        await interaction.response.send_message("🔒 Đang đóng ticket...", ephemeral=True)
        await interaction.channel.delete()

class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Tạo Ticket", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create(self, interaction: discord.Interaction, button: Button):

        if await has_ticket(interaction.guild, interaction.user):
            return await interaction.response.send_message("❌ Bạn đã có ticket", ephemeral=True)

        await interaction.response.send_modal(MinecraftModal())

class MinecraftModal(Modal, title="Thông tin"):
    mc = TextInput(label="Tên Minecraft")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await create_ticket(interaction, self.mc.value)

# ================= CREATE TICKET =================
async def create_ticket(interaction, mc):

    guild = interaction.guild
    category = discord.utils.get(guild.categories, id=TICKET_CATEGORY_ID)

    if not category:
        return await interaction.followup.send("❌ Không tìm thấy category")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

    for admin_id in ADMIN_IDS:
        member = guild.get_member(admin_id)
        if member:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True)

    try:
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            category=category
        )
    except Exception as e:
        return await interaction.followup.send(f"❌ Lỗi: {e}")

    channel.topic = str(interaction.user.id)

    embed = discord.Embed(title="🎫 Ticket Support", color=discord.Color.green())
    embed.add_field(name="👤 User", value=interaction.user.mention, inline=False)
    embed.add_field(name="🎮 Minecraft", value=mc, inline=False)

    await channel.send(
        content=f"<@&{SUPPORT_ROLE_ID}> có ticket mới!",
        embed=embed,
        view=TicketCloseView()
    )

# ================= COMMAND =================
@bot.command()
async def point(ctx):
    points = await get_points(ctx.author.id)

    embed = discord.Embed(title="💰 Point", color=discord.Color.gold())
    embed.add_field(name="User", value=ctx.author.mention)
    embed.add_field(name="Point", value=str(points))

    await ctx.reply(embed=embed, view=WithdrawView())

@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Không có quyền")

    embed = discord.Embed(title="🎫 Support", description="Nhấn nút để tạo ticket")

    await ctx.send(embed=embed, view=TicketPanel())

# ================= EVENT =================
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()

    bot.add_view(TicketPanel())
    bot.add_view(WithdrawView())
    bot.add_view(TicketCloseView())

    print("Bot online:", bot.user)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == CODE_CHANNEL_ID:
        if message.content.startswith("EP-"):
            data = await api_post(f"{API}/check-code", {
                "code": message.content,
                "discordId": str(message.author.id)
            })

            if not data:
                return await message.reply("❌ lỗi server")

            if data["status"] == "ok":
                await message.reply(f"✔️ +1 point | Tổng: {data['points']}")
            else:
                await message.reply("❌ code sai")

    await bot.process_commands(message)

bot.run(TOKEN)
