"""
core/data.py — MongoDB storage, in-memory cache, và tất cả helper đọc/ghi data.
Import từ file này trong tất cả các Cog.
"""

import os
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

# ══════════════════════════════════════════
# CONSTANTS (default — có thể override qua .settings)
# ══════════════════════════════════════════
LOG_CHANNEL           = 1482234024868053083
TICKET_CATEGORY_ID    = 1464426174611456195
SUPPORT_ROLE_ID       = 1474572393908404305
SELLER_ROLE_ID        = 0
COUNTER_CHANNEL_ID    = 0
LEGIT_CHANNEL_ID      = 0
PROOF_CHANNEL_ID      = 1469647159560241318
TRANSCRIPT_CHANNEL_ID = 1464430574524436679
FEEDBACK_CHANNEL_ID   = 1502464872686948403
BALANCE_CHANNEL_ID    = 1464999465294369035
CHANGELOG_CHANNEL_ID  = 1486967511839801414

ADMIN_IDS = [846332174734983219, 1464961078042689588]
QR_FILE   = "/data/qr_code.png" if os.path.isdir("/data") else "./qr_code.png"

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("❌ Thiếu biến môi trường MONGO_URI! Hãy thêm vào Railway Variables.")

# ══════════════════════════════════════════
# MONGO CLIENT (lazy init)
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
# DEFAULT DATA STRUCTURE
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
        "sellers": [],
        "sv_prices": [],
        "balance": {
            "current": 0, "total_in": 0, "total_fee": 0,
            "total_out": 0, "tx_count": 0, "history": []
        },
        "buy_roles":        [],
        "user_total_spent": {},
        "ratings":          [],
        "ticket_notes":     {},
        "invite_counts":    {},
        "ticket_history":   [],   # [{id, user_id, username, amount, opened_at, closed_at, staff}]
        "user_points":      {},   # {user_id: int}
        "point_codes":      {},   # {code: {user_id, expires_at, used}}
        "point_log":        [],   # lịch sử cộng/trừ point
        "seller_compensation": {},  # {seller_id: {total_owed, paid, records}}
        "point_cfg": {
            "points_per_redeem": 100,   # point mỗi lần vượt link
            "point_value":       100,   # 1 point = 100đ
            "max_discount_pct":  20,    # giảm tối đa 20% giá trị đơn
            "cooldown_hours":    24,    # giới hạn 1 lần/ngày
            "code_expire_mins":  10,    # mã hết hạn sau 10 phút
        },
    }

# ══════════════════════════════════════════
# IN-MEMORY CACHE
# ══════════════════════════════════════════
_data_cache: dict | None = None
_save_lock = None

def _get_save_lock():
    global _save_lock
    if _save_lock is None:
        _save_lock = asyncio.Lock()
    return _save_lock

# ══════════════════════════════════════════
# LOW-LEVEL MongoDB
# ══════════════════════════════════════════
async def _mongo_load() -> dict:
    col, _ = _get_mongo()
    try:
        doc = await col.find_one({"_id": "main"})
        if doc is None:
            doc = _default_data()
            await col.insert_one(doc)
            print("[DATA] 🆕 Tạo document mới trong MongoDB")
        else:
            for k, v in _default_data().items():
                if k not in doc:
                    doc[k] = v
            await _mongo_save(doc)
        return doc
    except Exception as e:
        print(f"[DATA] ❌ Lỗi đọc MongoDB: {e}")
        return _default_data()

async def _mongo_save(data: dict):
    col, _ = _get_mongo()
    try:
        save = {k: v for k, v in data.items() if k != "_id"}
        await col.update_one({"_id": "main"}, {"$set": save}, upsert=True)
    except Exception as e:
        print(f"[DATA] ❌ Lỗi ghi MongoDB: {e}")

async def _flush_to_mongo():
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
    global _data_cache
    _data_cache = data
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_flush_to_mongo())
    except Exception:
        pass

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
        print(f"[DATA] ⚠️ Không load được giveaways: {e}")
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
# TICKET COUNTER
# ══════════════════════════════════════════
def get_panel_channel_id():
    return load_data().get("panel_channel_id")

def save_panel_channel_id(channel_id: int):
    data = load_data(); data["panel_channel_id"] = channel_id; save_data(data)

