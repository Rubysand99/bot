# config.py — Hằng số, imports, helpers, DB, HELP_CATEGORIES
# Mỗi cog import: from config import bot, tree, ADMIN_IDS, ...

import os
import io
import json
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

# ╔══════════════════════════════════════════════════════════════════╗
# ║              RUDEUS BOT — TuyTam Store                          ║
# ║──────────────────────────────────────────────────────────────────║
# ║  Version : 3.3.5                                                ║
# ║  Updated : 2026-05-12                                           ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  CHANGELOG                                                       ║
# ║  v3.3.5 — Chỉ ADMIN_IDS mới dùng được tất cả lệnh prefix       ║
# ║            (.clear .close .done .addnote giới hạn admin)        ║
# ║            Thêm seller_role vào overwrites mọi loại ticket      ║
# ║            (view/send/history/manage/attach/embed_links)        ║
# ║            (💰 Money / 💀 Skeleton / 📦 Khác)                   ║
# ║            Tên kênh theo item: money-001, skeleton-001, khac-001 ║
# ║            Embed hiện "Loại hàng" thay vì "Seller"              ║
# ║  v3.3.2 — Seller dropdown hiển thị trạng thái online/idle/DND  ║
# ║            Bỏ lựa chọn Random seller                             ║
# ║            Thêm lệnh .delemoji — xoá emoji server               ║
# ║            Cập nhật .help mod + ticket                           ║
# ║  v3.3.1 — Xoá mục acc online khỏi bảng giá Steam               ║
# ║            Dọn comment thừa trong code                           ║
# ║            Cập nhật .help: thêm seller, giaset, sv              ║
# ║  v3.3.0 — Lệnh .addseller / .removeseller / .listseller        ║
# ║            Seller lưu MongoDB — không mất khi restart            ║
# ║            Tên ticket = tên seller + số ticket                   ║
# ║            Ticket ping đúng seller được chọn (không ping role)  ║
# ║  v3.2.0 — Bảng giá .sv lưu MongoDB, admin sửa qua .giaset      ║
# ║            .giaset: sửa/thêm/xoá/reset mục giá, xem trước      ║
# ║            Giá lưu persistent — không mất khi restart bot       ║
# ║  v3.1.0 — Ticket: nút mua/bán hiển thị danh sách seller        ║
# ║            Tên ticket = (tên seller)-(số ticket)                 ║
# ║            Buyer chọn seller → ping seller khi tạo ticket        ║
# ║            Nút "Claim" đổi thành "Mua"                           ║
# ║            Lệnh .sv → bảng giá sản phẩm store                   ║
# ║  v3.0.0 — Thêm lệnh .sv (giới thiệu dịch vụ Setup Server)     ║
# ║            Xoá admin ID 1438384178755276923 khỏi ADMIN_IDS      ║
# ║            Cập nhật .help chung + mục dịch vụ mới               ║
# ║  v2.9.0 — Hiển thị tên user dạng mention+(username) toàn file  ║
# ║            _uname() → mention (username) — render được click     ║
# ║            _uname_plain() → plain text — dùng footer/log/prompt ║
# ║  v2.8.0 — Giveaway: bật/tắt tự động check invite winner       ║
# ║            Confirm view trước khi đăng (toggle + xác nhận)      ║
# ║            Sau khi kết thúc, bot gửi thống kê invite winner     ║
# ║            (net/tổng/fake/rời) vào kênh — giống lệnh .invite    ║
# ║  v2.7.0 — Fix giveaway embed không cập nhật số người tham gia  ║
# ║            (gọi save_giveaways_data() sau mỗi lần join/leave)   ║
# ║            Thêm lệnh .gwlist <message_id> — xem ds tham gia    ║
# ║            Tự động bump version trong header mỗi lần sửa        ║
# ║  v2.6.0 — Invite tracking: đếm invite, fake detect, leaderboard ║
# ║            Lệnh .invite / .invitetop / .resetinvite              ║
# ║            Gửi changelog tự động vào kênh khi bot restart        ║
# ║            Cache snapshot invite trong on_ready                  ║
# ║  v2.5.0 — Thêm .mkchannel (tạo kênh đồng bộ font server)       ║
# ║            Lưu font server tự động sau khi rename hàng loạt     ║
# ║            Cập nhật .help + botinfo                              ║
# ║  v2.4.0 — Thêm .ai (chat/tomtat/dich/phantich) dùng mọi kênh   ║
# ║            Fix giveaway embed không ẩn nút sau khi kết thúc     ║
# ║  v2.3.0 — Tích hợp AI Groq (llama-3.3-70b-versatile, free)     ║
# ║            Lệnh .aireset / .mychat                               ║
# ║            Kênh AI chat chỉ định qua .settings                  ║
# ║  v2.2.0 — Fix giveaway button "Tương tác không thành công"      ║
# ║            Đăng ký GiveawayView persistent sau restart           ║
# ║  v2.1.0 — Fix transcript chỉ gửi 1 lần vào kênh transcript     ║
# ║            Xoá log channel (thay bằng transcript)                ║
# ║            Tách feedback rating riêng kênh feedback              ║
# ║  v2.0.0 — Bỏ qua voice channel khi rename font hàng loạt       ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  LƯU Ý QUAN TRỌNG                                               ║
# ║  • Biến môi trường bắt buộc: TOKEN, MONGO_URI                   ║
# ║  • Biến môi trường tuỳ chọn: GROQ_API_KEY (cho AI chat)        ║
# ║  • ADMIN_IDS: danh sách Discord ID có quyền admin bot           ║
# ║  • OWNER_ID : chỉ owner mới chỉnh lệnh nguy hiểm               ║
# ║  • INVITE TRACKING:                                              ║
# ║    - Dữ liệu lưu MongoDB key "invite_counts" — riêng biệt hoàn  ║
# ║      toàn với giveaway/buyer/ticket/balance                      ║
# ║    - Fake = join rồi leave trong 10 phút                         ║
# ║    - Net = Total − Fake − Left (luôn ≥ 0)                        ║
# ║    - Bot cần quyền "Manage Server" để đọc invites               ║
# ║  • Font server lưu trong MongoDB key "cfg_font" — tự động       ║
# ║    cập nhật sau mỗi lần rename hàng loạt thành công             ║
# ║  • Kênh AI chat: cài qua .settings → 🤖 AI Channel             ║
# ║  • Transcript: gửi embed + HTML vào kênh transcript              ║
# ║    Feedback: chỉ embed đánh giá (⭐) — kênh riêng               ║
# ║  • Giveaway dùng nút bấm (button) — persistent sau restart      ║
# ║  • Groq free tier: 6000 req/ngày, không cần card tín dụng      ║
# ║  • CHANGELOG_CHANNEL_ID: 1486967511839801414                    ║
# ╚══════════════════════════════════════════════════════════════════╝

