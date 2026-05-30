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
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("data")

# ══════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════
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
BALANCE_CHANNEL_ID    = 1464999465294369035
CHANGELOG_CHANNEL_ID  = 1486967511839801414

# FIX: ADMIN_IDS đọc từ env, fallback hardcode
def _load_admin_ids() -> list[int]:
    env = os.getenv("ADMIN_IDS", "")
    if env:
        try:
            return [int(x.strip()) for x in env.split(",") if x.strip()]
        except ValueError:
            log.warning("[DATA] ⚠️ ADMIN_IDS env không hợp lệ, dùng hardcode")
    return [846332174734983219, 1464961078042689588]

ADMIN_IDS = _load_admin_ids()
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
# DEFAULT DATA
# ══════════════════════════════════════════
def _default_data() -> dict:
    return {
        "_id": "main",
        "ticket": 0,
        "panel_channel_id": None,
        "qr_path": None,
        "cfg_log_rudy":        0,
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
        "sellers":          [],
        "sv_prices":        [],
        "balance": {
            "current": 0, "total_in": 0, "total_fee": 0,
            "total_out": 0, "tx_count": 0, "history": []
        },
        "buy_roles":        [],
        "user_total_spent": {},
        "ratings":          [],
        "ticket_notes":     {},
        "invite_counts":    {},
        "ticket_history":   [],
        "user_points":      {},
        "point_codes":      {},
        "point_log":        [],
        "seller_compensation": {},
        "point_cfg": {
            "points_per_redeem": 1,
            "point_value":       0,
            "max_discount_pct":  0,
            "cooldown_hours":    24,
            "code_expire_mins":  10,
        },
        "reward_shop":      [],
        "exchange_log":     [],
        "seller_qr":        {},        # {user_id: qr_path} — QR riêng của từng seller
        "seller_categories": {},       # {user_id: category_id} — category riêng của từng seller
        "log_channels":     {},        # {group: channel_id} — kênh log theo nhóm
        "banking_cfg": {
            "log_channel":    0,       # Channel ID nhận embed mỗi GD ngân hàng
            "notify_channel": 0,       # (tuỳ chọn) kênh ping riêng
        },
        "banking_txs":      [],        # List giao dịch từ Casso webhook (max 500)
    }

# ══════════════════════════════════════════
# LOCKS
# ══════════════════════════════════════════
_save_lock    = None   # Lock ghi MongoDB
_ticket_lock  = None   # FIX: Lock tránh trùng số ticket

def _get_save_lock():
    global _save_lock
    if _save_lock is None:
        _save_lock = asyncio.Lock()
    return _save_lock

def _get_ticket_lock():
    global _ticket_lock
    if _ticket_lock is None:
        _ticket_lock = asyncio.Lock()
    return _ticket_lock


# ══════════════════════════════════════════
# LOW-LEVEL MongoDB
# ══════════════════════════════════════════
_data_cache: dict | None = None

async def _mongo_load() -> dict:
    col, _ = _get_mongo()
    try:
        doc = await col.find_one({"_id": "main"})
        if doc is None:
            doc = _default_data()
            await col.insert_one(doc)
            print("[DATA] 🆕 Tạo document mới trong MongoDB")
        else:
            changed = False
            for k, v in _default_data().items():
                if k not in doc:
                    doc[k] = v
                    changed = True
            if changed:
                await _mongo_save(doc)
        return doc
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi đọc MongoDB: {e}")
        return _default_data()

async def _mongo_save(data: dict):
    col, _ = _get_mongo()
    try:
        save = {k: v for k, v in data.items() if k != "_id"}
        await col.update_one({"_id": "main"}, {"$set": save}, upsert=True)
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi ghi MongoDB: {e}")

async def _flush_to_mongo():
    """FIX: Dùng Lock đảm bảo không ghi đồng thời."""
    lock = _get_save_lock()
    async with lock:
        if _data_cache is not None:
            await _mongo_save(_data_cache)

# ══════════════════════════════════════════
# HIGH-LEVEL API
# ══════════════════════════════════════════
def load_data() -> dict:
    if _data_cache is not None:
        return _data_cache
    return _default_data()

def save_data(data: dict):
    """
    FIX: Dùng asyncio.create_task thay ensure_future.
    create_task an toàn hơn, có thể track được task.
    """
    global _data_cache
    _data_cache = data
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_flush_to_mongo())
    except RuntimeError:
        # Không có event loop (test/init context) — bỏ qua
        pass
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi tạo save task: {e}")

async def init_data_cache():
    global _data_cache
    _data_cache = await _mongo_load()
    _, col_gw = _get_mongo()
    try:
        giveaways = {}
        async for doc in col_gw.find({}):
            mid = str(doc.get("message_id", doc.get("_id", "")))
            giveaways[mid] = {k: v for k, v in doc.items() if k not in ("_id", "message_id")}
        _data_cache["_giveaways"] = giveaways
    except Exception as e:
        log.warning(f"[DATA] ⚠️ Không load được giveaways: {e}")
        _data_cache.setdefault("_giveaways", {})
    print(f"[DATA] ✅ Đã kết nối MongoDB — ticket#{_data_cache.get('ticket', 0):03d}")

