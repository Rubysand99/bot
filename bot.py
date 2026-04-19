import os
import io
import json
import asyncio
import aiohttp
from datetime import datetime, timezone
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select

TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
print(f"[DEBUG] TOKEN loaded: {'OK' if TOKEN else 'MISSING'}")
print(f"[DEBUG] GEMINI_API_KEY loaded: {'OK' if GEMINI_API_KEY else 'MISSING'}")

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
    1438384178755276923
]

LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305
COUNTER_CHANNEL_ID = 1495055958827602092  # ← Thay bằng ID kênh lưu counter của bạn
AI_CHANNEL_ID = 1495234134212083884        # ← Thay bằng ID kênh chat AI của bạn

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ================= BẢNG GIÁ =================
PRICE_TABLE = {
    "sell": {
        "money":    {"label": "💰 Money",    "unit": "1m",    "price": "950đ",     "note": "Tối thiểu 10m"},
        "skeleton": {"label": "🦴 Skeleton", "unit": "5m",    "price": "4.000đ",   "note": ""},
        "elytra":   {"label": "🪽 Elytra",   "unit": "1 cái", "price": "330.000đ", "note": "Liên hệ trước"},
    },
    "buy": {
        "money":    {"label": "💰 Money",    "unit": "1m",    "price": "700đ",                     "note": ""},
        "skeleton": {"label": "🦴 Skeleton", "unit": "1 cái", "price": "3.200đ hoặc 3,5m ingame", "note": ""},
        "elytra":   {"label": "🪽 Elytra",   "unit": "1 cái", "price": "300.000đ",                "note": ""},
    }
}

# Dịch vụ không có giá — tạo ticket thẳng, không qua modal
SERVICE_TABLE = {
    "orderbase": {"label": "🏯 Order Base",    "note": "Đặt thiết kế base theo yêu cầu",  "color": 0xE67E22, "type_label": "🏯 ORDER BASE",    "channel_prefix": "base"},
    "modfixlag": {"label": "⚡ Mod Fix Lag",   "note": "Hỗ trợ cài mod tối ưu FPS",       "color": 0x1ABC9C, "type_label": "⚡ MOD FIX LAG",   "channel_prefix": "mod"},
    "giveaway":  {"label": "🎁 Nhận Giveaway", "note": "Xác nhận & nhận thưởng giveaway", "color": 0xF1C40F, "type_label": "🎁 NHẬN GIVEAWAY",  "channel_prefix": "ticket"},
    "support":   {"label": "🆘 Hỗ Trợ",        "note": "Hỗ trợ mọi vấn đề",              "color": 0x3498DB, "type_label": "🆘 HỖ TRỢ",         "channel_prefix": "ticket"},
}

NO_PRICE_KEYS = set(SERVICE_TABLE.keys())

PAYMENT_INFO = """
> 💳 **Thẻ siêu rẻ:** `ruby197` — `Khấu trừ 2,000 vnd cho mỗi lần chuyển`
> 📱 **Thẻ Viettel:** Bị trừ thêm **18% thuế** trên tổng tiền nạp
> 🏦 **Ngân hàng:** `0702557706` — MB Bank — HOVANBUT
> ⚠️ Ghi rõ nội dung: `[tên tài khoản Minecraft] mua [item]`
"""

# ================= DATA =================
def load_data():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except:
        return {
            "ticket": 0,
            "stock": {
                "money": "Chưa cập nhật",
                "skeleton": "Chưa cập nhật",
                "elytra": "Chưa cập nhật"
            },
            "panel_channel_id": None,
            "ratings": [],
            "ticket_notes": {}
        }

def save_data(data):
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_ticket_number():
    """Lấy số ticket tiếp theo từ data.json (fallback khi chưa sync được channel)."""
    data = load_data()
    data["ticket"] = data.get("ticket", 0) + 1
    save_data(data)
    return f"{data['ticket']:03d}"

async def read_counter_from_channel() -> int:
    """Đọc số ticket hiện tại từ kênh counter trên Discord."""
    if not COUNTER_CHANNEL_ID:
        return 0
    channel = bot.get_channel(COUNTER_CHANNEL_ID)
    if not channel:
        return 0
    try:
        async for msg in channel.history(limit=1):
            # Tin nhắn có dạng: "ticket:007"
            if msg.content.startswith("ticket:"):
                return int(msg.content.split(":")[1])
    except:
        pass
    return 0

async def write_counter_to_channel(number: int):
    """Ghi số ticket mới nhất vào kênh counter."""
    if not COUNTER_CHANNEL_ID:
        return
    channel = bot.get_channel(COUNTER_CHANNEL_ID)
    if not channel:
        return
    try:
        # Xoá tin nhắn cũ và ghi mới
        await channel.purge(limit=5)
        await channel.send(f"ticket:{number:03d}")
    except:
        pass

async def get_next_ticket_number() -> str:
    """
    Lấy số ticket tiếp theo từ kênh Discord.
    Nếu kênh chưa có → đọc từ data.json.
    Sau đó ghi số mới vào cả hai nơi.
    """
    channel_num = await read_counter_from_channel()
    data = load_data()
    file_num = data.get("ticket", 0)

    # Lấy số cao hơn để tránh trùng
    current = max(channel_num, file_num)
    next_num = current + 1

    # Lưu vào cả data.json lẫn kênh Discord
    data["ticket"] = next_num
    save_data(data)
    asyncio.create_task(write_counter_to_channel(next_num))

    return f"{next_num:03d}"

