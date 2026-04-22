import os
import io
import json
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select

TOKEN = os.getenv("TOKEN")
print(f"[DEBUG] TOKEN loaded: {'OK' if TOKEN else 'MISSING'}")

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
    1438384178755276923
]

LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305
COUNTER_CHANNEL_ID = 0  # ← Thay bằng ID kênh lưu counter của bạn

# ── ID kênh dùng làm "database" Discord ──
DATA_CHANNEL_ID = 1495055958827602092

# ── Getter động — đọc từ data.json nếu admin đã đổi qua .settings ──
def get_cfg_log_channel() -> int:
    return load_data().get("cfg_log_channel", LOG_CHANNEL)

def get_cfg_category() -> int:
    return load_data().get("cfg_ticket_category", TICKET_CATEGORY_ID)

def get_cfg_support_role() -> int:
    return load_data().get("cfg_support_role", SUPPORT_ROLE_ID)

def get_cfg_counter_channel() -> int:
    return load_data().get("cfg_counter_channel", COUNTER_CHANNEL_ID)

def get_cfg_balance_channel() -> int:
    return load_data().get("cfg_balance_channel", 0)

def save_cfg(key: str, value: int):
    data = load_data()
    data[key] = value
    save_data(data)

# ── Số dư & thống kê kênh balance ──
def get_balance_data() -> dict:
    data = load_data()
    if "balance" not in data:
        data["balance"] = {
            "current": 0,
            "total_in": 0,
            "total_fee": 0,
            "total_out": 0,
            "tx_count": 0,
            "history": []   # [{"type": "+/-", "raw": int, "fee": int, "net": int, "user": str, "time": str}]
        }
        save_data(data)
    return data["balance"]

def save_balance_data(bal: dict):
    data = load_data()
    data["balance"] = bal
    save_data(data)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)
tree = bot.tree

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

# ================= DATA (Discord Channel Storage) =================
# Toàn bộ data lưu trong 1 tin nhắn JSON ở kênh DATA_CHANNEL_ID
# Không cần file data.json — không bị mất khi redeploy

QR_FILE = "/data/qr_code.png" if os.path.isdir("/data") else "./qr_code.png"

_DATA_MSG_ID: int | None = None   # cache message ID sau lần đầu tìm thấy

DEFAULT_DATA = {
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

def _default_data() -> dict:
    import copy
    return copy.deepcopy(DEFAULT_DATA)

# ── Cache in-memory (tránh gọi Discord API liên tục) ──
_data_cache: dict | None = None
_cache_dirty: bool = False

async def _get_data_channel():
    ch = bot.get_channel(DATA_CHANNEL_ID)
    if ch is None:
        try:
            ch = await bot.fetch_channel(DATA_CHANNEL_ID)
        except Exception as e:
            print(f"[DATA] Không lấy được kênh data: {e}")
    return ch

async def _find_data_message():
    """Tìm tin nhắn JSON duy nhất trong kênh (do bot gửi, bắt đầu bằng DATA:)."""
    global _DATA_MSG_ID
    if _DATA_MSG_ID:
        return _DATA_MSG_ID
    ch = await _get_data_channel()
    if not ch:
        return None
    try:
        async for msg in ch.history(limit=50):
            if msg.author == bot.user and msg.content.startswith("DATA:"):
                _DATA_MSG_ID = msg.id
                return _DATA_MSG_ID
    except Exception as e:
        print(f"[DATA] Lỗi khi tìm message: {e}")
    return None

async def load_data_async() -> dict:
    """Đọc data từ Discord channel (có cache)."""
    global _data_cache
    if _data_cache is not None:
        return _data_cache

    msg_id = await _find_data_message()
    if not msg_id:
        _data_cache = _default_data()
        return _data_cache

    ch = await _get_data_channel()
    if not ch:
        _data_cache = _default_data()
        return _data_cache

    try:
        msg = await ch.fetch_message(msg_id)
        raw = msg.content[len("DATA:"):]
        _data_cache = json.loads(raw)
        # Đảm bảo các key mặc định luôn có
        for k, v in _default_data().items():
            _data_cache.setdefault(k, v)
        return _data_cache
    except Exception as e:
        print(f"[DATA] Lỗi đọc data message: {e}")
        _data_cache = _default_data()
        return _data_cache

async def save_data_async(data: dict):
    """Ghi data lên Discord channel (edit tin nhắn cũ hoặc gửi mới)."""
    global _DATA_MSG_ID, _data_cache
    _data_cache = data

    ch = await _get_data_channel()
    if not ch:
        print("[DATA] ❌ Không lưu được — kênh không tồn tại!")
        return

    content = "DATA:" + json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    # Discord giới hạn 2000 ký tự/message → dùng file đính kèm nếu quá dài
    if len(content) > 1990:
        # Lưu dưới dạng file đính kèm
        buf = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode())
        buf.seek(0)
        file = discord.File(buf, filename="data.json")
        content_short = "DATA_FILE:see_attachment"

    msg_id = await _find_data_message()
    try:
        if msg_id:
            msg = await ch.fetch_message(msg_id)
            if len(content) > 1990:
                await msg.delete()
                sent = await ch.send(content_short, file=file)
            else:
                await msg.edit(content=content)
                return
        else:
            if len(content) > 1990:
                sent = await ch.send(content_short, file=file)
            else:
                sent = await ch.send(content)
        _DATA_MSG_ID = sent.id
    except Exception as e:
        print(f"[DATA] ❌ Lỗi ghi data: {e}")

# ── Wrapper đồng bộ (để không phải sửa toàn bộ code gọi load_data/save_data) ──
# Các hàm đồng bộ sẽ dùng cache in-memory; việc sync lên Discord do _flush_task xử lý.

_flush_lock = asyncio.Lock()

def load_data() -> dict:
    """Đọc từ cache (nếu chưa có → trả default, sẽ được sync khi bot ready)."""
    if _data_cache is not None:
        return _data_cache
    return _default_data()

def save_data(data: dict):
    """Lưu vào cache và lên lịch flush lên Discord."""
    global _data_cache, _cache_dirty
    _data_cache = data
    _cache_dirty = True
    # Tạo task flush bất đồng bộ nếu bot đã chạy
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_flush_to_discord())
    except Exception:
        pass

async def _flush_to_discord():
    """Đẩy cache lên Discord (gọi tự động sau save_data)."""
    global _cache_dirty
    async with _flush_lock:
        if not _cache_dirty:
            return
        _cache_dirty = False
        if _data_cache is not None:
            await save_data_async(_data_cache)