BOT_VERSION = "3.3.5"
BOT_UPDATED = "2026-05-12"

def _uname(user) -> str:
    """
    Trả về 'mention (username)' — dùng trong embed field/description/title/reply.
    Mention sẽ render thành tên hiển thị có thể click trong Discord.
    """
    if user is None:
        return "Unknown"
    uid = getattr(user, "id", None)
    un  = getattr(user, "name", None) or str(user)
    if uid:
        return f"<@{uid}> ({un})"
    dn = getattr(user, "display_name", None) or un
    return f"{dn} ({un})" if dn != un else dn

def _uname_plain(user) -> str:
    """
    Trả về 'Display Name (username)' plain text — dùng trong:
    - embed footer (không render mention)
    - AI prompt gửi Groq
    - log console / button label
    """
    if user is None:
        return "Unknown"
    dn = getattr(user, "display_name", None) or getattr(user, "name", str(user))
    un = getattr(user, "name", None)
    if un and un != dn:
        return f"{dn} ({un})"
    return dn

if os.path.exists(".env"):
    load_dotenv()

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select

TOKEN = os.getenv("TOKEN")
print(f"[DEBUG] TOKEN loaded: {'OK' if TOKEN else 'MISSING'}")

CHANGELOG_CHANNEL_ID = 1486967511839801414  # kênh gửi changelog khi bot khởi động

# ── AI Chat: lịch sử hội thoại (tối đa 10 tin/user) ──
_ai_chat_history: dict = {}   # user_id → list of {"role": ..., "content": ...}
AI_HISTORY_LIMIT = 10         # số tin nhắn tối đa mỗi user

