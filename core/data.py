"""
core/data.py — MongoDB storage, in-memory cache, và tất cả helper đọc/ghi data.
v3.6.3 fixes:
- save_data() dùng asyncio.create_task thay ensure_future (an toàn hơn)
- get_ticket_number() có asyncio.Lock tránh trùng số
- ADMIN_IDS đọc từ env ADMIN_IDS thay vì hardcode
- Logging lỗi rõ ràng thay vì except: pass
"""

import os
import asyncio
import logging
import contextvars
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import discord

log = logging.getLogger("data")

# ══════════════════════════════════════════
# MULTI-GUILD SUPPORT (thêm khi mở rộng ra server thứ 2)
# ══════════════════════════════════════════
# Guild ID của server chính (TuyTam Community) — dùng để migrate 1 lần dữ liệu
# từ document "main" cũ (single-guild) sang document "guild_<id>" (multi-guild).
LEGACY_MAIN_GUILD_ID = 1464407860640219189

# ContextVar giữ guild_id đang được xử lý trong task/coroutine hiện tại.
# Được set tự động ở bot.py (before_invoke + CommandTree.interaction_check + on_message)
# và ở GuildContextView/GuildContextModal bên dưới (cho các nút bấm/modal).
_current_guild_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_guild_id", default=None
)

def set_current_guild(guild_id: int | None):
    """Set guild đang xử lý cho task hiện tại. Trả về token để reset (không bắt buộc dùng)."""
    return _current_guild_id.set(guild_id)

def reset_current_guild(token) -> None:
    try:
        _current_guild_id.reset(token)
    except Exception:
        pass

def get_current_guild_id() -> int | None:
    return _current_guild_id.get()


# ══════════════════════════════════════════
# DATA CACHE READY EVENT
# ══════════════════════════════════════════
# FIX: init_data_cache() chạy trong on_ready nhưng hoàn tất ĐỘC LẬP và có thể MUỘN
# HƠN thời điểm bot.wait_until_ready() trả về (mất ~2-3s để load hết cache mọi guild).
# Các tasks.loop nền (check_expiry_loop, daily_report_task...) trước đây chỉ
# `await bot.wait_until_ready()` trong before_loop → vòng lặp đầu tiên có thể chạy
# TRƯỚC KHI _data_cache được nạp xong → "Guild X chưa có trong cache" lúc khởi động.
# Mọi tasks.loop nền đọc/ghi data theo guild PHẢI `await wait_data_cache_ready()`
# trong before_loop, SAU bot.wait_until_ready().
_data_cache_ready = asyncio.Event()

def is_data_cache_ready() -> bool:
    return _data_cache_ready.is_set()

async def wait_data_cache_ready() -> None:
    await _data_cache_ready.wait()


class GuildContextView(discord.ui.View):
    """Thay thế discord.ui.View — tự set guild context trước khi chạy callback của bất kỳ
    nút/select nào bên trong, để load_data()/save_data() thao tác đúng document của guild đó.
    Dùng: từ discord.ui import Button, Select  (KHÔNG import View)
          from core.data import GuildContextView as View
    """
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id:
            set_current_guild(interaction.guild_id)
        return True


class GuildContextModal(discord.ui.Modal):
    """Tương tự GuildContextView nhưng cho Modal."""
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id:
            set_current_guild(interaction.guild_id)
        return True


# ══════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════
# ⚠️ Các ID dưới đây là fallback mặc định — CHỈ đúng cho server chính (Tuytam Community).
# Server thứ 2 (hoặc bất kỳ guild mới nào) PHẢI tự cấu hình lại qua các lệnh .set*/.st,
# nếu không các hàm get_cfg_* sẽ trả về ID này (không tồn tại ở guild khác) → coi như "chưa cài".
LOG_CHANNEL           = 1482234024868053083
TICKET_CATEGORY_ID    = 1464426174611456195
SUPPORT_ROLE_ID       = 1474572393908404305
SELLER_ROLE_ID        = 0
BUILDER_BASE_ROLE_ID  = 1484158340849205308
COUNTER_CHANNEL_ID    = 0
LEGIT_CHANNEL_ID      = 0
PROOF_CHANNEL_ID      = 1469647159560241318
TRANSCRIPT_CHANNEL_ID = 1464430574524436679
FEEDBACK_CHANNEL_ID   = 1502464872686948403
STOCK_CATEGORY_ID     = 1506520186063163423
SOLD_CATEGORY_ID      = 1506652491779932240
CHANGELOG_CHANNEL_ID  = 1486967511839801414
# ADMIN_IDS — đọc từ 2 biến riêng biệt:
#   ADMIN_RUBY_ID   — Ruby (phát triển, quản lý bot & server)
#   ADMIN_TUYTAM_ID — TuyTam (giao dịch, buôn bán)
# Cả 2 đều có toàn quyền như nhau.
def _load_admin_ids() -> list[int]:
    ids = []
    for var in ("ADMIN_RUBY_ID", "ADMIN_TUYTAM_ID"):
        val = os.getenv(var, "").strip()
        if val:
            try:
                ids.append(int(val))
            except ValueError:
                log.error(f"[DATA] ❌ {var} không hợp lệ (phải là số): '{val}'")
        else:
            log.warning(f"[DATA] ⚠️ {var} chưa được cài trong Railway env.")
    if not ids:
        log.critical("[DATA] ❌ Không có ADMIN nào! Hãy set ADMIN_RUBY_ID và ADMIN_TUYTAM_ID.")
    return ids

ADMIN_IDS = _load_admin_ids()

# Tiện truy cập từng ID riêng nếu sau này cần phân quyền
ADMIN_RUBY_ID   = next((i for i in ADMIN_IDS if str(i) == os.getenv("ADMIN_RUBY_ID","").strip()), None)
ADMIN_TUYTAM_ID = next((i for i in ADMIN_IDS if str(i) == os.getenv("ADMIN_TUYTAM_ID","").strip()), None)
QR_FILE   = "/data/qr_code.png" if os.path.isdir("/data") else "./qr_code.png"

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("❌ Thiếu biến môi trường MONGO_URI!")