async def init_data_cache():
    """Gọi khi bot ready — tải data từ Discord lần đầu."""
    global _data_cache
    _data_cache = None   # xoá cache cũ để buộc đọc lại
    data = await load_data_async()
    print(f"[DATA] ✅ Đã tải data từ Discord — ticket#{data.get('ticket', 0):03d}")

def get_ticket_number():
    """Lấy số ticket tiếp theo từ data.json (fallback khi chưa sync được channel)."""
    data = load_data()
    data["ticket"] = data.get("ticket", 0) + 1
    save_data(data)
    return f"{data['ticket']:03d}"

async def read_counter_from_channel() -> int:
    """Đọc số ticket hiện tại từ kênh counter trên Discord."""
    if not get_cfg_counter_channel():
        return 0
    channel = bot.get_channel(get_cfg_counter_channel())
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
    if not get_cfg_counter_channel():
        return
    channel = bot.get_channel(get_cfg_counter_channel())
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

        log = bot.get_channel(get_cfg_log_channel())
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
        support_role = guild.get_role(get_cfg_support_role())
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True
            )

        category = discord.utils.get(guild.categories, id=get_cfg_category())
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
            f"<@&{get_cfg_support_role()}> | {interaction.user.mention}",
            embed=embed,
            view=TicketButtons()
        )

        await interaction.followup.send(
            f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True
        )

        # Auto-ping chạy nền, không block

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
            support_role = guild.get_role(get_cfg_support_role())
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True
                )

            category = discord.utils.get(guild.categories, id=get_cfg_category())
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
                f"<@&{get_cfg_support_role()}> | {interaction.user.mention}",
                embed=embed,
                view=TicketButtons()
            )

            await interaction.response.send_message(
                f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True
            )

            # Auto-ping chạy nền, không block

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
        support_role = interaction.guild.get_role(get_cfg_support_role())
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
        support_role = interaction.guild.get_role(get_cfg_support_role())
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
        support_role = interaction.guild.get_role(get_cfg_support_role())
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
        support_role = interaction.guild.get_role(get_cfg_support_role())
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
        support_role = interaction.guild.get_role(get_cfg_support_role())
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

    log = bot_instance.get_channel(get_cfg_log_channel())
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


HELP_CATEGORIES = {
    "chung": {
        "title": "🌐  Lệnh Chung",
        "fields": [
            ("`.ping`", "Kiểm tra độ trễ bot"),
            ("`.price`", "Xem bảng giá"),
            ("`.qr`", "Gửi mã QR thanh toán"),
            ("`.botinfo` / `.bi`", "Thông tin bot"),
            ("`.serverinfo` / `.si`", "Thông tin server"),
            ("`.userinfo [@user]` / `.ui`", "Thông tin thành viên"),
        ]
    },
    "ticket": {
        "title": "🎫  Lệnh Ticket",
        "fields": [
            ("`.panel`", "Gửi panel ticket *(admin)*"),
            ("`.close`", "Đóng ticket hiện tại *(admin/staff)*"),
            ("`.addnote <nội dung>`", "Thêm ghi chú nội bộ *(admin/staff)*"),
            ("`.stock`", "Xem stock hiện tại"),
            ("`.stock <item> <sl>`", "Cập nhật stock *(admin/staff)*"),
            ("`.ratings`", "Xem thống kê đánh giá *(admin)*"),
        ]
    },
    "mod": {
        "title": "🛡️  Lệnh Kiểm Duyệt",
        "fields": [
            ("`.clear <số>`", "Xoá tin nhắn (tối đa 100) *(admin)*"),
            ("`.addrole @user @role`", "Thêm role cho thành viên *(admin)*"),
            ("`.removerole @user @role`", "Xoá role của thành viên *(admin)*"),
            ("`.createchannel <tên>`", "Tạo kênh text mới *(admin)*"),
            ("`.deletechannel [#kênh]`", "Xoá kênh *(admin)*"),
        ]
    },
    "giveaway": {
        "title": "🎉  Lệnh Giveaway",
        "fields": [
            ("`.giveaway <time> <số> <thưởng>`", "Tạo giveaway — ví dụ: `.giveaway 1h 2 100m` *(admin)*"),
            ("`.gend <message_id>`", "Kết thúc giveaway sớm *(admin)*"),
            ("`.greroll <message_id>`", "Quay lại người thắng *(admin)*"),
            ("/giveaway", "Tạo giveaway qua modal (slash command) *(admin)*"),
        ]
    },
    "balance": {
        "title": "💰  Hệ Thống Số Dư",
        "fields": [
            ("+ <số tiền>", "Nạp tiền vào (tự trừ phí 5%) — dùng trong kênh balance"),
            ("- <số tiền>", "Chi tiền ra (số dư có thể âm) — dùng trong kênh balance"),
            ("`.balance` / `.bal`", "Xem số dư & thống kê giao dịch"),
            ("`.balset <số>`", "Đặt số dư về giá trị bất kỳ *(admin)*"),
            ("`.balreset`", "Reset số dư về 0 *(admin)*"),
        ]
    },
    "caidat": {
        "title": "⚙️  Lệnh Cài Đặt",
        "fields": [
            ("`.setpanel #kênh`", "Chỉ định kênh panel *(admin)*"),
            ("`.settings` / `.st`", "Cấu hình & đổi ID kênh, QR, balance *(admin)*"),
            ("`.orderbase`", "Gửi bảng giá Order Base *(admin)*"),
        ]
    },
}