async def sync_ticket_counter(guild: discord.Guild):
    """
    Khi bot khởi động: đồng bộ counter từ kênh Discord + quét channel thực tế.
    Lấy số cao nhất trong 3 nguồn: data.json, kênh counter, channel tên ticket-XXX.
    """
    # Nguồn 1: data.json
    data = load_data()
    max_num = data.get("ticket", 0)

    # Nguồn 2: kênh counter Discord
    channel_num = await read_counter_from_channel()
    if channel_num > max_num:
        max_num = channel_num

    # Nguồn 3: quét tên channel thực tế
    for channel in guild.text_channels:
        if channel.name.startswith("ticket-"):
            try:
                num = int(channel.name.split("-")[-1])
                if num > max_num:
                    max_num = num
            except ValueError:
                continue

    # Cập nhật nếu cần
    if max_num > data.get("ticket", 0):
        data["ticket"] = max_num
        save_data(data)
        asyncio.create_task(write_counter_to_channel(max_num))
        print(f"[SYNC] Ticket counter đồng bộ → {max_num:03d}")

def get_stock():
    data = load_data()
    return data.get("stock", {
        "money": "Chưa cập nhật",
        "skeleton": "Chưa cập nhật",
        "elytra": "Chưa cập nhật"
    })

def save_stock(stock: dict):
    data = load_data()
    data["stock"] = stock
    save_data(data)

def get_panel_channel_id():
    return load_data().get("panel_channel_id")

def save_panel_channel_id(channel_id: int):
    data = load_data()
    data["panel_channel_id"] = channel_id
    save_data(data)

def get_qr_path():
    data = load_data()
    return data.get("qr_path", None)

def save_qr_path(path: str):
    data = load_data()
    data["qr_path"] = path
    save_data(data)

def save_rating(ticket_name, user_id, stars):
    data = load_data()
    if "ratings" not in data:
        data["ratings"] = []
    data["ratings"].append({
        "ticket": ticket_name,
        "user_id": user_id,
        "stars": stars,
        "time": datetime.now(timezone.utc).isoformat()
    })
    save_data(data)

def get_ticket_note(channel_id):
    data = load_data()
    return data.get("ticket_notes", {}).get(str(channel_id), [])

def add_ticket_note(channel_id, author, note):
    data = load_data()
    if "ticket_notes" not in data:
        data["ticket_notes"] = {}
    key = str(channel_id)
    if key not in data["ticket_notes"]:
        data["ticket_notes"][key] = []
    data["ticket_notes"][key].append({
        "author": author,
        "note": note,
        "time": datetime.now(timezone.utc).isoformat()
    })
    save_data(data)

# ================= CHECK TICKET =================
async def has_ticket(guild, user):
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic:
            return True
    return False