# ══════════════════════════════════════════
# MONGO CLIENT
# ══════════════════════════════════════════
_mongo_client = None
_col_data     = None
_col_giveaway = None
def _get_mongo():
    global _mongo_client, _col_data, _col_giveaway
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _db           = _mongo_client["tuytam_bot"]
        _col_data     = _db["bot_data"]
        _col_giveaway = _db["giveaways"]
    return _col_data, _col_giveaway

# ══════════════════════════════════════════
# DEFAULT DATA (theo từng guild)
# ══════════════════════════════════════════
def _default_data(guild_id: int) -> dict:
    return {
        "_id": f"guild_{guild_id}",
        "ticket": 0,
        "panel_channel_id": None,
        "qr_path": None,
        "cfg_log_rudy":        0,
        "cfg_ticket_category": TICKET_CATEGORY_ID,
        "cfg_support_role":    SUPPORT_ROLE_ID,
        "cfg_seller_role":     SELLER_ROLE_ID,
        "cfg_counter_channel": COUNTER_CHANNEL_ID,
        "cfg_legit_channel":   LEGIT_CHANNEL_ID,
        "cfg_proof_channel":   PROOF_CHANNEL_ID,
        "cfg_legit_emoji":     "✅",   # Emoji bot thả khi +1legit — đổi qua .st
        "cfg_vouch_emoji":     "✅",   # Emoji bot thả khi done (vouch) — đổi qua .st
        "cfg_ai_channel":      0,
        "cfg_stock_category":  STOCK_CATEGORY_ID,
        "cfg_sold_category":   SOLD_CATEGORY_ID,
        "cfg_font":            "normal",
        "dangerous_cmd_overrides": {},
        "sellers":          [],
        "sv_prices":        [],
        "buy_roles":        [],
        "user_total_spent": {},
        "ratings":          [],
        "ticket_notes":     {},
        "invite_counts":    {},
        "ticket_history":   [],
        "seller_qr":        {},        # {user_id: qr_path} — QR riêng của từng seller
        "seller_categories": {},       # {user_id: category_id} — category riêng của từng seller
        "log_channels":     {},        # {group: channel_id} — kênh log theo nhóm
        "seller_sales":      [],       # [{user_id, amount, channel_name, channel_id, time}] — lịch sử sold-stock
        "pending_sold_price": {},      # {channel_id: {seller_id, channel_name, old_name, guild_id, time, tuytam_message_id, ruby_message_id, escalated}}
        "resolved_sold_price": {},     # {channel_id: {amount, resolved_by, old_name, time}} — đơn đã được admin xử lý
    }

def _default_data_global() -> dict:
    """Data KHÔNG tách theo guild — chống multi-acc/VPN (_ip_records) và tempban
    được cố ý dùng chung cho mọi server để không ai né được bằng cách nhảy server."""
    return {
        "_id": "main",
        "_tempbans": {},
        "_ip_records": {},
        # {channel_id (str): {"base": str, "target_num": int}} — hàng đợi đổi tên kênh
        # legit/vouch bị Discord rate limit (2 lần/10 phút), resume lại sau khi bot restart.
        # Xem bot.py: _queue_or_rename / _apply_rename_with_retry / _resume_pending_renames
        "_pending_renames": {},
    }

# ══════════════════════════════════════════
# LOCKS (1 lock riêng mỗi guild + 1 lock cho global doc)
# ══════════════════════════════════════════
_save_locks: dict[int, asyncio.Lock] = {}
_global_save_lock = None
_ticket_lock  = None   # FIX: Lock tránh trùng số ticket

def _get_save_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in _save_locks:
        _save_locks[guild_id] = asyncio.Lock()
    return _save_locks[guild_id]

def _get_global_save_lock() -> asyncio.Lock:
    global _global_save_lock
    if _global_save_lock is None:
        _global_save_lock = asyncio.Lock()
    return _global_save_lock

def _get_ticket_lock():
    global _ticket_lock
    if _ticket_lock is None:
        _ticket_lock = asyncio.Lock()
    return _ticket_lock


# ══════════════════════════════════════════
# LOW-LEVEL MongoDB
# ══════════════════════════════════════════
_data_cache: dict[int, dict] = {}      # {guild_id: data}
_global_cache: dict | None = None      # data KHÔNG tách theo guild (tempban, ip records)
_giveaways_cache: dict = {}            # {message_id: {...}} — KHÔNG tách theo guild (tự nhiên theo message_id)

async def _mongo_load(guild_id: int) -> dict:
    col, _ = _get_mongo()
    doc_id = f"guild_{guild_id}"
    try:
        doc = await col.find_one({"_id": doc_id})
        if doc is None and guild_id == LEGACY_MAIN_GUILD_ID:
            # Migrate 1 lần: document "main" cũ (trước khi tách multi-guild) → "guild_<id>".
            legacy = await col.find_one({"_id": "main"})
            if legacy:
                doc = {k: v for k, v in legacy.items() if k != "_id"}
                doc["_id"] = doc_id
                for k, v in _default_data(guild_id).items():
                    doc.setdefault(k, v)
                await col.insert_one(doc)
                log.info(f"[DATA] 🔀 Đã migrate document 'main' → '{doc_id}'")
        if doc is None:
            doc = _default_data(guild_id)
            await col.insert_one(doc)
            print(f"[DATA] 🆕 Tạo document mới cho guild {guild_id}")
        else:
            changed = False
            for k, v in _default_data(guild_id).items():
                if k not in doc:
                    doc[k] = v
                    changed = True
            if changed:
                await _mongo_save(guild_id, doc)
        return doc
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi đọc MongoDB (guild {guild_id}): {e}")
        return _default_data(guild_id)

