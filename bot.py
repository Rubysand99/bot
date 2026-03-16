import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import datetime
import json
import io
import os

TOKEN = os.getenv("TOKEN")

ADMIN_IDS = [846332174734983219,1464961078042689588]

STATUS_CHANNEL = 1482233794512556223
LOG_CHANNEL = 1482234024868053083

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= STATS =================

def load_stats():

    try:
        with open("stats.json","r") as f:
            return json.load(f)
    except:
        return {"orders":0}

def save_stats(data):

    with open("stats.json","w") as f:
        json.dump(data,f)

# ================= TICKET COUNT =================

async def get_ticket_number(guild):

    count = 0

    for channel in guild.text_channels:
        if channel.name.startswith("ticket-"):
            count += 1

    return f"{count+1:03d}"

# ================= CHECK OPEN =================

async def has_ticket(guild,user):

    for channel in guild.text_channels:

        if channel.topic:

            if str(user.id) in channel.topic:
                return True

    return False

# ================= PANEL =================

class TicketPanel(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Tạo Ticket",style=discord.ButtonStyle.green)
    async def create(self,interaction:discord.Interaction,button:Button):

        if await has_ticket(interaction.guild,interaction.user):

            return await interaction.response.send_message(
                "❌ Bạn đã có ticket đang mở",
                ephemeral=True
            )

        await interaction.response.send_modal(MinecraftModal())

# ================= MINECRAFT =================

class MinecraftModal(Modal,title="Thông tin khách hàng"):

    mc = TextInput(
        label="Tên Minecraft",
        placeholder="Ví dụ: quannmc"
    )

    async def on_submit(self,interaction:discord.Interaction):

        await interaction.response.send_message(
            "Chọn dịch vụ",
            view=TicketTypeView(self.mc.value),
            ephemeral=True
        )

# ================= TYPE =================

class TicketTypeView(View):

    def __init__(self,mc):
        super().__init__(timeout=None)

        options=[

        discord.SelectOption(label="selling ske"),
        discord.SelectOption(label="selling money"),
        discord.SelectOption(label="buying ske"),
        discord.SelectOption(label="buying money"),
        discord.SelectOption(label="order vật phẩm"),
        discord.SelectOption(label="thuê dịch vụ"),
        discord.SelectOption(label="hỗ trợ"),
        discord.SelectOption(label="bảo hành")

        ]

        self.add_item(TypeSelect(options,mc))


class TypeSelect(Select):

    def __init__(self,options,mc):
        super().__init__(placeholder="Chọn dịch vụ",options=options)
        self.mc = mc

    async def callback(self,interaction:discord.Interaction):

        ticket_type=self.values[0]

        if "selling" in ticket_type or "buying" in ticket_type:

            await interaction.response.send_modal(
                AmountModal(self.mc,ticket_type)
            )

        else:

            await create_ticket(
                interaction,
                self.mc,
                ticket_type,
                "không có"
            )

# ================= AMOUNT =================

class AmountModal(Modal,title="Nhập số lượng"):

    amount = TextInput(
        label="Số lượng",
        placeholder="Chỉ nhập số"
    )

    def __init__(self,mc,ticket_type):
        super().__init__()
        self.mc=mc
        self.ticket_type=ticket_type

    async def on_submit(self,interaction:discord.Interaction):

        if not self.amount.value.isdigit():

            return await interaction.response.send_message(
                "❌ Số lượng phải là số",
                ephemeral=True
            )

        await create_ticket(
            interaction,
            self.mc,
            self.ticket_type,
            self.amount.value
        )

# ================= CREATE =================

async def create_ticket(interaction,mc,ticket_type,amount):

    guild=interaction.guild

    number=await get_ticket_number(guild)

    safe=ticket_type.replace(" ","-")

    name=f"ticket-{mc}-{safe}-{number}"

    overwrites={

    guild.default_role:discord.PermissionOverwrite(view_channel=False),

    interaction.user:discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True
    )

    }

    for admin in ADMIN_IDS:

        member=guild.get_member(admin)

        if member:

            overwrites[member]=discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True
            )

    channel=await guild.create_text_channel(
        name=name,
        overwrites=overwrites
    )

    channel.topic=f"{interaction.user.id}|{mc}|{ticket_type}|{amount}"

    embed=discord.Embed(
        title="🛒 Ticket mới",
        color=discord.Color.green()
    )

    embed.add_field(name="Buyer",value=interaction.user.mention)
    embed.add_field(name="Minecraft",value=mc)
    embed.add_field(name="Loại",value=ticket_type)
    embed.add_field(name="Số lượng",value=amount)

    await channel.send(
        f"<@{ADMIN_IDS[1]}> có khách",
        embed=embed,
        view=TicketButtons()
    )

    await interaction.response.send_message(
        f"Ticket của bạn: {channel.mention}",
        ephemeral=True
    )