@bot.command(name="help")
async def help_cmd(ctx, category: str = None):
    if category is None:
        # Tổng quan
        embed = discord.Embed(
            title="📋  Trợ Lý TuyTam Store",
            description=(
                "Dùng `.help <mục>` để xem chi tiết từng nhóm lệnh.\n"
                "Slash commands `/` cũng khả dụng cho hầu hết lệnh!"
            ),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        cats = [
            ("🌐 `.help chung`",    "Ping, thông tin bot/server/user, giá, QR"),
            ("🎫 `.help ticket`",   "Tạo ticket, đóng ticket, stock, rating"),
            ("🛡️ `.help mod`",      "Xoá tin nhắn, role, kênh"),
            ("🎉 `.help giveaway`", "Tạo & quản lý giveaway"),
            ("💰 `.help balance`",  "Hệ thống số dư, nạp/chi tiền"),
            ("⚙️ `.help caidat`",   "Cài đặt panel, kênh, QR, balance"),
        ]
        for name, desc in cats:
            embed.add_field(name=name, value=desc, inline=False)
        embed.set_footer(text="TuyTam Store  •  Prefix: .  |  Slash: /")
        return await ctx.reply(embed=embed)

    cat = category.lower()
    if cat not in HELP_CATEGORIES:
        keys = " / ".join(f"`{k}`" for k in HELP_CATEGORIES)
        return await ctx.reply(f"❌ Mục không tồn tại! Chọn: {keys}")

    data = HELP_CATEGORIES[cat]
    embed = discord.Embed(
        title=data["title"],
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    for cmd, desc in data["fields"]:
        embed.add_field(name=cmd, value=desc, inline=False)
    embed.set_footer(text="TuyTam Store  •  Dùng .help để xem tất cả mục")
    await ctx.reply(embed=embed)


# ================= MODERATION =================
@bot.command(name="clear", aliases=["purge"])
async def clear_cmd(ctx, amount: int = 10):
    support_role = ctx.guild.get_role(get_cfg_support_role())
    has_role = support_role in ctx.author.roles if support_role else False
    if not (ctx.author.id in ADMIN_IDS or has_role):
        return await ctx.reply("❌ Bạn không có quyền.", delete_after=3)
    if not 1 <= amount <= 100:
        return await ctx.reply("❌ Số tin cần xoá phải từ 1–100.", delete_after=3)
    try:
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.send(f"🗑️ Đã xoá **{len(deleted)}** tin nhắn.")
        await asyncio.sleep(3)
        await msg.delete()
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Messages`.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")


@bot.command(name="addrole")
async def addrole_cmd(ctx, member: discord.Member = None, role: discord.Role = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not member or not role:
        return await ctx.reply("❌ Dùng: `.addrole @user @role`")
    try:
        await member.add_roles(role)
        embed = discord.Embed(
            title="✅  Đã Thêm Role",
            description=f"Đã thêm {role.mention} cho {member.mention}",
            color=0x57F287, timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Bởi {ctx.author}")
        await ctx.reply(embed=embed)
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Roles` hoặc role cao hơn bot.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")


@bot.command(name="removerole")
async def removerole_cmd(ctx, member: discord.Member = None, role: discord.Role = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not member or not role:
        return await ctx.reply("❌ Dùng: `.removerole @user @role`")
    try:
        await member.remove_roles(role)
        embed = discord.Embed(
            title="✅  Đã Gỡ Role",
            description=f"Đã gỡ {role.mention} khỏi {member.mention}",
            color=0xED4245, timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Bởi {ctx.author}")
        await ctx.reply(embed=embed)
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Roles` hoặc role cao hơn bot.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")


@bot.command(name="createchannel", aliases=["cc"])
async def createchannel_cmd(ctx, name: str = None, ch_type: str = "text"):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not name:
        return await ctx.reply("❌ Dùng: `.createchannel <tên> [text/voice]`")
    try:
        name = name.lower().replace(" ", "-")
        if ch_type.lower() == "voice":
            channel = await ctx.guild.create_voice_channel(name, category=ctx.channel.category)
            icon = "🔊"
        else:
            channel = await ctx.guild.create_text_channel(name, category=ctx.channel.category)
            icon = "💬"
        embed = discord.Embed(
            title="✅  Đã Tạo Kênh",
            description=f"{icon} {channel.mention} đã được tạo!",
            color=0x57F287, timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Tạo bởi {ctx.author}")
        await ctx.reply(embed=embed)
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Channels`.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")


@bot.command(name="deletechannel", aliases=["dc"])
async def deletechannel_cmd(ctx, channel: discord.TextChannel = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    target = channel or ctx.channel
    try:
        name = target.name
        await target.delete()
        if target != ctx.channel:
            embed = discord.Embed(
                title="✅  Đã Xoá Kênh",
                description=f"Kênh `#{name}` đã bị xoá.",
                color=0xED4245, timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Xoá bởi {ctx.author}")
            await ctx.reply(embed=embed)
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Channels`.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")


# ================= GIVEAWAY =================
import re as _re
import random

active_giveaways: dict[int, dict] = {}

def parse_time(time_str: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = _re.fullmatch(r"(\d+)([smhd])", time_str.lower())
    if not match:
        return 0
    return int(match.group(1)) * units[match.group(2)]


async def end_giveaway(message_id: int, channel: discord.TextChannel, winners_count: int, prize: str, host_id: int):
    try:
        msg = await channel.fetch_message(message_id)
    except:
        return
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    if not reaction:
        return await channel.send("❌ Không có ai tham gia giveaway!")
    entries = [u async for u in reaction.users() if not u.bot]
    if not entries:
        return await channel.send("❌ Không có người tham gia hợp lệ!")
    count = min(winners_count, len(entries))
    winners = random.sample(entries, count)
    winner_mentions = ", ".join(w.mention for w in winners)
    embed = discord.Embed(
        title="🎉  Giveaway Kết Thúc!",
        description=f"**Phần thưởng:** {prize}\n**🏆 Winner:** {winner_mentions}",
        color=0xF1C40F, timestamp=datetime.now(timezone.utc)
    )
    host = channel.guild.get_member(host_id)
    embed.set_footer(text=f"Host: {host.display_name if host else host_id}")
    await msg.edit(embed=embed)
    await channel.send(f"🎊 Chúc mừng {winner_mentions}! Bạn đã thắng **{prize}**!")
    if message_id in active_giveaways:
        active_giveaways[message_id]["ended"] = True
        active_giveaways[message_id]["winner_ids"] = [w.id for w in winners]


@bot.command(name="gstart")
async def gstart_cmd(ctx, time_str: str = None, winners: str = None, *, prize: str = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not time_str or not winners or not prize:
        return await ctx.reply("❌ Dùng: `.gstart <time> <winners> <prize>`\nVí dụ: `.gstart 10m 1 100m ingame`")
    duration = parse_time(time_str)
    if duration <= 0:
        return await ctx.reply("❌ Thời gian không hợp lệ! Dùng: `30s`, `10m`, `1h`, `1d`")
    try:
        w_count = max(1, int(winners))
    except ValueError:
        return await ctx.reply("❌ Số người thắng phải là số!")
    ends_at = int(datetime.now(timezone.utc).timestamp()) + duration
    embed = discord.Embed(
        title="🎉  GIVEAWAY",
        description=(
            f"**Phần thưởng:** {prize}\n\n"
            f"React 🎉 để tham gia!\n"
            f"⏰ Kết thúc: <t:{ends_at}:R>\n"
            f"🏆 Số người thắng: **{w_count}**"
        ),
        color=0xF1C40F,
        timestamp=datetime.fromtimestamp(ends_at, tz=timezone.utc)
    )
    embed.set_footer(text=f"Host: {ctx.author.display_name}  •  Kết thúc lúc")
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")
    try:
        await ctx.message.delete()
    except:
        pass
    active_giveaways[msg.id] = {
        "channel_id": ctx.channel.id, "winners": w_count,
        "prize": prize, "host_id": ctx.author.id,
        "ends_at": ends_at, "ended": False
    }

    async def _countdown():
        await asyncio.sleep(duration)
        if not active_giveaways.get(msg.id, {}).get("ended"):
            await end_giveaway(msg.id, ctx.channel, w_count, prize, ctx.author.id)
    asyncio.create_task(_countdown())


@bot.command(name="greroll")
async def greroll_cmd(ctx, message_id: int = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not message_id:
        return await ctx.reply("❌ Dùng: `.greroll <message_id>`")
    try:
        msg = await ctx.channel.fetch_message(message_id)
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        if not reaction:
            return await ctx.reply("❌ Không tìm thấy reaction 🎉!")
        entries = [u async for u in reaction.users() if not u.bot]
        if not entries:
            return await ctx.reply("❌ Không có người tham gia hợp lệ!")
        winner = random.choice(entries)
        prize = active_giveaways.get(message_id, {}).get("prize", "phần thưởng")
        await ctx.send(f"🎊 **Reroll!** Chúc mừng {winner.mention}! Bạn đã thắng **{prize}**!")
    except discord.NotFound:
        await ctx.reply("❌ Không tìm thấy tin nhắn!")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")


@bot.command(name="gend")
async def gend_cmd(ctx, message_id: int = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not message_id:
        return await ctx.reply("❌ Dùng: `.gend <message_id>`")
    gw = active_giveaways.get(message_id)
    if not gw:
        return await ctx.reply("❌ Không tìm thấy giveaway đang hoạt động!")
    if gw.get("ended"):
        return await ctx.reply("❌ Giveaway này đã kết thúc rồi!")
    await end_giveaway(message_id, ctx.channel, gw["winners"], gw["prize"], gw["host_id"])
    await ctx.reply("✅ Đã kết thúc giveaway sớm!")


# ================= INFO COMMANDS =================
@bot.command(name="botinfo")
async def botinfo_cmd(ctx):
    import platform
    embed = discord.Embed(
        title=f"🤖  {bot.user.name}",
        color=0x5865F2, timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="👤  Tên",         value=str(bot.user),                                        inline=True)
    embed.add_field(name="🆔  ID",          value=str(bot.user.id),                                     inline=True)
    embed.add_field(name="🏓  Latency",     value=f"{round(bot.latency*1000)}ms",                       inline=True)
    embed.add_field(name="🌐  Servers",     value=str(len(bot.guilds)),                                 inline=True)
    embed.add_field(name="👥  Users",       value=str(sum(g.member_count or 0 for g in bot.guilds)),    inline=True)
    embed.add_field(name="🐍  Python",      value=platform.python_version(),                            inline=True)
    embed.add_field(name="📚  discord.py",  value=discord.__version__,                                  inline=True)
    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await ctx.reply(embed=embed)


@bot.command(name="serverinfo", aliases=["si"])
async def serverinfo_cmd(ctx):
    g = ctx.guild
    embed = discord.Embed(
        title=f"🌐  {g.name}",
        color=0x5865F2, timestamp=datetime.now(timezone.utc)
    )
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="🆔  ID",              value=str(g.id),                                                inline=True)
    embed.add_field(name="👑  Owner",            value=g.owner.mention if g.owner else "N/A",                   inline=True)
    embed.add_field(name="👥  Members",          value=str(g.member_count),                                     inline=True)
    embed.add_field(name="💬  Text Channels",    value=str(len(g.text_channels)),                               inline=True)
    embed.add_field(name="🔊  Voice Channels",   value=str(len(g.voice_channels)),                              inline=True)
    embed.add_field(name="🎭  Roles",            value=str(len(g.roles)),                                       inline=True)
    embed.add_field(name="😀  Emojis",           value=str(len(g.emojis)),                                      inline=True)
    embed.add_field(name="🚀  Boost",            value=f"Level {g.premium_tier} ({g.premium_subscription_count} boosts)", inline=True)
    embed.add_field(name="📅  Ngày tạo",         value=f"<t:{int(g.created_at.timestamp())}:D>",                inline=True)
    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await ctx.reply(embed=embed)


@bot.command(name="userinfo", aliases=["ui"])
async def userinfo_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in reversed(member.roles) if r != ctx.guild.default_role]
    roles_str = ", ".join(roles[:10]) + ("..." if len(roles) > 10 else "") if roles else "Không có"
    embed = discord.Embed(
        title=f"👤  {member.display_name}",
        color=member.color if member.color.value else 0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🏷️  Tag",             value=str(member),                                              inline=True)
    embed.add_field(name="🆔  ID",               value=str(member.id),                                          inline=True)
    embed.add_field(name="🤖  Bot",              value="✅" if member.bot else "❌",                             inline=True)
    embed.add_field(name="📅  Tạo tài khoản",    value=f"<t:{int(member.created_at.timestamp())}:D>",           inline=True)
    embed.add_field(name="📥  Vào server",        value=f"<t:{int(member.joined_at.timestamp())}:D>" if member.joined_at else "N/A", inline=True)
    embed.add_field(name="🎭  Roles",             value=roles_str,                                               inline=False)
    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await ctx.reply(embed=embed)


@bot.command(name="stock")
async def stock_cmd(ctx, item: str = None, *, amount: str = None):
    support_role = ctx.guild.get_role(get_cfg_support_role())
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


# ================= SETTINGS MODALS =================
class ChangeChannelModal(Modal):
    def __init__(self, field_key: str, field_label: str):
        super().__init__(title=f"🔧 Đổi {field_label}")
        self.field_key = field_key
        self.field_label = field_label
        self.id_input = TextInput(
            label=f"ID {field_label}",
            placeholder="Dán ID vào đây (chuột phải → Copy ID)",
            min_length=15, max_length=20
        )
        self.add_item(self.id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_id = int(self.id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

        save_cfg(self.field_key, new_id)
        embed = discord.Embed(
            title="✅  Đã Cập Nhật",
            description=f"**{self.field_label}** → `{new_id}`",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Cập nhật bởi {interaction.user}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ================= SETTINGS VIEW =================
class SettingsView(View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="📋 Log Channel", style=discord.ButtonStyle.grey, row=0)
    async def change_log(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_log_channel", "Log Channel"))

    @discord.ui.button(label="📂 Ticket Category", style=discord.ButtonStyle.grey, row=0)
    async def change_category(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_ticket_category", "Ticket Category"))

    @discord.ui.button(label="🛡️ Support Role", style=discord.ButtonStyle.grey, row=0)
    async def change_role(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_support_role", "Support Role ID"))

    @discord.ui.button(label="🔢 Counter Channel", style=discord.ButtonStyle.grey, row=1)
    async def change_counter(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_counter_channel", "Counter Channel"))

    @discord.ui.button(label="📱 Đổi QR", style=discord.ButtonStyle.blurple, row=1)
    async def change_qr(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(SetQRModal())

    @discord.ui.button(label="👁️ Xem QR", style=discord.ButtonStyle.grey, row=1)
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

    @discord.ui.button(label="💰 Balance Channel", style=discord.ButtonStyle.green, row=2)
    async def change_balance(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_balance_channel", "Balance Channel"))

    @discord.ui.button(label="📌 Panel Channel", style=discord.ButtonStyle.green, row=2)
    async def change_panel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("panel_channel_id", "Panel Channel"))


@bot.command(name="settings", aliases=["st"])
async def settings(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return

    panel_channel_id = get_panel_channel_id()
    if panel_channel_id:
        ch = ctx.guild.get_channel(panel_channel_id)
        panel_value = ch.mention if ch else f"⚠️ Kênh đã bị xoá (ID: `{panel_channel_id}`)"
    else:
        panel_value = "Chưa cài — dùng `.setpanel #kênh`"

    log_id      = get_cfg_log_channel()
    cat_id      = get_cfg_category()
    role_id     = get_cfg_support_role()
    counter_id  = get_cfg_counter_channel()
    balance_id  = get_cfg_balance_channel()
    qr_path     = get_qr_path()

    log_val     = f"<#{log_id}>" if log_id else "❌ Chưa cài"
    cat_val     = f"<#{cat_id}>" if cat_id else "❌ Chưa cài"
    role_val    = f"<@&{role_id}>" if role_id else "❌ Chưa cài"
    counter_val = f"<#{counter_id}>" if counter_id else "❌ Chưa cài"
    balance_val = f"<#{balance_id}>" if balance_id else "❌ Chưa cài — nhấn **💰 Balance Channel**"
    qr_val      = "✅ Đã có" if qr_path and os.path.exists(qr_path) else "❌ Chưa có"

    embed = discord.Embed(
        title="⚙️  Cấu Hình Hiện Tại",
        description="Nhấn các nút bên dưới để chỉnh sửa từng mục.",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📌  Panel Channel",   value=panel_value,  inline=False)
    embed.add_field(name="📋  Log Channel",      value=log_val,      inline=True)
    embed.add_field(name="📂  Ticket Category",  value=cat_val,      inline=True)
    embed.add_field(name="🛡️  Support Role",     value=role_val,     inline=True)
    embed.add_field(name="🔢  Counter Channel",  value=counter_val,  inline=True)
    embed.add_field(name="💰  Balance Channel",  value=balance_val,  inline=True)
    embed.add_field(name="📱  Mã QR",            value=qr_val,       inline=True)
    embed.set_footer(text="TuyTam Store  •  Dùng .st hoặc .settings")
    await ctx.reply(embed=embed, view=SettingsView())


@bot.command()
async def close(ctx):
    support_role = ctx.guild.get_role(get_cfg_support_role())
    has_role = support_role in ctx.author.roles if support_role else False
    if not (ctx.author.id in ADMIN_IDS or has_role):
        return await ctx.reply("❌ Bạn không có quyền.")
    if not (ctx.channel.topic and "|" in ctx.channel.topic):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    await _close_ticket(ctx.channel, bot)


@bot.command(name="addnote")
async def addnote_cmd(ctx, *, note: str = None):
    support_role = ctx.guild.get_role(get_cfg_support_role())
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

    note_input = TextInput(
        label="Xác nhận",
        placeholder="Nhấn Gửi, rồi đính kèm ảnh QR trong 60 giây",
        required=False,
        max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "📎 Hãy **gửi ảnh QR** (đính kèm file) vào kênh này trong vòng **60 giây**.",
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
                return await interaction.followup.send("❌ File không phải ảnh! Hãy gửi file .png / .jpg.", ephemeral=True)

            # Lưu trực tiếp từ attachment — tránh lỗi 403 khi dùng URL CDN Discord
            qr_path = QR_FILE
            await attachment.save(qr_path)
            save_qr_path(qr_path)

            try:
                await msg.delete()
            except Exception:
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



# ================= SLASH COMMANDS =================

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.id in ADMIN_IDS or interaction.user.guild_permissions.administrator

def is_staff_or_admin(interaction: discord.Interaction) -> bool:
    role = interaction.guild.get_role(get_cfg_support_role())
    has_role = role in interaction.user.roles if role else False
    return interaction.user.id in ADMIN_IDS or has_role

# ── Giveaway Modal ──
# ── Button tham gia giveaway (slash /giveaway) ──
class GiveawayView(View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="🎉 Tham gia", style=discord.ButtonStyle.primary, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: Button):
        gw = active_giveaways.get(self.message_id)
        if not gw:
            return await interaction.response.send_message("❌ Giveaway này không còn hoạt động.", ephemeral=True)
        if gw.get("ended"):
            return await interaction.response.send_message("❌ Giveaway đã kết thúc rồi!", ephemeral=True)

        uid = interaction.user.id
        if uid in gw["entries"]:
            gw["entries"].discard(uid)
            await interaction.response.send_message("↩️ Bạn đã **rút khỏi** giveaway.", ephemeral=True)
        else:
            gw["entries"].add(uid)
            await interaction.response.send_message("✅ Bạn đã **tham gia** giveaway!", ephemeral=True)

        # Cập nhật số người tham gia trên embed
        try:
            msg = await interaction.channel.fetch_message(self.message_id)
            embed = msg.embeds[0]
            for i, field in enumerate(embed.fields):
                if "Người tham gia" in field.name:
                    embed.set_field_at(i, name=field.name, value=f"**{len(gw['entries'])}** người", inline=field.inline)
                    break
            await msg.edit(embed=embed)
        except Exception:
            pass


async def giveaway_timer(channel_id: int, message_id: int, winners_count: int, seconds: int):
    """Đếm ngược và tự động kết thúc giveaway."""
    await asyncio.sleep(seconds)
    gw = active_giveaways.get(message_id)
    if not gw or gw.get("ended"):
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        return

    gw["ended"] = True
    entries = list(gw.get("entries", set()))

    try:
        msg = await channel.fetch_message(message_id)
    except Exception:
        return

    if not entries:
        embed = discord.Embed(
            title="🎉  Giveaway Kết Thúc",
            description="❌ Không có ai tham gia giveaway này.",
            color=0x99AAB5,
            timestamp=datetime.now(timezone.utc)
        )
        await msg.edit(embed=embed, view=None)
        await channel.send("❌ Giveaway kết thúc nhưng không có người tham gia!")
        return

    count = min(winners_count, len(entries))
    winner_ids = random.sample(entries, count)
    winner_mentions = ", ".join(f"<@{uid}>" for uid in winner_ids)

    embed = discord.Embed(
        title="🎉  Giveaway Kết Thúc!",
        description=f"**Phần thưởng:** {gw['prize']}\n**🏆 Winner:** {winner_mentions}",
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    host = channel.guild.get_member(gw["host"])
    embed.set_footer(text=f"Host: {host.display_name if host else gw['host']}")
    await msg.edit(embed=embed, view=None)
    await channel.send(f"🎊 Chúc mừng {winner_mentions}! Bạn đã thắng **{gw['prize']}**!")

    gw["winner_ids"] = winner_ids


class GiveawayModal(discord.ui.Modal, title="🎉 Tạo Giveaway"):
    duration = discord.ui.TextInput(
        label="Thời gian",
        placeholder="Ví dụ: 30s / 10m / 1h / 2d",
        min_length=2, max_length=10
    )
    winners_count = discord.ui.TextInput(
        label="Số người trúng thưởng",
        placeholder="Ví dụ: 1",
        min_length=1, max_length=2
    )
    prize = discord.ui.TextInput(
        label="Phần thưởng",
        placeholder="Ví dụ: 100m ingame, Elytra...",
        min_length=1, max_length=200
    )
    description = discord.ui.TextInput(
        label="Mô tả (tuỳ chọn)",
        placeholder="Điều kiện tham gia, ghi chú thêm...",
        style=discord.TextStyle.paragraph,
        required=False, max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Parse thời gian
        dur = self.duration.value.strip()
        unit = dur[-1].lower()
        try:
            val = int(dur[:-1])
        except:
            return await interaction.response.send_message("❌ Thời gian không hợp lệ! Dùng: `30s`, `10m`, `1h`, `2d`", ephemeral=True)
        seconds = {"s": val, "m": val*60, "h": val*3600, "d": val*86400}.get(unit)
        if not seconds:
            return await interaction.response.send_message("❌ Đơn vị thời gian không hợp lệ! Dùng: `s`, `m`, `h`, `d`", ephemeral=True)

        # Parse số người thắng
        try:
            w_count = int(self.winners_count.value.strip())
            if w_count < 1: raise ValueError
        except:
            return await interaction.response.send_message("❌ Số người trúng thưởng phải là số nguyên dương!", ephemeral=True)

        end_time = datetime.now(timezone.utc).timestamp() + seconds

        embed = discord.Embed(
            title="🎉  GIVEAWAY!",
            description=self.description.value or "Nhấn nút **🎉 Tham gia** để tham dự!",
            color=0xF1C40F,
            timestamp=datetime.fromtimestamp(end_time, tz=timezone.utc)
        )
        embed.add_field(name="🏆  Phần thưởng",    value=self.prize.value,                inline=False)
        embed.add_field(name="🎊  Số người thắng", value=f"**{w_count}** người",           inline=True)
        embed.add_field(name="👥  Người tham gia", value="**0** người",                    inline=True)
        embed.add_field(name="⏰  Kết thúc",       value=f"<t:{int(end_time)}:R>",         inline=True)
        embed.add_field(name="🎤  Host",           value=interaction.user.mention,         inline=True)
        embed.set_footer(text="TuyTam Store  •  Kết thúc lúc")

        await interaction.response.send_message("✅ Đang tạo giveaway...", ephemeral=True)
        msg = await interaction.channel.send(embed=embed, view=GiveawayView(0))
        view = GiveawayView(msg.id)
        await msg.edit(view=view)

        active_giveaways[msg.id] = {
            "prize": self.prize.value,
            "winners": w_count,
            "entries": set(),
            "channel_id": interaction.channel.id,
            "end_time": end_time,
            "host": interaction.user.id
        }
        asyncio.create_task(giveaway_timer(interaction.channel.id, msg.id, w_count, seconds))


@tree.command(name="giveaway", description="Tạo giveaway mới")
async def slash_giveaway(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Chỉ admin mới được tạo giveaway.", ephemeral=True)
    await interaction.response.send_modal(GiveawayModal())


@tree.command(name="gend", description="Kết thúc giveaway sớm")
@app_commands.describe(message_id="ID tin nhắn giveaway")
async def slash_gend(interaction: discord.Interaction, message_id: str):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
    try:
        mid = int(message_id)
    except:
        return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)
    gw = active_giveaways.get(mid)
    if not gw:
        return await interaction.response.send_message("❌ Không tìm thấy giveaway đang chạy.", ephemeral=True)
    await interaction.response.send_message("✅ Đang kết thúc giveaway...", ephemeral=True)
    channel = bot.get_channel(gw["channel_id"])
    if channel:
        await end_giveaway(mid, channel, gw["winners"], gw.get("prize", "phần thưởng"), gw.get("host", 0))


@tree.command(name="clear", description="Xoá tin nhắn trong kênh")
@app_commands.describe(amount="Số tin nhắn cần xoá (1-500)")
async def slash_clear(interaction: discord.Interaction, amount: int):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
    if amount < 1 or amount > 500:
        return await interaction.response.send_message("❌ Số lượng phải từ 1 đến 500.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🗑️ Đã xoá **{len(deleted)}** tin nhắn.", ephemeral=True)


@tree.command(name="addrole", description="Thêm role cho thành viên")
@app_commands.describe(member="Thành viên", role="Role cần thêm")
async def slash_addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
    if role >= interaction.guild.me.top_role:
        return await interaction.response.send_message("❌ Role này cao hơn role của bot.", ephemeral=True)
    await member.add_roles(role, reason=f"Bởi {interaction.user}")
    embed = discord.Embed(title="✅ Đã Thêm Role", color=0x57F287)
    embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
    embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="removerole", description="Xoá role của thành viên")
@app_commands.describe(member="Thành viên", role="Role cần xoá")
async def slash_removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
    if role >= interaction.guild.me.top_role:
        return await interaction.response.send_message("❌ Role này cao hơn role của bot.", ephemeral=True)
    await member.remove_roles(role, reason=f"Bởi {interaction.user}")
    embed = discord.Embed(title="✅ Đã Xoá Role", color=0xFEE75C)
    embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
    embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="createchannel", description="Tạo kênh text mới")
@app_commands.describe(name="Tên kênh", category="Category (tuỳ chọn)")
async def slash_createchannel(interaction: discord.Interaction, name: str, category: discord.CategoryChannel = None):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
    name = name.lower().replace(" ", "-")
    ch = await interaction.guild.create_text_channel(name, category=category, reason=f"Bởi {interaction.user}")
    await interaction.response.send_message(f"✅ Đã tạo kênh {ch.mention}!", ephemeral=True)


@tree.command(name="deletechannel", description="Xoá kênh")
@app_commands.describe(channel="Kênh cần xoá (để trống = kênh hiện tại)")
async def slash_deletechannel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
    target = channel or interaction.channel
    name = target.name
    await interaction.response.send_message(f"✅ Đang xoá kênh `#{name}`...", ephemeral=True)
    await target.delete(reason=f"Bởi {interaction.user}")


@tree.command(name="userinfo", description="Xem thông tin thành viên")
@app_commands.describe(member="Thành viên (để trống = bản thân)")
async def slash_userinfo(interaction: discord.Interaction, member: discord.Member = None):
    m = member or interaction.user
    roles = [r.mention for r in m.roles if r.name != "@everyone"]
    roles_str = " ".join(roles[-10:]) if roles else "Không có"
    embed = discord.Embed(title=f"👤  {m}", color=m.color if m.color.value else 0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="🆔 ID",         value=f"`{m.id}`",                                      inline=True)
    embed.add_field(name="🤖 Bot",        value="✅" if m.bot else "❌",                            inline=True)
    embed.add_field(name="📅 Tạo acc",    value=f"<t:{int(m.created_at.timestamp())}:D>",         inline=True)
    embed.add_field(name="📥 Vào server", value=f"<t:{int(m.joined_at.timestamp())}:D>" if m.joined_at else "N/A", inline=True)
    embed.add_field(name="🏷️ Roles",      value=roles_str,                                         inline=False)
    embed.set_thumbnail(url=m.display_avatar.url)
    embed.set_footer(text=f"TuyTam Store  •  Yêu cầu bởi {interaction.user}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="serverinfo", description="Xem thông tin server")
async def slash_serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    bots   = sum(1 for m in g.members if m.bot)
    humans = g.member_count - bots
    embed = discord.Embed(title=f"🏠  {g.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="🆔 ID",        value=f"`{g.id}`",                                  inline=True)
    embed.add_field(name="👑 Owner",      value=g.owner.mention if g.owner else "N/A",        inline=True)
    embed.add_field(name="📅 Tạo lúc",   value=f"<t:{int(g.created_at.timestamp())}:D>",     inline=True)
    embed.add_field(name="👥 Thành viên", value=f"👤 {humans}  🤖 {bots}",                    inline=True)
    embed.add_field(name="💬 Kênh",       value=f"📝 {len(g.text_channels)}  🔊 {len(g.voice_channels)}", inline=True)
    embed.add_field(name="💎 Boost",      value=f"Lv **{g.premium_tier}** — **{g.premium_subscription_count}** boost", inline=True)
    if g.icon: embed.set_thumbnail(url=g.icon.url)
    embed.set_footer(text=f"TuyTam Store  •  {interaction.user}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="botinfo", description="Xem thông tin bot")
async def slash_botinfo(interaction: discord.Interaction):
    import platform
    embed = discord.Embed(title=f"🤖  {bot.user.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="🆔 ID",       value=f"`{bot.user.id}`",                                          inline=True)
    embed.add_field(name="🌐 Servers",  value=f"**{len(bot.guilds)}**",                                    inline=True)
    embed.add_field(name="🏓 Latency",  value=f"**{round(bot.latency*1000)}ms**",                          inline=True)
    embed.add_field(name="🐍 Python",   value=f"`{platform.python_version()}`",                            inline=True)
    embed.add_field(name="📦 discord.py", value=f"`{discord.__version__}`",                                inline=True)
    embed.add_field(name="📅 Tạo lúc",  value=f"<t:{int(bot.user.created_at.timestamp())}:D>",            inline=True)
    if bot.user.avatar: embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await interaction.response.send_message(embed=embed)


@tree.command(name="ping", description="Kiểm tra độ trễ bot")
async def slash_ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = 0x57F287 if latency < 100 else (0xFEE75C if latency < 200 else 0xED4245)
    status = "Tốt 🟢" if latency < 100 else ("Bình thường 🟡" if latency < 200 else "Chậm 🔴")
    embed = discord.Embed(title="🏓 Pong!", description=f"Độ trễ: **{latency}ms** — {status}", color=color)
    await interaction.response.send_message(embed=embed)


@tree.command(name="price", description="Xem bảng giá TuyTam Store")
async def slash_price(interaction: discord.Interaction):
    embed = build_price_embed(interaction.guild)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="qr", description="Gửi mã QR thanh toán")
async def slash_qr(interaction: discord.Interaction):
    qr_path = get_qr_path()
    if not qr_path or not os.path.exists(qr_path):
        return await interaction.response.send_message("❌ Chưa có QR! Admin cài qua `.settings`.", ephemeral=True)
    file = discord.File(qr_path, filename="qr.png")
    embed = discord.Embed(title="📱  Mã QR Thanh Toán", color=0x57F287, timestamp=datetime.now(timezone.utc))
    embed.description = "> 🏦 **MB Bank** — `0702557706` — HOVANBUT\n> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n> ⚠️ Ghi rõ: `[tên MC] mua [item]`"
    embed.set_image(url="attachment://qr.png")
    await interaction.response.send_message(embed=embed, file=file)


@tree.command(name="stock", description="Xem stock hiện tại")
async def slash_stock(interaction: discord.Interaction):
    current_stock = get_stock()
    lines = "\n".join(
        f"{PRICE_TABLE['sell'][k]['label']}  —  **{current_stock.get(k, 'Chưa cập nhật')}**"
        for k in PRICE_TABLE["sell"]
    )
    embed = discord.Embed(title="📦  Stock Hiện Tại", description=lines, color=0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await interaction.response.send_message(embed=embed)


# ================= BALANCE SYSTEM =================

def fmt_vnd(amount: int) -> str:
    """Format số tiền VND đẹp: 1.500.000đ hoặc -500.000đ"""
    if amount < 0:
        return f"-{abs(amount):,}đ".replace(",", ".")
    return f"{amount:,}đ".replace(",", ".")

async def handle_balance_message(message: discord.Message):
    """Xử lý tin nhắn + / - trong kênh balance."""
    content = message.content.strip()

    # Nhận dạng dạng "+ 1500000" hoặc "- 500000"
    if not (content.startswith("+") or content.startswith("-")):
        return
    op = content[0]
    raw_str = content[1:].strip().replace(".", "").replace(",", "").replace(" ", "")
    if not raw_str.isdigit():
        return

    raw = int(raw_str)
    if raw <= 0:
        return

    bal = get_balance_data()
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    if op == "+":
        fee    = round(raw * 0.05)
        net    = raw - fee
        bal["current"]   += net
        bal["total_in"]  += net
        bal["total_fee"] += fee
        bal["tx_count"]  += 1
        bal["history"].append({
            "type": "+", "raw": raw, "fee": fee, "net": net,
            "user": str(message.author), "time": now_str
        })
        # Giữ tối đa 100 giao dịch gần nhất
        bal["history"] = bal["history"][-100:]
        save_balance_data(bal)

        embed = discord.Embed(
            title="💰  Nạp Tiền",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="💵  Số tiền nhận",   value=f"**{fmt_vnd(raw)}**",  inline=True)
        embed.add_field(name="📉  Phí 5%",         value=f"- {fmt_vnd(fee)}",    inline=True)
        embed.add_field(name="✅  Thực nhận",       value=f"**{fmt_vnd(net)}**",  inline=True)
        embed.add_field(name="🏦  Số dư hiện tại", value=f"**{fmt_vnd(bal['current'])}**", inline=False)
        embed.set_footer(text=f"Bởi {message.author.display_name}  •  {now_str}")

    else:  # op == "-"
        bal["current"]    -= raw
        bal["total_out"]  += raw
        bal["tx_count"]   += 1
        bal["history"].append({
            "type": "-", "raw": raw, "fee": 0, "net": raw,
            "user": str(message.author), "time": now_str
        })
        bal["history"] = bal["history"][-100:]
        save_balance_data(bal)

        color = 0xED4245 if bal["current"] >= 0 else 0x9B59B6
        embed = discord.Embed(
            title="💸  Chi Tiền",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="💵  Số tiền chi",    value=f"**{fmt_vnd(raw)}**",           inline=True)
        embed.add_field(name="🏦  Số dư còn lại",  value=f"**{fmt_vnd(bal['current'])}**" + (" ⚠️" if bal["current"] < 0 else ""), inline=True)
        embed.set_footer(text=f"Bởi {message.author.display_name}  •  {now_str}")

    try:
        await message.delete()
    except:
        pass
    await message.channel.send(embed=embed)


@bot.command(name="balance", aliases=["bal"])
async def balance_cmd(ctx):
    bal = get_balance_data()
    ch_id = get_cfg_balance_channel()
    ch_mention = f"<#{ch_id}>" if ch_id else "Chưa cài"

    embed = discord.Embed(
        title="📊  Thống Kê Số Dư",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏦  Số dư hiện tại",  value=f"**{fmt_vnd(bal['current'])}**",   inline=False)
    embed.add_field(name="📥  Tổng nạp",        value=fmt_vnd(bal['total_in']),            inline=True)
    embed.add_field(name="📤  Tổng chi",        value=fmt_vnd(bal['total_out']),           inline=True)
    embed.add_field(name="📉  Tổng phí 5%",     value=fmt_vnd(bal['total_fee']),           inline=True)
    embed.add_field(name="🔢  Tổng giao dịch",  value=f"**{bal['tx_count']}** lần",       inline=True)
    embed.add_field(name="📌  Kênh balance",     value=ch_mention,                          inline=True)

    # 5 giao dịch gần nhất
    history = bal.get("history", [])
    if history:
        last5 = history[-5:][::-1]
        lines = []
        for tx in last5:
            icon = "📥" if tx["type"] == "+" else "📤"
            lines.append(f"{icon} **{fmt_vnd(tx['net'])}** — {tx['user']} — {tx['time']}")
        embed.add_field(name="🕐  5 giao dịch gần nhất", value="\n".join(lines), inline=False)

    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await ctx.reply(embed=embed)


@bot.command(name="balreset")
async def balreset_cmd(ctx):
    """Reset toàn bộ số dư (chỉ admin)."""
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới được reset.")
    data = load_data()
    data["balance"] = {
        "current": 0, "total_in": 0, "total_fee": 0,
        "total_out": 0, "tx_count": 0, "history": []
    }
    save_data(data)
    await ctx.reply("✅ Đã reset toàn bộ số dư về 0.")


@bot.command(name="balset")
async def balset_cmd(ctx, *, amount: str = None):
    """Đặt số dư về một giá trị cụ thể (admin). Dùng: .balset 1500000"""
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới được đặt số dư.")
    if amount is None:
        return await ctx.reply("❌ Dùng: `.balset <số tiền>`\nVí dụ: `.balset 1500000` hoặc `.balset -200000`")

    raw_str = amount.strip().replace(".", "").replace(",", "").replace(" ", "")
    negative = raw_str.startswith("-")
    raw_str = raw_str.lstrip("-+")
    if not raw_str.isdigit():
        return await ctx.reply("❌ Số tiền không hợp lệ!")

    new_balance = int(raw_str) * (-1 if negative else 1)
    bal = get_balance_data()
    old_balance = bal["current"]
    bal["current"] = new_balance
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    bal["history"].append({
        "type": "set", "raw": new_balance, "fee": 0, "net": new_balance,
        "user": str(ctx.author), "time": now_str
    })
    bal["history"] = bal["history"][-100:]
    save_balance_data(bal)

    color = 0x57F287 if new_balance >= 0 else 0x9B59B6
    embed = discord.Embed(
        title="⚙️  Đã Đặt Số Dư",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📊  Số dư cũ",    value=fmt_vnd(old_balance),  inline=True)
    embed.add_field(name="✅  Số dư mới",   value=f"**{fmt_vnd(new_balance)}**", inline=True)
    embed.set_footer(text=f"Đặt bởi {ctx.author}")
    await ctx.reply(embed=embed)


# ================= ON MESSAGE =================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)

    # Balance channel handler
    bal_ch = get_cfg_balance_channel()
    if bal_ch and message.channel.id == bal_ch:
        await handle_balance_message(message)


# ================= ERROR HANDLER =================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ Bạn không có quyền thực hiện lệnh này.")

# ================= ON READY =================
@bot.event
async def on_ready():
    # ── Bước 1: Tải data từ Discord channel trước mọi thứ ──
    await init_data_cache()

    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    for guild in bot.guilds:
        await sync_ticket_counter(guild)
    try:
        synced = await tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")
    print(f"✅ Bot online: {bot.user} | {len(bot.guilds)} server(s)")

bot.run(TOKEN)