async def _mongo_save(guild_id: int, data: dict):
    col, _ = _get_mongo()
    doc_id = f"guild_{guild_id}"
    try:
        save = {k: v for k, v in data.items() if k != "_id"}
        await col.update_one({"_id": doc_id}, {"$set": save}, upsert=True)
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi ghi MongoDB (guild {guild_id}): {e}")

async def _mongo_load_global() -> dict:
    col, _ = _get_mongo()
    try:
        doc = await col.find_one({"_id": "main"})
        if doc is None:
            doc = _default_data_global()
            await col.insert_one(doc)
        else:
            changed = False
            for k, v in _default_data_global().items():
                if k not in doc:
                    doc[k] = v
                    changed = True
            if changed:
                await _mongo_save_global(doc)
        return doc
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi đọc MongoDB (global): {e}")
        return _default_data_global()

async def _mongo_save_global(data: dict):
    col, _ = _get_mongo()
    try:
        save = {k: v for k, v in data.items() if k != "_id"}
        await col.update_one({"_id": "main"}, {"$set": save}, upsert=True)
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi ghi MongoDB (global): {e}")

async def _flush_to_mongo(guild_id: int):
    """FIX: Dùng Lock đảm bảo không ghi đồng thời (mỗi guild 1 lock riêng)."""
    lock = _get_save_lock(guild_id)
    async with lock:
        data = _data_cache.get(guild_id)
        if data is not None:
            await _mongo_save(guild_id, data)

async def _flush_global_to_mongo():
    lock = _get_global_save_lock()
    async with lock:
        if _global_cache is not None:
            await _mongo_save_global(_global_cache)

# ══════════════════════════════════════════
# HIGH-LEVEL API
# ══════════════════════════════════════════
def load_data() -> dict:
    """Trả về shallow copy của cache CHO GUILD ĐANG XỬ LÝ (lấy từ contextvar).
    Dùng save_data() để ghi lại sau khi thay đổi.
    ⚠️ Nếu gọi mà không có guild context (bug ở nơi gọi), sẽ log lỗi và trả về default rỗng
    thay vì crash hoặc lỡ tay ghi nhầm sang guild khác."""
    guild_id = get_current_guild_id()
    if guild_id is None:
        # Đã xác định xong các nguồn gốc phổ biến nhất gây lỗi này (on_member_join/remove,
        # verify callback ở invite.py, on_message relay ở ticket.py — xem CHANGELOG v4.10.3
        # và AI_CONTEXT.md mục Multi-guild). Chỉ log 1 dòng ngắn, KHÔNG dump full stack trace
        # nữa để tránh flood log (trước đây in kèm traceback.format_stack() gây hàng trăm dòng
        # log lặp lại mỗi lần listener chạy).
        log.error("[DATA] ⚠️ load_data() được gọi mà KHÔNG có guild context — trả về default tạm. "
                  "Nếu vừa thêm listener/task mới, nhớ set_current_guild() đầu hàm.")
        return _default_data(0)
    if guild_id in _data_cache:
        return dict(_data_cache[guild_id])
    log.warning(f"[DATA] ⚠️ Guild {guild_id} chưa có trong cache — trả về default tạm (chưa lưu).")
    return _default_data(guild_id)

def save_data(data: dict):
    """FIX: Dùng asyncio.create_task thay ensure_future. Ghi vào cache của guild đang xử lý
    (lấy từ contextvar) — KHÔNG cần truyền guild_id, mọi cog cũ gọi save_data(data) vẫn hoạt động
    y nguyên, chỉ khác là giờ nó tự biết ghi đúng guild nào."""
    guild_id = get_current_guild_id()
    if guild_id is None:
        log.error("[DATA] ❌ save_data() được gọi mà KHÔNG có guild context — dữ liệu KHÔNG được lưu để tránh ghi nhầm guild.")
        return
    _data_cache[guild_id] = data
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_flush_to_mongo(guild_id))
    except RuntimeError:
        pass
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi tạo save task (guild {guild_id}): {e}")

def load_global_data() -> dict:
    """Data KHÔNG tách theo guild (tempban, ip records) — dùng chung cho mọi server."""
    if _global_cache is not None:
        return dict(_global_cache)
    return _default_data_global()

def save_global_data(data: dict):
    global _global_cache
    _global_cache = data
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_flush_global_to_mongo())
    except RuntimeError:
        pass
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi tạo save task (global): {e}")

async def ensure_guild_loaded(guild_id: int) -> None:
    """Gọi khi bot join guild mới giữa chừng (on_guild_join) để guild đó có cache ngay,
    không phải đợi restart bot."""
    if guild_id not in _data_cache:
        _data_cache[guild_id] = await _mongo_load(guild_id)
        log.info(f"[DATA] ✅ Đã load cache cho guild mới {guild_id}")

async def init_data_cache(bot) -> None:
    """Gọi 1 lần ở on_ready. Load riêng document cho TỪNG guild bot đang ở,
    cộng thêm 1 document global (tempban/ip) và toàn bộ giveaways (tách theo message_id,
    không thuộc guild nào cụ thể trong cache)."""
    global _data_cache, _global_cache, _giveaways_cache
    _data_cache = {}
    for guild in bot.guilds:
        _data_cache[guild.id] = await _mongo_load(guild.id)

    _global_cache = await _mongo_load_global()

    _, col_gw = _get_mongo()
    try:
        giveaways = {}
        async for doc in col_gw.find({}):
            mid = str(doc.get("message_id", doc.get("_id", "")))
            giveaways[mid] = {k: v for k, v in doc.items() if k not in ("_id", "message_id")}
        _giveaways_cache = giveaways
    except Exception as e:
        log.warning(f"[DATA] ⚠️ Không load được giveaways: {e}")
        _giveaways_cache = {}

    guild_list = ", ".join(f"{g.id}(#{_data_cache[g.id].get('ticket', 0):03d})" for g in bot.guilds)
    print(f"[DATA] ✅ Đã kết nối MongoDB — {len(_data_cache)} guild(s): {guild_list}")

    # FIX: báo hiệu cho mọi tasks.loop nền đang chờ (xem wait_data_cache_ready())
    # rằng _data_cache đã nạp xong, an toàn để load_data()/save_data() theo guild.
    _data_cache_ready.set()