ADMIN_IDS = [
    846332174734983219,
    1464961078042689588,
]


LOG_CHANNEL = 1482234024868053083
TICKET_CATEGORY_ID = 1464426174611456195
SUPPORT_ROLE_ID = 1474572393908404305
SELLER_ROLE_ID  = 0
COUNTER_CHANNEL_ID = 0
LEGIT_CHANNEL_ID = 0
PROOF_CHANNEL_ID = 1469647159560241318

TRANSCRIPT_CHANNEL_ID = 1464430574524436679
FEEDBACK_CHANNEL_ID   = 1502464872686948403

# ── ID kênh dùng làm "database" Discord ──
DATA_CHANNEL_ID    = 1496994486927229018
TICKET_DATA_CH_ID  = 1495055958827602092

BALANCE_CHANNEL_ID = 1464999465294369035

# ── Getter động — đọc từ data.json nếu admin đã đổi qua .settings ──
def get_cfg_log_channel() -> int:
    return load_data().get("cfg_log_channel", LOG_CHANNEL)

def get_cfg_font() -> str:
    return load_data().get("cfg_font", "normal")

def set_cfg_font(font: str):
    data = load_data()
    data["cfg_font"] = font
    save_data(data)

def get_cfg_category() -> int:
    return load_data().get("cfg_ticket_category", TICKET_CATEGORY_ID)

def get_cfg_support_role() -> int:
    return load_data().get("cfg_support_role", SUPPORT_ROLE_ID)

def get_cfg_seller_role() -> int:
    return load_data().get("cfg_seller_role", SELLER_ROLE_ID)

def is_staff(member: discord.Member) -> bool:
    if member.id in ADMIN_IDS:
        return True
    guild = member.guild
    support_role = guild.get_role(get_cfg_support_role())
    if support_role and support_role in member.roles:
        return True
    seller_role = guild.get_role(get_cfg_seller_role())
    if seller_role and seller_role in member.roles:
        return True
    return False

def get_cfg_counter_channel() -> int:
    return load_data().get("cfg_counter_channel", COUNTER_CHANNEL_ID)

def get_cfg_balance_channel() -> int:
    return load_data().get("cfg_balance_channel", BALANCE_CHANNEL_ID)

def get_cfg_legit_channel() -> int:
    return load_data().get("cfg_legit_channel", LEGIT_CHANNEL_ID)

def get_cfg_proof_channel() -> int:
    return load_data().get("cfg_proof_channel", PROOF_CHANNEL_ID)

def get_cfg_ai_channel() -> int:
    return load_data().get("cfg_ai_channel", 0)

def save_cfg(key: str, value: int):
    data = load_data()
    data[key] = value
    save_data(data)

def get_sellers() -> list:
    data = load_data()
    return data.get("sellers", [])

def save_sellers(sellers: list):
    data = load_data()
    data["sellers"] = sellers
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

# Dịch vụ không có giá — tạo ticket thẳng, không qua modal
SERVICE_TABLE = {
    "orderbase": {"label": "🏯 Order Base",    "note": "Đặt thiết kế base theo yêu cầu",  "color": 0xE67E22, "type_label": "🏯 ORDER BASE",    "channel_prefix": "base"},
    "modfixlag": {"label": "⚡ Mod Fix Lag",   "note": "Hỗ trợ cài mod tối ưu FPS",       "color": 0x1ABC9C, "type_label": "⚡ MOD FIX LAG",   "channel_prefix": "mod"},
    "giveaway":  {"label": "🎁 Nhận Giveaway", "note": "Xác nhận & nhận thưởng giveaway", "color": 0xF1C40F, "type_label": "🎁 NHẬN GIVEAWAY",  "channel_prefix": "ticket"},
    "support":   {"label": "🆘 Hỗ Trợ",        "note": "Hỗ trợ mọi vấn đề",              "color": 0x3498DB, "type_label": "🆘 HỖ TRỢ",         "channel_prefix": "ticket"},
}