# ══════════════════════════════════════════
# CONFIG GETTERS / SETTERS
# ══════════════════════════════════════════
def get_cfg_log_rudy()        -> int: return load_data().get("cfg_log_rudy", 0)
def get_cfg_font()            -> str: return load_data().get("cfg_font", "normal")
def get_cfg_category()        -> int: return load_data().get("cfg_ticket_category", TICKET_CATEGORY_ID)
def get_cfg_support_role()    -> int: return load_data().get("cfg_support_role", SUPPORT_ROLE_ID)
def get_cfg_seller_role()     -> int: return load_data().get("cfg_seller_role", SELLER_ROLE_ID)
def get_cfg_counter_channel() -> int: return load_data().get("cfg_counter_channel", COUNTER_CHANNEL_ID)
def get_cfg_balance_channel() -> int: return load_data().get("cfg_balance_channel", BALANCE_CHANNEL_ID)
def get_cfg_legit_channel()   -> int: return load_data().get("cfg_legit_channel", LEGIT_CHANNEL_ID)
def get_cfg_proof_channel()   -> int: return load_data().get("cfg_proof_channel", PROOF_CHANNEL_ID)
def get_cfg_ai_channel()      -> int: return load_data().get("cfg_ai_channel", 0)

def set_cfg_font(font: str):
    data = load_data(); data["cfg_font"] = font; save_data(data)

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
# BALANCE
# ══════════════════════════════════════════
def get_balance_data() -> dict:
    data = load_data()
    if "balance" not in data:
        data["balance"] = {"current":0,"total_in":0,"total_fee":0,"total_out":0,"tx_count":0,"history":[]}
        save_data(data)
    return data["balance"]

def save_balance_data(bal: dict):
    data = load_data(); data["balance"] = bal; save_data(data)

# ══════════════════════════════════════════
# TICKET COUNTER — FIX: async + Lock
# ══════════════════════════════════════════
def get_panel_channel_id():
    return load_data().get("panel_channel_id")

def save_panel_channel_id(channel_id: int):
    data = load_data(); data["panel_channel_id"] = channel_id; save_data(data)

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

async def get_ticket_number() -> str:
    """FIX: async + Lock đảm bảo không bao giờ tạo 2 ticket trùng số."""
    async with _get_ticket_lock():
        data = load_data()
        data["ticket"] = data.get("ticket", 0) + 1
        num = data["ticket"]
        # Ghi trực tiếp vào MongoDB ngay lập tức (không dùng queue)
        col, _ = _get_mongo()
        try:
            await col.update_one({"_id": "main"}, {"$set": {"ticket": num}}, upsert=True)
        except Exception as e:
            log.error(f"[DATA] ❌ Lỗi cập nhật ticket counter: {e}")
        if _data_cache is not None:
            _data_cache["ticket"] = num
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
# SELLER COMPENSATION
# ══════════════════════════════════════════
def add_seller_compensation(seller_id: int, amount: int, ticket_name: str, buyer_id: int):
    data = load_data()
    data.setdefault("seller_compensation", {})
    key = str(seller_id)
    if key not in data["seller_compensation"]:
        data["seller_compensation"][key] = {"total_owed": 0, "paid": 0, "records": []}
    data["seller_compensation"][key]["total_owed"] += amount
    data["seller_compensation"][key]["records"].append({
        "ticket": ticket_name, "buyer_id": buyer_id,
        "amount": amount, "time": datetime.now(timezone.utc).isoformat(), "paid": False,
    })
    save_data(data)

def mark_seller_paid(seller_id: int, amount: int):
    data = load_data()
    key  = str(seller_id)
    if key in data.get("seller_compensation", {}):
        data["seller_compensation"][key]["paid"] = data["seller_compensation"][key].get("paid", 0) + amount
        save_data(data)

def get_seller_compensation(seller_id: int) -> dict:
    return load_data().get("seller_compensation", {}).get(str(seller_id), {"total_owed": 0, "paid": 0, "records": []})

def get_all_seller_compensation() -> dict:
    return load_data().get("seller_compensation", {})

# ══════════════════════════════════════════
# REWARD SHOP
# ══════════════════════════════════════════
def get_reward_shop() -> list:
    return load_data().get("reward_shop", [])

def get_reward_item(item_id: str) -> dict | None:
    return next((i for i in get_reward_shop() if i["id"] == item_id), None)

def save_reward_shop(items: list):
    data = load_data(); data["reward_shop"] = items; save_data(data)

def add_exchange_record(user_id: int, item_id: str, item_name: str, points_used: int):
    data = load_data()
    data.setdefault("exchange_log", [])
    data["exchange_log"].append({
        "user_id": user_id, "item_id": item_id, "item_name": item_name,
        "points": points_used, "time": datetime.now(timezone.utc).isoformat(), "status": "pending",
    })
    save_data(data)


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
    return load_data().get("_giveaways", {})

def _save_giveaway_section(giveaways: dict):
    serializable = {
        str(mid): {k: list(v) if isinstance(v, set) else v for k, v in gw.items()}
        for mid, gw in giveaways.items()
    }
    data = load_data().copy()
    data["_giveaways"] = serializable
    save_data(data)
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
    m = _re.match(r"^(\d+)tr(\d+)$", raw)
    if m: return int(m.group(1)) * 1_000_000 + int(m.group(2)) * 100_000
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