# ══════════════════════════════════════════
# CONFIG GETTERS / SETTERS
# ══════════════════════════════════════════
def get_cfg_log_rudy()        -> int: return load_data().get("cfg_log_rudy", 0)
def get_cfg_font()            -> str: return load_data().get("cfg_font", "normal")
def get_cfg_category()        -> int: return load_data().get("cfg_ticket_category", TICKET_CATEGORY_ID)
def get_cfg_stock_category()  -> int: return load_data().get("cfg_stock_category",  STOCK_CATEGORY_ID)
def get_cfg_sold_category()   -> int: return load_data().get("cfg_sold_category",   SOLD_CATEGORY_ID)
def get_cfg_support_role()    -> int: return load_data().get("cfg_support_role", SUPPORT_ROLE_ID)
def get_cfg_seller_role()     -> int: return load_data().get("cfg_seller_role", SELLER_ROLE_ID)
def get_cfg_counter_channel() -> int: return load_data().get("cfg_counter_channel", COUNTER_CHANNEL_ID)
def get_cfg_legit_channel()   -> int: return load_data().get("cfg_legit_channel", LEGIT_CHANNEL_ID)
def get_cfg_proof_channel()   -> int: return load_data().get("cfg_proof_channel", PROOF_CHANNEL_ID)
def get_cfg_ai_channel()      -> int: return load_data().get("cfg_ai_channel", 0)
def get_cfg_legit_emoji()     -> str: return load_data().get("cfg_legit_emoji", "✅")
def get_cfg_vouch_emoji()     -> str: return load_data().get("cfg_vouch_emoji", "✅")

def set_cfg_font(font: str):
    data = load_data(); data["cfg_font"] = font; save_data(data)

def set_cfg_legit_emoji(emoji: str):
    save_cfg("cfg_legit_emoji", emoji.strip())

def set_cfg_vouch_emoji(emoji: str):
    save_cfg("cfg_vouch_emoji", emoji.strip())

def save_cfg(key: str, value):
    data = load_data(); data[key] = value; save_data(data)

# ══════════════════════════════════════════
# SELLERS
# ══════════════════════════════════════════
def get_sellers() -> list:
    return load_data().get("sellers", [])

def save_sellers(sellers: list):
    data = load_data(); data["sellers"] = sellers; save_data(data)

# ══════════════════════════════════════════
# ══════════════════════════════════════════


# ══════════════════════════════════════════
# TICKET COUNTER — FIX: async + Lock
# ══════════════════════════════════════════
def get_panel_channel_id():
    return load_data().get("panel_channel_id")

def save_panel_channel_id(channel_id: int):
    data = load_data(); data["panel_channel_id"] = channel_id; save_data(data)

# ── Bật/tắt từng nút trong panel ticket (.st) — mặc định TẤT CẢ đều bật ──
PANEL_BUTTON_KEYS = ["donut", "kingmc", "ff", "accpre", "build", "giveaway", "support"]

def get_panel_buttons_config() -> dict:
    """{"donut": True, "kingmc": False, ...} — key vắng mặt coi như bật (default)."""
    return load_data().get("panel_buttons", {})

def is_panel_button_enabled(key: str) -> bool:
    return get_panel_buttons_config().get(key, True)

def set_panel_button_enabled(key: str, enabled: bool):
    data = load_data()
    cfg = data.setdefault("panel_buttons", {})
    cfg[key] = enabled
    save_data(data)

def get_qr_path():
    return load_data().get("qr_path", None)

def save_qr_path(path: str):
    data = load_data(); data["qr_path"] = path; save_data(data)

# ── Seller QR (mỗi seller có QR riêng) ──
def get_seller_qr(user_id: int) -> str | None:
    return load_data().get("seller_qr", {}).get(str(user_id))

def save_seller_qr(user_id: int, path: str):
    data = load_data()
    data.setdefault("seller_qr", {})
    data["seller_qr"][str(user_id)] = path
    save_data(data)

def get_all_seller_qr() -> dict:
    return load_data().get("seller_qr", {})

# ── Seller category (mỗi seller có 1 category riêng) ──
def get_seller_category(user_id: int) -> int:
    return load_data().get("seller_categories", {}).get(str(user_id), 0)

def save_seller_category(user_id: int, cat_id: int):
    data = load_data()
    data.setdefault("seller_categories", {})
    data["seller_categories"][str(user_id)] = cat_id
    save_data(data)

def remove_seller_category(user_id: int):
    data = load_data()
    data.setdefault("seller_categories", {})
    data["seller_categories"].pop(str(user_id), None)
    save_data(data)

def get_all_seller_categories() -> dict:
    return load_data().get("seller_categories", {})

# ══════════════════════════════════════════
# SELLER SOLD-STOCK SALES (.stock → sold qua "sold"/"SOLD")
# Mỗi lần seller gõ "sold" thành công (seller hợp lệ + parse được giá)
# sẽ ghi 1 record vào "seller_sales" (list). Thống kê 24h tính theo
# timestamp, all-time là cộng dồn toàn bộ list.
# ══════════════════════════════════════════
def add_seller_sale(user_id: int, amount: int, channel_name: str, channel_id: int) -> dict:
    """Ghi nhận 1 đơn sold cho seller. Trả về record vừa lưu."""
    data = load_data()
    data.setdefault("seller_sales", [])
    record = {
        "user_id":     user_id,
        "amount":      amount,
        "channel_name": channel_name,
        "channel_id":  channel_id,
        "time":        datetime.now(timezone.utc).isoformat(),
    }
    data["seller_sales"].append(record)
    save_data(data)
    return record

def get_seller_sales() -> list:
    """Trả về toàn bộ lịch sử sold-stock (mọi seller)."""
    return load_data().get("seller_sales", [])

