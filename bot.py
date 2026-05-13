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

        log = bot.get_channel(FEEDBACK_CHANNEL_ID)
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
async def create_service_ticket(interaction: discord.Interaction, service_key: str):
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
        seller_role = guild.get_role(get_cfg_seller_role())
        if seller_role:
            overwrites[seller_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True,
                attach_files=True, embed_links=True,
                manage_channels=True, manage_permissions=True
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
            seller_role = guild.get_role(get_cfg_seller_role())
            if seller_role:
                overwrites[seller_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True,
                    attach_files=True, embed_links=True,
                manage_channels=True, manage_permissions=True
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

        except Exception as e:
            try:
                await interaction.response.send_message(
                    f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`\nVui lòng thử lại hoặc liên hệ admin.",
                    ephemeral=True
                )
            except:
                pass

async def create_order_ticket(interaction: discord.Interaction, trade_type: str,
                              item_key: str = "other", item_label: str = "📦 Khác",
                              seller_id: int | None = None, seller_name: str = "staff"):
    """Tạo ticket mua/bán. Interaction đã được defer trước."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send(
                "❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True
            )

        number     = await get_next_ticket_number()
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        _key_slug = {"money": "money", "skeleton": "skeleton", "other": "khac"}
        channel_name = f"{_key_slug.get(item_key, 'ticket')}-{number}"

        if trade_type == "sell":
            color      = 0x57F287
            type_label = "🛒 MUA HÀNG"
        else:
            color      = 0xFEE75C
            type_label = "💸 BÁN HÀNG"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user:   discord.PermissionOverwrite(
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
        if seller_id:
            seller_member = guild.get_member(seller_id)
            if seller_member:
                overwrites[seller_member] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True
                )
        seller_role = guild.get_role(get_cfg_seller_role())
        if seller_role:
            overwrites[seller_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True,
                attach_files=True, embed_links=True,
                manage_channels=True, manage_permissions=True
            )

        category = discord.utils.get(guild.categories, id=get_cfg_category())
        channel  = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            category=category,
            topic=f"{interaction.user.id}||{trade_type}|{item_key}|open"
        )

        embed = discord.Embed(
            title=f"{type_label}  •  {item_label}  •  #{number}",
            description=(
                f"Xin chào {interaction.user.mention}! 👋\n"
                f"Staff sẽ xử lý giao dịch sớm nhất có thể.\n"
                f"🟡 **Trạng thái:** Đang chờ staff nhận"
            ),
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="📦  Loại hàng",  value=item_label,               inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(
            text="TuyTam Store  •  Ticket System",
            icon_url=guild.icon.url if guild.icon else None
        )

        ping_target = f"<@{seller_id}>" if seller_id else f"<@&{get_cfg_support_role()}>"
        await channel.send(
            f"{ping_target} | {interaction.user.mention}",
            embed=embed,
            view=TicketButtons()
        )

        await interaction.followup.send(
            f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True
        )

    except Exception as e:
        try:
            await interaction.followup.send(
                f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`\nVui lòng thử lại hoặc liên hệ admin.",
                ephemeral=True
            )
        except:
            pass

# ================= SELECT ITEM TYPE =================
_ITEM_OPTIONS = [
    discord.SelectOption(
        label="💰 Money",
        value="money",
        description="Giao dịch tiền tệ trong game",
        emoji="💰",
    ),
    discord.SelectOption(
        label="💀 Skeleton",
        value="skeleton",
        description="Giao dịch skeleton",
        emoji="💀",
    ),
    discord.SelectOption(
        label="📦 Khác",
        value="other",
        description="Item / dịch vụ khác — ghi rõ trong ticket",
        emoji="📦",
    ),
]

_ITEM_LABEL = {
    "money":    "💰 Money",
    "skeleton": "💀 Skeleton",
    "other":    "📦 Khác",
}

class ItemSelect(Select):
    def __init__(self, trade_type: str):
        self.trade_type = trade_type
        action = "mua" if trade_type == "sell" else "bán"
        super().__init__(
            placeholder=f"Bạn muốn {action} loại nào?",
            options=_ITEM_OPTIONS,
            custom_id=f"item_select_{trade_type}",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            item_key   = self.values[0]
            item_label = _ITEM_LABEL.get(item_key, item_key)
            await interaction.response.defer(ephemeral=True)
            await create_order_ticket(
                interaction,
                trade_type=self.trade_type,
                item_key=item_key,
                item_label=item_label,
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

class ItemSelectView(View):
    def __init__(self, trade_type: str):
        super().__init__(timeout=60)
        self.add_item(ItemSelect(trade_type))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

# ================= LỆNH QUẢN LÝ SELLER =================

@bot.command(name="addseller")
async def addseller_cmd(ctx: commands.Context, user_id: str = None, *, username: str = None):
    """
    Thêm seller vào danh sách chọn trong ticket.
    Cú pháp: .addseller <ID> <tên hiển thị>
    Ví dụ:   .addseller 846332174734983219 TuyTam
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
    if not user_id or not username:
        return await ctx.reply(
            "❌ Thiếu thông tin!\n"
            "Cú pháp: `.addseller <ID> <tên hiển thị>`\n"
            "Ví dụ: `.addseller 846332174734983219 TuyTam`"
        )
    try:
        seller_id = int(user_id.strip())
    except ValueError:
        return await ctx.reply("❌ ID không hợp lệ! Phải là dãy số.")

    sellers = get_sellers()
    for s in sellers:
        if s["id"] == seller_id:
            return await ctx.reply(f"❌ Seller ID `{seller_id}` đã có trong danh sách rồi!")

    member = ctx.guild.get_member(seller_id)
    display = f"{member.mention} ({member.name})" if member else f"ID: `{seller_id}`"

    sellers.append({"id": seller_id, "label": username.strip()})
    save_sellers(sellers)

    embed = discord.Embed(
        title="✅ Đã Thêm Seller",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 User",          value=display,                  inline=True)
    embed.add_field(name="🏷️ Tên hiển thị", value=f"**{username.strip()}**", inline=True)
    embed.add_field(name="📋 Tổng sellers",  value=f"**{len(sellers)}** người", inline=True)
    embed.add_field(
        name="📝 Danh sách hiện tại",
        value="\n".join(f"`{i+1}.` **{s['label']}** — `{s['id']}`" for i, s in enumerate(sellers)) or "—",
        inline=False
    )
    embed.set_footer(text=f"Thêm bởi {ctx.author}")
    await ctx.reply(embed=embed)

@bot.command(name="removeseller", aliases=["delseller", "xoaseller"])
async def removeseller_cmd(ctx: commands.Context, *, target: str = None):
    """
    Xoá seller khỏi danh sách.
    Cú pháp: .removeseller <ID hoặc tên>
    Ví dụ:   .removeseller 846332174734983219
             .removeseller TuyTam
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
    if not target:
        return await ctx.reply("❌ Cú pháp: `.removeseller <ID hoặc tên hiển thị>`")

    sellers = get_sellers()
    target  = target.strip()

    found = None
    for s in sellers:
        if str(s["id"]) == target or s["label"].lower() == target.lower():
            found = s
            break

    if not found:
        return await ctx.reply(
            f"❌ Không tìm thấy seller `{target}` trong danh sách.\n"
            f"Dùng `.listseller` để xem danh sách hiện tại."
        )

    sellers.remove(found)
    save_sellers(sellers)

    embed = discord.Embed(
        title="🗑️ Đã Xoá Seller",
        color=0xED4245,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏷️ Seller đã xoá", value=f"**{found['label']}** (`{found['id']}`)", inline=False)
    embed.add_field(
        name=f"📋 Còn lại ({len(sellers)} người)",
        value="\n".join(f"`{i+1}.` **{s['label']}** — `{s['id']}`" for i, s in enumerate(sellers)) or "*(trống)*",
        inline=False
    )
    embed.set_footer(text=f"Xoá bởi {ctx.author}")
    await ctx.reply(embed=embed)

@bot.command(name="listseller", aliases=["sellers", "danhsachseller"])
async def listseller_cmd(ctx: commands.Context):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

    sellers = get_sellers()
    embed = discord.Embed(
        title="📋 Danh Sách Seller",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    if sellers:
        lines = []
        for i, s in enumerate(sellers):
            member = ctx.guild.get_member(s["id"])
            mention = member.mention if member else f"`{s['id']}`"
            lines.append(f"`{i+1}.` **{s['label']}** — {mention}")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Tổng: {len(sellers)} seller  •  .addseller <ID> <tên> để thêm")
    else:
        embed.description = (
            "*(Chưa có seller nào)*\n\n"
            "Thêm seller bằng lệnh:\n"
            "`.addseller <ID> <tên hiển thị>`\n"
            "Ví dụ: `.addseller 846332174734983219 TuyTam`"
        )
    await ctx.reply(embed=embed)

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
                "🛒 **Bạn muốn mua loại nào?**",
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
                "💸 **Bạn muốn bán loại nào?**",
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

# ================= TICKET BUTTONS =================
class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Mua",
        emoji="🛒",
        style=discord.ButtonStyle.blurple,
        custom_id="claim_ticket"
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            for item in self.children:
                if item.custom_id == "claim_ticket":
                    item.disabled = True
                    item.label = f"Claimed: {_uname_plain(interaction.user)}"
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
        if not is_staff(interaction.user):
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
        if not is_staff(interaction.user):
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
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Không có quyền.", ephemeral=True)
        try:
            await interaction.response.defer()
            await _close_ticket(interaction.channel, bot, closer=interaction.user)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi khi đóng ticket: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Hoàn thành đơn",
        emoji="✅",
        style=discord.ButtonStyle.green,
        custom_id="complete_order"
    )
    async def complete_order(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            await interaction.response.defer(ephemeral=True)
            await _complete_order(interaction)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

    @discord.ui.button(
        label="Gửi QR",
        emoji="📱",
        style=discord.ButtonStyle.green,
        custom_id="send_qr"
    )
    async def send_qr(self, interaction: discord.Interaction, button: Button):
        if not is_staff(interaction.user):
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
            embed.set_footer(text=f"Gửi bởi {_uname_plain(interaction.user)}")
            await interaction.response.send_message(embed=embed, file=file)
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                pass

# ================= HOÀN THÀNH ĐƠN (GIVE ROLE) =================
async def _complete_order(interaction: discord.Interaction):
    """
    Staff nhấn nút 'Hoàn thành đơn' trong ticket.
    Bot đọc buyer từ topic kênh → +1 đơn → give role phù hợp.
    Chỉ hoạt động với ticket loại mua hàng (sell/buy), không áp dụng cho service/support.
    """
    channel = interaction.channel
    guild   = interaction.guild

    if not channel.topic or "|" not in channel.topic:
        return await interaction.followup.send("❌ Đây không phải kênh ticket.", ephemeral=True)

    parts = channel.topic.split("|")
    try:
        user_id = int(parts[0]) if parts[0].isdigit() else None
    except Exception:
        user_id = None

    if not user_id:
        return await interaction.followup.send("❌ Không đọc được thông tin buyer từ ticket.", ephemeral=True)

    trade_type = parts[2] if len(parts) > 2 else None

    if trade_type not in ("sell", "buy"):
        return await interaction.followup.send(
            "ℹ️ Ticket dịch vụ / hỗ trợ không tính vào đơn mua hàng.", ephemeral=True
        )

    buyer = guild.get_member(user_id)
    if not buyer:
        return await interaction.followup.send(
            f"❌ Không tìm thấy buyer (ID: `{user_id}`) trong server — họ có thể đã rời.", ephemeral=True
        )

    data = load_data()
    completed_key = f"completed_{channel.id}"
    if data.get(completed_key):
        total = get_user_total_spent(user_id)
        return await interaction.followup.send(
            f"⚠️ Đơn này đã được đánh dấu hoàn thành rồi!\n"
            f"Buyer: {buyer.mention} — tổng đã mua: **{fmt_amount(total)}**",
            ephemeral=True
        )

    await interaction.followup.send("💵 Vui lòng nhập số tiền của đơn này:", ephemeral=True, view=None)
    await interaction.channel.send(
        f"⚠️ {interaction.user.mention} — hãy dùng lệnh `.done <số tiền>` để hoàn thành đơn.\n"
        f"Ví dụ: `.done 50k`, `.done 1tr5`, `.done 200000`",
        delete_after=20
    )

# ================= CLOSE LOGIC =================
async def _close_ticket(channel, bot_instance, closer: discord.Member = None):
    user_id    = None
    mc_name    = None
    trade_type = None
    item_key   = None
    ticket_name = channel.name

    if channel.topic:
        parts = channel.topic.split("|")
        try: user_id    = int(parts[0]) if parts[0].isdigit() else None
        except: pass
        mc_name    = parts[1] if len(parts) > 1 and parts[1] not in ("service", "") else None
        trade_type = parts[2] if len(parts) > 2 else None
        item_key   = parts[3] if len(parts) > 3 else None

    guild = channel.guild
    creator: discord.Member | None = guild.get_member(user_id) if user_id else None

    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    created_at_str = messages[0].created_at.strftime("%d/%m/%Y %H:%M:%S UTC") if messages else "Không rõ"

    item_label = None
    if item_key and trade_type:
        try:
            item_label = PRICE_TABLE[trade_type][item_key]["label"]
        except (KeyError, TypeError):
            pass
    if not item_label and item_key:
        svc = SERVICE_TABLE.get(item_key)
        item_label = svc["label"] if svc else item_key

    type_map = {"sell": "🛒 Mua Hàng", "buy": "💸 Bán Hàng", "service": "🎮 Dịch Vụ"}
    ticket_type_label = type_map.get(trade_type, trade_type or "Ticket")

    info = {
        "created_by_name":   str(creator) if creator else (f"ID:{user_id}" if user_id else "Không rõ"),
        "created_by_id":     str(user_id) if user_id else "",
        "created_by_avatar": creator.display_avatar.url if creator else "",
        "closed_by_name":    str(closer) if closer else "Hệ thống",
        "closed_by_id":      str(closer.id) if closer else "",
        "ticket_type":       ticket_type_label,
        "mc_name":           mc_name,
        "item":              item_label,
        "trade_type":        trade_type,
        "created_at":        created_at_str,
    }

    html = build_transcript_html(channel.name, messages, info)
    file = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")

    transcript_ch = bot_instance.get_channel(TRANSCRIPT_CHANNEL_ID)
    close_time = datetime.now(timezone.utc)
    if messages:
        duration = close_time - messages[0].created_at.replace(tzinfo=timezone.utc)
        total_sec = int(duration.total_seconds())
        h, m, s = total_sec // 3600, (total_sec % 3600) // 60, total_sec % 60
        duration_str = f"{h}g {m}p {s}s" if h else f"{m}p {s}s"
    else:
        duration_str = "Không rõ"

    embed = discord.Embed(
        title="📄 Ticket Đã Đóng",
        color=0xED4245,
        timestamp=close_time
    )
    embed.add_field(name="🎫 Ticket",        value=f"`{ticket_name}`",                                    inline=True)
    embed.add_field(name="🏷️ Loại",          value=ticket_type_label,                                     inline=True)
    embed.add_field(name="💬 Tin nhắn",       value=f"**{len(messages)}**",                                inline=True)
    embed.add_field(name="👤 Người tạo",      value=str(creator) if creator else f"`ID:{user_id}`",        inline=True)
    embed.add_field(name="🔒 Người đóng",     value=closer.mention if closer else "Hệ thống",              inline=True)
    embed.add_field(name="⏱️ Thời lượng",     value=duration_str,                                          inline=True)
    embed.add_field(name="🕐 Thời gian tạo",  value=created_at_str,                                        inline=True)
    embed.add_field(name="🕑 Thời gian đóng", value=close_time.strftime("%d/%m/%Y %H:%M:%S UTC"),          inline=True)
    if mc_name:
        embed.add_field(name="🎮 Minecraft",  value=f"`{mc_name}`",                                        inline=True)
    if item_label:
        embed.add_field(name="📦 Item",       value=item_label,                                            inline=True)
    if creator:
        embed.set_thumbnail(url=creator.display_avatar.url)
    embed.set_footer(text="TuyTam Store • Ticket System")

    if transcript_ch:
        file2 = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")
        await transcript_ch.send(embed=embed, file=file2)

    notes = get_ticket_note(channel.id)
    if notes and transcript_ch:
        note_text = "\n".join([f"**{n['author']}:** {n['note']}" for n in notes])
        note_embed = discord.Embed(
            title="📝 Ghi Chú Nội Bộ",
            description=note_text,
            color=0xFEE75C,
            timestamp=datetime.now(timezone.utc)
        )
        note_embed.set_footer(text=f"Ticket: {ticket_name}")
        await transcript_ch.send(embed=note_embed)

    await channel.delete()

    if creator:
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
            await creator.send(embed=rate_embed, view=RatingView(ticket_name, creator.id))
        except discord.Forbidden:
            pass

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

HELP_CATEGORIES = {
    "chung": {
        "title": "🌐  Lệnh Chung",
        "fields": [
            ("`.ping`",                       "Kiểm tra độ trễ bot"),
            ("`.qr`",                         "Gửi mã QR thanh toán"),
            ("`.botinfo` / `.bi`",            "Thông tin bot (version, ping, uptime)"),
            ("`.serverinfo` / `.si`",         "Thông tin server Discord"),
            ("`.userinfo [@user]` / `.ui`",   "Thông tin thành viên"),
            ("`.sv` / `.dichvu` / `.service`","Xem thông tin dịch vụ Setup Server Discord"),
        ]
    },
    "dichvu": {
        "title": "🛠️  Dịch Vụ Setup Server Discord",
        "fields": [
            ("`.sv` / `.dichvu` / `.service`", "Gửi embed giới thiệu dịch vụ Setup Server Discord"),
            ("📦 Phù hợp với",                 "Game, học tập, shop bán hàng, tiền ảo, trading, nhóm bạn bè…"),
            ("✅ Chất lượng",                  "Thiết kế đúng nhu cầu, dùng bot mạnh (Dyno, MEE6, Carl-bot…)\nGiao diện thẩm mỹ, tối ưu quyền & vai trò"),
            ("💰 Giá",                         "Thoả thuận thoải mái — deal đến khi hai bên hài lòng"),
            ("🔧 Quy trình",                   "1️⃣ Bạn mô tả nhu cầu → 2️⃣ Tư vấn & báo giá → 3️⃣ Setup & bàn giao"),
            ("📩 Liên hệ",                     "Mở ticket hoặc nhắn trực tiếp để được tư vấn miễn phí!"),
        ]
    },
    "ticket": {
        "title": "🎫  Lệnh Ticket",
        "fields": [
            ("`.panel`",                      "Gửi panel tạo ticket *(admin)*"),
            ("`.setpanel #kênh`",             "Chỉ định kênh đặt panel ticket *(admin)*"),
            ("`.done`",                       "Hoàn thành đơn — +1 đơn & give role buyer *(admin/staff)*"),
            ("`.close`",                      "Đóng ticket — gửi transcript + mở form đánh giá *(admin/staff)*"),
            ("`.addnote <nội dung>`",         "Thêm ghi chú nội bộ vào ticket *(admin/staff)*"),
            ("`.ratings`",                    "Xem thống kê đánh giá từ khách *(admin)*"),
            ("`.orderbase`",                  "Gửi thông tin Order Base *(admin)*"),
            ("`.addseller <ID> <tên>`",       "Thêm seller vào danh sách chọn trong ticket *(admin)*"),
            ("`.removeseller <ID hoặc tên>`\n`.delseller` `.xoaseller`", "Xoá seller khỏi danh sách *(admin)*"),
            ("`.listseller`\n`.sellers`",     "Xem danh sách seller hiện tại *(admin)*"),
        ]
    },
    "mod": {
        "title": "🛡️  Lệnh Kiểm Duyệt",
        "fields": [
            ("`.clear <số>` / `.purge`",              "Xoá tin nhắn trong kênh (1–100) *(admin/staff)*"),
            ("`.addrole @user @role`",                "Thêm role cho thành viên *(admin)*"),
            ("`.removerole @user @role`",             "Xoá role của thành viên *(admin)*"),
            ("`.mkchannel <text/voice/category> <tên>`\n`.mkch` `.taokenh`",
                                                      "Tạo kênh mới đồng bộ font server *(admin)*"),
            ("`.createchannel <tên> [text/voice]` / `.cc`", "Tạo kênh cơ bản (không có font) *(admin)*"),
            ("`.deletechannel [#kênh]` / `.dc`",      "Xoá kênh (mặc định: kênh hiện tại) *(admin)*"),
            ("`.rename #kênh <tên mới>`",             "Đổi tên kênh, giữ icon & số đếm *(admin)*"),
            ("`.setperm #kênh @role xem=true ...`",   "Sửa quyền kênh nhanh *(admin)*"),
            ("`.emoji` / `.emoji <emoji>`",           "Thêm emoji từ ảnh/GIF hoặc server khác *(admin)*"),
            ("`.delemoji <emoji hoặc tên>`\n`.deleteemoji` `.xoaemoji`",
                                                      "Xoá emoji khỏi server (paste emoji hoặc gõ tên) *(admin)*"),
        ]
    },
    "giveaway": {
        "title": "🎉  Lệnh Giveaway",
        "fields": [
            ("`.gstart <time> <số người> <phần thưởng>`",  "Tạo giveaway — VD: `.gstart 1h 2 100m` *(admin)*"),
            ("`.gend <message_id>`",                        "Kết thúc giveaway sớm *(admin)*"),
            ("`.greroll <message_id>`",                     "Quay lại người thắng *(admin)*"),
            ("`.gwlist <message_id>`",                      "Xem danh sách người tham gia giveaway *(admin)*"),
            ("`/giveaway`",                                 "Tạo giveaway qua slash command *(admin)*"),
            ("`/gend`",                                     "Kết thúc giveaway qua slash command *(admin)*"),
            ("⚠️ Lưu ý",                                   "Nút **Tham gia** tự ẩn sau khi giveaway kết thúc. Giveaway được khôi phục tự động sau khi bot restart."),
        ]
    },
    "balance": {
        "title": "💰  Hệ Thống Số Dư",
        "fields": [
            ("`+ <số tiền>`",         "Nạp tiền vào (tự trừ phí 5%) — nhập trong kênh balance"),
            ("`- <số tiền>`",         "Chi tiền ra (số dư có thể âm) — nhập trong kênh balance"),
            ("`.balance` / `.bal`",   "Xem số dư & lịch sử giao dịch"),
            ("`.balset <số>`",        "Đặt số dư về giá trị bất kỳ *(admin)*"),
            ("`.balreset`",           "Reset toàn bộ số dư về 0 *(admin)*"),
        ]
    },
    "ai": {
        "title": "🤖  Lệnh AI (Groq — Miễn Phí)",
        "fields": [
            ("`.ai <câu hỏi>`",                   "Chat với AI, nhớ lịch sử 10 tin nhắn gần nhất"),
            ("`.ai tomtat [n]`",                  "Tóm tắt `n` tin nhắn gần nhất trong kênh (mặc định 30, tối đa 100)"),
            ("`.ai dich <ngôn ngữ> <văn bản>`",   "Dịch văn bản sang ngôn ngữ bất kỳ"),
            ("`.ai phantich [@user]`",             "Phân tích phong cách chat của user (mặc định: bạn)"),
            ("`.ai reset`",                        "Xoá lịch sử hội thoại AI của bạn"),
            ("`.mychat`",                          "Xoá lịch sử chat AI của bản thân"),
            ("`.aireset`",                         "Xoá lịch sử AI của tất cả user *(admin)*"),
            ("⚙️ Kênh AI tự động",                "Cài kênh AI riêng qua `.settings` → 🤖 AI Channel\nBot sẽ trả lời MỌI tin nhắn trong kênh đó"),
            ("⚠️ Lưu ý",                           "Cần cài `GROQ_API_KEY` trong Railway. Giới hạn free: 6000 req/ngày."),
        ]
    },
    "invite": {
        "title": "📨  Hệ Thống Invite",
        "fields": [
            ("`.invite [@user]`",           "Xem số lần invite của bản thân hoặc user khác"),
            ("`.invitetop [n]`",            "Bảng xếp hạng invite top N (mặc định 10) *(admin)*"),
            ("`.resetinvite @user`",        "Reset invite của 1 người *(admin)*"),
            ("`.resetinvite all`",          "Reset invite toàn bộ server *(admin)*"),
            ("⚙️ Net invite",               "Net = Tổng − Fake − Đã rời (luôn ≥ 0)"),
            ("⚠️ Fake invite",              "Member join rồi leave trong **10 phút** → không được tính"),
            ("🔒 Lưu ý",                   "Dữ liệu invite hoàn toàn độc lập với giveaway/buyer/ticket/balance\nBot cần quyền **Manage Server** để đọc invites"),
        ]
    },
    "caidat": {
        "title": "⚙️  Lệnh Cài Đặt",
        "fields": [
            ("`.settings` / `.st`",   "Xem & cấu hình toàn bộ bot (kênh, QR, AI, font…) *(admin)*"),
            ("`.setup`",              "Mở menu Setup Server — đổi font, rename hàng loạt *(admin)*"),
            ("`.setpanel #kênh`",     "Chỉ định kênh panel ticket *(admin)*"),
            ("`.sv` / `.dichvu`",     "Xem bảng giá sản phẩm"),
            ("`.giaset`\n`.setgia` `.pricemanager`", "Quản lý bảng giá — sửa/thêm/xoá/reset mục giá *(admin)*"),
            ("⚙️ Font server",        "Font được lưu tự động sau khi rename hàng loạt.\n`.mkchannel` dùng font này để tạo kênh mới."),
        ]
    },
    "kenh": {
        "title": "📌  Kênh & Cấu Hình Quan Trọng",
        "fields": [
            ("Transcript Channel",  "Cài qua `.settings` → embed ticket đóng + file HTML"),
            ("Feedback Channel",    "Cài qua `.settings` → embed đánh giá ⭐ của buyer"),
            ("AI Channel",         "Cài qua `.settings` → 🤖 AI Channel — bot tự trả lời mọi tin"),
            ("Balance Channel",    "Cài qua `.settings` → 💰 gõ `+` / `-` để nạp/chi"),
            ("Proof Channel",      "Cài qua `.settings` → gõ `done` để +1 số đơn"),
            ("Legit Channel",      "Cài qua `.settings` → gõ `+1legit` để +1 số legit"),
            ("Counter Channel",    "Cài qua `.settings` → tự động đếm số ticket"),
        ]
    },
}

# Slash command equivalents (hiển thị trong help chung)
_SLASH_SUMMARY = (
    "`/ping` `/qr` `/botinfo` `/serverinfo` `/userinfo`\n"
    "`/clear` `/addrole` `/removerole` `/createchannel` `/deletechannel`\n"
    "`/giveaway` `/gend`"
)

@bot.command(name="help")
async def help_cmd(ctx, category: str = None):
    if category is None:
        embed = discord.Embed(
            title="📋  Trợ Lý TuyTam Store — Danh Sách Lệnh",
            description=(
                "Dùng **`.help <mục>`** để xem chi tiết từng nhóm lệnh.\n"
                "Slash commands `/` cũng khả dụng cho hầu hết lệnh!"
            ),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        cats = [
            ("🌐 `.help chung`",    "`.ping` `.qr` `.botinfo` `.serverinfo` `.userinfo`"),
            ("🛠️ `.help dichvu`",   "`.sv` — Giới thiệu dịch vụ Setup Server Discord"),
            ("🎫 `.help ticket`",   "`.panel` `.done` `.close` `.addnote` `.addseller` `.listseller`"),
            ("🛡️ `.help mod`",      "`.clear` `.addrole` `.removerole` `.mkchannel` `.emoji` `.delemoji`"),
            ("🎉 `.help giveaway`", "`.gstart` `.gend` `.greroll` `.gwlist`  +  `/giveaway` `/gend`"),
            ("💰 `.help balance`",  "`.balance` `.balset` `.balreset`  +  nạp/chi trong kênh balance"),
            ("🤖 `.help ai`",       "`.ai` `.ai tomtat` `.ai dich` `.ai phantich` `.mychat` `.aireset`"),
            ("📨 `.help invite`",   "`.invite` `.invitetop` `.resetinvite`"),
            ("⚙️ `.help caidat`",   "`.settings` `.setup` `.setpanel` `.sv` `.giaset`"),
            ("📌 `.help kenh`",     "Transcript, Feedback, AI, Balance, Proof, Legit, Counter channel"),
        ]
        for name, desc in cats:
            embed.add_field(name=name, value=desc, inline=False)
        embed.add_field(
            name="⚡ Slash Commands",
            value=_SLASH_SUMMARY,
            inline=False
        )
        embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  Prefix: .  |  Slash: /  |  *(admin)* = chỉ admin dùng được")
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
    for cmd_str, desc in data["fields"]:
        embed.add_field(name=cmd_str, value=desc, inline=False)
    embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  Dùng .help để xem tất cả mục  |  *(admin)* = chỉ admin")
    await ctx.reply(embed=embed)

# ================= MODERATION =================
@bot.command(name="clear", aliases=["purge"])
async def clear_cmd(ctx, amount: int = 10):
    if ctx.author.id not in ADMIN_IDS:
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
    if not can_use_dangerous_cmd(ctx.author.id, "createchannel"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
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
    if not can_use_dangerous_cmd(ctx.author.id, "deletechannel"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
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

# ── Lưu/load giveaway — dùng section GIVEAWAY riêng ──
def save_giveaways_data():
    _save_giveaway_section(active_giveaways)

def load_giveaways_data() -> dict:
    raw = _load_giveaway_section()
    result = {}
    for mid_str, gw in raw.items():
        gw = dict(gw)
        gw["entries"] = set(gw.get("entries", []))
        result[int(mid_str)] = gw
    return result

async def end_giveaway(message_id: int, channel: discord.TextChannel, winners_count: int, prize: str, host_id: int):
    try:
        msg = await channel.fetch_message(message_id)
    except:
        return
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    entries = [u async for u in reaction.users() if not u.bot] if reaction else []
    if not entries:
        embed = discord.Embed(
            title="🎉  Giveaway Kết Thúc",
            description="❌ Không có ai tham gia giveaway này.",
            color=0x99AAB5, timestamp=datetime.now(timezone.utc)
        )
    try:
        await msg.edit(embed=embed, view=None)
    except:
        pass
    await channel.send("❌ Giveaway kết thúc nhưng không có người tham gia!")
    if message_id in active_giveaways:
        active_giveaways[message_id]["ended"] = True
    save_giveaways_data()
    return
    count = min(winners_count, len(entries))
    winners = random.sample(entries, count)
    winner_mentions = ", ".join(w.mention for w in winners)
    embed = discord.Embed(
        title="🎉  Giveaway Kết Thúc!",
        description=f"**Phần thưởng:** {prize}\n**🏆 Winner:** {winner_mentions}",
        color=0xF1C40F, timestamp=datetime.now(timezone.utc)
    )
    host = channel.guild.get_member(host_id)
    embed.set_footer(text=f"Host: {_uname_plain(host) if host else host_id}")
    await msg.edit(embed=embed, view=None)
    await channel.send(f"🎊 Chúc mừng {winner_mentions}! Bạn đã thắng **{prize}**!")
    if message_id in active_giveaways:
        active_giveaways[message_id]["ended"] = True
        active_giveaways[message_id]["winner_ids"] = [w.id for w in winners]
    save_giveaways_data()

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
    embed.set_footer(text=f"Host: {_uname_plain(ctx.author)}  •  Kết thúc lúc")
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")
    try:
        await ctx.message.delete()
    except:
        pass
    active_giveaways[msg.id] = {
        "type": "reaction",                 # phân biệt với slash /giveaway
        "channel_id": ctx.channel.id,
        "winners": w_count,
        "prize": prize,
        "host_id": ctx.author.id,
        "end_time": ends_at,
        "ended": False,
    }
    save_giveaways_data()

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
        entries_reaction = [u async for u in reaction.users() if not u.bot] if reaction else []
        gw = active_giveaways.get(message_id, {})
        entries_btn = [ctx.guild.get_member(uid) for uid in gw.get("entries", set())]
        entries_btn = [m for m in entries_btn if m]
        entries = entries_reaction or entries_btn
        if not entries:
            return await ctx.reply("❌ Không có người tham gia hợp lệ!")
        winner = random.choice(entries)
        prize = gw.get("prize", "phần thưởng")
        await ctx.send(f"🎊 **Reroll!** Chúc mừng {winner.mention}! Bạn đã thắng **{prize}**!")
    except discord.NotFound:
        await ctx.reply("❌ Không tìm thấy tin nhắn!")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")

@bot.command(name="gwlist")
async def gwlist_cmd(ctx, message_id: int = None):
    """
    Xem danh sách người tham gia giveaway.
    Dùng: .gwlist <message_id>
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not message_id:
        return await ctx.reply("❌ Dùng: `.gwlist <message_id>`\nVí dụ: `.gwlist 1234567890123456789`")

    gw = active_giveaways.get(message_id)
    if not gw:
        return await ctx.reply("❌ Không tìm thấy giveaway với ID này!\n> ℹ️ Giveaway có thể đã bị xoá khỏi bộ nhớ. Chỉ hoạt động khi bot còn giữ data.")

    entries = gw.get("entries", set())
    if not isinstance(entries, set):
        entries = set(entries)

    prize    = gw.get("prize", "?")
    ended    = gw.get("ended", False)
    w_count  = gw.get("winners", 1)
    end_time = gw.get("end_time", 0)

    status_str = "✅ Đã kết thúc" if ended else f"🟢 Đang chạy — kết thúc <t:{int(end_time)}:R>"

    embed = discord.Embed(
        title="👥  Danh Sách Người Tham Gia Giveaway",
        color=0xF1C40F if not ended else 0x99AAB5,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏆 Phần thưởng", value=prize,            inline=True)
    embed.add_field(name="🎊 Số người thắng", value=f"**{w_count}**", inline=True)
    embed.add_field(name="📊 Trạng thái",   value=status_str,      inline=False)
    embed.add_field(name="👥 Tổng tham gia", value=f"**{len(entries)}** người", inline=True)

    if entries:
        mentions = []
        for uid in entries:
            member = ctx.guild.get_member(int(uid))
            mentions.append(member.mention if member else f"`{uid}`")

        # Chia thành nhiều field nếu danh sách dài (giới hạn 1024 ký tự/field)
        chunk_size = 20
        chunks = [mentions[i:i+chunk_size] for i in range(0, len(mentions), chunk_size)]
        for idx, chunk in enumerate(chunks):
            field_name = "📋 Danh sách" if idx == 0 else f"📋 (tiếp {idx+1})"
            embed.add_field(name=field_name, value=" ".join(chunk), inline=False)
    else:
        embed.add_field(name="📋 Danh sách", value="*(Chưa có ai tham gia)*", inline=False)

    if gw.get("winner_ids"):
        winner_mentions = ", ".join(
            ctx.guild.get_member(wid).mention if ctx.guild.get_member(wid) else f"`{wid}`"
            for wid in gw["winner_ids"]
        )
        embed.add_field(name="🏆 Winner", value=winner_mentions, inline=False)

    embed.set_footer(text=f"Message ID: {message_id}  •  Yêu cầu bởi {_uname_plain(ctx.author)}")
    await ctx.reply(embed=embed)

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
    host_id = gw.get("host_id") or gw.get("host", 0)
    await end_giveaway(message_id, ctx.channel, gw["winners"], gw["prize"], host_id)
    await ctx.reply("✅ Đã kết thúc giveaway sớm!")

# ================= INFO COMMANDS =================
@bot.command(name="botinfo", aliases=["bi"])
async def botinfo_cmd(ctx):
    import platform, sys, time
    latency = round(bot.latency * 1000)
    lat_status = "🟢 Tốt" if latency < 100 else ("🟡 Bình thường" if latency < 200 else "🔴 Chậm")

    total_users  = sum(g.member_count or 0 for g in bot.guilds)
    total_ch     = sum(len(g.channels) for g in bot.guilds)
    total_roles  = sum(len(g.roles) for g in bot.guilds)
    cmds_count   = len(bot.commands)

    embed = discord.Embed(
        title=f"🤖  {bot.user.name}",
        description=f"Bot ticket & quản lý giao dịch của **TuyTam Store**",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(name="👤  Tag",          value=f"`{bot.user}`",                               inline=True)
    embed.add_field(name="🆔  ID",           value=f"`{bot.user.id}`",                            inline=True)
    embed.add_field(name="🏷️  Version",      value=f"`v{BOT_VERSION}` ({BOT_UPDATED})",           inline=True)

    embed.add_field(name="🏓  Latency",      value=f"**{latency}ms** {lat_status}",          inline=True)
    embed.add_field(name="🐍  Python",       value=f"`{platform.python_version()}`",         inline=True)
    embed.add_field(name="📚  discord.py",   value=f"`{discord.__version__}`",               inline=True)

    embed.add_field(name="🌐  Servers",      value=f"**{len(bot.guilds)}** server",           inline=True)
    embed.add_field(name="👥  Tổng users",   value=f"**{total_users:,}** người",             inline=True)
    embed.add_field(name="💬  Tổng kênh",    value=f"**{total_ch}** kênh",                   inline=True)

    embed.add_field(name="🎭  Tổng roles",   value=f"**{total_roles}** roles",               inline=True)
    embed.add_field(name="⌨️  Lệnh",         value=f"**{cmds_count}** prefix + slash",       inline=True)
    embed.add_field(name="🖥️  OS",           value=f"`{platform.system()} {platform.release()}`", inline=True)

    embed.set_footer(
        text=f"TuyTam Store  •  Prefix: .  |  Được yêu cầu bởi {_uname_plain(ctx.author)}",
        icon_url=ctx.author.display_avatar.url
    )
    await ctx.reply(embed=embed)

@bot.command(name="serverinfo", aliases=["si"])
async def serverinfo_cmd(ctx):
    g = ctx.guild

    bots    = sum(1 for m in g.members if m.bot)
    humans  = (g.member_count or 0) - bots
    online  = sum(1 for m in g.members if m.status != discord.Status.offline)

    cats    = len(g.categories)
    text_ch = len(g.text_channels)
    voice_ch= len(g.voice_channels)
    stage_ch= len(g.stage_channels)
    forum_ch= len([c for c in g.channels if isinstance(c, discord.ForumChannel)])

    verify_map = {
        discord.VerificationLevel.none:    "Không",
        discord.VerificationLevel.low:     "Thấp",
        discord.VerificationLevel.medium:  "Trung bình",
        discord.VerificationLevel.high:    "Cao",
        discord.VerificationLevel.highest: "Rất cao",
    }
    verify = verify_map.get(g.verification_level, str(g.verification_level))

    data   = load_data()
    tickets_total = data.get("ticket", 0)

    embed = discord.Embed(
        title=f"🌐  {g.name}",
        description=g.description or "",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    if g.banner:
        embed.set_image(url=g.banner.url)

    embed.add_field(name="🆔  ID",              value=f"`{g.id}`",                                                       inline=True)
    embed.add_field(name="👑  Owner",            value=g.owner.mention if g.owner else "N/A",                            inline=True)
    embed.add_field(name="📅  Ngày tạo",         value=f"<t:{int(g.created_at.timestamp())}:F>",                         inline=True)

    embed.add_field(
        name="👥  Members",
        value=f"**{g.member_count:,}** tổng\n🟢 Online: **{online}** | 👤 Người: **{humans}** | 🤖 Bot: **{bots}**",
        inline=False
    )

    embed.add_field(
        name="💬  Kênh",
        value=f"📁 Categories: **{cats}** | 💬 Text: **{text_ch}** | 🔊 Voice: **{voice_ch}**"
              + (f" | 🎭 Stage: **{stage_ch}**" if stage_ch else "")
              + (f" | 📋 Forum: **{forum_ch}**" if forum_ch else ""),
        inline=False
    )

    embed.add_field(name="🎭  Roles",            value=f"**{len(g.roles)}** roles",                                      inline=True)
    embed.add_field(name="😀  Emojis",           value=f"**{len(g.emojis)}** / {g.emoji_limit}",                        inline=True)
    embed.add_field(name="🔒  Xác minh",         value=verify,                                                           inline=True)

    boost_bar = "⭐" * g.premium_tier if g.premium_tier else "—"
    embed.add_field(
        name="🚀  Nitro Boost",
        value=f"Level **{g.premium_tier}** {boost_bar}\n💎 **{g.premium_subscription_count}** boosts",
        inline=True
    )

    embed.add_field(name="🎫  Tổng ticket",      value=f"**{tickets_total}** đơn đã tạo",                               inline=True)
    embed.add_field(name="🖼️  Features",          value=f"**{len(g.features)}** tính năng",                             inline=True)

    embed.set_footer(
        text=f"TuyTam Store  •  Được yêu cầu bởi {_uname_plain(ctx.author)}",
        icon_url=ctx.author.display_avatar.url
    )
    await ctx.reply(embed=embed)

@bot.command(name="userinfo", aliases=["ui"])
async def userinfo_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author

    roles = [r for r in reversed(member.roles) if r != ctx.guild.default_role]
    roles_str = " ".join(r.mention for r in roles[:15]) + (f"\n*...và {len(roles)-15} roles nữa*" if len(roles) > 15 else "")
    roles_str = roles_str or "Không có"

    key_perms = []
    if member.guild_permissions.administrator:        key_perms.append("👑 Administrator")
    if member.guild_permissions.manage_guild:         key_perms.append("⚙️ Manage Server")
    if member.guild_permissions.manage_channels:      key_perms.append("📁 Manage Channels")
    if member.guild_permissions.manage_roles:         key_perms.append("🎭 Manage Roles")
    if member.guild_permissions.manage_messages:      key_perms.append("🗑️ Manage Messages")
    if member.guild_permissions.kick_members:         key_perms.append("👢 Kick")
    if member.guild_permissions.ban_members:          key_perms.append("🔨 Ban")
    if member.guild_permissions.moderate_members:     key_perms.append("🔇 Timeout")
    perm_str = " | ".join(key_perms) if key_perms else "Không có quyền đặc biệt"

    data = load_data()
    user_tickets = sum(
        1 for t in data.get("ticket_notes", {}).values()
        for note in t if note.get("author", "").startswith(str(member))
    )

    status_map = {
        discord.Status.online:    "🟢 Online",
        discord.Status.idle:      "🟡 Idle",
        discord.Status.dnd:       "🔴 Do Not Disturb",
        discord.Status.offline:   "⚫ Offline",
    }
    status_str = status_map.get(member.status, str(member.status))

    activity_str = "Không có"
    if member.activities:
        for act in member.activities:
            if isinstance(act, discord.Game):
                activity_str = f"🎮 Đang chơi **{act.name}**"
                break
            elif isinstance(act, discord.Streaming):
                activity_str = f"📡 Stream: **{act.name}**"
                break
            elif isinstance(act, discord.CustomActivity) and act.name:
                activity_str = f"💬 {act.name}"
                break
            elif isinstance(act, discord.Activity):
                activity_str = f"▶️ {act.name}"
                break

    joined_str = f"<t:{int(member.joined_at.timestamp())}:F>" if member.joined_at else "N/A"

    sorted_members = sorted(
        [m for m in ctx.guild.members if m.joined_at],
        key=lambda m: m.joined_at
    )
    join_pos = next((i+1 for i, m in enumerate(sorted_members) if m.id == member.id), "?")

    embed = discord.Embed(
        title=f"👤  {_uname(member)}",
        description=f"{'🤖 Bot' if member.bot else '👤 Người dùng'} | {status_str}",
        color=member.color if member.color.value else 0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(name="🏷️  Tag",          value=f"`{member.name}`",                                             inline=True)
    embed.add_field(name="🆔  ID",            value=f"`{member.id}`",                                          inline=True)
    embed.add_field(name="🤖  Bot",           value="✅ Có" if member.bot else "❌ Không",                      inline=True)

    embed.add_field(name="📅  Tạo tài khoản", value=f"<t:{int(member.created_at.timestamp())}:F>",             inline=True)
    embed.add_field(name="📥  Vào server",    value=f"{joined_str}\n*(thứ **#{join_pos}** vào server)*",        inline=True)
    embed.add_field(name="🎨  Màu role",      value=str(member.color) if member.color.value else "#mặc định",  inline=True)

    embed.add_field(name="🎮  Hoạt động",     value=activity_str,                                               inline=False)

    embed.add_field(name="🔑  Quyền nổi bật", value=perm_str,                                                   inline=False)

    embed.add_field(name=f"🎭  Roles ({len(roles)})", value=roles_str,                                          inline=False)

    embed.set_footer(
        text=f"TuyTam Store  •  Được yêu cầu bởi {_uname_plain(ctx.author)}",
        icon_url=ctx.author.display_avatar.url
    )
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
        description=f"Bot sẽ gửi panel ticket vào {channel.mention}.",
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

    @discord.ui.button(label="🏷️ Seller Role", style=discord.ButtonStyle.grey, row=0)
    async def change_seller_role(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_seller_role", "Seller Role ID"))

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

    @discord.ui.button(label="✅ Legit Channel", style=discord.ButtonStyle.green, row=2)
    async def change_legit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_legit_channel", "Legit Channel"))

    @discord.ui.button(label="📌 Panel Channel", style=discord.ButtonStyle.green, row=2)
    async def change_panel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("panel_channel_id", "Panel Channel"))

    @discord.ui.button(label="🔖 Proof Channel", style=discord.ButtonStyle.blurple, row=3)
    async def change_proof(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_proof_channel", "Proof Channel"))

    @discord.ui.button(label="🏆 Role Mua Hàng", style=discord.ButtonStyle.blurple, row=4)
    async def change_buy_roles(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await _show_buy_role_panel(interaction)

    @discord.ui.button(label="🔒 Lệnh Nguy Hiểm", style=discord.ButtonStyle.danger, row=4)
    async def dangerous_cmds(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message(
                "❌ Chỉ admin mới chỉnh được phân quyền lệnh nguy hiểm.", ephemeral=True
            )
        embed = _build_dangerous_embed()
        await interaction.response.send_message(embed=embed, view=DangerousCommandsView(), ephemeral=True)

    @discord.ui.button(label="🤖 AI Channel", style=discord.ButtonStyle.blurple, row=4)
    async def change_ai_channel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_ai_channel", "AI Chat Channel"))

# ================= DANGEROUS COMMANDS SETTINGS =================
# Danh sách lệnh nguy hiểm — OWNER_ID tự chọn ai được dùng
# Lưu vào section CFG với key "dangerous_cmd_overrides"
# Format: {"cmd_name": "owner_only" | "admin"}

DANGEROUS_CMDS = {
    "createchannel": "🏗️ Tạo kênh",
    "deletechannel": "🗑️ Xoá kênh",
    "balreset":      "💸 Reset số dư",
    "balset":        "💰 Đặt số dư",
    "setup":         "⚙️ Setup server",
    "setperm":       "🔐 Sửa quyền kênh",
    "rename":        "✏️ Đổi tên kênh",
    "emoji":         "😀 Thêm emoji",
}

def get_dangerous_overrides() -> dict:
    cfg = _get_section("CFG")
    return cfg.get("dangerous_cmd_overrides", {})

def save_dangerous_overrides(overrides: dict):
    cfg = _get_section("CFG").copy()
    cfg["dangerous_cmd_overrides"] = overrides
    _set_section("CFG", cfg)

def can_use_dangerous_cmd(user_id: int, cmd_name: str) -> bool:
    return user_id in ADMIN_IDS

class DangerousCommandsView(View):
    """Panel chọn quyền từng lệnh nguy hiểm — chỉ OWNER mới mở được."""
    def __init__(self):
        super().__init__(timeout=180)
        self._build_buttons()

    def _build_buttons(self):
        overrides = get_dangerous_overrides()
        for i, (cmd, label) in enumerate(DANGEROUS_CMDS.items()):
            level = overrides.get(cmd, "owner_only")
            is_owner_only = (level == "owner_only")
            btn = discord.ui.Button(
                label=f"{label}: {'🔴 Chỉ Owner' if is_owner_only else '🟢 Cả Admin'}",
                style=discord.ButtonStyle.danger if is_owner_only else discord.ButtonStyle.success,
                custom_id=f"dcmd_{cmd}",
                row=i // 3
            )
            btn.callback = self._make_callback(cmd)
            self.add_item(btn)

        close_btn = discord.ui.Button(
            label="❌ Đóng",
            style=discord.ButtonStyle.grey,
            custom_id="dcmd_close",
            row=len(DANGEROUS_CMDS) // 3 + 1
        )
        close_btn.callback = self._close_callback
        self.add_item(close_btn)

    def _make_callback(self, cmd: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id not in ADMIN_IDS:
                return await interaction.response.send_message("❌ Chỉ admin mới chỉnh được.", ephemeral=True)
            overrides = get_dangerous_overrides()
            current = overrides.get(cmd, "owner_only")
            overrides[cmd] = "admin" if current == "owner_only" else "owner_only"
            save_dangerous_overrides(overrides)
            new_view = DangerousCommandsView()
            embed = _build_dangerous_embed()
            await interaction.response.edit_message(embed=embed, view=new_view)
        return callback

    async def _close_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.delete_original_response()

def _build_dangerous_embed() -> discord.Embed:
    overrides = get_dangerous_overrides()
    embed = discord.Embed(
        title="🔒  Phân Quyền Lệnh Nguy Hiểm",
        description=(
            "Nhấn nút để **toggle** quyền của từng lệnh.\n"
            "🔴 **Chỉ Owner** — chỉ bạn dùng được\n"
            "🟢 **Cả Admin** — tất cả admin trong `ADMIN_IDS` dùng được"
        ),
        color=0xED4245,
        timestamp=datetime.now(timezone.utc)
    )
    for cmd, label in DANGEROUS_CMDS.items():
        level = overrides.get(cmd, "owner_only")
        val = "🔴 Chỉ Owner" if level == "owner_only" else "🟢 Cả Admin"
        embed.add_field(name=label, value=val, inline=True)
    embed.set_footer(text="TuyTam Store  •  Chỉ Owner mới chỉnh được")
    return embed

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

    cat_id      = get_cfg_category()
    role_id     = get_cfg_support_role()
    seller_id   = get_cfg_seller_role()
    counter_id  = get_cfg_counter_channel()
    balance_id  = get_cfg_balance_channel()
    legit_id    = get_cfg_legit_channel()
    proof_id    = get_cfg_proof_channel()
    ai_ch_id    = get_cfg_ai_channel()
    qr_path     = get_qr_path()
    buy_roles   = get_buy_roles()

    cat_val     = f"<#{cat_id}>" if cat_id else "❌ Chưa cài"
    role_val    = f"<@&{role_id}>" if role_id else "❌ Chưa cài"
    seller_val  = f"<@&{seller_id}>" if seller_id else "❌ Chưa cài — nhấn **🏷️ Seller Role**"
    counter_val = f"<#{counter_id}>" if counter_id else "❌ Chưa cài"
    balance_val = f"<#{balance_id}>" if balance_id else "❌ Chưa cài — nhấn **💰 Balance Channel**"
    legit_val   = f"<#{legit_id}>" if legit_id else "❌ Chưa cài — nhấn **✅ Legit Channel**"
    proof_val   = f"<#{proof_id}>" if proof_id else "❌ Chưa cài — nhấn **🔖 Proof Channel**"
    ai_ch_val   = f"<#{ai_ch_id}>" if ai_ch_id else "❌ Chưa cài — nhấn **🤖 AI Channel**"
    qr_val      = "✅ Đã có" if qr_path and os.path.exists(qr_path) else "❌ Chưa có"
    if buy_roles:
        buy_role_val = "\n".join(
            f"› **{r.get('label','?')}** — {fmt_amount(r.get('min_amount',0))} → {fmt_amount(r['max_amount']) if r.get('max_amount') else '∞'}"
            for r in buy_roles
        )
    else:
        buy_role_val = "❌ Chưa cài — nhấn **🏆 Role Mua Hàng**"

    embed = discord.Embed(
        title="⚙️  Cấu Hình Hiện Tại",
        description="Nhấn các nút bên dưới để chỉnh sửa từng mục.",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📌  Panel Channel",   value=panel_value,  inline=False)
    embed.add_field(name="📂  Ticket Category",  value=cat_val,      inline=True)
    embed.add_field(name="🛡️  Support Role",     value=role_val,     inline=True)
    embed.add_field(name="🏷️  Seller Role",      value=seller_val,   inline=True)
    embed.add_field(name="🔢  Counter Channel",  value=counter_val,  inline=True)
    embed.add_field(name="💰  Balance Channel",  value=balance_val,  inline=True)
    embed.add_field(name="✅  Legit Channel",    value=legit_val,    inline=True)
    embed.add_field(name="🔖  Proof Channel",    value=proof_val,    inline=True)
    embed.add_field(name="🤖  AI Chat Channel",  value=ai_ch_val,    inline=True)
    embed.add_field(name="📱  Mã QR",            value=qr_val,       inline=True)
    embed.add_field(name="🏆  Role Mua Hàng",    value=buy_role_val, inline=False)
    embed.set_footer(text="TuyTam Store  •  Dùng .st hoặc .settings")
    await ctx.reply(embed=embed, view=SettingsView())

@bot.command()
async def close(ctx):
    if not is_staff(ctx.author):
        return await ctx.reply("❌ Bạn không có quyền.")
    if not (ctx.channel.topic and "|" in ctx.channel.topic):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    await _close_ticket(ctx.channel, bot, closer=ctx.author)

@bot.command(name="done")
async def done_cmd(ctx, amount_str: str = None):
    """
    Đánh dấu hoàn thành đơn: .done 50k / .done 1tr5 / .done 200000
    Cộng số tiền vào tổng của buyer → give role phù hợp.
    """
    if not is_staff(ctx.author):
        return await ctx.reply("❌ Bạn không có quyền.")
    if not (ctx.channel.topic and "|" in ctx.channel.topic):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    if not amount_str:
        return await ctx.reply("❌ Thiếu số tiền! Ví dụ: `.done 50k`, `.done 1tr5`, `.done 200000`")

    amount = parse_amount(amount_str)
    if amount is None or amount <= 0:
        return await ctx.reply(
            f"❌ Số tiền `{amount_str}` không hợp lệ!\n"
            f"Ví dụ đúng: `50k` `1tr` `1tr5` `200000`"
        )

    parts = ctx.channel.topic.split("|")
    try:
        user_id = int(parts[0]) if parts[0].isdigit() else None
    except Exception:
        user_id = None

    if not user_id:
        return await ctx.reply("❌ Không đọc được thông tin buyer từ ticket.")

    trade_type = parts[2] if len(parts) > 2 else None
    if trade_type not in ("sell", "buy"):
        return await ctx.reply("ℹ️ Ticket dịch vụ / hỗ trợ không tính vào đơn mua hàng.")

    buyer = ctx.guild.get_member(user_id)
    if not buyer:
        return await ctx.reply(f"❌ Không tìm thấy buyer (ID: `{user_id}`) — họ có thể đã rời server.")

    data = load_data()
    completed_key = f"completed_{ctx.channel.id}"
    if data.get(completed_key):
        total = get_user_total_spent(user_id)
        return await ctx.reply(
            f"⚠️ Đơn này đã được đánh dấu hoàn thành rồi!\n"
            f"Buyer: {buyer.mention} — tổng đã mua: **{fmt_amount(total)}**"
        )

    data[completed_key] = True
    save_data(data)

    new_total = add_user_spent(user_id, amount)
    role_cfg  = await auto_give_buy_roles(ctx.guild, buyer, new_total)

    buy_roles = get_buy_roles()
    embed = discord.Embed(
        title="✅ Hoàn Thành Đơn",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 Buyer",       value=buyer.mention,           inline=True)
    embed.add_field(name="💵 Đơn này",     value=f"**{fmt_amount(amount)}**", inline=True)
    embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(new_total)}**", inline=True)

    if role_cfg:
        role_obj = ctx.guild.get_role(role_cfg.get("role_id", 0))
        embed.add_field(
            name="🏆 Role hiện tại",
            value=role_obj.mention if role_obj else f"**{role_cfg.get('label','?')}**",
            inline=False
        )
    elif buy_roles:
        next_r = buy_roles[0]
        need   = next_r.get("min_amount", 0) - new_total
        embed.add_field(
            name="⏳ Role tiếp theo",
            value=f"**{next_r.get('label','?')}** — cần thêm **{fmt_amount(need)}**",
            inline=False
        )
    else:
        embed.add_field(
            name="⚙️ Chưa cấu hình role",
            value="Dùng `.setup` → 🏆 Cài Role Mua Hàng",
            inline=False
        )

    embed.set_footer(text=f"Xác nhận bởi {_uname_plain(ctx.author)}")
    await ctx.reply(embed=embed)

@bot.command(name="addnote")
async def addnote_cmd(ctx, *, note: str = None):
    if ctx.author.id not in ADMIN_IDS:
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
        url = self.url_input.value.strip()
        if url:
            import urllib.request
            try:
                qr_path = QR_FILE
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

            qr_path = QR_FILE
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
    def __init__(self, message_id: int = None):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="🎉 Tham gia", style=discord.ButtonStyle.primary, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: Button):
        mid = interaction.message.id
        gw = active_giveaways.get(mid) or active_giveaways.get(str(mid))
        if not gw:
            return await interaction.response.send_message("❌ Giveaway này không còn hoạt động.", ephemeral=True)
        if gw.get("ended"):
            return await interaction.response.send_message("❌ Giveaway đã kết thúc rồi!", ephemeral=True)

        uid = interaction.user.id
        entries = gw.setdefault("entries", set())
        if not isinstance(entries, set):
            gw["entries"] = set(entries)
            entries = gw["entries"]

        if uid in entries:
            entries.discard(uid)
            msg_reply = "↩️ Bạn đã **rút khỏi** giveaway."
        else:
            entries.add(uid)
            msg_reply = "✅ Bạn đã **tham gia** giveaway!"

        save_giveaways_data()

        try:
            msg = await interaction.channel.fetch_message(mid)
            embed = msg.embeds[0]
            updated = False
            for i, field in enumerate(embed.fields):
                if "Người tham gia" in field.name:
                    embed.set_field_at(i, name=field.name, value=f"**{len(entries)}** người", inline=field.inline)
                    updated = True
                    break
            if updated:
                await msg.edit(embed=embed)
        except Exception as e:
            print(f"[GIVEAWAY] ⚠️ Không cập nhật được embed: {e}")

        await interaction.response.send_message(msg_reply, ephemeral=True)

async def giveaway_timer(channel_id: int, message_id: int, winners_count: int, seconds: int):
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
    embed.set_footer(text=f"Host: {_uname_plain(host) if host else gw['host']}")
    await msg.edit(embed=embed, view=None)
    await channel.send(f"🎊 Chúc mừng {winner_mentions}! Bạn đã thắng **{gw['prize']}**!")

    gw["winner_ids"] = winner_ids
    save_giveaways_data()

    if gw.get("send_invite", False):
        await _check_winner_invites(channel, winner_ids, gw["prize"])

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
        dur = self.duration.value.strip()
        unit = dur[-1].lower()
        try:
            val = int(dur[:-1])
        except:
            return await interaction.response.send_message("❌ Thời gian không hợp lệ! Dùng: `30s`, `10m`, `1h`, `2d`", ephemeral=True)
        seconds = {"s": val, "m": val*60, "h": val*3600, "d": val*86400}.get(unit)
        if not seconds:
            return await interaction.response.send_message("❌ Đơn vị thời gian không hợp lệ! Dùng: `s`, `m`, `h`, `d`", ephemeral=True)

        try:
            w_count = int(self.winners_count.value.strip())
            if w_count < 1: raise ValueError
        except:
            return await interaction.response.send_message("❌ Số người trúng thưởng phải là số nguyên dương!", ephemeral=True)

        end_time = datetime.now(timezone.utc).timestamp() + seconds

        confirm_view = GiveawayConfirmView(
            host=interaction.user,
            channel=interaction.channel,
            prize=self.prize.value,
            w_count=w_count,
            seconds=seconds,
            end_time=end_time,
            description=self.description.value or "",
        )
        embed_preview = confirm_view.build_preview_embed()
        await interaction.response.send_message(
            content="## ⚙️ Xác nhận trước khi đăng giveaway",
            embed=embed_preview,
            view=confirm_view,
            ephemeral=True
        )

async def _check_winner_invites(channel: discord.TextChannel, winner_ids: list, prize: str):
    """
    Kiểm tra số lượng invite của từng winner (giống lệnh .invite)
    và gửi embed tổng hợp vào kênh giveaway.
    """
    guild = channel.guild
    lines = []
    medals = ["🥇", "🥈", "🥉"]

    for i, uid in enumerate(winner_ids):
        icon   = medals[i] if i < len(medals) else f"`{i+1}.`"
        member = guild.get_member(uid)
        name   = _uname(member) if member else f"<@{uid}>"
        total, fake, left, net = _get_net_invites(uid)
        lines.append(
            f"{icon} **{name}**\n"
            f"  ✅ Net: **{net}**  •  📊 Tổng: `{total}`  •  ⚠️ Fake: `{fake}`  •  🚪 Rời: `{left}`"
        )

    embed = discord.Embed(
        title="📨  Thống Kê Invite — Winner Giveaway",
        description="\n".join(lines) if lines else "*(không có winner nào)*",
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏆 Phần thưởng", value=prize, inline=False)
    embed.set_footer(text="Net = Tổng − Fake − Đã rời  •  TuyTam Store")
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[GIVEAWAY] ⚠️ Không gửi được check invite winner: {e}")

class GiveawayConfirmView(View):
    """
    View xác nhận giveaway — hiển thị ephemeral cho admin.
    Cho phép bật/tắt gửi invite link cho winner trước khi xác nhận đăng.
    """
    def __init__(self, host, channel, prize, w_count, seconds, end_time, description):
        super().__init__(timeout=120)
        self.host        = host
        self.channel     = channel
        self.prize       = prize
        self.w_count     = w_count
        self.seconds     = seconds
        self.end_time    = end_time
        self.description = description
        self.send_invite = False   # mặc định TẮT
        self._update_button_label()

    def _update_button_label(self):
        for item in self.children:
            if getattr(item, "custom_id", None) == "gw_toggle_invite":
                if self.send_invite:
                    item.label  = "📨 Check Invite Winner: BẬT"
                    item.style  = discord.ButtonStyle.success
                else:
                    item.label  = "📨 Check Invite Winner: TẮT"
                    item.style  = discord.ButtonStyle.secondary
                break

    def build_preview_embed(self) -> discord.Embed:
        invite_status = "✅ **BẬT** — Bot sẽ tự kiểm tra & hiển thị số invite của winner" if self.send_invite \
                   else "❌ **TẮT** — Không kiểm tra invite tự động"
        embed = discord.Embed(
            title="👀  Xem Trước Giveaway",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🏆 Phần thưởng",       value=self.prize,                   inline=False)
        embed.add_field(name="🎊 Số người thắng",    value=f"**{self.w_count}** người",   inline=True)
        embed.add_field(name="⏰ Kết thúc",           value=f"<t:{int(self.end_time)}:R>", inline=True)
        embed.add_field(name="📨 Kiểm tra Invite Winner", value=invite_status,            inline=False)
        if self.description:
            embed.add_field(name="📝 Mô tả", value=self.description, inline=False)
        embed.set_footer(text="Nhấn Toggle để bật/tắt • Nhấn Xác Nhận để đăng")
        return embed

    @discord.ui.button(label="📨 Check Invite Winner: TẮT", style=discord.ButtonStyle.secondary, custom_id="gw_toggle_invite")
    async def toggle_invite(self, interaction: discord.Interaction, button: Button):
        self.send_invite = not self.send_invite
        self._update_button_label()
        await interaction.response.edit_message(
            embed=self.build_preview_embed(),
            view=self
        )

    @discord.ui.button(label="✅ Xác Nhận & Đăng", style=discord.ButtonStyle.primary, custom_id="gw_confirm")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        self.stop()

        for item in self.children:
            item.disabled = True

        end_time = self.end_time
        embed = discord.Embed(
            title="🎉  GIVEAWAY!",
            description=self.description or "Nhấn nút **🎉 Tham gia** để tham dự!",
            color=0xF1C40F,
            timestamp=datetime.fromtimestamp(end_time, tz=timezone.utc)
        )
        embed.add_field(name="🏆  Phần thưởng",    value=self.prize,                          inline=False)
        embed.add_field(name="🎊  Số người thắng", value=f"**{self.w_count}** người",          inline=True)
        embed.add_field(name="👥  Người tham gia", value="**0** người",                        inline=True)
        embed.add_field(name="⏰  Kết thúc",       value=f"<t:{int(end_time)}:R>",             inline=True)
        embed.add_field(name="🎤  Host",           value=self.host.mention,                    inline=True)
        if self.send_invite:
            embed.add_field(name="📨  Invite Check",  value="Bot sẽ kiểm tra invite của winner", inline=False)
        embed.set_footer(text="TuyTam Store  •  Kết thúc lúc")

        await interaction.response.edit_message(
            content="✅ **Đã đăng giveaway!**",
            embed=self.build_preview_embed(),
            view=self
        )
        msg = await self.channel.send(embed=embed, view=GiveawayView())

        active_giveaways[msg.id] = {
            "type":        "button",
            "prize":       self.prize,
            "winners":     self.w_count,
            "entries":     set(),
            "channel_id":  self.channel.id,
            "end_time":    end_time,
            "host":        self.host.id,
            "ended":       False,
            "send_invite": self.send_invite,
        }
        save_giveaways_data()
        asyncio.create_task(giveaway_timer(self.channel.id, msg.id, self.w_count, self.seconds))

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.danger, custom_id="gw_cancel")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="🚫 **Đã huỷ tạo giveaway.**",
            embed=None,
            view=self
        )

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
    if not can_use_dangerous_cmd(interaction.user.id, "createchannel"):
        return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
    name = name.lower().replace(" ", "-")
    ch = await interaction.guild.create_text_channel(name, category=category, reason=f"Bởi {interaction.user}")
    await interaction.response.send_message(f"✅ Đã tạo kênh {ch.mention}!", ephemeral=True)

@tree.command(name="deletechannel", description="Xoá kênh")
@app_commands.describe(channel="Kênh cần xoá (để trống = kênh hiện tại)")
async def slash_deletechannel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not can_use_dangerous_cmd(interaction.user.id, "deletechannel"):
        return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
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

# ================= BALANCE SYSTEM =================

def fmt_vnd(amount: int) -> str:
    if amount < 0:
        return f"-{abs(amount):,}đ".replace(",", ".")
    return f"{amount:,}đ".replace(",", ".")

async def handle_balance_message(message: discord.Message):
    content = message.content.strip()

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
        embed.set_footer(text=f"Bởi {_uname_plain(message.author)}  •  {now_str}")

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
        embed.set_footer(text=f"Bởi {_uname_plain(message.author)}  •  {now_str}")

    try:
        await message.delete()
    except:
        pass
    await message.channel.send(embed=embed)

class BuyerSpendingView(View):
    """View hiển thị danh sách buyer + số tiền đã tiêu, phân trang."""
    def __init__(self, entries: list, requester: discord.Member):
        super().__init__(timeout=120)
        self.entries   = entries   # list of (member_or_none, user_id, total_spent)
        self.requester = requester
        self.page      = 0
        self.per_page  = 15

    def _build_embed(self) -> discord.Embed:
        total_pages = max(1, -(-len(self.entries) // self.per_page))
        start = self.page * self.per_page
        chunk = self.entries[start : start + self.per_page]

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (member, uid, spent) in enumerate(chunk):
            rank   = start + i
            icon   = medals[rank] if rank < 3 else f"`{rank+1}.`"
            name   = _uname(member) if member else f"<@{uid}>"
            lines.append(f"{icon} **{name}** — {fmt_vnd(spent)}")

        grand_total = sum(s for _, _, s in self.entries)
        embed = discord.Embed(
            title=f"👥 Danh Sách Buyer — Tổng Chi Tiêu",
            description="\n".join(lines) or "Chưa có dữ liệu.",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="💰 Tổng doanh thu",  value=f"**{fmt_vnd(grand_total)}**", inline=True)
        embed.add_field(name="👤 Số buyer",        value=f"**{len(self.entries)}** người", inline=True)
        embed.set_footer(
            text=f"Trang {self.page+1}/{total_pages}  •  Yêu cầu bởi {_uname_plain(self.requester)}"
        )
        return embed

    def _update_buttons(self):
        total_pages = max(1, -(-len(self.entries) // self.per_page))
        self.btn_prev.disabled = self.page <= 0
        self.btn_next.disabled = self.page >= total_pages - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.grey)
    async def btn_prev(self, interaction: discord.Interaction, button: Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.grey)
    async def btn_next(self, interaction: discord.Interaction, button: Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

class BalanceView(View):
    """View đính kèm embed .balance — nút xem danh sách buyer."""
    def __init__(self, guild: discord.Guild, requester: discord.Member):
        super().__init__(timeout=120)
        self.guild     = guild
        self.requester = requester

    @discord.ui.button(label="👥 Xem Buyer", style=discord.ButtonStyle.blurple)
    async def show_buyers(self, interaction: discord.Interaction, button: Button):
        data = load_data()
        raw = data.get("user_total_spent", {})
        if not raw:
            return await interaction.response.send_message("❌ Chưa có dữ liệu buyer nào.", ephemeral=True)

        entries = []
        for uid_str, spent in raw.items():
            if spent <= 0:
                continue
            uid    = int(uid_str)
            member = self.guild.get_member(uid)
            entries.append((member, uid, spent))
        entries.sort(key=lambda x: x[2], reverse=True)

        if not entries:
            return await interaction.response.send_message("❌ Chưa có dữ liệu buyer nào.", ephemeral=True)

        view = BuyerSpendingView(entries, self.requester)
        view._update_buttons()
        await interaction.response.send_message(embed=view._build_embed(), view=view, ephemeral=True)

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

    history = bal.get("history", [])
    if history:
        last5 = history[-5:][::-1]
        lines = []
        for tx in last5:
            icon = "📥" if tx["type"] == "+" else "📤"
            lines.append(f"{icon} **{fmt_vnd(tx['net'])}** — {tx['user']} — {tx['time']}")
        embed.add_field(name="🕐  5 giao dịch gần nhất", value="\n".join(lines), inline=False)

    embed.set_footer(text="TuyTam Store  •  Nhấn nút bên dưới để xem danh sách buyer")
    await ctx.reply(embed=embed, view=BalanceView(ctx.guild, ctx.author))

@bot.command(name="balreset")
async def balreset_cmd(ctx):
    if not can_use_dangerous_cmd(ctx.author.id, "balreset"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    data = load_data()
    data["balance"] = {
        "current": 0, "total_in": 0, "total_fee": 0,
        "total_out": 0, "tx_count": 0, "history": []
    }
    save_data(data)
    await ctx.reply("✅ Đã reset toàn bộ số dư về 0.")

@bot.command(name="balset")
async def balset_cmd(ctx, *, amount: str = None):
    if not can_use_dangerous_cmd(ctx.author.id, "balset"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
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

# ================= AI CHAT (Groq) =================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Model theo thứ tự ưu tiên — tự động fallback khi hết quota
# llama-3.1-8b-instant: 500k TPD (nhẹ, nhanh, đủ dùng cho chat bot)
# llama-3.3-70b-versatile: 100k TPD (mạnh hơn, dùng khi cần)
# gemma2-9b-it: 500k TPD (backup)
GROQ_MODELS = [
    "llama-3.1-8b-instant",      # primary — 500k token/ngày
    "llama-3.3-70b-versatile",   # fallback 1 — 100k token/ngày
    "gemma2-9b-it",              # fallback 2 — 500k token/ngày
]
GROQ_SYSTEM  = (
    "Bạn là trợ lý AI của TuyTam Store — một cửa hàng game. "
    "Hãy trả lời ngắn gọn, thân thiện, bằng tiếng Việt. "
    "Nếu không biết thông tin cụ thể về cửa hàng, hãy hướng dẫn user mở ticket để được hỗ trợ."
)

async def _call_groq(user_id: int, user_message: str) -> str:
    if not GROQ_API_KEY:
        return "❌ Chưa cài `GROQ_API_KEY` trong biến môi trường."

    history = _ai_chat_history.setdefault(user_id, [])
    history.append({"role": "user", "content": user_message})
    if len(history) > AI_HISTORY_LIMIT * 2:
        _ai_chat_history[user_id] = history[-(AI_HISTORY_LIMIT * 2):]
        history = _ai_chat_history[user_id]

    messages = [{"role": "system", "content": GROQ_SYSTEM}] + history

    import aiohttp as _aiohttp_ai
    last_err = "Unknown error"

    for model in GROQ_MODELS:
        try:
            async with _aiohttp_ai.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 1024,
                        "temperature": 0.7,
                    },
                    timeout=_aiohttp_ai.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        print(f"[AI] ⚠️ Model {model} hết quota, thử model tiếp...")
                        last_err = f"Model `{model}` hết quota"
                        continue
                    if resp.status != 200:
                        err = await resp.text()
                        print(f"[AI] ❌ Groq lỗi {resp.status} ({model}): {err[:150]}")
                        last_err = f"Lỗi {resp.status}"
                        continue
                    data = await resp.json()
                    reply = data["choices"][0]["message"]["content"]

            _ai_chat_history[user_id].append({"role": "assistant", "content": reply})
            return reply

        except Exception as e:
            print(f"[AI] ❌ Exception ({model}): {e}")
            last_err = str(e)
            continue

    return f"⚠️ AI tạm thời không khả dụng ({last_err}). Vui lòng thử lại sau ít phút."

async def handle_ai_message(message: discord.Message):
    ai_ch_id = get_cfg_ai_channel()
    if not ai_ch_id or message.channel.id != ai_ch_id:
        return

    async with message.channel.typing():
        reply = await _call_groq(message.author.id, message.content)

    if len(reply) <= 2000:
        await message.reply(reply, mention_author=False)
    else:
        chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
        for chunk in chunks:
            await message.channel.send(chunk)

@bot.command(name="aireset")
async def ai_reset(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin.")
    _ai_chat_history.clear()
    await ctx.reply("✅ Đã xoá toàn bộ lịch sử hội thoại AI.")

@bot.command(name="mychat")
async def my_chat_reset(ctx):
    if ctx.author.id in _ai_chat_history:
        del _ai_chat_history[ctx.author.id]
        await ctx.reply("✅ Đã xoá lịch sử chat AI của bạn.", delete_after=10)
    else:
        await ctx.reply("ℹ️ Bạn chưa có lịch sử chat AI.", delete_after=10)

@bot.command(name="ai")
async def ai_cmd(ctx, *, prompt: str = None):
    """
    Dùng AI ở bất kỳ kênh nào.
    Subcommands:
      .ai <câu hỏi>            — chat thường
      .ai tomtat [n]           — tóm tắt n tin nhắn gần nhất (mặc định 30)
      .ai dich <ngôn ngữ> ...  — dịch văn bản sang ngôn ngữ chỉ định
      .ai phantich @user       — phân tích phong cách chat của user
      .ai reset                — xoá lịch sử chat của bạn
    """
    if not prompt:
        embed = discord.Embed(
            title="🤖 Hướng dẫn dùng AI",
            color=0x5865F2,
            description=(
                "**`.ai <câu hỏi>`** — Chat với AI\n"
                "**`.ai tomtat [n]`** — Tóm tắt `n` tin nhắn gần nhất trong kênh (mặc định 30)\n"
                "**`.ai dich <ngôn ngữ> <văn bản>`** — Dịch văn bản\n"
                "**`.ai phantich @user`** — Phân tích phong cách chat của user\n"
                "**`.ai reset`** — Xoá lịch sử hội thoại của bạn\n\n"
                "💡 AI nhớ tối đa **10 tin nhắn** gần nhất trong hội thoại với bạn."
            )
        )
        return await ctx.reply(embed=embed)

    parts = prompt.strip().split()
    sub = parts[0].lower()

    if sub == "reset":
        if ctx.author.id in _ai_chat_history:
            del _ai_chat_history[ctx.author.id]
        return await ctx.reply("✅ Đã xoá lịch sử chat AI của bạn.", delete_after=10)

    if sub == "tomtat":
        limit = 30
        if len(parts) > 1 and parts[1].isdigit():
            limit = max(5, min(int(parts[1]), 100))
        async with ctx.typing():
            msgs = [m async for m in ctx.channel.history(limit=limit + 1) if not m.author.bot and m.id != ctx.message.id]
            msgs.reverse()
            if not msgs:
                return await ctx.reply("❌ Không có tin nhắn nào để tóm tắt.")
            chat_log = "\n".join(f"{_uname_plain(m.author)}: {m.content}" for m in msgs if m.content)[:4000]
            task = (
                f"Tóm tắt ngắn gọn nội dung cuộc trò chuyện sau trong kênh Discord "
                f"(bằng tiếng Việt, tối đa 300 từ):\n\n{chat_log}"
            )
            reply = await _call_groq(ctx.author.id, task)
        embed = discord.Embed(
            title=f"📋 Tóm tắt {len(msgs)} tin nhắn gần nhất",
            description=reply,
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
        return await ctx.reply(embed=embed)

    if sub == "dich":
        if len(parts) < 3:
            return await ctx.reply("❌ Dùng: `.ai dich <ngôn ngữ> <văn bản>`\nVí dụ: `.ai dich tiếng Anh xin chào bạn`")
        lang = parts[1]
        text = " ".join(parts[2:])
        async with ctx.typing():
            task = f"Dịch đoạn văn bản sau sang {lang}, chỉ trả về bản dịch, không giải thích:\n\n{text}"
            reply = await _call_groq(ctx.author.id, task)
        embed = discord.Embed(
            title=f"🌐 Dịch sang {lang}",
            color=0x57F287,
        )
        embed.add_field(name="📝 Gốc", value=text[:1024], inline=False)
        embed.add_field(name="✅ Dịch", value=reply[:1024], inline=False)
        embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
        return await ctx.reply(embed=embed)

    if sub == "phantich":
        target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
        async with ctx.typing():
            msgs = [m async for m in ctx.channel.history(limit=200) if m.author.id == target.id and m.content]
            if len(msgs) < 5:
                return await ctx.reply(f"❌ Không đủ tin nhắn của {_uname(target)} để phân tích (cần ít nhất 5).")
            sample = "\n".join(m.content for m in msgs[:50])[:3000]
            task = (
                f"Phân tích phong cách chat của người dùng Discord tên '{_uname_plain(target)}' "
                f"dựa trên các tin nhắn sau. Nhận xét về: cách dùng từ, tính cách, sở thích, "
                f"mức độ hoạt động, emoji thường dùng. Trả lời bằng tiếng Việt, vui vẻ và thân thiện:\n\n{sample}"
            )
            reply = await _call_groq(ctx.author.id, task)
        embed = discord.Embed(
            title=f"🔍 Phân tích phong cách chat của {_uname(target)}",
            description=reply[:2000],
            color=0xEB459E,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"Yêu cầu bởi {_uname_plain(ctx.author)}")
        return await ctx.reply(embed=embed)

    async with ctx.typing():
        reply = await _call_groq(ctx.author.id, prompt)
    if len(reply) <= 2000:
        await ctx.reply(reply)
    else:
        chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
        for chunk in chunks:
            await ctx.channel.send(chunk)

# ================= INVITE COMMANDS =================

@bot.command(name="invite", aliases=["inv", "invites"])
async def invite_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    total, fake, left, net = _get_net_invites(target.id)
    embed = discord.Embed(
        title=f"📨 Invite của {_uname(target)}",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="✅ Net (thực tế)",  value=f"**{net}** người",   inline=True)
    embed.add_field(name="📊 Tổng",           value=f"**{total}** lần",   inline=True)
    embed.add_field(name="⚠️ Fake",           value=f"**{fake}** người",  inline=True)
    embed.add_field(name="🚪 Đã rời",         value=f"**{left}** người",  inline=True)
    embed.set_footer(text=f"Net = Tổng − Fake − Đã rời  •  TuyTam Store")
    await ctx.reply(embed=embed)

@bot.command(name="invitetop", aliases=["invtop"])
async def invitetop_cmd(ctx, top: int = 10):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin.")
    top = max(1, min(top, 25))
    counts = _get_invite_counts()
    board = []
    for uid_str, c in counts.items():
        total = c.get("total", 0)
        fake  = c.get("fake",  0)
        left  = c.get("left",  0)
        net   = max(0, total - fake - left)
        board.append((int(uid_str), net, total, fake, left))
    board.sort(key=lambda x: x[1], reverse=True)
    board = board[:top]

    if not board:
        return await ctx.reply("❌ Chưa có dữ liệu invite nào.")

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, net, total, fake, left) in enumerate(board):
        icon = medals[i] if i < 3 else f"`{i+1}.`"
        member = ctx.guild.get_member(uid)
        name = _uname(member) if member else f"<@{uid}>"
        lines.append(f"{icon} **{name}** — **{net}** net (`{total}` tổng, `{fake}` fake, `{left}` rời)")

    embed = discord.Embed(
        title=f"🏆 Bảng xếp hạng Invite — Top {top}",
        description="\n".join(lines),
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="TuyTam Store  •  Net = Tổng − Fake − Đã rời")
    await ctx.reply(embed=embed)

@bot.command(name="resetinvite", aliases=["resetinv"])
async def resetinvite_cmd(ctx, member: discord.Member = None):
    """
    Reset invite của 1 user hoặc toàn bộ server. *(admin)*
    .resetinvite @user  — reset 1 người
    .resetinvite all    — reset tất cả
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin.")

    raw = ctx.message.content.split()
    is_all = len(raw) > 1 and raw[-1].lower() == "all" and not ctx.message.mentions

    if is_all:
        _save_invite_counts({})
        await ctx.reply("✅ Đã reset toàn bộ invite của server.")
    elif member:
        counts = _get_invite_counts()
        uid = str(member.id)
        if uid in counts:
            del counts[uid]
            _save_invite_counts(counts)
        await ctx.reply(f"✅ Đã reset invite của **{_uname(member)}**.")
    else:
        await ctx.reply(
            "❌ Dùng:\n"
            "`.resetinvite @user` — reset 1 người\n"
            "`.resetinvite all` — reset toàn bộ server"
        )

@bot.command(name="mkchannel", aliases=["mkch", "taokenh"])
async def mkchannel_cmd(ctx, *, args: str = None):
    """
    Tạo kênh mới với font đồng bộ server.
    Dùng: .mkchannel <loại> <tên kênh> [category]
    Ví dụ:
      .mkchannel text thông-báo
      .mkchannel voice Phòng Chờ
      .mkchannel category Mua Bán
      .mkchannel text tin-tức "Thông Báo"
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin.")

    if not args:
        embed = discord.Embed(
            title="📖 Hướng dẫn tạo kênh",
            color=0x5865F2,
            description=(
                "**`.mkchannel text <tên>`** — Tạo kênh text\n"
                "**`.mkchannel voice <tên>`** — Tạo kênh voice\n"
                "**`.mkchannel category <tên>`** — Tạo category\n\n"
                "Tên kênh sẽ tự động áp dụng font server đang dùng.\n"
                f"Font hiện tại: **{FONT_LABELS.get(get_cfg_font(), get_cfg_font())}**"
            )
        )
        return await ctx.reply(embed=embed)

    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return await ctx.reply("❌ Thiếu tên kênh. Dùng: `.mkchannel text <tên kênh>`")

    ch_type = parts[0].lower()
    raw_name = parts[1].strip().strip('"').strip("'")

    if ch_type not in ("text", "voice", "category", "t", "v", "c"):
        return await ctx.reply("❌ Loại kênh không hợp lệ. Dùng: `text`, `voice`, hoặc `category`")

    server_font = get_cfg_font()
    ch_parts = _detect_channel_parts(raw_name)
    styled_name = _rebuild_name(ch_parts, ch_parts["base_text"], server_font)

    category = ctx.channel.category  # đặt vào category của kênh hiện tại

    try:
        if ch_type in ("text", "t"):
            new_ch = await ctx.guild.create_text_channel(
                name=styled_name,
                category=category,
                reason=f"Tạo bởi {ctx.author}"
            )
            ch_icon = "📝"
        elif ch_type in ("voice", "v"):
            new_ch = await ctx.guild.create_voice_channel(
                name=styled_name,
                category=category,
                reason=f"Tạo bởi {ctx.author}"
            )
            ch_icon = "🔊"
        else:  # category
            new_ch = await ctx.guild.create_category(
                name=styled_name,
                reason=f"Tạo bởi {ctx.author}"
            )
            ch_icon = "📂"

        embed = discord.Embed(
            title=f"{ch_icon} Đã tạo kênh thành công!",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Tên gốc", value=f"`{raw_name}`", inline=True)
        embed.add_field(name="Tên đã tạo", value=new_ch.mention, inline=True)
        embed.add_field(name="Font", value=FONT_LABELS.get(server_font, server_font), inline=True)
        if category:
            embed.add_field(name="Category", value=category.name, inline=True)
        embed.set_footer(text=f"Tạo bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền tạo kênh.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)

    await handle_ai_message(message)

    bal_ch = get_cfg_balance_channel()
    if bal_ch and message.channel.id == bal_ch:
        await handle_balance_message(message)

    await handle_legit_message(message)

    await handle_vouch_message(message)

async def handle_legit_message(message: discord.Message):
    """
    Lắng nghe tin nhắn +1legit trong kênh legit.
    Cú pháp: +1legit(+1 legit) {seller} {loại đơn}
    Tự động +1 vào số đếm trong tên kênh.
    """
    import re as _re_legit

    IGNORED_BOT_IDS = {628400349979344919}
    if message.author.id in IGNORED_BOT_IDS:
        return

    legit_ch_id = get_cfg_legit_channel()
    if legit_ch_id:
        if message.channel.id != legit_ch_id:
            return
    else:
        if "legit" not in message.channel.name.lower():
            return

    content = message.content.strip()

    # Nhận dạng cú pháp: +1legit hoặc +1 legit (không phân biệt hoa thường)
    if not _re_legit.match(r"^\+1\s*legit\b", content, _re_legit.IGNORECASE):
        return

    channel = message.channel
    current_name = channel.name  # ví dụ: ✅•𝐋𝐞𝐠𝐢𝐭-58

    match = _re_legit.search(r"-(\d+)$", current_name)
    if not match:
        new_count = 1
        base_name = current_name
    else:
        new_count = int(match.group(1)) + 1
        base_name = current_name[:match.start()]  # phần tên trước dấu -số

    new_name = f"{base_name}-{new_count}"

    try:
        await channel.edit(name=new_name, reason=f"+1 legit bởi {message.author} → {new_count} đơn")
        await message.add_reaction("✅")
    except discord.Forbidden:
        pass  # Bot thiếu quyền Manage Channels — bỏ qua
    except Exception as e:
        print(f"[LEGIT] Lỗi cập nhật tên kênh: {e}")

async def handle_vouch_message(message: discord.Message):
    """
    Lắng nghe tin nhắn 'done {loại đơn}' trong kênh vouch.
    Tự động +1 vào số đếm ở cuối tên kênh.
    (Việc give role mua hàng do staff nhấn nút trong ticket.)
    """
    import re as _re_vouch

    IGNORED_BOT_IDS = {628400349979344919}
    if message.author.id in IGNORED_BOT_IDS:
        return

    proof_ch_id = get_cfg_proof_channel()
    if message.channel.id != proof_ch_id:
        return

    content = message.content.strip()

    if not _re_vouch.match(r"^done\b", content, _re_vouch.IGNORECASE):
        return

    channel = message.channel
    current_name = channel.name  # ví dụ: 🎉•vouch-120

    match = _re_vouch.search(r"-(\d+)$", current_name)
    if not match:
        new_count = 1
        base_name = current_name
    else:
        new_count = int(match.group(1)) + 1
        base_name = current_name[:match.start()]

    new_name = f"{base_name}-{new_count}"

    try:
        await channel.edit(name=new_name, reason=f"+1 vouch bởi {message.author} → {new_count} đơn")
        await message.add_reaction("✅")
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"[VOUCH] Lỗi cập nhật tên kênh: {e}")

# ================= ON MEMBER JOIN =================
WELCOME_GUILDS = {
    950363132679831642: 1276087208150827070,  # Star Clan → kênh welcome
}

# ================= INVITE TRACKING =================
# LƯU Ý:
# • Bot cache snapshot invites của từng guild sau mỗi lần join/leave
# • So sánh snapshot trước/sau để xác định ai đã invite member mới
# • Dữ liệu lưu trong MongoDB key "invite_counts" — không bao giờ xoá
#   trừ khi admin dùng .resetinvite
# • fake invite: member join rồi leave trong vòng 10 phút không được tính
# • Hoàn toàn tách biệt khỏi giveaway/buyer/ticket data

_invite_cache: dict[int, dict[str, int]] = {}
# guild_id → { invite_code: uses_count }

_pending_joins: dict[int, dict] = {}
# member_id → { "inviter_id": int, "guild_id": int, "joined_at": float }
# dùng để phát hiện fake invite (leave trong 10 phút)

async def _cache_invites(guild: discord.Guild):
    try:
        invites = await guild.invites()
        _invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
    except (discord.Forbidden, discord.HTTPException):
        pass

def _get_invite_counts() -> dict:
    data = load_data()
    return data.get("invite_counts", {})

def _save_invite_counts(counts: dict):
    data = load_data()
    data["invite_counts"] = counts
    save_data(data)

def _add_invite(inviter_id: int, field: str, amount: int = 1):
    counts = _get_invite_counts()
    uid = str(inviter_id)
    if uid not in counts:
        counts[uid] = {"total": 0, "fake": 0, "left": 0}
    counts[uid][field] = counts[uid].get(field, 0) + amount
    _save_invite_counts(counts)

def _get_net_invites(inviter_id: int) -> tuple[int, int, int, int]:
    counts = _get_invite_counts()
    uid = str(inviter_id)
    c = counts.get(uid, {"total": 0, "fake": 0, "left": 0})
    total = c.get("total", 0)
    fake  = c.get("fake",  0)
    left  = c.get("left",  0)
    net   = max(0, total - fake - left)
    return total, fake, left, net

@bot.event
async def on_member_join(member: discord.Member):
    ch_id = WELCOME_GUILDS.get(member.guild.id)
    if ch_id:
        channel = member.guild.get_channel(ch_id)
        if channel:
            try:
                msg = await channel.send(member.mention)
                await asyncio.sleep(10)
                await msg.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

    try:
        old_cache = _invite_cache.get(member.guild.id, {})
        new_invites = await member.guild.invites()
        new_cache = {inv.code: inv.uses for inv in new_invites}

        inviter_id = None
        for inv in new_invites:
            old_uses = old_cache.get(inv.code, 0)
            if inv.uses > old_uses:
                if inv.inviter:
                    inviter_id = inv.inviter.id
                break

        _invite_cache[member.guild.id] = new_cache

        if inviter_id and inviter_id != member.id:
            import time as _time
            _pending_joins[member.id] = {
                "inviter_id": inviter_id,
                "guild_id":   member.guild.id,
                "joined_at":  _time.time(),
            }
            _add_invite(inviter_id, "total", 1)

            async def _check_fake():
                await asyncio.sleep(600)  # 10 phút
                still_here = member.guild.get_member(member.id)
                if not still_here:
                    _add_invite(inviter_id, "fake", 1)
                    print(f"[INVITE] ⚠️ Fake invite: {member} invited by {inviter_id}")
                _pending_joins.pop(member.id, None)

            asyncio.create_task(_check_fake())

    except (discord.Forbidden, discord.HTTPException):
        pass

@bot.event
async def on_member_remove(member: discord.Member):
    await _cache_invites(member.guild)

    pend = _pending_joins.pop(member.id, None)
    if pend is None:
        pass
    await _cache_invites(member.guild)

# ================= ERROR HANDLER =================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ Bạn không có quyền thực hiện lệnh này.")

# ================= SETUP SERVER =================
import re as _re_setup
import unicodedata as _unicodedata

# ── Bảng font chữ Unicode đặc biệt (Bold, Bold Italic, Circled, v.v.) ──
_FONT_MAPS = {
    "bold": {
        **{chr(ord('A')+i): chr(0x1D400+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D41A+i) for i in range(26)},
        **{str(i): chr(0x1D7CE+i) for i in range(10)},
    },
    "bold_italic": {
        **{chr(ord('A')+i): chr(0x1D468+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D482+i) for i in range(26)},
    },
    "sans_bold": {
        **{chr(ord('A')+i): chr(0x1D5D4+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D5EE+i) for i in range(26)},
        **{str(i): chr(0x1D7EC+i) for i in range(10)},
    },
    "script": {
        **{chr(ord('A')+i): chr(0x1D4D0+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D4EA+i) for i in range(26)},
    },
    "double": {
        **{chr(ord('A')+i): chr(0x1D538+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D552+i) for i in range(26)},
    },
    "math_bold_serif": {
        **{chr(ord('A')+i): chr(0x1D400+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D41A+i) for i in range(26)},
        **{str(i): chr(0x1D7CE+i) for i in range(10)},
    },
    "normal": {},  # giữ nguyên
}

# Vài override đặc biệt (script/double có ký tự ngoại lệ)
_FONT_MAPS["script"].update({"B": "ℬ","E": "ℰ","F": "ℱ","H": "ℋ","I": "ℐ","L": "ℒ","M": "ℳ","R": "ℛ","e":"ℯ","g":"ℊ","o":"ℴ"})
_FONT_MAPS["double"].update({"C": "ℂ","H": "ℍ","N": "ℕ","P": "ℙ","Q": "ℚ","R": "ℝ","Z": "ℤ"})

def _apply_font(text: str, font: str) -> str:
    if font == "normal" or font not in _FONT_MAPS:
        return text
    mapping = _FONT_MAPS[font]
    return "".join(mapping.get(c, c) for c in text)

def _strip_unicode_font(text: str) -> str:
    ranges = [
        (0x1D400, 0x1D419, ord('A')),   # Bold A-Z
        (0x1D41A, 0x1D433, ord('a')),   # Bold a-z
        (0x1D434, 0x1D44D, ord('A')),   # Italic A-Z
        (0x1D44E, 0x1D467, ord('a')),   # Italic a-z
        (0x1D468, 0x1D481, ord('A')),   # Bold Italic A-Z
        (0x1D482, 0x1D49B, ord('a')),   # Bold Italic a-z
        (0x1D49C, 0x1D4B5, ord('A')),   # Script A-Z (thường)
        (0x1D4B6, 0x1D4CF, ord('a')),   # Script a-z (thường)
        (0x1D4D0, 0x1D4E9, ord('A')),   # Script Bold A-Z
        (0x1D4EA, 0x1D503, ord('a')),   # Script Bold a-z
        (0x1D538, 0x1D551, ord('A')),   # Double A-Z
        (0x1D552, 0x1D56B, ord('a')),   # Double a-z
        (0x1D5D4, 0x1D5ED, ord('A')),   # Sans Bold A-Z
        (0x1D5EE, 0x1D607, ord('a')),   # Sans Bold a-z
        (0x1D7CE, 0x1D7D7, ord('0')),   # Bold digits 0-9
        (0x1D7EC, 0x1D7F5, ord('0')),   # Sans Bold digits 0-9
    ]
    special = {
        'ℬ':'B','ℰ':'E','ℱ':'F','ℋ':'H','ℐ':'I','ℒ':'L','ℳ':'M','ℛ':'R',
        'ℯ':'e','ℊ':'g','ℴ':'o',
        'ℂ':'C','ℍ':'H','ℕ':'N','ℙ':'P','ℚ':'Q','ℝ':'R','ℤ':'Z',
        'ℬ':'B',  # đã trên
        # Script thường — lowercase ngoại lệ: e=ℯ(0x212F), g=ℊ(0x210A), o=ℴ(0x2134)
        '\u212F':'e',  # ℯ
        '\u210A':'g',  # ℊ
        '\u2134':'o',  # ℴ
        '\u212C':'B',  # ℬ
        '\u2130':'E',  # ℰ
        '\u2131':'F',  # ℱ
        '\u210B':'H',  # ℋ
        '\u2110':'I',  # ℐ
        '\u2112':'L',  # ℒ
        '\u2133':'M',  # ℳ
        '\u211B':'R',  # ℛ
    }
    result = []
    for c in text:
        if c in special:
            result.append(special[c])
            continue
        cp = ord(c)
        converted = False
        for start, end, base in ranges:
            if start <= cp <= end:
                result.append(chr(base + (cp - start)))
                converted = True
                break
        if not converted:
            result.append(c)
    return ''.join(result)

def _detect_channel_parts(name: str):
    """
    Phân tích tên kênh thành các phần:
    - icon (emoji đầu nếu có)
    - separator (• hoặc ký tự phân cách)
    - base_text (phần chữ chính, đã strip font cũ về ASCII)
    - trailing_num (số cuối nếu có, vd: -58)
    Trả về dict.
    """
    icon_match = _re_setup.match(
        r'^((?:[\U00010000-\U0010FFFF]|[\u2600-\u26FF]|[\u2700-\u27BF]|[\U0001F300-\U0001F9FF])+)',
        name
    )
    icon = icon_match.group(1) if icon_match else ""
    rest = name[len(icon):].lstrip()

    sep = ""
    sep_match = _re_setup.match(r'^([•·\-–—|])\s*', rest)
    if sep_match:
        sep = sep_match.group(1)
        rest = rest[sep_match.end():]

    rest_plain = _strip_unicode_font(rest)

    num_match = _re_setup.search(r'[\-–](\d+)$', rest_plain)
    trailing_num = ""
    base_text = rest_plain
    if num_match:
        trailing_num = num_match.group(0)   # vd: "-58"
        base_text = rest_plain[:num_match.start()]

    return {
        "icon": icon,
        "sep": sep,
        "base_text": base_text,
        "trailing_num": trailing_num,
        "original": name,
    }

def _rebuild_name(parts: dict, new_base: str, font: str = "normal") -> str:
    styled_base = _apply_font(new_base, font)
    result = parts["icon"]
    if parts["icon"] and parts["sep"]:
        result += parts["sep"]
    elif parts["icon"]:
        result += ""
    result += styled_base + parts["trailing_num"]
    return result.strip()

# ── State cho phiên .setup ──
_setup_sessions: dict = {}   # guild_id → session dict

FONT_LABELS = {
    "normal":           "Thường (giữ nguyên)",
    "bold":             "𝐁𝐨𝐥𝐝  —  𝐐𝐮𝐢𝐞𝐭 𝐒𝐜𝐡𝐞𝐦𝐚𝐭𝐢𝐜𝐬",
    "bold_italic":      "𝑩𝒐𝒍𝒅 𝑰𝒕𝒂𝒍𝒊𝒄  —  𝑸𝒖𝒊𝒆𝒕 𝑺𝒄𝒉𝒆𝒎𝒂𝒕𝒊𝒄𝒔",
    "sans_bold":        "𝗦𝗮𝗻𝘀 𝗕𝗼𝗹𝗱  —  𝗤𝘂𝗶𝗲𝘁 𝗦𝗰𝗵𝗲𝗺𝗮𝘁𝗶𝗰𝘀",
    "script":           "𝒮𝒸𝓇𝒾𝓅𝓉  —  𝒬𝓊𝒾ℯ𝓉 𝒮𝒸𝒽ℯ𝓂𝒶𝓉𝒾𝒸𝓈",
    "double":           "𝔻𝕠𝕦𝕓𝕝𝕖  —  ℚ𝕦𝕚𝕖𝕥 𝕊𝕔𝕙𝕖𝕞𝕒𝕥𝕚𝕔𝕤",
    "math_bold_serif":  "𝐌𝐚𝐭𝐡 𝐁𝐨𝐥𝐝 𝐒𝐞𝐫𝐢𝐟  —  𝐐𝐮𝐢𝐞𝐭 𝐒𝐜𝐡𝐞𝐦𝐚𝐭𝐢𝐜𝐬",
}

# Alias để user gõ tên font dễ hơn
FONT_ALIASES = {
    "quiet": "bold",
    "schematics": "bold",
    "math bold": "bold",
    "mathbold": "bold",
    "bi": "bold_italic",
    "italic": "bold_italic",
    "sb": "sans_bold",
    "sansbold": "sans_bold",
    "sc": "script",
    "db": "double",
    "bb": "double",
    "math_bold_serif": "math_bold_serif",
    "mathboldserif": "math_bold_serif",
    "mbs": "math_bold_serif",
    "serif": "math_bold_serif",
    "bold serif": "math_bold_serif",
    "boldserif": "math_bold_serif",
}

class SetupMainView(View):
    """Menu chính của .setup."""
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=300)
        self.guild = guild

    @discord.ui.button(label="📋 Xem danh sách kênh", style=discord.ButtonStyle.secondary, row=0)
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await _show_channel_list(interaction, self.guild)

    @discord.ui.button(label="✏️ Đổi tên kênh (hàng loạt)", style=discord.ButtonStyle.primary, row=0)
    async def btn_rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(SetupFontSampleModal(self.guild, mode="rename"))

    @discord.ui.button(label="➕ Tạo kênh mới", style=discord.ButtonStyle.success, row=0)
    async def btn_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(CreateChannelModal(self.guild))

    @discord.ui.button(label="🔒 Sửa quyền kênh", style=discord.ButtonStyle.danger, row=1)
    async def btn_perms(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_message(
            "🔒 **Sửa quyền kênh**\nDùng lệnh: `.setperm #kênh @role xem=true gửi=false`\n"
            "Hoặc chọn kênh cụ thể từ danh sách bên dưới.",
            ephemeral=True,
            view=PermSelectView(self.guild)
        )

    @discord.ui.button(label="🔤 Chọn font chữ", style=discord.ButtonStyle.secondary, row=1)
    async def btn_font(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_message(
            "🔤 **Chọn font chữ mẫu**\nBot sẽ áp dụng font này khi tạo/đổi tên kênh.",
            ephemeral=True,
            view=FontSelectView(self.guild)
        )

    @discord.ui.button(label="🏆 Cài Role Mua Hàng", style=discord.ButtonStyle.blurple, row=2)
    async def btn_buy_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await _show_buy_role_panel(interaction)

async def _show_buy_role_panel(interaction: discord.Interaction):
    buy_roles = get_buy_roles()
    embed = discord.Embed(
        title="🏆  Cấu Hình Role Buyer Tự Động",
        description=(
            "Bot give role dựa trên **tổng tiền đã mua** của buyer.\n"
            "Mỗi role tương ứng 1 khoảng tiền. VD: buyer 50-100k, buyer 100-200k...\n\n"
            "**Cách hoạt động:**\n"
            "› Staff gõ `.done 50k` trong ticket sau khi giao dịch thành công\n"
            "› Bot cộng tiền vào tổng của buyer → give đúng role khoảng tương ứng\n"
            "› Khi tổng vượt khoảng hiện tại → tự động upgrade lên role cao hơn"
        ),
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    if buy_roles:
        lines = []
        for i, r in enumerate(buy_roles):
            role_obj = interaction.guild.get_role(r.get("role_id", 0))
            role_str = role_obj.mention if role_obj else f"❌ ID:{r.get('role_id')}"
            min_a    = fmt_amount(r.get("min_amount", 0))
            max_a    = fmt_amount(r.get("max_amount")) if r.get("max_amount") else "∞"
            lines.append(f"`{i+1}.` {role_str} — **{r.get('label','?')}** — {min_a} → {max_a}")
        embed.add_field(name=f"📋 Danh sách role ({len(buy_roles)})", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="📋 Danh sách role", value="*Chưa có role nào được cấu hình.*", inline=False)

    embed.set_footer(text="TuyTam Store  •  Setup → Role Buyer")
    await interaction.response.send_message(embed=embed, view=BuyRoleManageView(), ephemeral=True)

class BuyRoleManageView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="➕ Thêm Role", style=discord.ButtonStyle.success, row=0)
    async def btn_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(AddBuyRoleModal())

    @discord.ui.button(label="🗑️ Xoá Role", style=discord.ButtonStyle.danger, row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        if not get_buy_roles():
            return await interaction.response.send_message("❌ Chưa có role nào.", ephemeral=True)
        await interaction.response.send_modal(RemoveBuyRoleModal())

    @discord.ui.button(label="🔄 Xoá tất cả", style=discord.ButtonStyle.danger, row=0)
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        save_buy_roles([])
        await interaction.response.send_message("✅ Đã xoá toàn bộ cấu hình role buyer.", ephemeral=True)

    @discord.ui.button(label="📊 Xem tổng tiền user", style=discord.ButtonStyle.secondary, row=1)
    async def btn_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(CheckUserSpentModal())

    @discord.ui.button(label="✏️ Sửa tổng tiền user", style=discord.ButtonStyle.secondary, row=1)
    async def btn_set_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(SetUserSpentModal())

    @discord.ui.button(label="🔄 Sync role cũ", style=discord.ButtonStyle.blurple, row=2)
    async def btn_sync(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(SyncExistingRolesModal())

class AddBuyRoleModal(Modal, title="➕ Thêm Role Buyer"):
    role_id_input = TextInput(
        label="ID của Role",
        placeholder="Chuột phải vào role → Copy ID",
        min_length=15, max_length=20
    )
    min_amount_input = TextInput(
        label="Mốc tiền TỐI THIỂU để nhận role",
        placeholder="VD: 50k, 100k, 1tr5 (tổng tiền đã mua)",
        min_length=1, max_length=15
    )
    max_amount_input = TextInput(
        label="Mốc tiền TỐI ĐA (bỏ trống = không giới hạn)",
        placeholder="VD: 100k, 200k — để trống nếu là role cao nhất",
        required=False,
        max_length=15
    )
    label_input = TextInput(
        label="Tên hiển thị của role",
        placeholder="VD: buyer 50-100k, buyer 100-200k",
        min_length=1, max_length=40
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID role không hợp lệ!", ephemeral=True)

        min_a = parse_amount(self.min_amount_input.value)
        if min_a is None:
            return await interaction.response.send_message(
                f"❌ Mốc tiền tối thiểu `{self.min_amount_input.value}` không hợp lệ!\nVD: `50k`, `1tr`, `200000`",
                ephemeral=True
            )

        max_raw = self.max_amount_input.value.strip()
        max_a   = None
        if max_raw:
            max_a = parse_amount(max_raw)
            if max_a is None:
                return await interaction.response.send_message(
                    f"❌ Mốc tiền tối đa `{max_raw}` không hợp lệ!", ephemeral=True
                )
            if max_a <= min_a:
                return await interaction.response.send_message(
                    "❌ Mốc tối đa phải lớn hơn mốc tối thiểu!", ephemeral=True
                )

        label    = self.label_input.value.strip()
        role_obj = interaction.guild.get_role(role_id)
        if not role_obj:
            return await interaction.response.send_message(
                f"❌ Không tìm thấy role ID `{role_id}` trong server.", ephemeral=True
            )

        buy_roles = get_buy_roles()
        for r in buy_roles:
            if r["role_id"] == role_id:
                return await interaction.response.send_message(
                    f"❌ Role {role_obj.mention} đã được cấu hình rồi.", ephemeral=True
                )

        buy_roles.append({"role_id": role_id, "min_amount": min_a, "max_amount": max_a, "label": label})
        buy_roles = sorted(buy_roles, key=lambda r: r["min_amount"])
        save_buy_roles(buy_roles)

        embed = discord.Embed(title="✅ Đã Thêm Role Buyer", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏷️ Role",      value=role_obj.mention,                           inline=True)
        embed.add_field(name="📛 Tên",        value=f"`{label}`",                               inline=True)
        embed.add_field(name="💰 Khoảng tiền",
                        value=f"**{fmt_amount(min_a)}** → **{fmt_amount(max_a) if max_a else '∞'}**",
                        inline=True)
        all_lines = []
        for r in buy_roles:
            ro   = interaction.guild.get_role(r["role_id"])
            mn   = fmt_amount(r["min_amount"])
            mx   = fmt_amount(r["max_amount"]) if r.get("max_amount") else "∞"
            all_lines.append(f"› {ro.mention if ro else r['role_id']} — **{r['label']}** ({mn}→{mx})")
        embed.add_field(name="📋 Danh sách hiện tại", value="\n".join(all_lines) or "—", inline=False)
        embed.set_footer(text=f"Thêm bởi {interaction.user}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class RemoveBuyRoleModal(Modal, title="🗑️ Xoá Role Buyer"):
    role_id_input = TextInput(
        label="ID của Role muốn xoá",
        placeholder="Chuột phải vào role → Copy ID",
        min_length=15, max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

        buy_roles = get_buy_roles()
        new_roles = [r for r in buy_roles if r["role_id"] != role_id]
        if len(new_roles) == len(buy_roles):
            return await interaction.response.send_message(
                f"❌ Không tìm thấy role ID `{role_id}` trong danh sách.", ephemeral=True
            )

        save_buy_roles(new_roles)
        role_obj = interaction.guild.get_role(role_id)
        await interaction.response.send_message(
            f"✅ Đã xoá role **{role_obj.name if role_obj else role_id}** khỏi danh sách buyer.",
            ephemeral=True
        )

class CheckUserSpentModal(Modal, title="📊 Xem Tổng Tiền Của User"):
    user_id_input = TextInput(
        label="ID của User",
        placeholder="Chuột phải vào user → Copy ID",
        min_length=15, max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

        member    = interaction.guild.get_member(uid)
        total     = get_user_total_spent(uid)
        buy_roles = get_buy_roles()

        embed = discord.Embed(title="📊 Thống Kê Buyer", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 User",        value=member.mention if member else f"ID: {uid}", inline=True)
        embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(total)}**",                inline=True)

        cur_cfg = None
        for r in reversed(buy_roles):
            min_a = r.get("min_amount", 0)
            max_a = r.get("max_amount")
            if total >= min_a and (max_a is None or total < max_a):
                cur_cfg = r
                break
        if cur_cfg:
            ro = interaction.guild.get_role(cur_cfg["role_id"])
            embed.add_field(name="🏆 Role hiện tại", value=ro.mention if ro else cur_cfg["label"], inline=True)
        else:
            embed.add_field(name="🏆 Role hiện tại", value="Chưa đủ điều kiện", inline=True)

        next_roles = [r for r in buy_roles if total < r.get("min_amount", 0)]
        if next_roles:
            nxt  = next_roles[0]
            need = nxt["min_amount"] - total
            ro2  = interaction.guild.get_role(nxt["role_id"])
            embed.add_field(
                name="⬆️ Role tiếp theo",
                value=f"{ro2.mention if ro2 else nxt['label']} — cần thêm **{fmt_amount(need)}**",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

class SetUserSpentModal(Modal, title="✏️ Sửa Tổng Tiền Của User"):
    user_id_input = TextInput(
        label="ID của User",
        placeholder="Chuột phải vào user → Copy ID",
        min_length=15, max_length=20
    )
    amount_input = TextInput(
        label="Tổng tiền mới",
        placeholder="VD: 50k, 1tr5, 200000",
        min_length=1, max_length=15
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

        new_total = parse_amount(self.amount_input.value)
        if new_total is None or new_total < 0:
            return await interaction.response.send_message(
                f"❌ Số tiền `{self.amount_input.value}` không hợp lệ!", ephemeral=True
            )

        data = load_data()
        if "user_total_spent" not in data:
            data["user_total_spent"] = {}
        old_total = data["user_total_spent"].get(str(uid), 0)
        data["user_total_spent"][str(uid)] = new_total
        save_data(data)

        member = interaction.guild.get_member(uid)
        if member:
            await auto_give_buy_roles(interaction.guild, member, new_total)

        embed = discord.Embed(title="✅ Đã Sửa Tổng Tiền", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 User",         value=member.mention if member else f"ID:{uid}",   inline=True)
        embed.add_field(name="💰 Tổng tiền cũ", value=f"**{fmt_amount(old_total)}**",              inline=True)
        embed.add_field(name="💰 Tổng tiền mới", value=f"**{fmt_amount(new_total)}**",             inline=True)
        embed.set_footer(text=f"Sửa bởi {interaction.user}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SyncExistingRolesModal(Modal, title="🔄 Sync Role Cũ → Tổng Tiền"):
    default_amount_input = TextInput(
        label="Tổng tiền mặc định theo từng bậc role",
        placeholder="VD: 50k,100k,200k — từ thấp→cao (bỏ trống = dùng min_amount)",
        required=False,
        max_length=100
    )
    overwrite_input = TextInput(
        label="Ghi đè người đã có data? (yes/no)",
        placeholder="no = chỉ set cho người chưa có dữ liệu (mặc định)",
        default="no",
        max_length=5,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        buy_roles = get_buy_roles()
        if not buy_roles:
            return await interaction.followup.send("❌ Chưa cấu hình role nào.", ephemeral=True)

        overwrite = self.overwrite_input.value.strip().lower() in ("yes", "y", "có", "co")

        raw = self.default_amount_input.value.strip()
        if raw:
            parts = [x.strip() for x in raw.split(",")]
            default_amounts = []
            for p in parts:
                a = parse_amount(p)
                if a is None:
                    return await interaction.followup.send(f"❌ Số tiền `{p}` không hợp lệ!", ephemeral=True)
                default_amounts.append(a)
        else:
            default_amounts = [r["min_amount"] for r in buy_roles]

        while len(default_amounts) < len(buy_roles):
            default_amounts.append(default_amounts[-1] if default_amounts else 0)

        guild = interaction.guild
        data  = load_data()
        if "user_total_spent" not in data:
            data["user_total_spent"] = {}

        synced = 0; skipped = 0; lines = []

        for member in guild.members:
            if member.bot:
                continue
            uid_str = str(member.id)
            already = uid_str in data["user_total_spent"]

            highest_idx = -1
            for i, r_cfg in enumerate(buy_roles):
                role = guild.get_role(r_cfg["role_id"])
                if role and role in member.roles:
                    highest_idx = i

            if highest_idx == -1:
                continue
            if already and not overwrite:
                skipped += 1
                continue

            target = default_amounts[highest_idx]
            old    = data["user_total_spent"].get(uid_str, 0)
            data["user_total_spent"][uid_str] = target
            synced += 1
            label  = buy_roles[highest_idx].get("label", "?")
            lines.append(f"› {_uname(member)} — **{label}** → **{fmt_amount(target)}** (cũ: {fmt_amount(old)})")

        save_data(data)

        embed = discord.Embed(title="🔄 Sync Hoàn Tất", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="✅ Đã sync", value=f"**{synced}** thành viên",     inline=True)
        embed.add_field(name="⏭️ Bỏ qua", value=f"**{skipped}** (đã có data)", inline=True)
        embed.add_field(name="🔁 Ghi đè", value="Có" if overwrite else "Không", inline=True)
        if lines:
            preview = "\n".join(lines[:20])
            if len(lines) > 20:
                preview += f"\n... (+{len(lines)-20} người nữa)"
            embed.add_field(name="📋 Chi tiết", value=preview[:1024], inline=False)
        embed.set_footer(text=f"Sync bởi {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def _show_channel_list(interaction: discord.Interaction, guild: discord.Guild):
    lines = []
    no_cat = [ch for ch in guild.channels if ch.category is None and isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
    if no_cat:
        lines.append("**— Không có category —**")
        for ch in sorted(no_cat, key=lambda c: c.position):
            icon = "💬" if isinstance(ch, discord.TextChannel) else "🔊"
            lines.append(f"  {icon} `#{ch.name}` (ID: {ch.id})")

    for cat in sorted(guild.categories, key=lambda c: c.position):
        lines.append(f"\n**📁 {cat.name}**")
        for ch in sorted(cat.channels, key=lambda c: c.position):
            icon = "💬" if isinstance(ch, discord.TextChannel) else ("🔊" if isinstance(ch, discord.VoiceChannel) else "📢")
            lines.append(f"  {icon} `{ch.name}` (ID: {ch.id})")

    text = "\n".join(lines) if lines else "Server không có kênh nào."
    chunks = []
    cur = ""
    for line in lines:
        if len(cur) + len(line) + 1 > 1800:
            chunks.append(cur)
            cur = line
        else:
            cur += "\n" + line
    if cur:
        chunks.append(cur)

    await interaction.response.send_message(
        f"📋 **Danh sách kênh — {guild.name}** ({len(guild.channels)} kênh)\n{chunks[0] if chunks else '(trống)'}",
        ephemeral=True
    )
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)

# ── Modal: Tạo kênh mới ──
class CreateChannelModal(Modal, title="➕ Tạo Kênh Mới"):
    ch_name = TextInput(label="Tên kênh", placeholder="vd: 💰•money hoặc ✅•legit-0", max_length=100)
    ch_type = TextInput(label="Loại (text/voice/category)", placeholder="text", default="text", max_length=10)
    font    = TextInput(label="Font (normal/bold/sans_bold/serif/script/double)", placeholder="normal", default="normal", max_length=20, required=False)

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        raw_name = self.ch_name.value.strip()
        ch_type  = self.ch_type.value.strip().lower()
        font     = self.font.value.strip().lower() or "normal"

        parts = _detect_channel_parts(raw_name)
        final_name = _rebuild_name(parts, parts["base_text"], font)
        # Discord yêu cầu tên kênh không có ký tự đặc biệt trong phần slug (chỉ với text channel)

        try:
            if ch_type in ("voice", "vc"):
                ch = await self.guild.create_voice_channel(final_name, reason=f"Setup bởi {interaction.user}")
                icon = "🔊"
            elif ch_type in ("category", "cat"):
                ch = await self.guild.create_category(final_name, reason=f"Setup bởi {interaction.user}")
                icon = "📁"
            else:
                ch = await self.guild.create_text_channel(final_name, reason=f"Setup bởi {interaction.user}")
                icon = "💬"

            embed = discord.Embed(title="✅ Tạo Kênh Thành Công", color=0x57F287,
                                  timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Tên", value=f"`{final_name}`", inline=True)
            embed.add_field(name="Loại", value=f"{icon} {ch_type}", inline=True)
            embed.add_field(name="Font", value=FONT_LABELS.get(font, font), inline=True)
            if isinstance(ch, discord.TextChannel):
                embed.add_field(name="Kênh", value=ch.mention, inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền tạo kênh!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Lỗi: {e}", ephemeral=True)

# ── Modal: Nhập font mẫu để đổi tên hàng loạt ──
class SetupFontSampleModal(Modal, title="✏️ Đổi Tên Kênh Hàng Loạt"):
    sample = TextInput(
        label="Font mẫu (paste ký tự hoặc gõ tên font)",
        placeholder="Paste: 𝐐𝐮𝐢𝐞𝐭 𝐒𝐜𝐡𝐞𝐦𝐚𝐭𝐢𝐜𝐬  hoặc gõ: bold",
        max_length=50,
        required=False
    )
    font_name = TextInput(
        label="Font: bold/sans_bold/serif/script/double",
        placeholder="bold | sans_bold | serif | script | double | normal",
        default="bold",
        max_length=20,
        required=False
    )
    scope = TextInput(
        label="Áp dụng cho? (all/text/voice/category)",
        placeholder="all",
        default="all",
        max_length=20,
        required=False
    )

    def __init__(self, guild: discord.Guild, mode: str = "rename"):
        super().__init__()
        self.guild = guild
        self.mode  = mode

    async def on_submit(self, interaction: discord.Interaction):
        font     = self.font_name.value.strip().lower() or "sans_bold"
        scope    = self.scope.value.strip().lower() or "all"

        sample_text = self.sample.value.strip()
        if sample_text:
            font = _detect_font_from_sample(sample_text) or font

        await interaction.response.send_message(
            f"⏳ Đang xem trước... Font: **{FONT_LABELS.get(font, font)}** | Scope: **{scope}**",
            ephemeral=True,
            view=RenamePreviewView(self.guild, font, scope)
        )

def _detect_font_from_sample(sample: str) -> str:
    """Nhận diện font từ ký tự Unicode mẫu người dùng paste vào, hoặc từ alias tên."""
    if not sample:
        return "normal"

    # Kiểm tra alias trước (user gõ tên như "bold", "quiet", "sb", "serif"...)
    low = sample.strip().lower()
    if low in FONT_ALIASES:
        return FONT_ALIASES[low]
    if low in FONT_LABELS:
        return low

    c = sample[0]
    cp = ord(c)
    if 0x1D400 <= cp <= 0x1D433:
        return "bold"
    if 0x1D7CE <= cp <= 0x1D7D7:
        return "bold"
    if 0x1D468 <= cp <= 0x1D49B:
        return "bold_italic"
    if 0x1D5D4 <= cp <= 0x1D607:
        return "sans_bold"
    if 0x1D7EC <= cp <= 0x1D7F5:
        return "sans_bold"
    if 0x1D4D0 <= cp <= 0x1D503 or c in "ℬℰℱℋℐℒℳℛℯℊℴ":
        return "script"
    if 0x1D538 <= cp <= 0x1D56B or c in "ℂℍℕℙℚℝℤ":
        return "double"
    return "normal"

# ── View: Preview đổi tên hàng loạt ──
class RenamePreviewView(View):
    def __init__(self, guild: discord.Guild, font: str, scope: str):
        super().__init__(timeout=180)
        self.guild = guild
        self.font  = font
        self.scope = scope

    def _get_channels(self):
        import re as _re_tc
        scope = self.scope
        channels = []
        for ch in self.guild.channels:
            if scope == "text"     and not isinstance(ch, discord.TextChannel):     continue
            if scope == "voice"    and not isinstance(ch, discord.VoiceChannel):    continue
            if scope == "category" and not isinstance(ch, discord.CategoryChannel): continue
            # Bỏ qua kênh có tên bắt đầu bằng ticket- (ticket-001, ticket-002, ...)
            if _re_tc.match(r'^ticket-', ch.name, _re_tc.IGNORECASE):
                continue
            channels.append(ch)
        return sorted(channels, key=lambda c: c.position)

    def _build_preview(self):
        channels = self._get_channels()
        lines = []
        for ch in channels[:30]:   # preview tối đa 30
            parts  = _detect_channel_parts(ch.name)
            new_name = _rebuild_name(parts, parts["base_text"], self.font)
            if new_name != ch.name:
                lines.append(f"`{ch.name}` → `{new_name}`")
        return lines, len(channels)

    @discord.ui.button(label="👁️ Xem trước 30 kênh đầu", style=discord.ButtonStyle.secondary)
    async def btn_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        import re as _re_tc3
        ticket_skipped = sum(
            1 for ch in self.guild.channels
            if _re_tc3.match(r'^ticket-', ch.name, _re_tc3.IGNORECASE)
        )
        lines, total = self._build_preview()
        if not lines:
            return await interaction.response.send_message(
                f"✅ Không có kênh nào cần đổi tên với font này.\n"
                f"⏭️ Đã bỏ qua **{ticket_skipped}** kênh ticket-.",
                ephemeral=True
            )
        text = "\n".join(lines[:25])
        await interaction.response.send_message(
            f"👁️ **Preview** ({total} kênh — font: {FONT_LABELS.get(self.font, self.font)})\n"
            f"⏭️ Bỏ qua **{ticket_skipped}** kênh ticket-\n```\n{text}\n```",
            ephemeral=True
        )

    @discord.ui.button(label="✅ Xác nhận đổi tên", style=discord.ButtonStyle.success)
    async def btn_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        import re as _re_tc2
        ticket_skipped = [
            ch for ch in self.guild.channels
            if _re_tc2.match(r'^ticket-', ch.name, _re_tc2.IGNORECASE)
        ]
        channels = self._get_channels()
        await interaction.response.send_message(
            f"⏳ Đang đổi tên **{len(channels)}** kênh... "
            f"(bỏ qua **{len(ticket_skipped)}** kênh ticket-)",
            ephemeral=True
        )
        done, errors = 0, []
        skipped_already = []   # đã đúng font
        skipped_empty   = []   # base_text rỗng (divider, ký tự đặc biệt)

        for ch in channels:
            parts    = _detect_channel_parts(ch.name)
            new_name = _rebuild_name(parts, parts["base_text"], self.font)

            if new_name == ch.name:
                if not parts["base_text"].strip():
                    skipped_empty.append(f"`{ch.name}`")
                else:
                    skipped_already.append(f"`{ch.name}`")
                continue

            try:
                await ch.edit(name=new_name, reason=f"Setup font bởi {interaction.user}")
                done += 1
                await asyncio.sleep(0.7)
            except discord.Forbidden:
                errors.append(f"`{ch.name}` — thiếu quyền")
            except Exception as e:
                errors.append(f"`{ch.name}` — {e}")

        result = f"✅ Đổi tên thành công: **{done}** kênh"

        if done > 0:
            set_cfg_font(self.font)
            result += f"\n💾 Đã lưu font server: **{FONT_LABELS.get(self.font, self.font)}**"

        if skipped_already:
            result += f"\n\n⏭️ **Đã đúng font ({len(skipped_already)})** — bỏ qua:\n"
            result += " ".join(skipped_already[:20])
            if len(skipped_already) > 20:
                result += f" ... (+{len(skipped_already)-20})"

        if skipped_empty:
            result += f"\n\n🚫 **Không xử lý được ({len(skipped_empty)})** — divider/ký tự đặc biệt:\n"
            result += " ".join(skipped_empty[:20])

        if errors:
            result += f"\n\n❌ Lỗi ({len(errors)}):\n" + "\n".join(errors[:10])

        await interaction.followup.send(result, ephemeral=True)

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🚫 Đã huỷ thao tác.", ephemeral=True)
        self.stop()

# ── View: Chọn font ──
class FontSelectView(View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        self.guild = guild
        options = [
            discord.SelectOption(label=label, value=key, description=f"Font: {key}")
            for key, label in FONT_LABELS.items()
        ]
        self.add_item(FontSelectMenu(guild, options))

class FontSelectMenu(Select):
    def __init__(self, guild: discord.Guild, options):
        super().__init__(placeholder="Chọn font chữ...", options=options, min_values=1, max_values=1)
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        font = self.values[0]
        _setup_sessions[self.guild.id] = _setup_sessions.get(self.guild.id, {})
        _setup_sessions[self.guild.id]["font"] = font
        sample = _apply_font("Legit Money Store", font)
        await interaction.response.send_message(
            f"✅ Đã chọn font: **{FONT_LABELS.get(font, font)}**\nMẫu: `{sample}`\n\n"
            f"Dùng nút **✏️ Đổi tên kênh** để áp dụng.",
            ephemeral=True
        )

# ── View: Chọn kênh để sửa quyền ──
class PermSelectView(View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        options = [
            discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
            for ch in sorted(guild.text_channels, key=lambda c: c.position)[:25]
        ]
        if options:
            self.add_item(PermChannelSelect(guild, options))

    @discord.ui.button(label="🔒 Khoá @everyone đọc kênh này", style=discord.ButtonStyle.danger, row=1)
    async def btn_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        ch = interaction.channel
        try:
            await ch.set_permissions(interaction.guild.default_role,
                                     read_messages=False,
                                     reason=f"Lock bởi {interaction.user}")
            await interaction.response.send_message(f"🔒 Đã khoá `#{ch.name}` với @everyone.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)

    @discord.ui.button(label="🔓 Mở khoá @everyone", style=discord.ButtonStyle.success, row=1)
    async def btn_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        ch = interaction.channel
        try:
            await ch.set_permissions(interaction.guild.default_role,
                                     read_messages=True,
                                     reason=f"Unlock bởi {interaction.user}")
            await interaction.response.send_message(f"🔓 Đã mở khoá `#{ch.name}` với @everyone.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)

class PermChannelSelect(Select):
    def __init__(self, guild: discord.Guild, options):
        super().__init__(placeholder="Chọn kênh để xem/sửa quyền...", options=options)
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        ch_id = int(self.values[0])
        ch = self.guild.get_channel(ch_id)
        if not ch:
            return await interaction.response.send_message("❌ Không tìm thấy kênh.", ephemeral=True)

        overwrites = ch.overwrites
        lines = []
        for target, ow in overwrites.items():
            name = target.name if hasattr(target, "name") else str(target)
            pairs = []
            if ow.read_messages is not None:
                pairs.append(f"xem={'✅' if ow.read_messages else '❌'}")
            if ow.send_messages is not None:
                pairs.append(f"gửi={'✅' if ow.send_messages else '❌'}")
            if ow.manage_messages is not None:
                pairs.append(f"quản lý={'✅' if ow.manage_messages else '❌'}")
            lines.append(f"**{name}**: {', '.join(pairs) or 'mặc định'}")

        perm_text = "\n".join(lines) if lines else "Không có quyền tuỳ chỉnh"
        await interaction.response.send_message(
            f"🔒 **Quyền kênh `#{ch.name}`**\n{perm_text}\n\n"
            f"Dùng `.setperm #{ch.name} @role xem=true gửi=false` để sửa.",
            ephemeral=True
        )

@bot.command(name="setup")
async def setup_cmd(ctx):
    if not can_use_dangerous_cmd(ctx.author.id, "setup"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    guild = ctx.guild
    if not guild:
        return await ctx.reply("❌ Lệnh này chỉ dùng trong server.")

    text_ch  = len(guild.text_channels)
    voice_ch = len(guild.voice_channels)
    cats     = len(guild.categories)
    members  = guild.member_count

    embed = discord.Embed(
        title=f"⚙️  Setup Server — {guild.name}",
        description=(
            f"👥 **{members}** thành viên  |  "
            f"💬 **{text_ch}** text  |  "
            f"🔊 **{voice_ch}** voice  |  "
            f"📁 **{cats}** category\n\n"
            "Chọn thao tác bên dưới:"
        ),
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(
        name="📝 Các chức năng",
        value=(
            "› **📋 Xem danh sách kênh** — liệt kê toàn bộ kênh theo category\n"
            "› **✏️ Đổi tên hàng loạt** — áp dụng font chữ mới cho tên kênh\n"
            "› **➕ Tạo kênh mới** — tạo kênh text/voice/category với font\n"
            "› **🔒 Sửa quyền kênh** — xem & chỉnh quyền @everyone / role\n"
            "› **🔤 Chọn font chữ** — xem trước các kiểu font Unicode\n"
            "› **🏆 Cài Role Mua Hàng** — cấu hình role tự động theo số đơn (buy+, buy++, ...)"
        ),
        inline=False
    )
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Hết hạn sau 5 phút")
    await ctx.reply(embed=embed, view=SetupMainView(guild))

@bot.command(name="setperm")
async def setperm_cmd(ctx, channel: discord.TextChannel = None, role: discord.Role = None, *, flags: str = ""):
    """
    Sửa quyền kênh nhanh.
    Cú pháp: .setperm #kênh @role xem=true gửi=false
    """
    if not can_use_dangerous_cmd(ctx.author.id, "setperm"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    if not channel or not role:
        return await ctx.reply("❌ Dùng: `.setperm #kênh @role xem=true gửi=false`")

    overwrite = channel.overwrites_for(role)
    flag_map = {
        "xem": "read_messages", "gửi": "send_messages",
        "đọc": "read_messages", "view": "read_messages",
        "send": "send_messages", "manage": "manage_messages",
        "ql": "manage_messages", "reaction": "add_reactions",
        "embed": "embed_links", "file": "attach_files",
    }
    changes = []
    for part in flags.split():
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.lower().strip()
        v = v.lower().strip()
        attr = flag_map.get(k)
        if not attr:
            continue
        val = True if v in ("true", "1", "yes", "✅", "on") else (False if v in ("false", "0", "no", "❌", "off") else None)
        if val is None:
            setattr(overwrite, attr, None)
        else:
            setattr(overwrite, attr, val)
        changes.append(f"{k}={'✅' if val else ('❌' if val is False else '↩️ default')}")

    if not changes:
        return await ctx.reply("❌ Không có flag hợp lệ.\nVí dụ: `xem=true gửi=false`")

    try:
        await channel.set_permissions(role, overwrite=overwrite, reason=f"setperm bởi {ctx.author}")
        await ctx.reply(f"✅ Đã sửa quyền `#{channel.name}` cho {role.mention}:\n" + "\n".join(f"  › {c}" for c in changes))
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền Manage Channels.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: {e}")

@bot.command(name="rename")
async def rename_cmd(ctx, channel: discord.abc.GuildChannel = None, *, new_name: str = None):
    """
    Đổi tên 1 kênh cụ thể, giữ icon & số đếm.
    Cú pháp: .rename #kênh tên-mới
    """
    if not can_use_dangerous_cmd(ctx.author.id, "rename"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    if not channel or not new_name:
        return await ctx.reply("❌ Dùng: `.rename #kênh tên-mới`")

    old_name = channel.name
    parts    = _detect_channel_parts(old_name)

    font = _setup_sessions.get(ctx.guild.id, {}).get("font", "normal")
    final_name = _rebuild_name(parts, new_name, font)

    try:
        await channel.edit(name=final_name, reason=f"Rename bởi {ctx.author}")
        await ctx.reply(f"✅ `{old_name}` → `{final_name}`")
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền.")
    except Exception as e:
        await ctx.reply(f"❌ {e}")

# ================= EMOJI COMMAND =================
import re as _re_emoji

@bot.command(name="emoji")
async def emoji_cmd(ctx, *, args: str = None):
    """
    .emoji         → Lắng nghe 60s, tự động thêm ảnh/GIF được gửi trong kênh làm emoji server.
    .emoji <emoji> → Thêm emoji từ server khác vào server này (có thể nhiều emoji cách nhau bởi khoảng trắng).
    Chỉ admin mới dùng được.
    """
    if not can_use_dangerous_cmd(ctx.author.id, "emoji"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")

    guild: discord.Guild = ctx.guild
    if guild is None:
        return await ctx.reply("❌ Lệnh này chỉ dùng được trong server.")

    if args:
        import aiohttp as _aiohttp

        _emoji_pattern = r"<(a?):([^:>]+):(\d+)>"
        matches = _re_emoji.findall(_emoji_pattern, args)
        if not matches:
            return await ctx.reply("❌ Không tìm thấy emoji hợp lệ.\nCú pháp: `.emoji <emoji1> <emoji2> ...`")

        prog_msg = await ctx.reply(f"⏳ Đang thêm **{len(matches)}** emoji, vui lòng chờ...")

        added, failed = [], []
        name_count: dict = {}

        n = len(matches)
        delay = 1.0 if n <= 5 else 2.0 if n <= 15 else 3.0 if n <= 30 else 5.0

        async with _aiohttp.ClientSession() as session:
            for idx, (animated, name, emoji_id) in enumerate(matches):
                ext = "gif" if animated else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?quality=lossless"

                base_name = name[:32]
                if base_name in name_count:
                    name_count[base_name] += 1
                    final_name = f"{base_name[:29]}_{name_count[base_name]}"
                else:
                    name_count[base_name] = 1
                    final_name = base_name

                try:
                    async with session.get(url, timeout=_aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            raise Exception(f"Không tải được ảnh (HTTP {resp.status})")
                        image_bytes = await resp.read()

                    new_emoji = await guild.create_custom_emoji(
                        name=final_name,
                        image=image_bytes,
                        reason=f"Thêm bởi {ctx.author} qua .emoji"
                    )
                    added.append(str(new_emoji))
                except discord.HTTPException as e:
                    failed.append(f"`{final_name}` — {e.text}")
                except Exception as e:
                    failed.append(f"`{final_name}` — {e}")

                if idx < n - 1:
                    await asyncio.sleep(delay)
                if (idx + 1) % 10 == 0:
                    await prog_msg.edit(content=f"⏳ Đang thêm emoji... **{idx+1}/{n}**")

        lines = []
        if added:
            emoji_str = " ".join(added)
            lines.append(f"✅ Đã thêm **{len(added)}** emoji:\n{emoji_str[:900]}")
        if failed:
            fail_str = "\n".join(failed[:20])
            lines.append(f"❌ Thất bại **{len(failed)}**:\n{fail_str}")

        result_text = "\n\n".join(lines) if lines else "Không có emoji nào được thêm."
        try:
            await prog_msg.edit(content=result_text)
        except Exception:
            await ctx.reply(result_text)
        return

    embed = discord.Embed(
        title="🖼️  Chế độ thêm Emoji",
        description="Gửi **ảnh hoặc GIF** vào kênh này trong **60 giây**.\n"
                    "Bot sẽ tự động thêm tất cả làm emoji của server.\n"
                    "Gõ `hủy` để dừng sớm.",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Được kích hoạt bởi {ctx.author}")
    status_msg = await ctx.reply(embed=embed)

    added, failed = [], []

    def check(m: discord.Message):
        return (
            m.channel == ctx.channel
            and not m.author.bot
            and m.author.id in ADMIN_IDS
            and (m.attachments or m.content.strip().lower() == "hủy")
        )

    deadline = asyncio.get_event_loop().time() + 60

    while asyncio.get_event_loop().time() < deadline:
        timeout_left = deadline - asyncio.get_event_loop().time()
        try:
            msg: discord.Message = await bot.wait_for("message", check=check, timeout=timeout_left)
        except asyncio.TimeoutError:
            break

        if msg.content.strip().lower() == "hủy":
            await msg.add_reaction("🛑")
            break

        for idx, attachment in enumerate(msg.attachments):
                content_type = attachment.content_type or ""
                if not (content_type.startswith("image/") or content_type.startswith("video/")):
                    failed.append(f"`{attachment.filename}` (không phải ảnh/GIF)")
                    continue

                raw_name = attachment.filename.rsplit(".", 1)[0]
                emoji_name = _re_emoji.sub(r"[^a-zA-Z0-9_]", "_", raw_name)[:32] or "emoji"
                if len(emoji_name) < 2:
                    emoji_name = emoji_name + "_"

                try:
                    image_bytes = await attachment.read()
                    new_emoji = await guild.create_custom_emoji(
                        name=emoji_name,
                        image=image_bytes,
                        reason=f"Thêm bởi {ctx.author} qua .emoji"
                    )
                    added.append(str(new_emoji))
                    await msg.add_reaction("✅")
                except discord.HTTPException as e:
                    failed.append(f"`{emoji_name}` ({e.text})")
                    await msg.add_reaction("❌")
                except Exception as e:
                    failed.append(f"`{emoji_name}` ({e})")
                    await msg.add_reaction("❌")

                if idx < len(msg.attachments) - 1:
                    await asyncio.sleep(1.5)

    result_embed = discord.Embed(
        title="✅  Kết Quả Thêm Emoji",
        color=0x57F287 if added else 0xED4245,
        timestamp=datetime.now(timezone.utc)
    )
    if added:
        result_embed.add_field(
            name=f"✅ Đã thêm ({len(added)})",
            value=" ".join(added) if added else "—",
            inline=False
        )
    if failed:
        result_embed.add_field(
            name=f"❌ Thất bại ({len(failed)})",
            value="\n".join(failed),
            inline=False
        )
    if not added and not failed:
        result_embed.description = "Không có ảnh nào được gửi trong 60 giây."

    result_embed.set_footer(text=f"Kích hoạt bởi {ctx.author}")
    await status_msg.edit(embed=result_embed)

# ================= XOÁ EMOJI COMMAND =================

@bot.command(name="delemoji", aliases=["deleteemoji", "xoaemoji", "removeemoji"])
async def delemoji_cmd(ctx, *, args: str = None):
    """
    Xoá emoji khỏi server.
    .delemoji <emoji>       → Xoá 1 hoặc nhiều emoji (cách nhau bởi khoảng trắng)
    .delemoji tên:tên2      → Xoá theo tên emoji (không cần paste emoji)
    Chỉ admin mới dùng được.
    """
    if not can_use_dangerous_cmd(ctx.author.id, "delemoji"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")

    guild: discord.Guild = ctx.guild
    if guild is None:
        return await ctx.reply("❌ Lệnh này chỉ dùng được trong server.")

    if not args:
        embed = discord.Embed(
            title="🗑️  Xoá Emoji Server",
            color=0xED4245,
            description=(
                "**Cách dùng:**\n"
                "`.delemoji <emoji1> <emoji2> ...` — paste emoji trực tiếp\n"
                "`.delemoji tên` — xoá theo tên emoji\n\n"
                "**Ví dụ:**\n"
                "`.delemoji :pepe: :catjam:` — paste nhiều emoji\n"
                "`.delemoji pepe` — xoá emoji tên \"pepe\""
            )
        )
        return await ctx.reply(embed=embed)

    _emoji_pattern = r"<(a?):([^:>]+):(\d+)>"
    matches = _re_emoji.findall(_emoji_pattern, args)

    to_delete: list[discord.Emoji] = []
    not_found: list[str] = []

    if matches:
        for _, name, emoji_id in matches:
            emoji = discord.utils.get(guild.emojis, id=int(emoji_id))
            if emoji:
                to_delete.append(emoji)
            else:
                not_found.append(f"`{name}` (ID: {emoji_id})")
    else:
        # Tìm theo tên (cho phép nhiều tên cách nhau khoảng trắng hoặc dấu phẩy)
        names = [n.strip().strip(":") for n in _re_emoji.split(r"[\s,]+", args.strip()) if n.strip()]
        for name in names:
            found = [e for e in guild.emojis if e.name.lower() == name.lower()]
            if found:
                to_delete.extend(found)
            else:
                not_found.append(f"`{name}`")

    if not to_delete and not_found:
        return await ctx.reply(
            f"❌ Không tìm thấy emoji nào trong server:\n" + "\n".join(not_found)
        )

    prog_msg = await ctx.reply(f"⏳ Đang xoá **{len(to_delete)}** emoji...")

    deleted, failed = [], []
    for emoji in to_delete:
        try:
            await emoji.delete(reason=f"Xoá bởi {ctx.author} qua .delemoji")
            deleted.append(f"`:{emoji.name}:`")
        except discord.Forbidden:
            failed.append(f"`:{emoji.name}:` (thiếu quyền)")
        except Exception as e:
            failed.append(f"`:{emoji.name}:` ({e})")

    embed = discord.Embed(
        title="🗑️  Kết Quả Xoá Emoji",
        color=0x57F287 if deleted else 0xED4245,
        timestamp=datetime.now(timezone.utc)
    )
    if deleted:
        embed.add_field(
            name=f"✅ Đã xoá ({len(deleted)})",
            value=" ".join(deleted)[:1024],
            inline=False
        )
    if failed:
        embed.add_field(
            name=f"❌ Thất bại ({len(failed)})",
            value="\n".join(failed)[:1024],
            inline=False
        )
    if not_found:
        embed.add_field(
            name=f"🔍 Không tìm thấy ({len(not_found)})",
            value="\n".join(not_found)[:512],
            inline=False
        )
    embed.set_footer(text=f"Xoá bởi {ctx.author}")
    await prog_msg.edit(content=None, embed=embed)

# Cấu trúc mỗi mục: {"key": str, "name": str, "content": str}
# content là raw text hiển thị thẳng vào embed field (giữ markdown, emoji, blockquote)

_DEFAULT_PRICE_SECTIONS = [
    {
        "key": "steam",
        "name": "🎮  Game Steam",
        "content": (
            "**Giá stock:**\n"
            "> - **acc offline đông giá 60.000 VNĐ**"
        ),
    },
    {
        "key": "robux",
        "name": "<:robux:1456493708382830735>  Robux",
        "content": (
            "**Giá stock:**\n"
            "> - **250 <:robux:1456493708382830735> -> 47.000 VNĐ**\n"
            "> - **500 <:robux:1456493708382830735> -> 89.000 VNĐ**\n"
            "> - **750 <:robux:1456493708382830735> -> 129.000 VNĐ**\n"
            "> - **1000 <:robux:1456493708382830735> -> 165.000 VNĐ**"
        ),
    },
    {
        "key": "nitro",
        "name": "💎  Nitro",
        "content": (
            "**Giá stock:**\n"
            "> - **1 Tháng: 95.000 VNĐ**\n"
            "> - **2 Tháng: 119.000 VNĐ**\n"
            "> - **12 Tháng: 899.000 VNĐ**"
        ),
    },
    {
        "key": "decao_login_gip",
        "name": "🎵  Decao — Dạng Login & Gip",
        "content": (
            "**Dạng login**\n"
            "> - ~~66.000 VNĐ~~ -> **35.000 VNĐ**\n"
            "> - ~~79.000 VNĐ~~ -> **45.000 VNĐ**\n"
            "> - ~~92.000 VNĐ~~ -> **55.000 VNĐ**\n"
            "> - ~~105.000 VNĐ~~ -> **62.000 VNĐ**\n"
            "> - ~~111.000 VNĐ~~ -> **74.000 VNĐ**\n"
            "> - ~~118.000 VNĐ~~ -> **79.000 VNĐ**\n"
            "> - ~~131.000 VNĐ~~ -> **92.000 VNĐ**\n"
            "> - ~~136.000 VNĐ~~ -> **99.000 VNĐ**\n"
            "> - ~~141.000 VNĐ~~ -> **103.000 VNĐ**\n"
            "> - ~~146.000 VNĐ~~ -> **109.000 VNĐ**\n"
            "> - ~~189.000 VNĐ~~ -> **125.000 VNĐ**\n"
            "**Dạng gip**\n"
            "> - ~~66.000 VNĐ~~ -> **48.000 VNĐ**\n"
            "> - ~~79.000 VNĐ~~ -> **58.000 VNĐ**\n"
            "> - ~~92.000 VNĐ~~ -> **62.000 VNĐ**\n"
            "> - ~~105.000 VNĐ~~ -> **69.000 VNĐ**\n"
            "> - ~~111.000 VNĐ~~ -> **85.000 VNĐ**\n"
            "> - ~~118.000 VNĐ~~ -> **89.000 VNĐ**\n"
            "> - ~~131.000 VNĐ~~ -> **99.000 VNĐ**\n"
            "> - ~~136.000 VNĐ~~ -> **109.000 VNĐ**\n"
            "> - ~~141.000 VNĐ~~ -> **114.000 VNĐ**\n"
            "> - ~~146.000 VNĐ~~ -> **119.000 VNĐ**\n"
            "> - ~~189.000 VNĐ~~ -> **139.000 VNĐ**"
        ),
    },
    {
        "key": "decao_bundle",
        "name": "🎵  Decao — Gip Bundle",
        "content": (
            "> - **x2 dc66: 85.000 VNĐ**\n"
            "> - **x3 dc66: 120.000 VNĐ**\n"
            "> - **x3 dc79: 140.000 VNĐ**\n"
            "> - **x2 dc92: 115.000 VNĐ**\n"
            "> - **x3 dc92: 165.000 VNĐ**\n"
            "> - **x2 dc105: 115.000 VNĐ**\n"
            "> - **x2 dc118: 150.000 VNĐ**\n"
            "> - **x3 dc118: 240.000 VNĐ**\n"
            "> - **x2 dc131: 170.000 VNĐ**"
        ),
    },
    {
        "key": "chatgpt",
        "name": "🤖  Chat GPT",
        "content": (
            "**Giá stock:**\n"
            "> - **Chat GPT Plus 1 tháng: hết hàng**\n"
            "> - **Code Chat GPT Plus 1 tháng: hết hàng**"
        ),
    },
    {
        "key": "capcut",
        "name": "✂️  CapCut",
        "content": (
            "**Giá stock:**\n"
            "> - **Capcut Pro 35day: 20.000 VNĐ**\n"
            "> - **Capcut Pro 6 Tháng: 120.000 VNĐ**"
        ),
    },
    {
        "key": "canva",
        "name": "🎨  Canva",
        "content": (
            "**Giá stock:**\n"
            "> - **2 tháng pro: 15.000 VNĐ**"
        ),
    },
    {
        "key": "youtube",
        "name": "▶️  YouTube Premium",
        "content": (
            "**Giá stock:**\n"
            "> - **15.000 VNĐ/Tháng**"
        ),
    },
]

def get_price_sections() -> list:
    data = load_data()
    return data.get("price_sections", _DEFAULT_PRICE_SECTIONS)

def save_price_sections(sections: list):
    data = load_data()
    data["price_sections"] = sections
    save_data(data)

def build_sv_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏪  TuyTam Store — Bảng Giá",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc),
    )
    for sec in get_price_sections():
        embed.add_field(name=sec["name"], value=sec["content"], inline=False)
    embed.set_footer(text="TuyTam Store  •  .sv để xem lại bất cứ lúc nào")
    return embed

# ── Modal: Sửa nội dung 1 mục giá ──
class EditPriceModal(Modal):
    def __init__(self, section: dict, index: int):
        super().__init__(title=f"✏️ Sửa: {section['name'][:40]}")
        self.section = section
        self.index   = index

        self.name_input = TextInput(
            label="Tên mục (có thể chứa emoji)",
            default=section["name"],
            max_length=100,
        )
        self.add_item(self.name_input)

        self.content_input = TextInput(
            label="Nội dung (markdown, blockquote, emoji OK)",
            default=section["content"],
            style=discord.TextStyle.paragraph,
            max_length=1024,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        sections = get_price_sections()
        if self.index >= len(sections):
            return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)

        sections[self.index]["name"]    = self.name_input.value.strip()
        sections[self.index]["content"] = self.content_input.value.strip()
        save_price_sections(sections)

        await interaction.response.send_message(
            f"✅ Đã cập nhật mục **{sections[self.index]['name']}**!\n"
            f"Dùng `.sv` để xem bảng giá mới.",
            ephemeral=True
        )

# ── Select: Chọn mục muốn sửa ──
class EditPriceSectionSelect(Select):
    def __init__(self):
        sections = get_price_sections()
        options  = [
            discord.SelectOption(
                label=sec["name"][:100],
                value=str(i),
                description=f"Key: {sec['key']}"
            )
            for i, sec in enumerate(sections)
        ]
        super().__init__(placeholder="Chọn mục muốn sửa...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        idx      = int(self.values[0])
        sections = get_price_sections()
        if idx >= len(sections):
            return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)
        await interaction.response.send_modal(EditPriceModal(sections[idx], idx))

# ── View chính của .giaset ──
class PriceManagerView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(EditPriceSectionSelect())

    @discord.ui.button(label="➕ Thêm mục mới", style=discord.ButtonStyle.success, row=1)
    async def add_section(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(AddPriceSectionModal())

    @discord.ui.button(label="🗑️ Xoá mục", style=discord.ButtonStyle.danger, row=1)
    async def del_section(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_message(
            "Chọn mục muốn xoá:", view=DeletePriceSectionView(), ephemeral=True
        )

    @discord.ui.button(label="🔄 Reset về mặc định", style=discord.ButtonStyle.grey, row=1)
    async def reset_sections(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        save_price_sections(_DEFAULT_PRICE_SECTIONS)
        await interaction.response.send_message("✅ Đã reset bảng giá về mặc định!", ephemeral=True)

    @discord.ui.button(label="👁️ Xem trước .sv", style=discord.ButtonStyle.blurple, row=2)
    async def preview(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(embed=build_sv_embed(), ephemeral=True)

# ── Modal: Thêm mục giá mới ──
class AddPriceSectionModal(Modal, title="➕ Thêm Mục Giá Mới"):
    key_input = TextInput(
        label="Key (chữ thường, không dấu, không khoảng trắng)",
        placeholder="vd: spotify, tiktok, office",
        max_length=30,
    )
    name_input = TextInput(
        label="Tên mục (có thể chứa emoji)",
        placeholder="vd: 🎵  Spotify",
        max_length=100,
    )
    content_input = TextInput(
        label="Nội dung (markdown, blockquote, emoji OK)",
        placeholder="> - **Gói 1 tháng: 30.000 VNĐ**",
        style=discord.TextStyle.paragraph,
        max_length=1024,
    )

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip().lower().replace(" ", "_")
        sections = get_price_sections()
        for s in sections:
            if s["key"] == key:
                return await interaction.response.send_message(
                    f"❌ Key `{key}` đã tồn tại! Chọn key khác.", ephemeral=True
                )
        sections.append({
            "key":     key,
            "name":    self.name_input.value.strip(),
            "content": self.content_input.value.strip(),
        })
        save_price_sections(sections)
        await interaction.response.send_message(
            f"✅ Đã thêm mục **{self.name_input.value.strip()}** vào bảng giá!", ephemeral=True
        )

# ── View xoá mục ──
class DeletePriceSectionSelect(Select):
    def __init__(self):
        sections = get_price_sections()
        options  = [
            discord.SelectOption(label=sec["name"][:100], value=str(i), description=f"Key: {sec['key']}")
            for i, sec in enumerate(sections)
        ]
        super().__init__(placeholder="Chọn mục muốn xoá...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        idx      = int(self.values[0])
        sections = get_price_sections()
        if idx >= len(sections):
            return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)
        removed = sections.pop(idx)
        save_price_sections(sections)
        await interaction.response.send_message(
            f"🗑️ Đã xoá mục **{removed['name']}** khỏi bảng giá.", ephemeral=True
        )

class DeletePriceSectionView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(DeletePriceSectionSelect())

# ── Lệnh .sv — hiển thị bảng giá ──
@bot.command(name="sv", aliases=["dichvu", "service"])
async def sv_command(ctx: commands.Context):
    await ctx.send(embed=build_sv_embed())

# ── Lệnh .giaset — admin quản lý bảng giá ──
@bot.command(name="giaset", aliases=["setgia", "pricemanager", "priceset"])
async def giaset_command(ctx: commands.Context):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")

    sections = get_price_sections()
    embed = discord.Embed(
        title="⚙️  Quản Lý Bảng Giá — .sv",
        description=(
            f"Hiện có **{len(sections)} mục** trong bảng giá.\n"
            "Chọn mục từ dropdown để **sửa**, hoặc dùng nút bên dưới để **thêm/xoá/reset**.\n\n"
            + "\n".join(f"`{i+1}.` {s['name']}" for i, s in enumerate(sections))
        ),
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="💡 Hướng dẫn nội dung",
        value=(
            "Hỗ trợ đầy đủ **Discord markdown**:\n"
            "› `**bold**`, `~~gạch~~`, `> blockquote`\n"
            "› Emoji server: `<:tên:id>`\n"
            "› Mention: `<@userID>`\n"
            "› `### Tiêu đề nhỏ`"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Timeout 2 phút")
    await ctx.reply(embed=embed, view=PriceManagerView())

# ── Resume giveaway sau khi bot restart ──
async def resume_active_giveaways():
    saved = load_giveaways_data()
    if not saved:
        return
    now = datetime.now(timezone.utc).timestamp()
    resumed = 0
    for mid, gw in saved.items():
        if gw.get("ended"):
            active_giveaways[mid] = gw   # giữ lại để greroll hoạt động
            continue
        active_giveaways[mid] = gw
        channel_id  = gw.get("channel_id")
        winners_cnt = gw.get("winners", 1)
        end_time    = gw.get("end_time", 0)
        remaining   = end_time - now
        gw_type     = gw.get("type", "reaction")

        if remaining <= 0:
            channel = bot.get_channel(channel_id)
            if channel:
                if gw_type == "button":
                    asyncio.create_task(giveaway_timer(channel_id, mid, winners_cnt, 0))
                else:
                    prize   = gw.get("prize", "phần thưởng")
                    host_id = gw.get("host_id", 0)
                    asyncio.create_task(end_giveaway(mid, channel, winners_cnt, prize, host_id))
        else:
            if gw_type == "button":
                asyncio.create_task(giveaway_timer(channel_id, mid, winners_cnt, int(remaining)))
            else:
                async def _reaction_resume(m=mid, ch=channel_id, w=winners_cnt,
                                            p=gw.get("prize",""), h=gw.get("host_id",0), r=remaining):
                    await asyncio.sleep(r)
                    if not active_giveaways.get(m, {}).get("ended"):
                        channel_obj = bot.get_channel(ch)
                        if channel_obj:
                            await end_giveaway(m, channel_obj, w, p, h)
                asyncio.create_task(_reaction_resume())
        resumed += 1
        print(f"[GIVEAWAY] ▶️  Resume mid={mid} type={gw_type} còn {max(0,int(remaining))}s")
    if resumed:
        print(f"[GIVEAWAY] ✅ Đã resume {resumed} giveaway")

# ================= ON READY =================
@bot.event
async def on_ready():
    await init_data_cache()

    await resume_active_giveaways()

    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    bot.add_view(GiveawayView())  # persistent view cho nút Tham gia giveaway

    for guild in bot.guilds:
        await _cache_invites(guild)
        await sync_ticket_counter(guild)

    try:
        synced = await tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")

    print(f"✅ Bot online: {bot.user} | {len(bot.guilds)} server(s)")

    changelog_ch = bot.get_channel(CHANGELOG_CHANNEL_ID)
    if changelog_ch:
        embed = discord.Embed(
            title=f"📋 Changelog — v{BOT_VERSION}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
            description=(
                f"Bot đã khởi động lại và cập nhật lên **v{BOT_VERSION}** ({BOT_UPDATED})\n"
            )
        )
        embed.add_field(
            name="🆕 v3.3.5 — Phân Quyền Admin & Seller Role Ticket",
            value=(
                "• Chỉ **ADMIN_IDS** mới dùng được các lệnh: `.clear`, `.close`, `.done`, `.addnote`\n"
                "• **Seller Role** được tự động thêm vào **mọi ticket** khi tạo\n"
                "  *(view, send, history, manage messages, attach files, embed links)*\n"
                "• Các nút trong ticket (Mua/Add Staff/Ghi chú/Đóng/Hoàn thành/Gửi QR) vẫn cho phép staff dùng"
            ),
            inline=False
        )
        embed.add_field(
            name="🆕 v3.3.0 — Quản Lý Bảng Giá (.giaset)",
            value=(
                "• Lệnh `.giaset` — admin **sửa/thêm/xoá/reset** từng mục giá trong `.sv`\n"
                "• Giao diện dropdown + modal: chọn mục → sửa tên & nội dung trực tiếp\n"
                "• Bảng giá lưu **MongoDB** — persistent, không mất khi restart bot\n"
                "• Nút **👁️ Xem trước** để kiểm tra trước khi đăng"
            ),
            inline=False
        )
        embed.add_field(
            name="📦 v3.1.0 — Seller Ticket & Bảng Giá",
            value=(
                "• Nút **Mua/Bán** trong panel → hiển thị danh sách **seller** (không còn chọn item)\n"
                "• Tên ticket = **(tên seller)-(số ticket)** — VD: `tuytam-001`\n"
                "• Buyer chọn seller → bot ping seller đó khi tạo ticket\n"
                "• Nút `Claim` đổi thành **Mua** (🛒)\n"
                "• Lệnh `.sv` → bảng giá đầy đủ: Steam, Robux, Nitro, Decao, ChatGPT, CapCut, Canva, YT Premium"
            ),
            inline=False
        )
        embed.add_field(
            name="📦 v3.0.0 — Dịch Vụ Setup Server & Cập Nhật Admin",
            value=(
                "• Thêm lệnh `.sv` / `.dichvu` / `.service` — gửi embed giới thiệu dịch vụ\n"
                "• Xoá admin ID `1438384178755276923` khỏi `ADMIN_IDS`\n"
                "• Thêm mục `.help dichvu` vào danh sách lệnh"
            ),
            inline=False
        )
        embed.add_field(
            name="📦 v2.9.0 — Hiển Thị Tên User Dạng Mention",
            value=(
                "• Toàn bộ tên user trong embed field/title/reply → **mention (username)**\n"
                "• Click được trực tiếp, hiện avatar tooltip khi hover\n"
                "• Footer/log/AI prompt vẫn dùng plain text `Display Name (username)`"
            ),
            inline=False
        )
        embed.add_field(
            name="📦 v2.8.0 — Giveaway Check Invite Winner",
            value=(
                "• Confirm view trước khi đăng — toggle bật/tắt check invite\n"
                "• Khi BẬT: sau khi xong tự gửi thống kê invite của từng winner"
            ),
            inline=False
        )
        embed.add_field(
            name="📦 v2.7.0 — Giveaway Fix & .gwlist",
            value=(
                "• Fix embed số người tham gia không cập nhật\n"
                "• `.gwlist <message_id>` — xem danh sách người tham gia *(admin)*"
            ),
            inline=False
        )
        embed.set_footer(text=f"TuyTam Store  •  Dùng .help để xem tất cả lệnh")
        try:
            await changelog_ch.send(embed=embed)
        except Exception as e:
            print(f"[CHANGELOG] ❌ Không gửi được: {e}")

bot.run(TOKEN)