# ================= BUILD PANEL EMBED =================
def build_panel_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🏪  TuyTam Store",
        description=(
            "Chào mừng đến với **TuyTam Store**!\n"
            "Nhấn nút bên dưới để tạo ticket giao dịch.\n"
            "Dùng lệnh `.price` để xem bảng giá chi tiết."
        ),
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="🛒  Dịch vụ",
        value="› Mua / Bán Money, Skeleton, Elytra\n› 🏯 Order Base\n› ⚡ Mod Fix Lag\n› 🎁 Nhận Giveaway\n› 🆘 Hỗ Trợ",
        inline=True
    )
    embed.add_field(
        name="📋  Ticket bao gồm",
        value="› Tạo kênh riêng tư\n› Staff hỗ trợ 24/7\n› Transcript sau giao dịch",
        inline=True
    )
    embed.add_field(
        name="⚠️  Lưu ý",
        value="› Không spam ticket\n› Ghi rõ số lượng & item\n› Thanh toán đúng giá niêm yết",
        inline=False
    )
    embed.set_footer(
        text="TuyTam Store  •  Ticket System",
        icon_url=guild.icon.url if guild.icon else None
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed

# Các mục không hiển thị giá trong bảng giá
NO_PRICE_KEYS = {"modfixlag", "giveaway", "orderbase", "support"}

# ================= BUILD PRICE EMBED =================
def build_price_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="💰  Bảng Giá TuyTam Store",
        description="Giá cập nhật mới nhất. Liên hệ ticket để giao dịch.",
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )

    # Shop bán — chỉ hiện item có giá
    sell_lines = ""
    service_lines = ""
    for k, info in PRICE_TABLE["sell"].items():
        note = f" *({info['note']})*" if info["note"] else ""
        if k in NO_PRICE_KEYS:
            service_lines += f"{info['label']}{note}\n"
        else:
            sell_lines += f"{info['label']}\n┣ Giá: **{info['price']}** / {info['unit']}{note}\n\n"

    if sell_lines:
        embed.add_field(name="🛒  Shop Bán — Bạn Mua", value=sell_lines.strip(), inline=False)
    if service_lines:
        embed.add_field(name="🎮  Dịch Vụ Khác", value=service_lines.strip(), inline=False)

    # Shop mua
    buy_lines = ""
    for k, info in PRICE_TABLE["buy"].items():
        note = f" *({info['note']})*" if info["note"] else ""
        buy_lines += f"{info['label']}\n┣ Giá thu: **{info['price']}** / {info['unit']}{note}\n\n"
    embed.add_field(name="💸  Shop Mua — Bạn Bán", value=buy_lines.strip(), inline=False)

    # Thanh toán
    embed.add_field(name="💳  Thanh Toán", value=PAYMENT_INFO, inline=False)

    embed.set_footer(
        text="TuyTam Store  •  Giá có thể thay đổi, vui lòng hỏi staff trước khi giao dịch",
        icon_url=guild.icon.url if guild.icon else None
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed

# ================= CẬP NHẬT PANEL =================
async def update_panel_message(guild: discord.Guild):
    panel_channel_id = get_panel_channel_id()
    if panel_channel_id:
        channel = guild.get_channel(panel_channel_id)
        if not channel:
            return
        try:
            async for msg in channel.history(limit=50):
                if (
                    msg.author == guild.me
                    and msg.embeds
                    and msg.embeds[0].title == "🏪  TuyTam Store"
                ):
                    await msg.edit(embed=build_panel_embed(guild))
                    return
        except (discord.Forbidden, discord.HTTPException):
            return
    else:
        for channel in guild.text_channels:
            if channel.topic and "|" in channel.topic:
                continue
            try:
                async for msg in channel.history(limit=50):
                    if (
                        msg.author == guild.me
                        and msg.embeds
                        and msg.embeds[0].title == "🏪  TuyTam Store"
                    ):
                        await msg.edit(embed=build_panel_embed(guild))
                        return
            except (discord.Forbidden, discord.HTTPException):
                continue

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
  <div class="meta">Xuất lúc {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')} UTC • {len(messages)} tin nhắn</div>
  {rows}
</body>
</html>"""

# ================= RATING MODAL =================
class RatingModal(Modal):
    def __init__(self, ticket_name: str, user_id: int):
        super().__init__(title="⭐ Đánh Giá Dịch Vụ")
        self.ticket_name = ticket_name
        self.user_id = user_id

    stars_input = TextInput(
        label="Số sao (1-5)",
        placeholder="Nhập số từ 1 đến 5",
        min_length=1,
        max_length=1
    )
    comment = TextInput(
        label="Nhận xét (tuỳ chọn)",
        placeholder="Dịch vụ tốt, staff nhiệt tình...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars = int(self.stars_input.value)
            if stars < 1 or stars > 5:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Số sao không hợp lệ! Nhập từ 1 đến 5.", ephemeral=True
            )

        save_rating(self.ticket_name, self.user_id, stars)
        star_display = "⭐" * stars + "☆" * (5 - stars)

        log = bot.get_channel(LOG_CHANNEL)
        if log:
            embed = discord.Embed(
                title="⭐ Đánh Giá Mới",
                color=0xF1C40F,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Ticket", value=f"`{self.ticket_name}`", inline=True)
            embed.add_field(name="User", value=f"<@{self.user_id}>", inline=True)
            embed.add_field(name="Đánh giá", value=star_display, inline=True)
            if self.comment.value:
                embed.add_field(name="Nhận xét", value=self.comment.value, inline=False)
            await log.send(embed=embed)

        await interaction.response.send_message(
            f"✅ Cảm ơn bạn đã đánh giá! {star_display}", ephemeral=True
        )

class RatingView(View):
    def __init__(self, ticket_name: str, user_id: int):
        super().__init__(timeout=300)
        self.ticket_name = ticket_name
        self.user_id = user_id

    @discord.ui.button(label="⭐ Đánh giá dịch vụ", style=discord.ButtonStyle.blurple)
    async def rate(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Chỉ người tạo ticket mới được đánh giá.", ephemeral=True)
        await interaction.response.send_modal(RatingModal(self.ticket_name, self.user_id))

# ================= ADD STAFF MODAL =================
class AddStaffModal(Modal):
    def __init__(self):
        super().__init__(title="📎 Thêm Staff vào Ticket")

    user_id_input = TextInput(
        label="ID của Staff",
        placeholder="Nhập User ID (click chuột phải → Copy ID)",
        min_length=15,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
            member = interaction.guild.get_member(uid)
            if not member:
                return await interaction.response.send_message("❌ Không tìm thấy member này.", ephemeral=True)

            overwrite = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )
            await interaction.channel.set_permissions(member, overwrite=overwrite)
            await interaction.response.send_message(
                f"✅ Đã thêm {member.mention} vào ticket!", ephemeral=False
            )
        except ValueError:
            await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

# ================= NOTE MODAL =================
class NoteModal(Modal):
    def __init__(self, channel_id: int):
        super().__init__(title="📝 Thêm Ghi Chú Nội Bộ")
        self.channel_id = channel_id

    note_input = TextInput(
        label="Nội dung ghi chú",
        placeholder="Ghi chú chỉ staff thấy...",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        add_ticket_note(self.channel_id, str(interaction.user), self.note_input.value)
        embed = discord.Embed(
            title="📝 Ghi Chú Nội Bộ",
            description=self.note_input.value,
            color=0xFEE75C,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Bởi {interaction.user} • Chỉ staff thấy")
        await interaction.response.send_message(embed=embed)

# ================= ORDER MODAL =================
def estimate_price(item_key: str, trade_type: str, amount_str: str) -> str:
    """Tự động ước tính giá dựa trên số lượng nhập vào."""
    try:
        price_map = {
            ("sell", "money"):    (950,    "m"),
            ("sell", "skeleton"): (4000,   "5m"),
            ("sell", "elytra"):   (330000, "cái"),
            ("buy",  "money"):    (700,    "m"),
            ("buy",  "skeleton"): (3200,   "cái"),
            ("buy",  "elytra"):   (300000, "cái"),
        }
        key = (trade_type, item_key)
        if key not in price_map:
            return "Liên hệ staff"

        unit_price, unit = price_map[key]
        s = amount_str.lower().replace(",", "").replace(".", "")
        num = None

        if "m" in s:
            raw = s.replace("m", "").strip()
            if raw.isdigit():
                num = int(raw)
                if unit == "5m":
                    total = int(num / 5) * unit_price
                else:
                    total = num * unit_price
        elif s.isdigit():
            num = int(s)
            if unit == "5m":
                total = int(num / 5) * unit_price
            else:
                total = num * unit_price
        else:
            return "Liên hệ staff"

        if num is not None:
            formatted = f"{total:,}đ".replace(",", ".")
            return formatted
    except:
        pass
    return "Liên hệ staff"


async def auto_ping_unclaimed(channel, number, guild):
    """Chạy nền — ping staff nếu 5 phút chưa có ai claim."""
    await asyncio.sleep(300)
    ch = guild.get_channel(channel.id)
    if ch is None:
        return
    claimed = False
    try:
        async for m in ch.history(limit=20):
            if m.author == guild.me and "đã nhận ticket" in m.content.lower():
                claimed = True
                break
    except:
        return
    if not claimed:
        try:
            await ch.send(
                f"⏰ <@&{SUPPORT_ROLE_ID}> Ticket **#{number}** chưa có staff nhận sau 5 phút! Vui lòng xử lý sớm."
            )
        except:
            pass


async def create_service_ticket(interaction: discord.Interaction, service_key: str):
    """Tạo ticket dịch vụ thẳng không qua modal. Interaction đã được defer trước."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send(
                "❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True
            )

        info = SERVICE_TABLE[service_key]
        number = await get_next_ticket_number()
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

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
        support_role = guild.get_role(SUPPORT_ROLE_ID)
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )

        category = discord.utils.get(guild.categories, id=TICKET_CATEGORY_ID)
        channel = await guild.create_text_channel(
            name=f"ticket-{number}",
            overwrites=overwrites,
            category=category,
            topic=f"{interaction.user.id}||service|{service_key}|open"
        )

        embed = discord.Embed(
            title=f"{info['type_label']}  •  #{number}",
            description=(
                f"Xin chào {interaction.user.mention}! 👋\n"
                f"Staff sẽ hỗ trợ bạn sớm nhất có thể.\n"
                f"🟡 **Trạng thái:** Đang chờ staff nhận"
            ),
            color=info["color"],
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="📦  Dịch vụ",   value=info["label"],             inline=True)
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

        await interaction.followup.send(
            f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True
        )

        # Auto-ping chạy nền, không block
        asyncio.create_task(auto_ping_unclaimed(channel, number, guild))

    except Exception as e:
        try:
            await interaction.followup.send(
                f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`\nVui lòng thử lại hoặc liên hệ admin.", ephemeral=True
            )
        except:
            pass


class OrderModal(Modal):
    def __init__(self, trade_type: str, item_key: str):
        item_info = PRICE_TABLE[trade_type][item_key]
        action = "Mua" if trade_type == "sell" else "Bán"
        super().__init__(title=f"{action} {item_info['label']}")
        self.trade_type = trade_type
        self.item_key = item_key

        self.mc_name = TextInput(
            label="Tên Minecraft của bạn",
            placeholder="Ví dụ: quannmc",
            min_length=2, max_length=32
        )
        self.add_item(self.mc_name)
        self.amount = TextInput(
            label="Số lượng",
            placeholder="Ví dụ: 10m / 5 cái / 100",
            min_length=1, max_length=50
        )
        self.add_item(self.amount)
        self.payment = TextInput(
            label="Phương thức thanh toán",
            placeholder="MB Bank / Thẻ cào / Thẻ Viettel (+18% thuế) / Ingame",
            min_length=2, max_length=100
        )
        self.add_item(self.payment)
        self.note = TextInput(
            label="Ghi chú (tuỳ chọn)",
            placeholder="Ví dụ: cần gấp, giao hàng online...",
            style=discord.TextStyle.paragraph,
            required=False, max_length=200
        )
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        try:
            if await has_ticket(guild, interaction.user):
                return await interaction.response.send_message(
                    "❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.",
                    ephemeral=True
                )

            number = await get_next_ticket_number()
            item_info = PRICE_TABLE[self.trade_type][self.item_key]
            created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

            if self.trade_type == "sell":
                color = 0x57F287
                type_label = "🛒 MUA HÀNG"
            else:
                color = 0xFEE75C
                type_label = "💸 BÁN HÀNG"

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
            support_role = guild.get_role(SUPPORT_ROLE_ID)
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True
                )

            category = discord.utils.get(guild.categories, id=TICKET_CATEGORY_ID)
            channel = await guild.create_text_channel(
                name=f"ticket-{number}",
                overwrites=overwrites,
                category=category,
                topic=f"{interaction.user.id}|{self.mc_name.value}|{self.trade_type}|{self.item_key}|open"
            )

            embed = discord.Embed(
                title=f"{type_label}  •  {item_info['label']}  •  #{number}",
                description=(
                    f"Xin chào {interaction.user.mention}! 👋\n"
                    f"Staff sẽ xử lý giao dịch sớm nhất có thể.\n"
                    f"🟡 **Trạng thái:** Đang chờ staff nhận"
                ),
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="👤  Người dùng",    value=interaction.user.mention,  inline=True)
            embed.add_field(name="🎮  Tên Minecraft", value=f"`{self.mc_name.value}`", inline=True)
            embed.add_field(name="🕐  Thời gian",     value=created_at,                inline=True)
            embed.add_field(name="📦  Item",          value=item_info["label"],        inline=True)
            embed.add_field(name="🔢  Số lượng",      value=self.amount.value,         inline=True)
            est = estimate_price(self.item_key, self.trade_type, self.amount.value)
            embed.add_field(name="💲  Ước tính giá",  value=f"**~{est}**",             inline=True)
            embed.add_field(name="💳  Thanh toán",    value=self.payment.value,        inline=True)
            if "viettel" in self.payment.value.lower():
                embed.add_field(
                    name="⚠️  Lưu ý Viettel",
                    value="Thẻ Viettel bị trừ thêm **18% thuế**, giá thực tế sẽ cao hơn!",
                    inline=False
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
                f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True
            )

            # Auto-ping chạy nền, không block
            asyncio.create_task(auto_ping_unclaimed(channel, number, guild))

        except Exception as e:
            try:
                await interaction.response.send_message(
                    f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`\nVui lòng thử lại hoặc liên hệ admin.",
                    ephemeral=True
                )
            except:
                pass