def get_seller_sales_stats() -> dict:
    """
    Trả về {user_id_str: {"count_24h": int, "amount_24h": int,
                            "count_all": int, "amount_all": int}}
    Tính cho TẤT CẢ seller xuất hiện trong lịch sử seller_sales.
    """
    from datetime import timedelta
    sales = get_seller_sales()
    now   = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    stats: dict = {}
    for rec in sales:
        uid = str(rec.get("user_id"))
        amt = rec.get("amount", 0)
        stats.setdefault(uid, {"count_24h": 0, "amount_24h": 0, "count_all": 0, "amount_all": 0})
        stats[uid]["count_all"]  += 1
        stats[uid]["amount_all"] += amt
        try:
            t = datetime.fromisoformat(rec.get("time", ""))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t >= since:
                stats[uid]["count_24h"]  += 1
                stats[uid]["amount_24h"] += amt
        except Exception:
            continue
    return stats

# ── Pending sold price — chờ admin TuyTam/Ruby điền giá thủ công qua DM ──
# {channel_id_str: {seller_id, channel_name, old_name, guild_id, time,
#                    tuytam_message_id, ruby_message_id, escalated}}
def add_pending_sold_price(channel_id: int, seller_id: int, channel_name: str, old_name: str, guild_id: int):
    data = load_data()
    data.setdefault("pending_sold_price", {})
    data["pending_sold_price"][str(channel_id)] = {
        "seller_id":         seller_id,
        "channel_name":      channel_name,
        "old_name":          old_name,
        "guild_id":          guild_id,
        "time":              datetime.now(timezone.utc).isoformat(),
        "tuytam_message_id": None,
        "ruby_message_id":   None,
        "escalated":         False,
    }
    save_data(data)

def get_pending_sold_price(channel_id: int) -> dict | None:
    return load_data().get("pending_sold_price", {}).get(str(channel_id))

def get_all_pending_sold_price() -> dict:
    """Trả về toàn bộ pending {channel_id_str: doc} — dùng khi resume sau restart."""
    return dict(load_data().get("pending_sold_price", {}))

def set_pending_sold_dm(channel_id: int, *, tuytam_message_id: int = None, ruby_message_id: int = None):
    """Lưu message_id của DM (TuyTam và/hoặc Ruby) để resume persistent view sau restart."""
    data = load_data()
    pending = data.setdefault("pending_sold_price", {})
    doc = pending.get(str(channel_id))
    if not doc:
        return
    if tuytam_message_id is not None:
        doc["tuytam_message_id"] = tuytam_message_id
    if ruby_message_id is not None:
        doc["ruby_message_id"] = ruby_message_id
    pending[str(channel_id)] = doc
    save_data(data)

def mark_pending_sold_escalated(channel_id: int):
    data = load_data()
    pending = data.setdefault("pending_sold_price", {})
    doc = pending.get(str(channel_id))
    if not doc:
        return
    doc["escalated"] = True
    pending[str(channel_id)] = doc
    save_data(data)

def remove_pending_sold_price(channel_id: int):
    data = load_data()
    data.setdefault("pending_sold_price", {})
    data["pending_sold_price"].pop(str(channel_id), None)
    save_data(data)

# ── Resolved sold price — lưu kết quả sau khi 1 admin đã điền giá ──
# Cho phép admin còn lại (bấm nút trễ) biết đơn đã được ai xử lý + giá bao nhiêu.
# {channel_id_str: {amount, resolved_by (user_id), old_name, time}} — tự dọn sau 7 ngày
def mark_pending_sold_resolved(channel_id: int, amount: int, resolved_by: int, old_name: str):
    data = load_data()
    data.setdefault("resolved_sold_price", {})
    data["resolved_sold_price"][str(channel_id)] = {
        "amount":      amount,
        "resolved_by": resolved_by,
        "old_name":    old_name,
        "time":        datetime.now(timezone.utc).isoformat(),
    }
    save_data(data)

def get_resolved_sold_price(channel_id: int) -> dict | None:
    return load_data().get("resolved_sold_price", {}).get(str(channel_id))

async def get_ticket_number(guild_id: int) -> str:
    """FIX: async + Lock đảm bảo không bao giờ tạo 2 ticket trùng số.
    Mỗi guild đếm ticket riêng (guild_id bắt buộc truyền vào từ nơi gọi, VD ctx.guild.id)."""
    async with _get_ticket_lock():
        data = load_data()
        data["ticket"] = data.get("ticket", 0) + 1
        num = data["ticket"]
        # Ghi trực tiếp vào MongoDB ngay lập tức (không dùng queue)
        col, _ = _get_mongo()
        try:
            await col.update_one({"_id": f"guild_{guild_id}"}, {"$set": {"ticket": num}}, upsert=True)
        except Exception as e:
            log.error(f"[DATA] ❌ Lỗi cập nhật ticket counter (guild {guild_id}): {e}")
        if guild_id in _data_cache:
            _data_cache[guild_id]["ticket"] = num
        return f"{num:03d}"

# ══════════════════════════════════════════
# BUYER ROLES
# ══════════════════════════════════════════
def get_buy_roles() -> list:
    return sorted(load_data().get("buy_roles", []), key=lambda r: r.get("min_amount", 0))

def save_buy_roles(roles: list):
    data = load_data(); data["buy_roles"] = roles; save_data(data)

def get_user_total_spent(user_id: int) -> int:
    return load_data().get("user_total_spent", {}).get(str(user_id), 0)

def add_user_spent(user_id: int, amount: int) -> int:
    data = load_data()
    data.setdefault("user_total_spent", {})
    key = str(user_id)
    data["user_total_spent"][key] = data["user_total_spent"].get(key, 0) + amount
    save_data(data)
    return data["user_total_spent"][key]

def get_user_spent_by_server(user_id: int, server_key: str) -> int:
    """Trả về tổng chi tiêu của user trên 1 server cụ thể (donut / kingmc / accpre)."""
    return load_data().get("user_spent_by_server", {}).get(str(user_id), {}).get(server_key, 0)

