import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import io
import os
import json
from datetime import datetime

TOKEN = os.getenv("TOKEN")

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
    1438384178755276923
]

LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ================= BẢNG GIÁ =================
PRICE_TABLE = {
    "sell": {  # Shop bán → user mua
        "money":    {"label": "💰 Money",    "unit": "1m",    "price": "950đ"},
        "skeleton": {"label": "💀 Skeleton", "unit": "5m",    "price": "4.000đ"},
        "elytra":   {"label": "🪂 Elytra",   "unit": "1 cái", "price": "330.000đ"},
    },
    "buy": {   # Shop mua ← user bán
        "money":    {"label": "💰 Money",    "unit": "1m",    "price": "700đ"},
        "skeleton": {"label": "💀 Skeleton", "unit": "1 cái", "price": "3.200đ hoặc 3,5m ingame"},
        "elytra":   {"label": "🪂 Elytra",   "unit": "1 cái", "price": "300.000đ"},
    }
}

# ================= DATA =================
def load_data():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except:
        return {"ticket": 0}

def save_data(data):
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

def get_ticket_number():
    data = load_data()
    data["ticket"] += 1
    save_data(data)
    return f"{data['ticket']:03d}"

# ================= CHECK TICKET =================
async def has_ticket(guild, user):
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic:
            return True
    return False