def get_qr_path():
    return load_data().get("qr_path", None)

def save_qr_path(path: str):
    data = load_data(); data["qr_path"] = path; save_data(data)

def get_ticket_number() -> str:
    data = load_data()
    data["ticket"] = data.get("ticket", 0) + 1
    save_data(data)
    return f"{data['ticket']:03d}"

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
    """Lưu 1 đơn đã done vào lịch sử. record gồm:
    id, user_id, username, amount, opened_at, closed_at, staff, ticket_name
    """
    data = load_data()
    data.setdefault("ticket_history", [])
    data["ticket_history"].append(record)
    save_data(data)

def get_user_ticket_history(user_id: int) -> list:
    return [t for t in get_ticket_history() if t.get("user_id") == user_id]

def get_monthly_stats(year: int, month: int) -> dict:
    """Trả về thống kê ticket trong tháng: tổng đơn, tổng tiền, danh sách đơn."""
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
        "year":         year,
        "month":        month,
        "total_orders": len(records),
        "total_amount": total_amount,
        "records":      records,
    }


# ══════════════════════════════════════════
# POINT SYSTEM
# ══════════════════════════════════════════
def get_point_cfg() -> dict:
    return load_data().get("point_cfg", {
        "points_per_redeem": 100,
        "point_value":       100,
        "max_discount_pct":  20,
        "cooldown_hours":    24,
        "code_expire_mins":  10,
    })

def get_user_points(user_id: int) -> int:
    return load_data().get("user_points", {}).get(str(user_id), 0)

def add_user_points(user_id: int, points: int, reason: str = "") -> int:
    data = load_data()
    data.setdefault("user_points", {})
    data.setdefault("point_log", [])
    key = str(user_id)
    old = data["user_points"].get(key, 0)
    data["user_points"][key] = max(0, old + points)
    data["point_log"].append({
        "user_id": user_id,
        "delta":   points,
        "reason":  reason,
        "balance": data["user_points"][key],
        "time":    datetime.now(timezone.utc).isoformat(),
    })
    save_data(data)
    return data["user_points"][key]

def set_user_points(user_id: int, points: int):
    data = load_data()
    data.setdefault("user_points", {})
    data["user_points"][str(user_id)] = max(0, points)
    save_data(data)

def save_point_code(code: str, user_id: int, expires_at: str):
    data = load_data()
    data.setdefault("point_codes", {})
    data["point_codes"][code] = {"user_id": user_id, "expires_at": expires_at, "used": False}
    save_data(data)

def get_point_code(code: str) -> dict | None:
    return load_data().get("point_codes", {}).get(code)

def mark_code_used(code: str):
    data = load_data()
    if code in data.get("point_codes", {}):
        data["point_codes"][code]["used"] = True
        save_data(data)

def get_last_redeem_time(user_id: int) -> str | None:
    for entry in reversed(load_data().get("point_log", [])):
        if entry.get("user_id") == user_id and str(entry.get("reason", "")).startswith("redeem"):
            return entry.get("time")
    return None

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
        "ticket":   ticket_name,
        "buyer_id": buyer_id,
        "amount":   amount,
        "time":     datetime.now(timezone.utc).isoformat(),
        "paid":     False,
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
# GIVEAWAY PERSISTENCE (collection riêng)
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
            await col_gw.update_one({"message_id": int(mid_str)}, {"$set": doc}, upsert=True)
    except Exception as e:
        print(f"[DATA] ❌ Lỗi sync giveaway MongoDB: {e}")

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
# HELPERS FORMAT
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
    if unit == "k":       return int(num * 1_000)
    if unit in ("tr","m"): return int(num * 1_000_000)
    return int(num)

def fmt_amount(amount: int) -> str:
    if amount >= 1_000_000: return f"{amount/1_000_000:g}tr"
    if amount >= 1_000:     return f"{amount/1_000:g}k"
    return f"{amount:,}đ"

def is_staff_member(member) -> bool:
    import discord
    if member.id in ADMIN_IDS: return True
    guild = member.guild
    sr = guild.get_role(get_cfg_support_role())
    if sr and sr in member.roles: return True
    slr = guild.get_role(get_cfg_seller_role())
    if slr and slr in member.roles: return True
    return False