# ── PRICE_TABLE: chỉ dùng nội bộ cho ticket (label, unit, note) — không hiển thị giá ──
PRICE_TABLE = {
    "sell": {
        "money":    {"label": "💰 Money",    "unit": "1m",    "note": "Tối thiểu 10m"},
        "skeleton": {"label": "🦴 Skeleton", "unit": "5m",    "note": ""},
        "elytra":   {"label": "🪽 Elytra",   "unit": "1 cái", "note": "Liên hệ trước"},
    },
    "buy": {
        "money":    {"label": "💰 Money",    "unit": "1m",    "note": ""},
        "skeleton": {"label": "🦴 Skeleton", "unit": "1 cái", "note": ""},
        "elytra":   {"label": "🪽 Elytra",   "unit": "1 cái", "note": ""},
    }
}

# ── SELLERS lưu trong MongoDB — quản lý qua .addseller / .removeseller / .listseller ──

# ================= DATA (MongoDB Storage) =================
# Toàn bộ data lưu trong MongoDB Atlas — không mất khi redeploy
# Collection: bot_data, document duy nhất với _id = "main"
# Giveaway lưu riêng collection: giveaways
#
# MONGO_URI đọc từ biến môi trường MONGO_URI hoặc hardcode bên dưới

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("❌ Thiếu biến môi trường MONGO_URI! Hãy thêm vào Railway Variables.")

QR_FILE = "/data/qr_code.png" if os.path.isdir("/data") else "./qr_code.png"

# ── Khởi tạo client (lazy, kết nối khi dùng lần đầu) ──
_mongo_client: AsyncIOMotorClient | None = None
_db = None
_col_data     = None   # collection bot_data
_col_giveaway = None   # collection giveaways

def _get_mongo():
    global _mongo_client, _db, _col_data, _col_giveaway
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _db           = _mongo_client["tuytam_bot"]
        _col_data     = _db["bot_data"]
        _col_giveaway = _db["giveaways"]
    return _col_data, _col_giveaway

# ── Default data ──
def _default_cfg() -> dict:
    return {
        "panel_channel_id":    None,
        "qr_path":             None,
        "cfg_log_channel":     LOG_CHANNEL,
        "cfg_ticket_category": TICKET_CATEGORY_ID,
        "cfg_support_role":    SUPPORT_ROLE_ID,
        "cfg_seller_role":     SELLER_ROLE_ID,
        "cfg_counter_channel": COUNTER_CHANNEL_ID,
        "cfg_balance_channel": BALANCE_CHANNEL_ID,
        "cfg_legit_channel":   LEGIT_CHANNEL_ID,
        "cfg_proof_channel":   PROOF_CHANNEL_ID,
        "dangerous_cmd_overrides": {},
    }

def _default_data() -> dict:
    return {
        "_id":              "main",
        "ticket":           0,
        "panel_channel_id": None,
        "qr_path":          None,
        "cfg_log_channel":     LOG_CHANNEL,
        "cfg_ticket_category": TICKET_CATEGORY_ID,
        "cfg_support_role":    SUPPORT_ROLE_ID,
        "cfg_seller_role":     SELLER_ROLE_ID,
        "cfg_counter_channel": COUNTER_CHANNEL_ID,
        "cfg_balance_channel": BALANCE_CHANNEL_ID,
        "cfg_legit_channel":   LEGIT_CHANNEL_ID,
        "cfg_proof_channel":   PROOF_CHANNEL_ID,
        "cfg_ai_channel":      0,
        "cfg_font":            "normal",
        "dangerous_cmd_overrides": {},
        "balance": {
            "current": 0, "total_in": 0, "total_fee": 0,
            "total_out": 0, "tx_count": 0, "history": []
        },
        "buy_roles":        [],
        "user_total_spent": {},
        "ratings":          [],
        "ticket_notes":     {},
        "invite_counts":    {},
    }

# ── Cache in-memory ──
_data_cache: dict | None = None
_save_lock = None

def _get_save_lock():
    global _save_lock
    if _save_lock is None:
        _save_lock = asyncio.Lock()
    return _save_lock

# ════════════════════════════════════════════════════
# LOW-LEVEL: đọc/ghi MongoDB
# ════════════════════════════════════════════════════