# ================= TRANSCRIPT =================
def build_transcript_html(channel_name, messages):
    rows = ""
    for msg in messages:
        avatar = msg.author.display_avatar.url if msg.author.display_avatar else ""
        content = discord.utils.escape_mentions(msg.content) if msg.content else "<i>(no content)</i>"
        time_str = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
        rows += f"""
        <div class="message">
            <img class="avatar" src="{avatar}" onerror="this.style.display='none'">
            <div class="content">
                <span class="author">{msg.author}</span>
                <span class="time">{time_str}</span>
                <div class="text">{content}</div>
            </div>
        </div>"""
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<title>Transcript – {channel_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #313338; font-family: 'Segoe UI', sans-serif; color: #dcddde; padding: 24px; }}
  h1 {{ color: #fff; font-size: 20px; margin-bottom: 4px; }}
  .meta {{ color: #a3a6aa; font-size: 13px; margin-bottom: 20px; }}
  .message {{ display: flex; gap: 12px; padding: 8px 12px; border-radius: 8px; margin-bottom: 2px; }}
  .message:hover {{ background: #2e3035; }}
  .avatar {{ width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0; }}
  .content {{ display: flex; flex-direction: column; gap: 2px; }}
  .author {{ font-weight: 700; color: #fff; font-size: 14px; }}
  .time {{ color: #a3a6aa; font-size: 11px; margin-left: 6px; }}
  .text {{ font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }}
</style>
</head>
<body>
  <h1>📄 Transcript – #{channel_name}</h1>
  <div class="meta">Xuất lúc {datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S')} UTC • {len(messages)} tin nhắn</div>
  {rows}
</body>
</html>"""

# ================= MODAL (nhập SL + tên MC) =================
class OrderModal(Modal):
    mc_name = TextInput(
        label="Tên Minecraft của bạn",
        placeholder="Ví dụ: quannmc",
        min_length=2, max_length=32
    )
    amount = TextInput(
        label="Số lượng",
        placeholder="Ví dụ: 10m / 5 cái / 100",
        min_length=1, max_length=50
    )
    note = TextInput(
        label="Ghi chú (tuỳ chọn)",
        placeholder="Ví dụ: thanh toán MoMo, cần gấp...",
        style=discord.TextStyle.paragraph,
        required=False, max_length=200
    )

    def __init__(self, trade_type: str, item_key: str):
        item_info = PRICE_TABLE[trade_type][item_key]
        action = "Mua" if trade_type == "sell" else "Bán"
        super().__init__(title=f"{action} {item_info['label']}")
        self.trade_type = trade_type
        self.item_key = item_key

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild

        if await has_ticket(guild, interaction.user):
            return await interaction.response.send_message(
                "❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.",
                ephemeral=True
            )

        number = get_ticket_number()
        item_info = PRICE_TABLE[self.trade_type][self.item_key]
        created_at = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")

        # Màu & nhãn
        if self.trade_type == "sell":
            color = 0x57F287
            type_label = "🛒 MUA HÀNG"
            channel_prefix = f"mua-{self.item_key}"
        else:
            color = 0xFEE75C
            type_label = "💸 BÁN HÀNG"
            channel_prefix = f"ban-{self.item_key}"

        # Permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
        }
        for admin_id in ADMIN_IDS:
            m = guild.get_member(admin_id)
            if m:
                overwrites[m] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True
                )

        category = discord.utils.get(guild.categories, id=TICKET_CATEGORY_ID)
        channel = await guild.create_text_channel(
            name=f"{channel_prefix}-{number}",
            overwrites=overwrites,
            category=category,
            topic=f"{interaction.user.id}|{self.mc_name.value}|{self.trade_type}|{self.item_key}"
        )

        embed = discord.Embed(
            title=f"{type_label}  •  {item_info['label']}  •  #{number}",
            description=(
                f"Xin chào {interaction.user.mention}! 👋\n"
                f"Staff sẽ xử lý giao dịch của bạn sớm nhất có thể."
            ),
            color=color,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="👤  Người dùng",     value=interaction.user.mention,      inline=True)
        embed.add_field(name="🎮  Tên Minecraft",  value=f"`{self.mc_name.value}`",     inline=True)
        embed.add_field(name="🕐  Thời gian",      value=created_at,                    inline=True)
        embed.add_field(name="📦  Item",           value=item_info["label"],            inline=True)
        embed.add_field(name="🔢  Số lượng",       value=self.amount.value,             inline=True)
        embed.add_field(
            name="💲  Giá tham khảo",
            value=f"`{item_info['price']}` / {item_info['unit']}",
            inline=True
        )
        if self.note.value:
            embed.add_field(name="📝  Ghi chú", value=self.note.value, inline=False)

        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(
            text="TuyTam Store  •  Ticket System",
            icon_url=guild.icon.url if guild.icon else None
        )

        await channel.send(
            f"<@&{SUPPORT_ROLE_ID}> | {interaction.user.mention}",
            embed=embed,
            view=TicketButtons()
        )
        await interaction.response.send_message(
            f"✅ Ticket đã tạo! Vào đây: {channel.mention}",
            ephemeral=True
        )

# ================= SELECT ITEM =================
class ItemSelect(Select):
    def __init__(self, trade_type: str):
        self.trade_type = trade_type
        action = "mua" if trade_type == "sell" else "bán"
        options = [
            discord.SelectOption(
                label=info["label"],
                value=key,
                description=f"Giá: {info['price']} / {info['unit']}",
                emoji=info["label"].split()[0]
            )
            for key, info in PRICE_TABLE[trade_type].items()
        ]
        super().__init__(
            placeholder=f"Chọn item bạn muốn {action}...",
            options=options,
            custom_id=f"item_select_{trade_type}"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            OrderModal(trade_type=self.trade_type, item_key=self.values[0])
        )

class ItemSelectView(View):
    def __init__(self, trade_type: str):
        super().__init__(timeout=60)
        self.add_item(ItemSelect(trade_type))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# ================= PANEL VIEW =================
class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Mua hàng",
        emoji="🛒",
        style=discord.ButtonStyle.green,
        custom_id="panel_buy"
    )
    async def buy(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "🛒 **Bạn muốn mua item nào?**",
            view=ItemSelectView(trade_type="sell"),
            ephemeral=True
        )

    @discord.ui.button(
        label="Bán hàng",
        emoji="💸",
        style=discord.ButtonStyle.blurple,
        custom_id="panel_sell"
    )
    async def sell(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "💸 **Bạn muốn bán item nào?**",
            view=ItemSelectView(trade_type="buy"),
            ephemeral=True
        )

# ================= TICKET BUTTONS =================
class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim",
        emoji="🙋",
        style=discord.ButtonStyle.blurple,
        custom_id="claim_ticket"
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: Button):
        support_role = interaction.guild.get_role(SUPPORT_ROLE_ID)
        has_role = support_role in interaction.user.roles if support_role else False
        if not (interaction.user.id in ADMIN_IDS or has_role):
            return await interaction.response.send_message("❌ Bạn không có quyền claim.", ephemeral=True)

        for item in self.children:
            if item.custom_id == "claim_ticket":
                item.disabled = True
                item.label = f"Claimed: {interaction.user.display_name}"
                item.emoji = "✅"
                break

        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"✅ {interaction.user.mention} đã nhận ticket này!")

    @discord.ui.button(
        label="Đóng ticket",
        emoji="🔒",
        style=discord.ButtonStyle.red,
        custom_id="close_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        support_role = interaction.guild.get_role(SUPPORT_ROLE_ID)
        has_role = support_role in interaction.user.roles if support_role else False
        if not (interaction.user.id in ADMIN_IDS or has_role):
            return await interaction.response.send_message("❌ Không có quyền.", ephemeral=True)

        await interaction.response.defer()
        await _close_ticket(interaction.channel, bot)

# ================= CLOSE LOGIC =================
async def _close_ticket(channel, bot_instance):
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    html = build_transcript_html(channel.name, messages)
    file = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")

    log = bot_instance.get_channel(LOG_CHANNEL)
    if log:
        embed = discord.Embed(
            title="📄 Transcript Ticket",
            description=f"**Kênh:** `{channel.name}`\n**Tin nhắn:** {len(messages)}",
            color=0xED4245,
            timestamp=datetime.utcnow()
        )
        await log.send(embed=embed, file=file)
    await channel.delete()

# ================= COMMANDS =================
@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return

    sell_lines = "\n".join(
        f"{info['label']}  —  **{info['price']}** / {info['unit']}"
        for info in PRICE_TABLE["sell"].values()
    )
    buy_lines = "\n".join(
        f"{info['label']}  —  **{info['price']}** / {info['unit']}"
        for info in PRICE_TABLE["buy"].values()
    )

    embed = discord.Embed(
        title="🏪  TuyTam Store",
        description="Chào mừng! Xem bảng giá bên dưới rồi nhấn nút để bắt đầu giao dịch.",
        color=0x5865F2,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="🛒  Shop bán — bạn mua", value=sell_lines, inline=True)
    embed.add_field(name="💸  Shop mua — bạn bán", value=buy_lines,  inline=True)
    embed.add_field(
        name="⚠️  Lưu ý",
        value="› Không spam ticket\n› Ghi rõ số lượng & item\n› Thanh toán đúng giá niêm yết",
        inline=False
    )
    embed.set_footer(
        text="TuyTam Store  •  Ticket System",
        icon_url=ctx.guild.icon.url if ctx.guild.icon else None
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    await ctx.send(embed=embed, view=TicketPanel())
    await ctx.message.delete()

@bot.command()
async def close(ctx):
    support_role = ctx.guild.get_role(SUPPORT_ROLE_ID)
    has_role = support_role in ctx.author.roles if support_role else False
    if not (ctx.author.id in ADMIN_IDS or has_role):
        return await ctx.reply("❌ Bạn không có quyền.")
    if not any(ctx.channel.name.startswith(p) for p in ("mua-", "ban-")):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    await _close_ticket(ctx.channel, bot)

# ================= ON READY =================
@bot.event
async def on_ready():
    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    print(f"✅ Bot online: {bot.user} | {len(bot.guilds)} server(s)")

bot.run(TOKEN)
        