def get_user_spent_all_servers(user_id: int) -> dict:
    """Trả về dict {server_key: amount} của user."""
    return load_data().get("user_spent_by_server", {}).get(str(user_id), {})

def add_user_spent_server(user_id: int, amount: int, server_key: str) -> dict:
    """
    Cộng tiền vào tổng CHUNG (user_total_spent) VÀ tổng theo server (user_spent_by_server).
    Trả về dict {"total": int, "server_total": int}.
    """
    data = load_data()
    uid  = str(user_id)

    # Tổng chung
    data.setdefault("user_total_spent", {})
    data["user_total_spent"][uid] = data["user_total_spent"].get(uid, 0) + amount

    # Tổng theo server
    data.setdefault("user_spent_by_server", {})
    data["user_spent_by_server"].setdefault(uid, {})
    data["user_spent_by_server"][uid][server_key] = (
        data["user_spent_by_server"][uid].get(server_key, 0) + amount
    )

    save_data(data)
    return {
        "total":        data["user_total_spent"][uid],
        "server_total": data["user_spent_by_server"][uid][server_key],
    }

# ══════════════════════════════════════════
# RATINGS & NOTES
# ══════════════════════════════════════════
def save_rating(ticket_name, user_id, stars):
    data = load_data()
    data.setdefault("ratings", [])
    data["ratings"].append({"ticket": ticket_name, "user_id": user_id, "stars": stars,
                             "time": datetime.now(timezone.utc).isoformat()})
    save_data(data)

def get_ticket_note(channel_id):
    return load_data().get("ticket_notes", {}).get(str(channel_id), [])

def add_ticket_note(channel_id, author, note):
    data = load_data()
    data.setdefault("ticket_notes", {})
    key = str(channel_id)
    data["ticket_notes"].setdefault(key, [])
    data["ticket_notes"][key].append({"author": author, "note": note,
                                       "time": datetime.now(timezone.utc).isoformat()})
    save_data(data)

# ══════════════════════════════════════════
# TICKET HISTORY
# ══════════════════════════════════════════
def get_ticket_history() -> list:
    return load_data().get("ticket_history", [])

def save_ticket_record(record: dict):
    data = load_data()
    data.setdefault("ticket_history", [])
    data["ticket_history"].append(record)
    save_data(data)

def get_user_ticket_history(user_id: int) -> list:
    return [t for t in get_ticket_history() if t.get("user_id") == user_id]

def get_monthly_stats(year: int, month: int) -> dict:
    history = get_ticket_history()
    records = []
    for t in history:
        closed = t.get("closed_at", "")
        try:
            dt = datetime.fromisoformat(closed)
            if dt.year == year and dt.month == month:
                records.append(t)
        except Exception:
            continue
    total_amount = sum(t.get("amount", 0) for t in records)
    return {
        "year": year, "month": month,
        "total_orders": len(records),
        "total_amount": total_amount,
        "records":      records,
    }

# ══════════════════════════════════════════
# INVITE COUNTS
# ══════════════════════════════════════════
def get_invite_counts() -> dict:
    return load_data().get("invite_counts", {})

def save_invite_counts(counts: dict):
    data = load_data(); data["invite_counts"] = counts; save_data(data)

# ══════════════════════════════════════════
# SV PRICES
# ══════════════════════════════════════════
def get_price_sections() -> list:
    return load_data().get("sv_prices", [])

def save_price_sections(sections: list):
    data = load_data(); data["sv_prices"] = sections; save_data(data)

# ══════════════════════════════════════════
# GIVEAWAY
# ══════════════════════════════════════════
def _load_giveaway_section() -> dict:
    return dict(_giveaways_cache)

def _save_giveaway_section(giveaways: dict):
    """Giveaway KHÔNG đi qua load_data()/save_data() (vốn giờ tách theo guild) vì active_giveaways
    ở cogs/giveaway.py là 1 dict phẳng chứa giveaway của MỌI guild, phân biệt bằng message_id.
    Nếu đi qua save_data() sẽ vô tình ghi giveaway của cả 2 server lẫn vào document của guild
    đang xử lý tại thời điểm gọi. col_gw (collection riêng) mới là nguồn lưu trữ chính thức."""
    global _giveaways_cache
    serializable = {
        str(mid): {k: list(v) if isinstance(v, set) else v for k, v in gw.items()}
        for mid, gw in giveaways.items()
    }
    _giveaways_cache = serializable
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_sync_giveaways_to_mongo(serializable))
    except RuntimeError:
        pass
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi sync giveaway: {e}")

async def _sync_giveaways_to_mongo(giveaways: dict):
    _, col_gw = _get_mongo()
    try:
        for mid_str, gw in giveaways.items():
            doc = dict(gw)
            doc["message_id"] = int(mid_str)
            await col_gw.update_one({"message_id": int(mid_str)}, {"$set": doc}, upsert=True)
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi sync giveaway MongoDB: {e}")

def load_giveaways_data() -> dict:
    raw = _load_giveaway_section()
    result = {}
    for mid_str, gw in raw.items():
        gw = dict(gw)
        gw["entries"] = set(gw.get("entries", []))
        result[int(mid_str)] = gw
    return result

def save_giveaways_data(active_giveaways: dict):
    _save_giveaway_section(active_giveaways)

# ══════════════════════════════════════════
# DANGEROUS COMMANDS
# ══════════════════════════════════════════
def can_use_dangerous_cmd(user_id: int, cmd_name: str) -> bool:
    return user_id in ADMIN_IDS

def get_dangerous_overrides() -> dict:
    return load_data().get("dangerous_cmd_overrides", {})

def save_dangerous_overrides(overrides: dict):
    data = load_data(); data["dangerous_cmd_overrides"] = overrides; save_data(data)

# ══════════════════════════════════════════
# FORMAT HELPERS
# ══════════════════════════════════════════
def _uname(user) -> str:
    if user is None: return "Unknown"
    uid = getattr(user, "id", None)
    un  = getattr(user, "name", None) or str(user)
    if uid: return f"<@{uid}> ({un})"
    dn = getattr(user, "display_name", None) or un
    return f"{dn} ({un})" if dn != un else dn