async def _mongo_load() -> dict:
    col, _ = _get_mongo()
    try:
        doc = await col.find_one({"_id": "main"})
        if doc is None:
            doc = _default_data()
            await col.insert_one(doc)
            print("[DATA] 🆕 Tạo document mới trong MongoDB")
        else:
            default = _default_data()
            updated = False
            for k, v in default.items():
                if k not in doc:
                    doc[k] = v
                    updated = True
            if updated:
                await _mongo_save(doc)
        return doc
    except Exception as e:
        print(f"[DATA] ❌ Lỗi đọc MongoDB: {e}")
        return _default_data()

async def _mongo_save(data: dict):
    col, _ = _get_mongo()
    try:
        save = {k: v for k, v in data.items() if k != "_id"}
        await col.update_one(
            {"_id": "main"},
            {"$set": save},
            upsert=True
        )
    except Exception as e:
        print(f"[DATA] ❌ Lỗi ghi MongoDB: {e}")

# ════════════════════════════════════════════════════
# HIGH-LEVEL API (giữ nguyên load_data / save_data)
# ════════════════════════════════════════════════════

def load_data() -> dict:
    if _data_cache is not None:
        return _data_cache
    return _default_data()

def save_data(data: dict):
    global _data_cache
    _data_cache = data
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_flush_to_mongo())
    except Exception:
        pass

_flush_dirty = False

async def _flush_to_mongo():
    global _flush_dirty
    lock = _get_save_lock()
    async with lock:
        if _data_cache is not None:
            await _mongo_save(_data_cache)

async def init_data_cache():
    global _data_cache
    _data_cache = await _mongo_load()
    col, col_gw = _get_mongo()
    try:
        giveaways = {}
        async for doc in col_gw.find({}):
            mid = str(doc.get("message_id", doc.get("_id", "")))
            giveaways[mid] = {k: v for k, v in doc.items() if k not in ("_id", "message_id")}
        _data_cache["_giveaways"] = giveaways
    except Exception as e:
        print(f"[DATA] ⚠️ Không load được giveaways: {e}")
        _data_cache.setdefault("_giveaways", {})
    t = _data_cache.get("ticket", 0)
    print(f"[DATA] ✅ Đã kết nối MongoDB — ticket#{t:03d}")

# ── Helper get/set section (compat với code cũ dùng _get_section/_set_section) ──

def _get_section(section: str) -> dict:
    data = load_data()
    mapping = {
        "CFG":      lambda d: {k: d.get(k) for k in _default_cfg()},
        "TICKET":   lambda d: {"ticket": d.get("ticket", 0)},
        "BALANCE":  lambda d: d.get("balance", {"current":0,"total_in":0,"total_fee":0,"total_out":0,"tx_count":0,"history":[]}),
        "BUYER":    lambda d: {"buy_roles": d.get("buy_roles",[]), "user_total_spent": d.get("user_total_spent",{})},
        "RATINGS":  lambda d: {"ratings": d.get("ratings", [])},
        "NOTES":    lambda d: {"ticket_notes": d.get("ticket_notes", {})},
        "GIVEAWAY": lambda d: {"giveaways": {}},
    }
    return mapping.get(section, lambda d: {})(data)

def _set_section(section: str, value: dict):
    data = load_data().copy()
    if section == "CFG":
        data.update(value)
    elif section == "TICKET":
        data["ticket"] = value.get("ticket", 0)
    elif section == "BALANCE":
        data["balance"] = value
    elif section == "BUYER":
        data["buy_roles"]        = value.get("buy_roles", [])
        data["user_total_spent"] = value.get("user_total_spent", {})
    elif section == "RATINGS":
        data["ratings"] = value.get("ratings", [])
    elif section == "NOTES":
        data["ticket_notes"] = value.get("ticket_notes", {})
    save_data(data)

# ── Giveaway persistence (collection riêng) ──

def _load_giveaway_section() -> dict:
    data = load_data()
    return data.get("_giveaways", {})

def _save_giveaway_section(giveaways: dict):
    serializable = {}
    for mid, gw in giveaways.items():
        serializable[str(mid)] = {
            k: list(v) if isinstance(v, set) else v
            for k, v in gw.items()
        }
    data = load_data().copy()
    data["_giveaways"] = serializable
    save_data(data)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_sync_giveaways_to_mongo(serializable))
    except Exception:
        pass