# ================= SELECT ITEM =================
class ItemSelect(Select):
    def __init__(self, trade_type: str):
        self.trade_type = trade_type
        action = "mua" if trade_type == "sell" else "bán"
        options = [
            discord.SelectOption(
                label=info["label"],
                value=key,
                description=info["note"] if key in NO_PRICE_KEYS else f"Giá: {info['price']} / {info['unit']}",
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
        try:
            await interaction.response.send_modal(
                OrderModal(trade_type=self.trade_type, item_key=self.values[0])
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

class ItemSelectView(View):
    def __init__(self, trade_type: str):
        super().__init__(timeout=60)
        self.add_item(ItemSelect(trade_type))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# ================= SERVICE SELECT =================
class ServiceSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=info["label"],
                value=key,
                description=info["note"],
                emoji=info["label"].split()[0]
            )
            for key, info in SERVICE_TABLE.items()
        ]
        super().__init__(
            placeholder="Chọn dịch vụ bạn cần...",
            options=options,
            custom_id="service_select"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_service_ticket(interaction, self.values[0])
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

class ServiceSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(ServiceSelect())

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
        try:
            await interaction.response.send_message(
                "🛒 **Bạn muốn mua item nào?**",
                view=ItemSelectView(trade_type="sell"),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Bán hàng",
        emoji="💸",
        style=discord.ButtonStyle.blurple,
        custom_id="panel_sell"
    )
    async def sell(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "💸 **Bạn muốn bán item nào?**",
                view=ItemSelectView(trade_type="buy"),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Dịch Vụ",
        emoji="🎮",
        style=discord.ButtonStyle.grey,
        custom_id="panel_service"
    )
    async def service(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "🎮 **Bạn cần dịch vụ nào?**",
                view=ServiceSelectView(),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Xem giá",
        emoji="📋",
        style=discord.ButtonStyle.grey,
        custom_id="panel_price"
    )
    async def view_price(self, interaction: discord.Interaction, button: Button):
        embed = build_price_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
        try:
            for item in self.children:
                if item.custom_id == "claim_ticket":
                    item.disabled = True
                    item.label = f"Claimed: {interaction.user.display_name}"
                    item.emoji = "✅"
                    break
            await interaction.response.defer()
            await interaction.message.edit(view=self)
            await interaction.followup.send(f"✅ {interaction.user.mention} đã nhận ticket này!")
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Add Staff",
        emoji="📎",
        style=discord.ButtonStyle.grey,
        custom_id="add_staff"
    )
    async def add_staff(self, interaction: discord.Interaction, button: Button):
        support_role = interaction.guild.get_role(SUPPORT_ROLE_ID)
        has_role = support_role in interaction.user.roles if support_role else False
        if not (interaction.user.id in ADMIN_IDS or has_role):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            await interaction.response.send_modal(AddStaffModal())
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Ghi chú",
        emoji="📝",
        style=discord.ButtonStyle.grey,
        custom_id="add_note"
    )
    async def add_note(self, interaction: discord.Interaction, button: Button):
        support_role = interaction.guild.get_role(SUPPORT_ROLE_ID)
        has_role = support_role in interaction.user.roles if support_role else False
        if not (interaction.user.id in ADMIN_IDS or has_role):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            await interaction.response.send_modal(NoteModal(interaction.channel.id))
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

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
        try:
            await interaction.response.defer()
            await _close_ticket(interaction.channel, bot)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi khi đóng ticket: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Gửi QR",
        emoji="📱",
        style=discord.ButtonStyle.green,
        custom_id="send_qr"
    )
    async def send_qr(self, interaction: discord.Interaction, button: Button):
        support_role = interaction.guild.get_role(SUPPORT_ROLE_ID)
        has_role = support_role in interaction.user.roles if support_role else False
        if not (interaction.user.id in ADMIN_IDS or has_role):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            qr_path = get_qr_path()
            if not qr_path or not os.path.exists(qr_path):
                return await interaction.response.send_message(
                    "❌ Chưa có QR! Admin cài QR qua `.settings` trước.", ephemeral=True
                )
            file = discord.File(qr_path, filename="qr.png")
            embed = discord.Embed(
                title="📱  Mã QR Thanh Toán",
                description=(
                    "> 🏦 **MB Bank** — `0702557706` — HOVANBUT\n"
                    "> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n"
                    "> ⚠️ Ghi rõ nội dung: `[tên MC] mua [item]`"
                ),
                color=0x57F287,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_image(url="attachment://qr.png")
            embed.set_footer(text=f"Gửi bởi {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed, file=file)
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

# ================= CLOSE LOGIC =================
async def _close_ticket(channel, bot_instance):
    # Lấy user_id từ topic
    user_id = None
    ticket_name = channel.name
    if channel.topic:
        parts = channel.topic.split("|")
        if parts:
            try:
                user_id = int(parts[0])
            except ValueError:
                pass

    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    html = build_transcript_html(channel.name, messages)
    file = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")

    log = bot_instance.get_channel(LOG_CHANNEL)
    if log:
        embed = discord.Embed(
            title="📄 Transcript Ticket",
            description=f"**Kênh:** `{channel.name}`\n**Tin nhắn:** {len(messages)}",
            color=0xED4245,
            timestamp=datetime.now(timezone.utc)
        )
        await log.send(embed=embed, file=file)

    # Ghi chú nội bộ vào log nếu có
    notes = get_ticket_note(channel.id)
    if notes and log:
        note_text = "\n".join([f"**{n['author']}:** {n['note']}" for n in notes])
        note_embed = discord.Embed(
            title="📝 Ghi Chú Nội Bộ",
            description=note_text,
            color=0xFEE75C,
            timestamp=datetime.now(timezone.utc)
        )
        note_embed.set_footer(text=f"Ticket: {ticket_name}")
        await log.send(embed=note_embed)

    await channel.delete()

    # Gửi DM đánh giá cho user
    if user_id:
        guild = channel.guild
        member = guild.get_member(user_id)
        if member:
            try:
                rate_embed = discord.Embed(
                    title="⭐ Đánh Giá Dịch Vụ",
                    description=(
                        f"Ticket `{ticket_name}` của bạn đã được đóng.\n"
                        f"Hãy đánh giá dịch vụ để giúp chúng tôi cải thiện!"
                    ),
                    color=0xF1C40F,
                    timestamp=datetime.now(timezone.utc)
                )
                await member.send(embed=rate_embed, view=RatingView(ticket_name, user_id))
            except discord.Forbidden:
                pass  # User tắt DM

# ================= COMMANDS =================
@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    if latency < 100:
        color, status = 0x57F287, "Tốt 🟢"
    elif latency < 200:
        color, status = 0xFEE75C, "Bình thường 🟡"
    else:
        color, status = 0xED4245, "Chậm 🔴"
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Độ trễ: **{latency}ms** — {status}",
        color=color
    )
    await ctx.reply(embed=embed)


@bot.command(name="price")
async def price_cmd(ctx):
    embed = build_price_embed(ctx.guild)
    await ctx.reply(embed=embed)


@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="📋  Danh Sách Lệnh",
        description="Prefix: `.`",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="🌐  Chung",
        value=(
            "`.ping` — Kiểm tra độ trễ bot\n"
            "`.help` — Danh sách lệnh\n"
            "`.price` — Xem bảng giá chi tiết"
        ),
        inline=False
    )
    embed.add_field(
        name="🎫  Ticket",
        value=(
            "`.panel` — Gửi panel ticket *(admin)*\n"
            "`.close` — Đóng ticket hiện tại *(admin/staff)*\n"
            "`.addnote <nội dung>` — Thêm ghi chú nội bộ *(admin/staff)*"
        ),
        inline=False
    )
    embed.add_field(
        name="📦  Stock",
        value=(
            "`.stock` — Xem stock hiện tại\n"
            "`.stock <item> <số lượng>` — Cập nhật stock *(admin/staff)*\n"
            "Ví dụ: `.stock money 500m`  |  `.stock elytra 3 cái`"
        ),
        inline=False
    )
    embed.add_field(
        name="⭐  Rating",
        value="`.ratings` — Xem thống kê đánh giá *(admin)*",
        inline=False
    )
    embed.add_field(
        name="⚙️  Cài đặt",
        value=(
            "`.setpanel #kênh` — Chỉ định kênh chứa panel *(admin)*\n"
            "`.settings` — Xem cấu hình & đổi QR *(admin)*\n"
            "`.qr` — Gửi mã QR thanh toán\n"
            "`.orderbase` — Gửi bảng giá Order Base *(admin)*"
        ),
        inline=False
    )
    embed.add_field(
        name="🤖  AI",
        value=(
            "Chat tự do trong kênh AI được chỉ định\n"
            "`.aiclear` — Xoá lịch sử hội thoại của bạn"
        ),
        inline=False
    )
    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await ctx.reply(embed=embed)