def _uname_plain(user) -> str:
    if user is None: return "Unknown"
    dn = getattr(user, "display_name", None) or getattr(user, "name", str(user))
    un = getattr(user, "name", None)
    if un and un != dn: return f"{dn} ({un})"
    return dn

def parse_amount(raw: str) -> int | None:
    import re as _re
    raw = raw.strip().lower().replace(",", ".").replace(" ", "")
    m = _re.match(r"^(\d+)(tr|m)(\d)$", raw)   # chỉ 1 chữ số sau tr/m: 1tr5 / 1m2 = 1.500.000 / 1.200.000
    if m:
        a, b = int(m.group(1)), int(m.group(3))
        return a * 1_000_000 + b * 100_000
    m = _re.match(r"^(\d+(?:\.\d+)?)(k|tr|m|đ)?$", raw)
    if not m: return None
    num  = float(m.group(1))
    unit = m.group(2) or ""
    if unit == "k":        return int(num * 1_000)
    if unit in ("tr","m"): return int(num * 1_000_000)
    return int(num)

def fmt_amount(amount: int) -> str:
    if amount >= 1_000_000: return f"{amount/1_000_000:g}tr"
    if amount >= 1_000:     return f"{amount/1_000:g}k"
    return f"{amount:,}đ"

async def get_or_fetch_channel(bot, channel_id: int):
    """Lấy channel từ cache, nếu không có thì fetch thẳng từ API Discord.
    Dùng thay cho bot.get_channel() để hỗ trợ kênh private và kênh mới tạo."""
    if not channel_id:
        return None
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            channel = None
    return channel

# ══════════════════════════════════════════
# LOG CHANNELS (dùng bởi logger.py)
# ══════════════════════════════════════════
def get_log_channels() -> dict:
    return load_data().get("log_channels", {})

def get_log_channel_by_group(group: str) -> int | None:
    return load_data().get("log_channels", {}).get(group)

def set_log_channel_db(group: str, channel_id: int):
    data = load_data()
    data.setdefault("log_channels", {})
    data["log_channels"][group] = channel_id
    save_data(data)

def is_staff_member(member) -> bool:
    if member.id in ADMIN_IDS: return True
    guild = member.guild
    sr = guild.get_role(get_cfg_support_role())
    if sr and sr in member.roles: return True
    slr = guild.get_role(get_cfg_seller_role())
    if slr and slr in member.roles: return True
    bbr = guild.get_role(BUILDER_BASE_ROLE_ID)
    if bbr and bbr in member.roles: return True
    return False

# ══════════════════════════════════════════
# TICKET TYPE → ROLE GROUP
# ══════════════════════════════════════════
def get_ticket_type_role(ticket_key: str) -> str | None:
    """Trả về "seller" | "builder" | None cho loại ticket."""
    return load_data().get("ticket_type_roles", {}).get(ticket_key)

def set_ticket_type_role(ticket_key: str, group: str | None) -> None:
    """Lưu group ("seller" | "builder" | None) cho loại ticket."""
    data = load_data()
    roles_cfg = data.setdefault("ticket_type_roles", {})
    if group is None:
        roles_cfg.pop(ticket_key, None)
    else:
        roles_cfg[ticket_key] = group
    data["ticket_type_roles"] = roles_cfg
    save_data(data)

def get_all_ticket_type_roles() -> dict:
    """Trả về toàn bộ map {ticket_key: group}."""
    return load_data().get("ticket_type_roles", {})

# ══════════════════════════════════════════
# TICKET TYPE → ROLE ID (lưu role ID thực, dùng cho Donut/King/AccPre)
# ══════════════════════════════════════════
def get_ticket_role_id(ticket_key: str) -> int | None:
    """Trả về role ID (int) được gán cho loại ticket, hoặc None nếu chưa set."""
    val = load_data().get("ticket_role_ids", {}).get(ticket_key)
    return int(val) if val else None

def set_ticket_role_id(ticket_key: str, role_id: int | None) -> None:
    """Lưu role ID cho loại ticket. role_id=None để xóa."""
    data = load_data()
    cfg = data.setdefault("ticket_role_ids", {})
    if role_id is None:
        cfg.pop(ticket_key, None)
    else:
        cfg[str(ticket_key)] = role_id
    data["ticket_role_ids"] = cfg
    save_data(data)

def get_all_ticket_role_ids() -> dict:
    """Trả về toàn bộ map {ticket_key: role_id}."""
    return load_data().get("ticket_role_ids", {})

# ══════════════════════════════════════════
# TICKET TYPE → MULTI ROLE IDS
# ══════════════════════════════════════════
def get_ticket_role_ids(ticket_key: str) -> list:
    """Trả về list role IDs được gán cho loại ticket (có thể rỗng)."""
    val = load_data().get("ticket_multi_roles", {}).get(ticket_key, [])
    return [int(r) for r in val if r]

def set_ticket_role_ids(ticket_key: str, role_ids: list) -> None:
    """Lưu list role IDs cho loại ticket. Truyền [] để xóa."""
    data = load_data()
    cfg = data.setdefault("ticket_multi_roles", {})
    if not role_ids:
        cfg.pop(ticket_key, None)
    else:
        cfg[ticket_key] = [int(r) for r in role_ids]
    data["ticket_multi_roles"] = cfg
    save_data(data)

def get_all_ticket_multi_roles() -> dict:
    """Trả về toàn bộ map {ticket_key: [role_id, ...]}."""
    return load_data().get("ticket_multi_roles", {})

# ══════════════════════════════════════════
# TEMPBAN PERSISTENCE — CHUNG cho mọi guild (cố ý, xem _default_data_global)
# Lưu {user_id: {guild_id, unban_at (unix timestamp), reason}} vào MongoDB
# ══════════════════════════════════════════
def get_active_tempbans() -> dict:
    """Trả về dict {str(user_id): {guild_id, unban_at, reason}}."""
    return dict(load_global_data().get("_tempbans", {}))