async def _sync_giveaways_to_mongo(giveaways: dict):
    _, col_gw = _get_mongo()
    try:
        for mid_str, gw in giveaways.items():
            doc = dict(gw)
            doc["message_id"] = int(mid_str)
            await col_gw.update_one(
                {"message_id": int(mid_str)},
                {"$set": doc},
                upsert=True
            )
    except Exception as e:
        print(f"[DATA] ❌ Lỗi sync giveaway MongoDB: {e}")

def get_ticket_number():
    """Lấy số ticket tiếp theo từ data.json (fallback khi chưa sync được channel)."""
    data = load_data()
    data["ticket"] = data.get("ticket", 0) + 1
    save_data(data)
    return f"{data['ticket']:03d}"

async def read_counter_from_channel() -> int:
    if not get_cfg_counter_channel():
        return 0
    channel = bot.get_channel(get_cfg_counter_channel())
    if not channel:
        return 0
    try:
        async for msg in channel.history(limit=1):
            if msg.content.startswith("ticket:"):
                return int(msg.content.split(":")[1])
    except:
        pass
    return 0

async def write_counter_to_channel(number: int):
    if not get_cfg_counter_channel():
        return
    channel = bot.get_channel(get_cfg_counter_channel())
    if not channel:
        return
    try:
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

    current = max(channel_num, file_num)
    next_num = current + 1

    data["ticket"] = next_num
    save_data(data)
    asyncio.create_task(write_counter_to_channel(next_num))

    return f"{next_num:03d}"

async def sync_ticket_counter(guild: discord.Guild):
    """
    Khi bot khởi động: đồng bộ counter từ kênh Discord + quét channel thực tế.
    Lấy số cao nhất trong 3 nguồn: data.json, kênh counter, channel tên ticket-XXX.
    """
    data = load_data()
    max_num = data.get("ticket", 0)

    channel_num = await read_counter_from_channel()
    if channel_num > max_num:
        max_num = channel_num

    for channel in guild.text_channels:
        if channel.name.startswith("ticket-"):
            try:
                num = int(channel.name.split("-")[-1])
                if num > max_num:
                    max_num = num
            except ValueError:
                continue

    if max_num > data.get("ticket", 0):
        data["ticket"] = max_num
        save_data(data)
        asyncio.create_task(write_counter_to_channel(max_num))
        print(f"[SYNC] Ticket counter đồng bộ → {max_num:03d}")

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

# ── Cấu hình role mua hàng tự động ──
def get_buy_roles() -> list:
    """Trả về danh sách cấu hình role theo tổng tiền. Đã sắp xếp tăng dần min_amount."""
    data = load_data()
    roles = data.get("buy_roles", [])
    return sorted(roles, key=lambda r: r.get("min_amount", 0))

def save_buy_roles(roles: list):
    data = load_data()
    data["buy_roles"] = roles
    save_data(data)

def get_user_total_spent(user_id: int) -> int:
    data = load_data()
    return data.get("user_total_spent", {}).get(str(user_id), 0)

def add_user_spent(user_id: int, amount: int) -> int:
    data = load_data()
    if "user_total_spent" not in data:
        data["user_total_spent"] = {}
    key = str(user_id)
    data["user_total_spent"][key] = data["user_total_spent"].get(key, 0) + amount
    save_data(data)
    return data["user_total_spent"][key]

def parse_amount(raw: str) -> int | None:
    """
    Parse chuỗi tiền linh hoạt → số nguyên VNĐ.
    Ví dụ: '50k' → 50000, '1.5tr' → 1500000, '200000' → 200000, '2tr5' → 2500000
    """
    import re as _re
    raw = raw.strip().lower().replace(",", ".").replace(" ", "")
    m = _re.match(r"^(\d+)tr(\d+)$", raw)
    if m:
        return int(m.group(1)) * 1_000_000 + int(m.group(2)) * 100_000
    m = _re.match(r"^(\d+(?:\.\d+)?)(k|tr|m|đ)?$", raw)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2) or ""
    if unit == "k":
        return int(num * 1_000)
    if unit in ("tr", "m"):
        return int(num * 1_000_000)
    return int(num)