# ================= BUTTON =================

class TicketButtons(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Hoàn thành",style=discord.ButtonStyle.green)
    async def done(self,interaction:discord.Interaction,button:Button):

        if interaction.user.id not in ADMIN_IDS:

            return await interaction.response.send_message(
                "Bạn không có quyền",
                ephemeral=True
            )

        data=interaction.channel.topic.split("|")

        buyer=data[0]
        mc=data[1]
        t=data[2]
        amount=data[3]

        embed=discord.Embed(
            title="🟢 Đơn hoàn thành",
            color=discord.Color.green()
        )

        embed.add_field(name="Buyer",value=f"<@{buyer}>")
        embed.add_field(name="Minecraft",value=mc)
        embed.add_field(name="Loại",value=t)
        embed.add_field(name="Số lượng",value=amount)
        embed.add_field(name="Admin",value=interaction.user.mention)

        embed.timestamp=datetime.datetime.now()

        status=bot.get_channel(STATUS_CHANNEL)

        await status.send(embed=embed)

        stats=load_stats()

        stats["orders"]+=1

        save_stats(stats)

        await interaction.response.send_message("Đã đánh dấu hoàn thành")

    @discord.ui.button(label="🔒 Đóng ticket",style=discord.ButtonStyle.red)
    async def close(self,interaction:discord.Interaction,button:Button):

        if interaction.user.id not in ADMIN_IDS:

            return await interaction.response.send_message(
                "Bạn không có quyền",
                ephemeral=True
            )

        messages=[]

        async for msg in interaction.channel.history(limit=None):

            time=msg.created_at.strftime("%H:%M")

            messages.append(
                f"<p><b>[{time}] {msg.author}</b>: {msg.content}</p>"
            )

        html=f"""
<html>
<body>
<h2>Transcript {interaction.channel.name}</h2>
{''.join(messages[::-1])}
</body>
</html>
"""

        file=discord.File(
            io.BytesIO(html.encode()),
            filename="transcript.html"
        )

        log=bot.get_channel(LOG_CHANNEL)

        await log.send(
            f"Transcript {interaction.channel.name}",
            file=file
        )

        await interaction.channel.delete()

# ================= PANEL COMMAND =================

@bot.command()
async def panel(ctx):

    embed=discord.Embed(
        title="🏪 tuytam store",
        description=
        "💎 Selling ske\n"
        "💰 Selling money\n"
        "🛒 Buying ske\n"
        "💵 Buying money\n"
        "📦 Order vật phẩm\n"
        "🧑‍🔧 Thuê dịch vụ\n"
        "🆘 Hỗ trợ\n"
        "🛠 Bảo hành\n\n"
        "Chọn dịch vụ bên dưới",
        color=discord.Color.gold()
    )

    embed.set_thumbnail(
        url="https://cdn.discordapp.com/attachments/1465005765478584404/1482629221149966356/shop.gif"
    )

    await ctx.send(embed=embed,view=TicketPanel())

# ================= STATS COMMAND =================

@bot.command()
async def stats(ctx):

    stats=load_stats()

    await ctx.send(
        f"📊 Tổng đơn đã xử lý: {stats['orders']}"
    )

# ================= READY =================

@bot.event
async def on_ready():

    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())

    print("Bot online:",bot.user)

bot.run(TOKEN)