def add_tempban(user_id: int, guild_id: int, unban_at: float, reason: str = "") -> None:
    """Lưu tempban vào MongoDB (document global, không tách theo guild)."""
    data = load_global_data()
    data.setdefault("_tempbans", {})
    data["_tempbans"][str(user_id)] = {
        "guild_id": guild_id,
        "unban_at": unban_at,
        "reason": reason,
    }
    save_global_data(data)

def remove_tempban(user_id: int) -> None:
    """Xoá tempban khỏi MongoDB (sau khi unban xong)."""
    data = load_global_data()
    data.setdefault("_tempbans", {})
    data["_tempbans"].pop(str(user_id), None)
    save_global_data(data)

# ══════════════════════════════════════════
# INVITE STATE PERSISTENCE
# Lưu _member_inviters và _pending_joins vào MongoDB
# ══════════════════════════════════════════
def get_member_inviters() -> dict:
    """Trả về {str(member_id): {inviter_id, guild_id}}.
    FIX: dữ liệu này CHUNG cho mọi guild (mỗi entry tự lưu guild_id riêng, giống
    _tempbans/_ip_records) — trước đây dùng nhầm load_data() (theo guild) khiến
    cog_load() lỗi lúc khởi động (chưa có guild context) và dữ liệu bị tách lẻ
    sai theo guild hiện tại thay vì dùng chung như thiết kế ban đầu."""
    return dict(load_global_data().get("_member_inviters", {}))

def save_member_inviters(inviters: dict) -> None:
    data = load_global_data()
    data["_member_inviters"] = {str(k): v for k, v in inviters.items()}
    save_global_data(data)

def get_pending_joins() -> dict:
    """Trả về {str(member_id): {inviter_id, guild_id, joined_at}}.
    FIX: tương tự get_member_inviters() — data CHUNG cho mọi guild."""
    return dict(load_global_data().get("_pending_joins", {}))

def save_pending_joins(pending: dict) -> None:
    data = load_global_data()
    data["_pending_joins"] = {str(k): v for k, v in pending.items()}
    save_global_data(data)

# ══════════════════════════════════════════
# IP RECORDS PERSISTENCE — CHUNG cho mọi guild (cố ý, chống multi-acc né qua server khác)
# Lưu {ip: [user_id, ...]} — dùng cho fake detection
# ══════════════════════════════════════════

def get_ip_records() -> dict:
    """Trả về {ip: [user_id, ...]}."""
    return dict(load_global_data().get("_ip_records", {}))

def save_ip_records(records: dict) -> None:
    data = load_global_data()
    data["_ip_records"] = records
    save_global_data(data)

async def atomic_register_ip(ip: str, user_id: int) -> list[int]:
    """
    Atomic: dùng $addToSet để thêm user_id vào list IP trong MongoDB (document global).
    Tránh race condition khi 2 người verify cùng lúc.
    Trả về list user_ids hiện tại trên IP đó (SAU khi đã thêm).
    """
    col, _ = _get_mongo()
    key = f"_ip_records.{ip.replace('.', '_')}"
    try:
        await col.update_one(
            {"_id": "main"},
            {"$addToSet": {key: user_id}},
            upsert=True,
        )
        doc = await col.find_one({"_id": "main"}, {key: 1})
        users = (doc or {}).get("_ip_records", {}).get(ip.replace(".", "_"), [])
        # Sync lại cache global
        if _global_cache is not None:
            _global_cache.setdefault("_ip_records", {})[ip.replace(".", "_")] = users
        return users
    except Exception as e:
        log.error(f"[DATA] ❌ atomic_register_ip lỗi: {e}")
        # Fallback: in-memory
        if _global_cache is not None:
            recs = _global_cache.setdefault("_ip_records", {})
            ip_key = ip.replace(".", "_")
            if ip_key not in recs:
                recs[ip_key] = []
            if user_id not in recs[ip_key]:
                recs[ip_key].append(user_id)
            return recs[ip_key]
        return [user_id]


# ══════════════════════════════════════════
# SHOP QR (tính năng thử nghiệm — bật/tắt qua .st)
# Chỉ lưu cấu hình ngân hàng để tạo QR VietQR động kèm .done <số tiền>.
# ══════════════════════════════════════════
def get_cfg_shop_orders_enabled() -> bool:
    return load_data().get("cfg_shop_orders_enabled", False)

def set_cfg_shop_orders_enabled(enabled: bool) -> None:
    save_cfg("cfg_shop_orders_enabled", enabled)

def get_shop_orders_config() -> dict:
    """Trả về {bank_name, bank_code, account_number, account_holder, template, default_content}."""
    return load_data().get("shop_orders_cfg", {})

def save_shop_orders_config(**fields) -> None:
    data = load_data()
    cfg = data.setdefault("shop_orders_cfg", {})
    cfg.update(fields)
    data["shop_orders_cfg"] = cfg
    save_data(data)

def get_cfg_queue_channel() -> int:
    return load_data().get("cfg_queue_channel", 0)

def save_cfg_queue_channel(channel_id: int) -> None:
    save_cfg("cfg_queue_channel", channel_id)


async def get_ip_users_mongo(ip: str) -> list[int]:
    """Đọc trực tiếp từ MongoDB (không qua cache) — dùng khi check collision."""
    col, _ = _get_mongo()
    key = f"_ip_records.{ip.replace('.', '_')}"
    try:
        doc = await col.find_one({"_id": "main"}, {key: 1})
        return (doc or {}).get("_ip_records", {}).get(ip.replace(".", "_"), [])
    except Exception as e:
        log.error(f"[DATA] ❌ get_ip_users_mongo lỗi: {e}")
        # Fallback cache global
        if _global_cache is not None:
            return _global_cache.get("_ip_records", {}).get(ip.replace(".", "_"), [])
        return []