def fmt_amount(amount: int) -> str:
    if amount >= 1_000_000:
        val = amount / 1_000_000
        return f"{val:g}tr"
    if amount >= 1_000:
        val = amount / 1_000
        return f"{val:g}k"
    return f"{amount:,}đ"

async def auto_give_buy_roles(guild: discord.Guild, member: discord.Member, total_spent: int):
    """
    Give role buyer phù hợp dựa trên tổng tiền đã mua.
    Mỗi role có min_amount và max_amount (None = không giới hạn trên).
    Chỉ give đúng 1 role tương ứng với khoảng tiền hiện tại, xoá các role khác.
    """
    buy_roles = get_buy_roles()
    if not buy_roles:
        return None

    # Tìm role phù hợp: min_amount <= total_spent < max_amount (hoặc max_amount là None)
    target_cfg = None
    for r in reversed(buy_roles):  # từ cao xuống thấp
        min_a = r.get("min_amount", 0)
        max_a = r.get("max_amount")  # None = không giới hạn
        if total_spent >= min_a and (max_a is None or total_spent < max_a):
            target_cfg = r
            break

    for cfg in buy_roles:
        role = guild.get_role(cfg.get("role_id", 0))
        if not role:
            continue
        if target_cfg and cfg["role_id"] == target_cfg["role_id"]:
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Auto buyer role — {fmt_amount(total_spent)}")
                except Exception as e:
                    print(f"[BUY_ROLE] Lỗi give {role.name}: {e}")
        else:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason=f"Đổi buyer role — {fmt_amount(total_spent)}")
                except Exception as e:
                    print(f"[BUY_ROLE] Lỗi xoá {role.name}: {e}")

    return target_cfg
    return sorted(roles, key=lambda r: r.get("min_amount", 0))

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
            "Nhấn nút bên dưới để tạo ticket giao dịch."
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
def build_transcript_html(channel_name, messages, info: dict = None):
    """
    info dict (tuỳ chọn):
      created_by_name, created_by_id, created_by_avatar,
      closed_by_name,  closed_by_id,
      created_at,      closed_at,
      ticket_type,     mc_name,  item, trade_type
    """
    info = info or {}
    close_time_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")

    def row(icon, label, value):
        return f'<div class="info-row"><span class="info-icon">{icon}</span><span class="info-label">{label}</span><span class="info-value">{value}</span></div>'

    info_rows = ""
    if info.get("created_by_name"):
        avatar_url = info.get("created_by_avatar", "")
        avatar_tag = f'<img src="{avatar_url}" class="info-avatar" onerror="this.style.display=\'none\'">' if avatar_url else ""
        info_rows += f'<div class="info-row"><span class="info-icon">👤</span><span class="info-label">Người tạo</span><span class="info-value">{avatar_tag} {info["created_by_name"]} <span class="uid">(ID: {info.get("created_by_id","")})</span></span></div>'
    if info.get("closed_by_name"):
        info_rows += row("🔒", "Người đóng", f'{info["closed_by_name"]} <span class="uid">(ID: {info.get("closed_by_id","")})</span>')
    if info.get("ticket_type"):
        info_rows += row("🏷️", "Loại ticket", info["ticket_type"])
    if info.get("mc_name"):
        info_rows += row("🎮", "Tên Minecraft", info["mc_name"])
    if info.get("item"):
        action = "Mua" if info.get("trade_type") == "sell" else ("Bán" if info.get("trade_type") == "buy" else "")
        info_rows += row("📦", "Giao dịch", f'{action} {info["item"]}' if action else info["item"])
    if info.get("created_at"):
        info_rows += row("🕐", "Thời gian tạo", info["created_at"])
    info_rows += row("🕑", "Thời gian đóng", close_time_str)
    info_rows += row("💬", "Số tin nhắn", f"{len(messages)} tin nhắn")

    rows = ""
    for msg in messages:
        avatar = msg.author.display_avatar.url if msg.author.display_avatar else ""
        raw = msg.content or ""
        content = discord.utils.escape_mentions(raw).replace("<", "&lt;").replace(">", "&gt;") if raw else "<i style='color:#72767d'>(không có nội dung)</i>"
        attach_html = ""
        for att in msg.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                attach_html += f'<br><img src="{att.url}" class="attach-img" onerror="this.style.display=\'none\'">'
            else:
                attach_html += f'<br><a href="{att.url}" class="attach-link" target="_blank">📎 {att.filename}</a>'
        time_str = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
        is_bot = "bot-msg" if msg.author.bot else ""
        rows += f"""
        <div class="message {is_bot}">
            <img class="avatar" src="{avatar}" onerror="this.style.display='none'">
            <div class="content">
                <div class="msg-header">
                    <span class="author">{msg.author.display_name}</span>
                    <span class="username">@{msg.author}</span>
                    {"<span class='bot-badge'>BOT</span>" if msg.author.bot else ""}
                    <span class="time">{time_str} UTC</span>
                </div>
                <div class="text">{content}{attach_html}</div>
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transcript – {channel_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #313338; font-family: 'Segoe UI', Arial, sans-serif; color: #dcddde; padding: 0; }}

  /* ── HEADER ── */
  .header {{ background: #1e1f22; border-bottom: 2px solid #5865F2; padding: 24px 32px; }}
  .header-title {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
  .header-title h1 {{ color: #fff; font-size: 22px; }}
  .ticket-badge {{ background: #5865F2; color: #fff; font-size: 12px; padding: 3px 10px; border-radius: 12px; font-weight: 600; }}

  .info-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px; }}
  .info-row {{ display: flex; align-items: center; gap: 8px; background: #2b2d31; border-radius: 8px; padding: 8px 12px; }}
  .info-icon {{ font-size: 16px; flex-shrink: 0; }}
  .info-label {{ color: #a3a6aa; font-size: 12px; width: 110px; flex-shrink: 0; }}
  .info-value {{ color: #fff; font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
  .uid {{ color: #a3a6aa; font-size: 11px; font-weight: 400; }}
  .info-avatar {{ width: 20px; height: 20px; border-radius: 50%; }}

  /* ── MESSAGES ── */
  .messages {{ padding: 16px 32px; }}
  .divider {{ text-align: center; color: #a3a6aa; font-size: 11px; margin: 12px 0; border-top: 1px solid #3f4147; padding-top: 8px; }}
  .message {{ display: flex; gap: 14px; padding: 6px 10px; border-radius: 8px; margin-bottom: 1px; }}
  .message:hover {{ background: #2e3035; }}
  .bot-msg {{ opacity: 0.85; }}
  .avatar {{ width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0; margin-top: 2px; }}
  .content {{ display: flex; flex-direction: column; gap: 2px; min-width: 0; }}
  .msg-header {{ display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }}
  .author {{ font-weight: 700; color: #fff; font-size: 14px; }}
  .username {{ color: #a3a6aa; font-size: 11px; }}
  .bot-badge {{ background: #5865F2; color: #fff; font-size: 10px; padding: 1px 5px; border-radius: 4px; font-weight: 600; }}
  .time {{ color: #a3a6aa; font-size: 11px; }}
  .text {{ font-size: 14px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; color: #dcddde; }}
  .attach-img {{ max-width: 320px; max-height: 240px; border-radius: 6px; margin-top: 6px; }}
  .attach-link {{ color: #00aff4; text-decoration: none; font-size: 13px; }}
  .attach-link:hover {{ text-decoration: underline; }}

  /* ── FOOTER ── */
  .footer {{ text-align: center; color: #4f545c; font-size: 12px; padding: 20px; border-top: 1px solid #3f4147; margin-top: 16px; }}
</style>
</head>
<body>
  <div class="header">
    <div class="header-title">
      <h1>📄 Transcript</h1>
      <span class="ticket-badge">#{channel_name}</span>
    </div>
    <div class="info-grid">
      {info_rows}
    </div>
  </div>
  <div class="messages">
    <div class="divider">— Bắt đầu lịch sử tin nhắn —</div>
    {rows}
    <div class="divider">— Kết thúc — {len(messages)} tin nhắn —</div>
  </div>
  <div class="footer">TuyTam Store • Ticket System • Xuất lúc {close_time_str}</div>
</body>
</html>"""

# ================= RATING MODAL =================