@bot.command(name="stock")
async def stock_cmd(ctx, item: str = None, *, amount: str = None):
    support_role = ctx.guild.get_role(SUPPORT_ROLE_ID)
    has_role = support_role in ctx.author.roles if support_role else False
    is_staff = ctx.author.id in ADMIN_IDS or has_role

    current_stock = get_stock()

    if item is None:
        lines = "\n".join(
            f"{PRICE_TABLE['sell'][k]['label']}  —  **{current_stock.get(k, 'Chưa cập nhật')}**"
            for k in PRICE_TABLE["sell"]
        )
        embed = discord.Embed(
            title="📦  Stock Hiện Tại",
            description=lines,
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="TuyTam Store  •  Ticket System")
        return await ctx.reply(embed=embed)

    if not is_staff:
        return await ctx.reply("❌ Bạn không có quyền cập nhật stock.")

    item = item.lower()
    if item not in PRICE_TABLE["sell"]:
        valid = ", ".join(PRICE_TABLE["sell"].keys())
        return await ctx.reply(f"❌ Item không hợp lệ! Dùng: `{valid}`")

    if amount is None:
        return await ctx.reply("❌ Thiếu số lượng! Ví dụ: `.stock money 500m`")

    current_stock[item] = amount
    save_stock(current_stock)
    await update_panel_message(ctx.guild)

    item_label = PRICE_TABLE["sell"][item]["label"]
    embed = discord.Embed(
        title="✅  Đã Cập Nhật Stock",
        description=f"{item_label}  →  **{amount}**",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Cập nhật bởi {ctx.author}")
    await ctx.reply(embed=embed)


@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    await ctx.send(embed=build_panel_embed(ctx.guild), view=TicketPanel())
    await ctx.message.delete()


@bot.command()
async def setpanel(ctx, channel: discord.TextChannel = None):
    if ctx.author.id not in ADMIN_IDS:
        return
    if channel is None:
        return await ctx.reply("❌ Thiếu kênh! Ví dụ: `.setpanel #shop`")
    save_panel_channel_id(channel.id)
    embed = discord.Embed(
        title="⚙️  Đã Cài Đặt Panel Channel",
        description=f"Bot sẽ chỉ scan {channel.mention} khi cập nhật stock.",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Cài bởi {ctx.author}")
    await ctx.reply(embed=embed)


# ================= SETTINGS VIEW =================
class SettingsView(View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="📱 Đổi QR", style=discord.ButtonStyle.blurple)
    async def change_qr(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin mới được đổi QR.", ephemeral=True)
        await interaction.response.send_modal(SetQRModal())

    @discord.ui.button(label="👁️ Xem QR hiện tại", style=discord.ButtonStyle.grey)
    async def view_qr(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        qr_path = get_qr_path()
        if not qr_path or not os.path.exists(qr_path):
            return await interaction.response.send_message("❌ Chưa có QR nào được lưu.", ephemeral=True)
        file = discord.File(qr_path, filename="qr.png")
        embed = discord.Embed(title="📱 QR Hiện Tại", color=0x5865F2)
        embed.set_image(url="attachment://qr.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)


@bot.command()
async def settings(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    panel_channel_id = get_panel_channel_id()
    if panel_channel_id:
        channel = ctx.guild.get_channel(panel_channel_id)
        panel_value = channel.mention if channel else f"⚠️ Kênh đã bị xoá (ID: {panel_channel_id})"
    else:
        panel_value = "Chưa cài — dùng `.setpanel #kênh`"

    qr_path = get_qr_path()
    qr_value = f"✅ Đã có QR (`{qr_path}`)" if qr_path and os.path.exists(qr_path) else "❌ Chưa có — nhấn nút **Đổi QR** bên dưới"

    embed = discord.Embed(
        title="⚙️  Cấu Hình Hiện Tại",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📌  Panel Channel",   value=panel_value,              inline=False)
    embed.add_field(name="📋  Log Channel",      value=f"<#{LOG_CHANNEL}>",          inline=True)
    embed.add_field(name="📂  Ticket Category",  value=f"<#{TICKET_CATEGORY_ID}>",   inline=True)
    embed.add_field(name="🛡️  Support Role",     value=f"<@&{SUPPORT_ROLE_ID}>",     inline=True)
    embed.add_field(name="📱  Mã QR Thanh Toán", value=qr_value,                 inline=False)
    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await ctx.reply(embed=embed, view=SettingsView())


@bot.command()
async def close(ctx):
    support_role = ctx.guild.get_role(SUPPORT_ROLE_ID)
    has_role = support_role in ctx.author.roles if support_role else False
    if not (ctx.author.id in ADMIN_IDS or has_role):
        return await ctx.reply("❌ Bạn không có quyền.")
    if not (ctx.channel.topic and "|" in ctx.channel.topic):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    await _close_ticket(ctx.channel, bot)


@bot.command(name="addnote")
async def addnote_cmd(ctx, *, note: str = None):
    support_role = ctx.guild.get_role(SUPPORT_ROLE_ID)
    has_role = support_role in ctx.author.roles if support_role else False
    if not (ctx.author.id in ADMIN_IDS or has_role):
        return await ctx.reply("❌ Bạn không có quyền.")
    if not (ctx.channel.topic and "|" in ctx.channel.topic):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    if not note:
        return await ctx.reply("❌ Thiếu nội dung! Ví dụ: `.addnote khách đã chuyển tiền`")

    add_ticket_note(ctx.channel.id, str(ctx.author), note)
    embed = discord.Embed(
        title="📝 Ghi Chú Nội Bộ",
        description=note,
        color=0xFEE75C,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Bởi {ctx.author} • Chỉ staff thấy")
    await ctx.reply(embed=embed)
    try:
        await ctx.message.delete()
    except:
        pass


@bot.command(name="ratings")
async def ratings_cmd(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    data = load_data()
    ratings = data.get("ratings", [])
    if not ratings:
        return await ctx.reply("Chưa có đánh giá nào.")

    total = len(ratings)
    avg = sum(r["stars"] for r in ratings) / total
    dist = {i: sum(1 for r in ratings if r["stars"] == i) for i in range(1, 6)}

    bar = ""
    for s in range(5, 0, -1):
        count = dist[s]
        filled = int((count / total) * 10) if total > 0 else 0
        bar += f"{'⭐'*s}: {'█'*filled}{'░'*(10-filled)} {count}\n"

    embed = discord.Embed(
        title="⭐ Thống Kê Đánh Giá",
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Tổng đánh giá", value=str(total), inline=True)
    embed.add_field(name="Trung bình", value=f"{avg:.1f} ⭐", inline=True)
    embed.add_field(name="Phân bố", value=f"```{bar}```", inline=False)
    await ctx.reply(embed=embed)


@bot.command(name="orderbase")
async def orderbase_cmd(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="# Nhận Làm Base Village Trong <:emoji_17:1483684359415267449>",
        description=(
            "**Giá Chỉ Từ 20-35m Tùy Theo Base Mà Ae Chọn**\n\n"
            "**Cam Kết:**\n"
            "<:emoji_17:1483684359415267449> •Tự Tìm Chỗ Xây Base Lun Nhé Ae\n"
            "<:emoji_17:1483684359415267449> •Base Có Chỗ Nhân Giống Village\n"
            "<:emoji_17:1483684359415267449> •Base Sẽ Có Ít Nhất 3 Con Dân Làng Bán Tu Sửa\n"
            "<:emoji_17:1483684359415267449> •Còn Lại Sẽ Là Ngẫu Nhiên Và Có Thể Có Thêm Dòng Xịn Như Protection, Blast Protection, Fortune,...\n"
            "<:emoji_17:1483684359415267449> •Bảo Hành 8h Kể Từ Khi Mua\n"
            "<:emoji_17:1483684359415267449> •Nếu Bị Raid Trong Giờ Bảo Hành Sẽ Đc Hoàn Tiền\n"
            "<:emoji_17:1483684359415267449> •Và Sẽ Đảm Bảo Đc Với Anh Em Là Quay Video Xoá Home Base\n"
            "<:emoji_17:1483684359415267449> •Base 20m Sẽ Có 3 Con Roll Sẵn Tu Sửa Còn Lại Ae Tự Roll Và 35m Thì Sẽ Roll Hết Tất Cả Nhé Và Sẽ Đẹp Và Rộng Hơn Nên Ae K Lỗ Đâu\n\n"
            "**Nên Ae Yên Tâm Mà Thuê** ✅\n\n"
            "**Ai Muốn Có 1 Base Village Tuyệt Vời Như Vậy Mà Còn Rẻ Thì Hãy Tạo <#1464415587378659564> Để Có 1 Base Xịn Nhé**"
        ),
        color=0xE67E22,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="💰 DoанBaoNgoc-Stock  •  TuyTam Store")

    await ctx.send("<@&1464411190808805540> sorry ping", embed=embed)


@bot.command(name="qr")
async def qr_cmd(ctx):
    qr_path = get_qr_path()
    if not qr_path or not os.path.exists(qr_path):
        embed = discord.Embed(
            title="❌  Chưa Có Mã QR",
            description="Admin chưa cài mã QR.\nDùng `.settings` để thêm QR thanh toán.",
            color=0xED4245
        )
        return await ctx.reply(embed=embed)

    embed = discord.Embed(
        title="📱  Mã QR Thanh Toán",
        description=(
            "Quét mã bên dưới để thanh toán.\n"
            "> 🏦 **MB Bank** — HOVANBUT\n"
            "> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n"
            "> ⚠️ Ghi rõ nội dung: `[tên MC] mua [item]`"
        ),
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="TuyTam Store  •  Quét QR để thanh toán")
    file = discord.File(qr_path, filename="qr.png")
    embed.set_image(url="attachment://qr.png")
    await ctx.reply(embed=embed, file=file)


class SetQRModal(Modal):
    def __init__(self):
        super().__init__(title="🖼️ Cập Nhật Ảnh QR")

    url_input = TextInput(
        label="URL ảnh QR (để trống nếu đính kèm file)",
        placeholder="https://i.imgur.com/abc123.png",
        required=False,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Nếu nhập URL
        url = self.url_input.value.strip()
        if url:
            import urllib.request
            try:
                qr_path = "qr_code.png"
                urllib.request.urlretrieve(url, qr_path)
                save_qr_path(qr_path)
                embed = discord.Embed(
                    title="✅  Đã Cập Nhật QR",
                    description="Mã QR mới đã được lưu từ URL.",
                    color=0x57F287,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_image(url=url)
                embed.set_footer(text=f"Cập nhật bởi {interaction.user}")
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                return await interaction.response.send_message(
                    f"❌ Không tải được ảnh từ URL: `{e}`", ephemeral=True
                )

        await interaction.response.send_message(
            "📎 Hãy **đính kèm ảnh QR** vào tin nhắn tiếp theo trong vòng **60 giây**.",
            ephemeral=True
        )

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
                and len(m.attachments) > 0
            )

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            attachment = msg.attachments[0]
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                return await interaction.followup.send("❌ File không phải ảnh!", ephemeral=True)

            qr_path = "qr_code.png"
            await attachment.save(qr_path)
            save_qr_path(qr_path)

            try:
                await msg.delete()
            except:
                pass

            embed = discord.Embed(
                title="✅  Đã Cập Nhật QR",
                description="Mã QR mới đã được lưu thành công!\nDùng `.qr` để kiểm tra.",
                color=0x57F287,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Cập nhật bởi {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Hết thời gian! Không nhận được ảnh.", ephemeral=True)


# ================= GEMINI AI =================
# Lưu lịch sử hội thoại theo từng user (tối đa 20 tin gần nhất)
ai_history: dict[int, list] = {}

async def ask_gemini(user_id: int, user_message: str) -> str:
    """Gửi tin nhắn đến Gemini và trả về phản hồi, có nhớ lịch sử hội thoại."""
    if not GEMINI_API_KEY:
        return "❌ Chưa cài `GEMINI_API_KEY` trong biến môi trường!"

    # Khởi tạo lịch sử nếu chưa có
    if user_id not in ai_history:
        ai_history[user_id] = []

    # Thêm tin nhắn user vào lịch sử
    ai_history[user_id].append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    # Giới hạn 20 tin gần nhất để tránh token quá dài
    if len(ai_history[user_id]) > 20:
        ai_history[user_id] = ai_history[user_id][-20:]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "system_instruction": {
            "parts": [{
                "text": (
                    "Bạn là trợ lý AI của TuyTam Store — một cửa hàng bán đồ Minecraft. "
                    "Hãy trả lời thân thiện, ngắn gọn bằng tiếng Việt. "
                    "Nếu được hỏi về giá hohoặc giao dịch, hướng dẫn người dùng tạo ticket. "
                    "Không trả lời quá 500 từ."
                )
            }]
        },
        "contents": ai_history[user_id]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return f"❌ Gemini lỗi `{resp.status}`: {error[:200]}"
                data = await resp.json()
                reply = data["candidates"][0]["content"]["parts"][0]["text"]

                # Lưu phản hồi vào lịch sử
                ai_history[user_id].append({
                    "role": "model",
                    "parts": [{"text": reply}]
                })
                return reply
    except asyncio.TimeoutError:
        return "⏰ Gemini phản hồi quá chậm, thử lại nhé!"
    except Exception as e:
        return f"❌ Lỗi kết nối Gemini: `{e}`"


# ================= ON MESSAGE =================
@bot.event
async def on_message(message: discord.Message):
    # Bỏ qua tin nhắn của bot
    if message.author.bot:
        return

    # Xử lý lệnh như bình thường
    await bot.process_commands(message)

    # Chỉ xử lý AI trong kênh AI
    if not AI_CHANNEL_ID or message.channel.id != AI_CHANNEL_ID:
        return

    # Bỏ qua nếu là lệnh bot
    if message.content.startswith(bot.command_prefix):
        return

    content = message.content.strip()
    if not content:
        return

    # Hiện typing... để user biết bot đang xử lý
    async with message.channel.typing():
        reply = await ask_gemini(message.author.id, content)

    # Chia nhỏ nếu reply > 2000 ký tự (giới hạn Discord)
    if len(reply) <= 2000:
        await message.reply(reply)
    else:
        chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
        for i, chunk in enumerate(chunks):
            if i == 0:
                await message.reply(chunk)
            else:
                await message.channel.send(chunk)


@bot.command(name="aiclear")
async def aiclear_cmd(ctx):
    """Xoá lịch sử hội thoại AI của bản thân."""
    if AI_CHANNEL_ID and ctx.channel.id != AI_CHANNEL_ID:
        return await ctx.reply("❌ Lệnh này chỉ dùng được trong kênh AI.", delete_after=5)
    if ctx.author.id in ai_history:
        del ai_history[ctx.author.id]
    embed = discord.Embed(
        title="🗑️  Đã Xoá Lịch Sử",
        description="Lịch sử hội thoại AI của bạn đã được xoá.\nCuộc trò chuyện mới bắt đầu!",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author}")
    await ctx.reply(embed=embed)
    try:
        await ctx.message.delete(delay=3)
    except:
        pass


# ================= ERROR HANDLER =================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        pass

# ================= ON READY =================
@bot.event
async def on_ready():
    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    for guild in bot.guilds:
        await sync_ticket_counter(guild)
    print(f"✅ Bot online: {bot.user} | {len(bot.guilds)} server(s)")

bot.run(TOKEN)
