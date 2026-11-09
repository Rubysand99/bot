"""
shared/data.py — Hạ tầng dùng CHUNG cho mọi bot con (bot_core, bot_commerce, bot_ticket,
bot_ai, bot_growth...). Đây là bản tách ra từ core/data.py (dòng 1–666 của bản gốc) —
CHỈ chứa những gì THẬT SỰ dùng chung cho mọi tính năng:

  - contextvars guild context (set_current_guild/get_current_guild_id)
  - MongoDB client + cache engine (load_data/save_data theo guild, load/save_global_data)
  - GuildContextView/GuildContextModal (AUTH_GATE cho nút bấm/modal)
  - AUTH_GATE core (is_guild_authorized, add/remove/set_guild_authorized)
  - ADMIN_IDS (2 admin cố định từ env) + admin phụ theo guild (.ad) + is_admin()
  - init_data_cache() — load cache lúc on_ready, tự guard chống refire xoá cache

KHÔNG chứa (vẫn nằm ở module riêng của từng bot, xem AI_CONTEXT_SHARED.md):
  - Các hàm get_cfg_*/set_cfg_* + accessor riêng cho từng tính năng (seller, ticket,
    giveaway, shop_orders...) — mỗi bot tự định nghĩa accessor của tính năng mình, chỉ
    gọi load_data()/save_data() ở đây làm nền.
  - load_giveaways_data()/save_giveaways_data() và mọi hàm _*giveaway* khác — thuộc
    bot_growth, dùng get_giveaways_cache()/set_giveaways_cache() bên dưới làm cầu nối.
  - send_log() — xem shared/logger.py.

⚠️ Mọi bot import module này PHẢI dùng CHUNG 1 MONGO_URI (cùng database `tuytam_bot`,
cùng collection `bot_data`) — đây là cơ chế các bot "nói chuyện" với nhau (bot A ghi
cfg, bot B đọc được ngay), KHÔNG dùng contextvar/cache RAM để chia sẻ giữa các bot vì
mỗi bot là 1 process riêng, RAM không dùng chung.
"""

import os
import sys
import time
import asyncio
import logging
import contextvars
from motor.motor_asyncio import AsyncIOMotorClient
import discord

log = logging.getLogger("shared.data")

# ══════════════════════════════════════════
# MULTI-GUILD SUPPORT
# ══════════════════════════════════════════
LEGACY_MAIN_GUILD_ID = 1464407860640219189

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
# Mỗi bot con có process/cache RIÊNG → mỗi bot PHẢI tự gọi init_data_cache(bot) ở
# on_ready của chính nó, và mọi tasks.loop nền của bot đó PHẢI await wait_data_cache_ready()
# (của CHÍNH process đó) trong before_loop — event này KHÔNG chia sẻ được giữa các bot
# vì mỗi bot có instance module riêng (process riêng).
_data_cache_ready = asyncio.Event()

def is_data_cache_ready() -> bool:
    return _data_cache_ready.is_set()

async def wait_data_cache_ready() -> None:
    await _data_cache_ready.wait()


class GuildContextView(discord.ui.View):
    """Thay thế discord.ui.View — tự set guild context trước khi chạy callback của bất kỳ
    nút/select nào bên trong, để load_data()/save_data() thao tác đúng document của guild đó.
    Đồng thời áp dụng AUTH_GATE — chặn nút bấm/select ở server CHƯA được ủy quyền.
    Bắt buộc: mọi View có nút bấm/select đọc-ghi data theo guild PHẢI dùng class này
    (không phải discord.ui.View trực tiếp).
    Dùng: from shared.data import GuildContextView as View
    Mọi lượt bấm đều được log `[UI]`; lượt bị AUTH_GATE chặn log `[AUTH-GATE]` (xem guild_ui_gate).
    """
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guild_ui_gate(interaction, "view", self)


class GuildContextModal(discord.ui.Modal):
    """Tương tự GuildContextView nhưng cho Modal — cùng áp dụng AUTH_GATE, xem docstring trên."""
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guild_ui_gate(interaction, "modal", self)


# ══════════════════════════════════════════
# ADMIN_IDS — 2 admin cố định, đọc từ env, quyền ở MỌI guild
# ══════════════════════════════════════════
def _load_admin_ids() -> list[int]:
    ids = []
    for var in ("ADMIN_RUBY_ID", "ADMIN_TUYTAM_ID"):
        val = os.getenv(var, "").strip()
        if val:
            try:
                ids.append(int(val))
            except ValueError:
                log.error(f"[DATA] ❌ {var} không hợp lệ (phải là số): '{val}'")
        elif var == "ADMIN_TUYTAM_ID":
            # TuyTam có thể được hạ xuống admin PHỤ (cấp bằng `.ad` theo từng server) → biến này là TÙY CHỌN.
            log.info("[DATA] ℹ️ ADMIN_TUYTAM_ID không cài → TuyTam KHÔNG phải admin cố định (cấp quyền theo server bằng `.ad`).")
        else:
            log.warning(f"[DATA] ⚠️ {var} chưa được cài trong file .env.")
    if not ids:
        log.critical("[DATA] ❌ Không có ADMIN nào! Hãy set ADMIN_RUBY_ID và ADMIN_TUYTAM_ID.")
    return ids

ADMIN_IDS = _load_admin_ids()
ADMIN_RUBY_ID   = next((i for i in ADMIN_IDS if str(i) == os.getenv("ADMIN_RUBY_ID", "").strip()), None)
ADMIN_TUYTAM_ID = next((i for i in ADMIN_IDS if str(i) == os.getenv("ADMIN_TUYTAM_ID", "").strip()), None)

def _load_tuytam_notify_id() -> int | None:
    """ID người nhận thông báo riêng của shop TuyTam (DM hỏi giá/người mua đơn sold, ping ticket trung gian).
    TÁCH khỏi quyền admin: đặt env `TUYTAM_NOTIFY_ID` để TuyTam vẫn nhận các thông báo này dù KHÔNG còn là admin
    cố định. Không đặt → dùng `ADMIN_TUYTAM_ID` như trước (tương thích ngược, không đổi hành vi nếu chưa cấu hình)."""
    raw = (os.getenv("TUYTAM_NOTIFY_ID", "") or "").strip()
    if raw:
        try: return int(raw)
        except ValueError: log.error(f"[DATA] ❌ TUYTAM_NOTIFY_ID không hợp lệ (phải là số): '{raw}'")
    return ADMIN_TUYTAM_ID

TUYTAM_NOTIFY_ID = _load_tuytam_notify_id()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("❌ Thiếu biến môi trường MONGO_URI!")

# ══════════════════════════════════════════
# MONGO CLIENT
# ══════════════════════════════════════════
# ⚠️ Mỗi bot con là 1 PROCESS riêng → mỗi bot tự tạo client Mongo RIÊNG (biến module-level
# này KHÔNG chia sẻ được giữa các process). Nhiều process cùng mở connection tới cùng 1
# cluster Mongo Atlas là chuyện BÌNH THƯỜNG (đúng cách Mongo được thiết kế để dùng) —
# không cần lo về xung đột, chỉ cần theo dõi tổng số connection nếu Atlas free tier có giới hạn.
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

def get_db():
    """Trả về database 'tuytam_bot' để module khác (vd core/rag.py, bot_ai) mở collection
    riêng mà KHÔNG cần tạo AsyncIOMotorClient mới (tránh tốn connection pool)."""
    _get_mongo()
    return _mongo_client["tuytam_bot"]


# ══════════════════════════════════════════
# DEFAULT DATA
# ══════════════════════════════════════════
# ⚠️ GIỮ NGUYÊN dạng "1 dict khổng lồ chứa field của MỌI tính năng" ở Phase 1 (chưa tách
# bot thật) để đảm bảo hành vi y hệt bản gốc — core/data.py cũ import 2 hàm này từ đây.
# Khi tách bot thật (Phase 2+), CÂN NHẮC đổi sang cơ chế mỗi bot tự "đăng ký" default field
# của mình (vd DEFAULT_FIELDS_REGISTRY.update({...}) lúc import) thay vì 1 dict tĩnh ở đây,
# để bot_ticket không cần biết field mặc định của bot_commerce. CHƯA làm ở bước này vì rủi
# ro cao hơn lợi ích tại Phase 1 — ghi chú lại làm việc cần làm tiếp theo.
def _default_data(guild_id: int) -> dict:
    return {
        "_id": f"guild_{guild_id}",
        "ticket": 0,
        "panel_channel_id": None,
        "qr_path": None,
        "cfg_log_rudy":        0,
        "cfg_ticket_category": 0,
        "cfg_support_role":    0,
        "cfg_seller_role":     0,
        "cfg_seller_roles_extra": [],
        "cfg_counter_channel": 0,
        "cfg_legit_channel":   0,
        "cfg_proof_channel":   0,
        "cfg_legit_emoji":     "✅",
        "cfg_vouch_emoji":     "✅",
        "cfg_ai_channel":      0,
        "cfg_stock_category":  0,
        "cfg_sold_category":   0,
        "cfg_done_role":       0,
        "cfg_transcript_channel": 0,
        "cfg_builder_role":    0,
        "cfg_welcome_channel": 0,
        "cfg_font":            "normal",
        "extra_admin_ids":     [],
        "dangerous_cmd_overrides": {},
        "sellers":          [],
        "sv_prices":        [],
        "buy_roles":        [],
        "user_total_spent": {},
        "ratings":          [],
        "ticket_notes":     {},
        "invite_counts":    {},
        "ticket_history":   [],
        "seller_qr":        {},
        "seller_categories": {},
        "log_channels":     {},
        "seller_sales":      [],
        # TODO(Phase 2): cfg_shop_orders_enabled, cfg_receipt_style, cfg_receipt_thankyou,
        # shop_orders_banks, shop_order_counter, cfg_queue_channel — hiện core/data.py bản
        # gốc backfill các field này rải rác qua save_cfg() lần đầu gọi get_cfg_*(), KHÔNG
        # có trong _default_data() gốc — giữ nguyên như vậy, KHÔNG thêm mới ở đây để tránh
        # lệch hành vi so với bản đang chạy thật.
    }

def _default_data_global() -> dict:
    """Data KHÔNG tách theo guild — tempban dùng chung cho mọi server để không ai né
    được bằng cách nhảy server. (_ip_records của bản verify/IP cũ đã bỏ hẳn.)"""
    return {
        "_id": "main",
        "_tempbans": {},
        "_pending_renames": {},
        "_pending_sold_price":  {},
        "_resolved_sold_price": {},
        "_pending_sold_buyer":  {},
        "_shop_pending_orders":        {},
        "_shop_processed_webhook_ids": {},
    }

# ══════════════════════════════════════════
# TUYTAM LEGACY MIGRATION — CHỈ áp dụng 1 lần cho LEGACY_MAIN_GUILD_ID
# ══════════════════════════════════════════
_TUYTAM_LEGACY_CFG_MIGRATION = {
    "cfg_ticket_category":    1464426174611456195,
    "cfg_support_role":       1474572393908404305,
    "cfg_proof_channel":      1469647159560241318,
    "cfg_stock_category":     1506520186063163423,
    "cfg_sold_category":      1506652491779932240,
    "cfg_done_role":          1515393691206811901,
    "cfg_transcript_channel": 1464430574524436679,
    "cfg_builder_role":       1484158340849205308,
}

# ══════════════════════════════════════════
# LOCKS
# ══════════════════════════════════════════
_save_locks: dict[int, asyncio.Lock] = {}
_global_save_lock = None

def _get_save_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in _save_locks:
        _save_locks[guild_id] = asyncio.Lock()
    return _save_locks[guild_id]

def _get_global_save_lock() -> asyncio.Lock:
    global _global_save_lock
    if _global_save_lock is None:
        _global_save_lock = asyncio.Lock()
    return _global_save_lock

_ticket_locks: dict[int, asyncio.Lock] = {}

def get_ticket_lock(guild_id: int) -> asyncio.Lock:
    """Lock riêng theo guild cho get_ticket_number() (core/data.py) — tách khỏi
    _get_save_lock() vì 2 việc khác nhau: lock này chống trùng SỐ ticket, không phải
    chống ghi đè cache."""
    if guild_id not in _ticket_locks:
        _ticket_locks[guild_id] = asyncio.Lock()
    return _ticket_locks[guild_id]


# ══════════════════════════════════════════
# LOW-LEVEL MongoDB
# ══════════════════════════════════════════
_data_cache: dict[int, dict] = {}
_global_cache: dict | None = None

# FIX (audit v4.59.1): bảo vệ chống ghi đè Mongo bằng dữ liệu mặc định.
#  - _persisted_keys[guild_id]: tập key CÓ THẬT trong document Mongo của guild (chỉ được set khi
#    _mongo_load() THÀNH CÔNG). Guild không có trong dict này = chưa nạp được dữ liệu thật →
#    mọi lệnh ghi bị từ chối (trước đây cache chứa default rồi $set đè lên dữ liệu thật).
#  - cũng dùng để $unset các key top-level đã bị `del data[key]` (trước đây $set không xoá được).
_persisted_keys: dict[int, set] = {}
_persisted_keys_global: set = set()
_global_loaded: bool = False
_bg_tasks: set = set()   # giữ strong reference cho các task flush nền (tránh bị GC + log lỗi)
_LOAD_RETRY_ATTEMPTS = 4
_LOAD_RETRY_DELAY = 2.0  # giây, nhân đôi mỗi lần thử lại

def is_guild_loaded(guild_id: int) -> bool:
    """True nếu dữ liệu THẬT của guild đã nạp từ Mongo (an toàn để ghi)."""
    return guild_id in _persisted_keys

def is_global_loaded() -> bool:
    return _global_loaded

def _spawn_flush(coro_fn, *args) -> None:
    loop = asyncio.get_running_loop()   # ném RuntimeError (caller bắt) TRƯỚC khi tạo coroutine
    t = loop.create_task(coro_fn(*args))
    _bg_tasks.add(t)
    def _done(task):
        _bg_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error(f"[DATA] ❌ Task flush Mongo lỗi: {task.exception()!r}")
    t.add_done_callback(_done)

async def _with_retry(factory, what: str):
    """Chạy coroutine factory() tối đa _LOAD_RETRY_ATTEMPTS lần (backoff nhân đôi)."""
    last = None
    for i in range(_LOAD_RETRY_ATTEMPTS):
        try:
            return await factory()
        except Exception as e:
            last = e
            log.error(f"[DATA] ❌ {what} lỗi (lần {i + 1}/{_LOAD_RETRY_ATTEMPTS}): {e}")
            if i < _LOAD_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_LOAD_RETRY_DELAY * (2 ** i))
    raise last
# Cache giveaway KHÔNG tách theo guild (tự nhiên theo message_id) — thuộc domain
# bot_growth, nhưng NẠP ở đây (init_data_cache) vì lúc khởi động cần load 1 lần cùng
# guild+global. bot_growth's data_ext dùng get_giveaways_cache()/set_giveaways_cache()
# bên dưới để đọc/ghi, KHÔNG import thẳng biến private này.
_giveaways_cache: dict = {}

def get_giveaways_cache() -> dict:
    return _giveaways_cache

def set_giveaways_cache(data: dict) -> None:
    global _giveaways_cache
    _giveaways_cache = data


async def _mongo_load(guild_id: int) -> dict:
    col, _ = _get_mongo()
    doc_id = f"guild_{guild_id}"
    try:
        doc = await col.find_one({"_id": doc_id})
        if doc is None and guild_id == LEGACY_MAIN_GUILD_ID:
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

        # FIX: trước đây migration chạy lại MỖI lần nạp (không có cờ) → admin cố ý để trống
        # 1 cfg qua .st sẽ bị điền lại giá trị cũ sau mỗi lần restart. Giờ chỉ chạy ĐÚNG 1 lần.
        if guild_id == LEGACY_MAIN_GUILD_ID and not doc.get("_legacy_cfg_migrated"):
            for k, v in _TUYTAM_LEGACY_CFG_MIGRATION.items():
                if not doc.get(k):
                    doc[k] = v
            doc["_legacy_cfg_migrated"] = True
            await _mongo_save(guild_id, doc)
            log.info("[DATA] 🔀 Đã backfill cấu hình role/kênh cũ cho TuyTam Community (1 lần)")

        _persisted_keys[guild_id] = set(doc.keys()) - {"_id"}
        return doc
    except Exception as e:
        # FIX: KHÔNG trả _default_data() nữa — default bị cache rồi $set đè lên document thật
        # trong Mongo ở lần save kế tiếp. Ném lỗi để caller retry / bỏ qua guild này.
        log.error(f"[DATA] ❌ Lỗi đọc MongoDB (guild {guild_id}): {e}")
        raise

def _build_update(save: dict, removed: set) -> dict:
    ops = {}
    if save:
        ops["$set"] = save
    if removed:
        ops["$unset"] = {k: "" for k in removed}
    return ops

async def _mongo_save(guild_id: int, data: dict) -> bool:
    col, _ = _get_mongo()
    doc_id = f"guild_{guild_id}"
    save = {k: v for k, v in data.items() if k != "_id"}
    # FIX: $set không bao giờ xoá key → `del data[key]` ở code gọi không có tác dụng với
    # Mongo (key quay lại sau restart). So với tập key đã persist để $unset phần bị xoá.
    removed = _persisted_keys.get(guild_id, set()) - set(save)
    ops = _build_update(save, removed)
    if not ops:
        return True
    for attempt in range(3):
        try:
            await col.update_one({"_id": doc_id}, ops, upsert=True)
            _persisted_keys[guild_id] = set(save) | (_persisted_keys.get(guild_id, set()) - removed)
            return True
        except Exception as e:
            log.error(f"[DATA] ❌ Lỗi ghi MongoDB (guild {guild_id}, lần {attempt + 1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))
    log.critical(f"[DATA] 🚨 KHÔNG ghi được guild {guild_id} sau 3 lần — thay đổi chỉ còn trong RAM!")
    return False

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
        _persisted_keys_global.clear()
        _persisted_keys_global.update(set(doc.keys()) - {"_id"})
        return doc
    except Exception as e:
        # FIX: không trả default (sẽ đè _tempbans/_shop_pending_orders/... thật khi save).
        log.error(f"[DATA] ❌ Lỗi đọc MongoDB (global): {e}")
        raise

async def _mongo_save_global(data: dict) -> bool:
    col, _ = _get_mongo()
    save = {k: v for k, v in data.items() if k != "_id"}
    removed = _persisted_keys_global - set(save)
    ops = _build_update(save, removed)
    if not ops:
        return True
    for attempt in range(3):
        try:
            await col.update_one({"_id": "main"}, ops, upsert=True)
            _persisted_keys_global.difference_update(removed)
            _persisted_keys_global.update(save)
            return True
        except Exception as e:
            log.error(f"[DATA] ❌ Lỗi ghi MongoDB (global, lần {attempt + 1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))
    log.critical("[DATA] 🚨 KHÔNG ghi được document global sau 3 lần — thay đổi chỉ còn trong RAM!")
    return False

async def _flush_to_mongo(guild_id: int):
    if not is_guild_loaded(guild_id):
        log.error(f"[DATA] ⛔ Bỏ qua ghi guild {guild_id}: dữ liệu thật CHƯA nạp từ Mongo (tránh đè bằng default).")
        return
    lock = _get_save_lock(guild_id)
    async with lock:
        data = _data_cache.get(guild_id)
        if data is not None:
            await _mongo_save(guild_id, data)

async def _flush_global_to_mongo():
    if not _global_loaded:
        log.error("[DATA] ⛔ Bỏ qua ghi global: dữ liệu thật CHƯA nạp từ Mongo (tránh đè bằng default).")
        return
    lock = _get_global_save_lock()
    async with lock:
        if _global_cache is not None:
            await _mongo_save_global(_global_cache)

# ══════════════════════════════════════════
# HIGH-LEVEL API — dùng ở MỌI bot, MỌI cog
# ══════════════════════════════════════════
def load_data() -> dict:
    """Trả về shallow copy của cache CHO GUILD ĐANG XỬ LÝ (lấy từ contextvar).
    Dùng save_data() để ghi lại sau khi thay đổi."""
    guild_id = get_current_guild_id()
    if guild_id is None:
        log.error("[DATA] ⚠️ load_data() được gọi mà KHÔNG có guild context — trả về default tạm. "
                  "Nếu vừa thêm listener/task mới, nhớ set_current_guild() đầu hàm.")
        return _default_data(0)
    if guild_id in _data_cache:
        return dict(_data_cache[guild_id])
    log.warning(f"[DATA] ⚠️ Guild {guild_id} chưa có trong cache — trả về default tạm (chưa lưu).")
    return _default_data(guild_id)

def save_data(data: dict):
    guild_id = get_current_guild_id()
    if guild_id is None:
        log.error("[DATA] ❌ save_data() được gọi mà KHÔNG có guild context — dữ liệu KHÔNG được lưu để tránh ghi nhầm guild.")
        return
    if not is_guild_loaded(guild_id):
        log.error(f"[DATA] ⛔ save_data() bị từ chối: guild {guild_id} chưa nạp dữ liệu thật từ Mongo.")
        return
    _data_cache[guild_id] = data
    try:
        _spawn_flush(_flush_to_mongo, guild_id)
    except RuntimeError:
        pass
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi tạo save task (guild {guild_id}): {e}")

def load_global_data() -> dict:
    if _global_cache is not None:
        return dict(_global_cache)
    return _default_data_global()

def save_global_data(data: dict):
    global _global_cache
    if not _global_loaded:
        log.error("[DATA] ⛔ save_global_data() bị từ chối: document global chưa nạp từ Mongo.")
        return
    _global_cache = data
    try:
        _spawn_flush(_flush_global_to_mongo)
    except RuntimeError:
        pass
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi tạo save task (global): {e}")

def save_cfg(key: str, value) -> None:
    """Ghi nhanh 1 field cfg_* đơn giản — dùng chung cho mọi bot/mọi tính năng."""
    data = load_data()
    data[key] = value
    save_data(data)

async def flush_to_mongo(guild_id: int) -> None:
    """Bản PUBLIC của _flush_to_mongo() — dùng khi 1 hàm cần CHẮC CHẮN đã ghi xong Mongo
    trước khi trả kết quả cho người dùng (vd add_cfg_seller_role trả True), thay vì chỉ
    fire-and-forget như save_data()."""
    await _flush_to_mongo(guild_id)

async def flush_global_to_mongo() -> None:
    await _flush_global_to_mongo()

async def save_data_and_wait(data: dict) -> None:
    """Giống save_data() nhưng AWAIT luôn việc ghi Mongo thay vì chỉ tạo task nền — dùng
    khi hàm gọi cần đảm bảo dữ liệu đã persist trước khi return (vd add/remove_cfg_seller_role)."""
    guild_id = get_current_guild_id()
    if guild_id is None:
        log.error("[DATA] ❌ save_data_and_wait() được gọi mà KHÔNG có guild context.")
        return
    if not is_guild_loaded(guild_id):
        log.error(f"[DATA] ⛔ save_data_and_wait() bị từ chối: guild {guild_id} chưa nạp dữ liệu thật.")
        return
    _data_cache[guild_id] = data
    await _flush_to_mongo(guild_id)

def peek_guild_cache(guild_id: int) -> dict | None:
    """Đọc THẲNG vào _data_cache (KHÔNG copy, KHÔNG qua contextvar) — chỉ dùng cho chỗ
    cực sớm trong pipeline discord.py (vd get_guild_prefix ở core/data.py, chạy trước cả
    before_invoke). Ở MỌI nơi khác dùng load_data() như bình thường."""
    return _data_cache.get(guild_id)

def poke_guild_cache_field(guild_id: int, key: str, value) -> None:
    """Set NHANH 1 field trong cache của guild (nếu guild đã có trong cache) — KHÔNG tạo
    task flush Mongo (caller tự lo ghi Mongo ngay sau, xem get_ticket_number()). Dùng khi
    cần đóng 1 race-condition window nhỏ giữa lúc tính giá trị mới và lúc await Mongo."""
    if guild_id in _data_cache:
        _data_cache[guild_id][key] = value

def peek_global_cache() -> dict | None:
    """Tương tự peek_guild_cache() nhưng cho _global_cache — trả về THAM CHIẾU thật (không
    copy) để chỗ gọi có thể setdefault()/mutate in-place (vd atomic_register_ip)."""
    return _global_cache


# ══════════════════════════════════════════
# GUILD AUTHORIZATION — server chỉ hoạt động sau khi admin ủy quyền qua .as
# ══════════════════════════════════════════
def get_authorized_guilds() -> list[int]:
    g = load_global_data()
    return list(g.get("_authorized_guilds", []))

def is_guild_authorized(guild_id: int) -> bool:
    return guild_id in get_authorized_guilds()

def add_authorized_guild(guild_id: int) -> bool:
    global _global_cache
    if not _global_loaded:
        raise RuntimeError("Document global chưa nạp — không thể đổi danh sách ủy quyền.")
    g = load_global_data()
    lst = g.setdefault("_authorized_guilds", [])
    if guild_id in lst:
        return False
    lst.append(guild_id)
    _global_cache = g
    return True

def remove_authorized_guild(guild_id: int) -> bool:
    global _global_cache
    if not _global_loaded:
        raise RuntimeError("Document global chưa nạp — không thể đổi danh sách ủy quyền.")
    g = load_global_data()
    lst = g.get("_authorized_guilds", [])
    if guild_id not in lst:
        return False
    lst = [i for i in lst if i != guild_id]
    g["_authorized_guilds"] = lst
    _global_cache = g
    return True

async def set_guild_authorized(guild_id: int, authorized: bool) -> bool:
    """Bản AWAIT được — dùng cho lệnh `.as` (bot_core). Update RAM ngay rồi await ghi
    thẳng Mongo trước khi trả về, tránh race với on_ready() refire.
    ⚠️ Nếu tách bot thật: CHỈ bot_core chạy lệnh `.as`. Các bot khác chỉ ĐỌC
    is_guild_authorized() — không cần gọi hàm này."""
    changed = add_authorized_guild(guild_id) if authorized else remove_authorized_guild(guild_id)
    if changed:
        if not await _mongo_save_global(_global_cache):
            raise RuntimeError("Không ghi được MongoDB — thay đổi ủy quyền CHƯA được lưu.")
    return changed


# ══════════════════════════════════════════
# BOT ADMIN PHỤ — thêm qua lệnh .ad (bot_core), CHỈ Ruby dùng được
# ══════════════════════════════════════════
def get_extra_admins() -> list[int]:
    return list(load_data().get("extra_admin_ids", []))

async def add_extra_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        log.info(f"[ADMIN] add_extra_admin({user_id}) bỏ qua: đã là admin CỐ ĐỊNH (không cần thêm).")
        return False
    guild_id = get_current_guild_id()
    if guild_id is None:
        log.error("[DATA] ❌ add_extra_admin() được gọi mà KHÔNG có guild context.")
        return False
    if not is_guild_loaded(guild_id):
        log.error(f"[DATA] ⛔ add_extra_admin() bị từ chối: guild {guild_id} chưa nạp dữ liệu thật.")
        return False
    data = load_data()
    lst = data.setdefault("extra_admin_ids", [])
    if user_id in lst:
        log.info(f"[ADMIN] add_extra_admin({user_id}) guild={guild_id} bỏ qua: đã là admin phụ của guild này (hiện có {lst}).")
        return False
    lst.append(user_id)
    _data_cache[guild_id] = data
    await _flush_to_mongo(guild_id)
    log.info(f"[ADMIN] ➕ Đã thêm admin phụ {user_id} cho guild={guild_id}. Danh sách guild này giờ: {lst}")
    return True

async def remove_extra_admin(user_id: int) -> bool:
    guild_id = get_current_guild_id()
    if guild_id is None:
        log.error("[DATA] ❌ remove_extra_admin() được gọi mà KHÔNG có guild context.")
        return False
    if not is_guild_loaded(guild_id):
        log.error(f"[DATA] ⛔ remove_extra_admin() bị từ chối: guild {guild_id} chưa nạp dữ liệu thật.")
        return False
    data = load_data()
    lst = data.get("extra_admin_ids", [])
    if user_id not in lst:
        log.info(f"[ADMIN] remove_extra_admin({user_id}) guild={guild_id} bỏ qua: không có trong danh sách admin phụ guild này ({lst}).")
        return False
    lst.remove(user_id)
    data["extra_admin_ids"] = lst
    _data_cache[guild_id] = data
    await _flush_to_mongo(guild_id)
    log.info(f"[ADMIN] ➖ Đã xoá admin phụ {user_id} khỏi guild={guild_id}. Danh sách guild này giờ: {lst}")
    return True

# ── CONTEXT "ĐANG CHẠY LỆNH / UI NÀO" ──
# Set ở before_invoke (lệnh prefix), CommandTree.interaction_check (slash), guild_ui_gate (nút/select/modal).
# Dùng để: (1) log kiểm tra quyền ghi rõ lệnh nào đang bị chặn, (2) phân biệt kiểm tra quyền CHỦ ĐỘNG
# (user vừa gõ lệnh → log INFO) với kiểm tra THỤ ĐỘNG (listener on_message... → chỉ DEBUG, tránh spam log).
_command_ctx: contextvars.ContextVar = contextvars.ContextVar("command_ctx", default=None)

def set_command_context(label: str | None) -> None:
    _command_ctx.set(label)

def get_command_context() -> str | None:
    return _command_ctx.get()


# ── LOG KIỂM TRA QUYỀN ADMIN — phục vụ debug "sao user X báo không đủ quyền" ──
# Khi đang trong 1 lệnh/UI (get_command_context() != None): MỌI lần is_admin() từ chối / cho phép qua admin phụ
# đều log INFO (chống spam: cùng user+guild+lệnh+lý do chỉ 1 lần/60s) kèm: user, guild, lệnh, lý do, danh sách
# admin phụ của guild, hint "là admin phụ server khác", và DÒNG CODE gọi is_admin (file:dòng hàm()).
# Ngoài lệnh/UI (listener, task nền) chỉ log DEBUG. Thiếu guild context luôn log WARNING.
# Admin cố định chỉ log khi đặt env ADMIN_DEBUG=1 (bật luôn chế độ KHÔNG chống spam, mọi mức → INFO).
# Truyền quiet=True cho kiểm tra thụ động ở đường nóng (vd on_message) để khỏi tốn/ồn log.
_ADMIN_DEBUG = os.getenv("ADMIN_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
_ADMIN_LOG_THROTTLE = 60.0
_admin_log_last: dict[tuple, float] = {}

def _admin_check_log(level: int, uid, name, guild_id, allowed: bool, reason: str) -> None:
    if _ADMIN_DEBUG and level < logging.INFO:
        level = logging.INFO
    if not log.isEnabledFor(level):
        return
    cmd = get_command_context()
    if not _ADMIN_DEBUG:
        key = (uid, guild_id, allowed, cmd, reason[:80])
        now = time.monotonic()
        if now - _admin_log_last.get(key, -1e9) < _ADMIN_LOG_THROTTLE:
            return
        if len(_admin_log_last) > 2000:
            _admin_log_last.clear()
        _admin_log_last[key] = now
    try:
        f = sys._getframe(3)  # 0=hàm này, 1=_admin_decision, 2=is_admin/is_admin_id, 3=nơi gọi
        where = f"{os.path.basename(f.f_code.co_filename)}:{f.f_lineno} {f.f_code.co_name}()"
    except Exception:
        where = "?"
    log.log(level, f"[ADMIN-CHECK] user={uid} ({name}) guild={guild_id} lệnh={cmd or '—'} → "
                   f"{'✅ CHO PHÉP' if allowed else '⛔ TỪ CHỐI'} · {reason} · gọi từ {where}")

def get_all_extra_admins() -> dict[int, list[int]]:
    """{guild_id: [user_id, ...]} — admin phụ (.ad) của MỌI guild đang nằm trong cache RAM
    (guild không có admin phụ thì không xuất hiện). Dùng cho `.admin` / debug; KHÔNG đổi guild context."""
    out: dict[int, list[int]] = {}
    for gid, d in list(_data_cache.items()):
        ids = list(d.get("extra_admin_ids", []))
        if ids:
            out[gid] = ids
    return out

def _admin_decision(uid: int, name: str, quiet: bool) -> bool:
    if uid in ADMIN_IDS:
        if _ADMIN_DEBUG and not quiet:
            _admin_check_log(logging.INFO, uid, name, get_current_guild_id(), True, "admin cố định (ADMIN_IDS)")
        return True
    gid = get_current_guild_id()
    in_cmd = get_command_context() is not None
    if gid is None:
        if not quiet:
            _admin_check_log(logging.WARNING, uid, name, None, False,
                             "KHÔNG có guild context nên không tra được admin phụ — nếu user là admin phụ thì đây là "
                             "LỖI context (thiếu set_current_guild / DM / event không qua before_invoke)")
        return False
    extra = get_extra_admins()
    if uid in extra:
        if not quiet:
            _admin_check_log(logging.INFO if in_cmd else logging.DEBUG, uid, name, gid, True,
                             "admin phụ của server này (.ad)")
        return True
    if not quiet:
        elsewhere = sorted(g for g, ids in get_all_extra_admins().items() if uid in ids and g != gid)
        hint = (f" · ⚠️ user LÀ admin phụ của server khác {elsewhere} nhưng KHÔNG phải server này — "
                f"cần gõ `.ad {uid}` trong đúng server này") if elsewhere else ""
        _admin_check_log(logging.INFO if (in_cmd or elsewhere) else logging.DEBUG, uid, name, gid, False,
                         f"không nằm trong ADMIN_IDS {list(ADMIN_IDS)} và không có trong admin phụ của guild "
                         f"(guild có {len(extra)} admin phụ: {extra}){hint}")
    return False

def is_admin(member, *, quiet: bool = False) -> bool:
    """True nếu member là admin CỐ ĐỊNH (ADMIN_IDS, quyền mọi guild) HOẶC admin PHỤ
    (.ad) của ĐÚNG guild hiện tại (contextvar). Dùng hàm này thay vì check thẳng
    member.id in ADMIN_IDS ở bất kỳ đâu cần phân quyền admin theo guild.
    ⚠️ Admin phụ chỉ có quyền TRONG server được cấp. Lệnh có phạm vi LIÊN SERVER / toàn bot
    (`.as` `.serverlist` `.leaveguild` `.aireset`, nhận guild_id của server khác, dữ liệu dùng chung
    như giveaway...) KHÔNG được dùng is_admin() trần — dùng `member.id in ADMIN_IDS` hoặc tự kiểm tra
    đối tượng thuộc đúng server. Mọi kết quả đáng chú ý đều được log — xem chú thích ở trên."""
    return _admin_decision(member.id, getattr(member, "name", None) or getattr(member, "display_name", None) or "?", quiet)

def is_admin_id(user_id: int, *, quiet: bool = False, name: str = "?") -> bool:
    """Như is_admin() nhưng chỉ có user_id (không có object member)."""
    return _admin_decision(user_id, name, quiet)


def is_user_id(_id: int) -> bool:
    """True nếu `_id` là ID của một NGƯỜI (admin cố định / người nhận thông báo TuyTam / admin phụ của guild
    hiện tại) chứ không phải ID ROLE. Dùng ở các danh sách LẪN role + user (role ticket, ping, quyền kênh) để chọn
    `<@id>` thay vì `<@&id>`. KHÔNG dùng `id in ADMIN_IDS` cho việc này nữa: admin phụ / TuyTam (không còn trong
    ADMIN_IDS) sẽ bị coi là role → mention sai, không ping được, mất quyền vào kênh ticket."""
    if _id in ADMIN_IDS or (TUYTAM_NOTIFY_ID and _id == TUYTAM_NOTIFY_ID):
        return True
    if get_current_guild_id() is None:
        return False
    return _id in get_extra_admins()


async def guild_ui_gate(interaction: discord.Interaction, kind: str, obj) -> bool:
    """interaction_check dùng chung cho GuildContextView/Modal: set guild context + command context,
    áp dụng AUTH_GATE (chặn server chưa ủy quyền), và LOG mọi lượt bấm.
    ⚠️ Server chưa ủy quyền: mọi người bị chặn — admin cố định VÀ admin phụ được báo lý do, người khác im lặng
    (nhưng luôn có log `[AUTH-GATE]`)."""
    gid = interaction.guild_id
    cid = (interaction.data or {}).get("custom_id") if isinstance(interaction.data, dict) else None
    label = f"ui:{type(obj).__name__}" + (f":{str(cid)[:40]}" if cid else "")
    set_command_context(label)
    u = interaction.user
    uname = getattr(u, "name", "?")
    if not gid:
        return True
    set_current_guild(gid)
    if gid not in get_authorized_guilds():
        fixed = u.id in ADMIN_IDS
        extra = u.id in get_extra_admins()
        log.warning(f"[AUTH-GATE] ⛔ chặn {kind} {label} · user={u.id} ({uname}) · guild={gid}: server CHƯA ủy quyền "
                    f"(admin cố định={fixed}, admin phụ={extra}) → dùng `.as {gid}` để bật")
        if fixed or extra:
            try:
                await interaction.response.send_message(
                    f"🔒 Server này (`{gid}`) chưa được ủy quyền.\n"
                    + (f"Dùng `.as {gid}` để bật." if fixed else f"Nhờ Ruby/TuyTam dùng `.as {gid}` để bật."),
                    ephemeral=True,
                )
            except Exception:
                pass
        return False
    log.info(f"[UI] {kind} {label} · user={u.id} ({uname}) · guild={gid} · kênh={interaction.channel_id}")
    return True


# ══════════════════════════════════════════
# INIT / LIFECYCLE
# ══════════════════════════════════════════
async def ensure_guild_loaded(guild_id: int) -> bool:
    """Gọi khi bot join guild mới giữa chừng (on_guild_join). Trả về True nếu dữ liệu thật
    của guild đã sẵn sàng; False nếu đọc Mongo lỗi (guild đó sẽ bị từ chối ghi cho tới khi
    nạp lại được — on_ready refire sẽ thử lại)."""
    if is_guild_loaded(guild_id) and guild_id in _data_cache:
        return True
    try:
        _data_cache[guild_id] = await _with_retry(lambda: _mongo_load(guild_id), f"Nạp guild {guild_id}")
    except Exception as e:
        _data_cache.pop(guild_id, None)
        _persisted_keys.pop(guild_id, None)
        log.critical(f"[DATA] 🚨 Không nạp được guild {guild_id}: {e}")
        return False
    log.info(f"[DATA] ✅ Đã load cache cho guild mới {guild_id}")
    return True

async def init_data_cache(bot) -> None:
    """Gọi ở on_ready CỦA TỪNG BOT — mỗi bot con tự gọi hàm này với đúng client `bot` của
    mình, vì mỗi bot là process riêng, cache RAM (_data_cache/_global_cache/module-level ở
    trên) không dùng chung được. Tự guard chống on_ready() refire xoá cache — xem docstring
    gốc trong CHANGELOG v4.25.4."""
    global _data_cache, _global_cache, _global_loaded

    first_boot = not _data_cache_ready.is_set()

    if not first_boot:
        new_guilds = [g for g in bot.guilds if g.id not in _data_cache or not is_guild_loaded(g.id)]
        for guild in new_guilds:
            await ensure_guild_loaded(guild.id)
        if new_guilds:
            log.info(f"[DATA] 🔁 on_ready refire — nạp thêm {len(new_guilds)} guild mới, giữ nguyên cache cũ.")
        else:
            log.info("[DATA] 🔁 on_ready refire (reconnect) — giữ nguyên cache hiện có, không reload.")
        return

    # FIX: nạp document global TRƯỚC và BẮT BUỘC thành công (retry) — nếu không, bot ở trạng
    # thái "chưa sẵn sàng" (mặc định từ chối mọi guild) thay vì chạy với dữ liệu mặc định rồi
    # ghi đè lên dữ liệu thật. Guild nào nạp lỗi sau khi retry sẽ bị bỏ qua (không cache,
    # không cho ghi) và được thử lại ở on_ready refire kế tiếp.
    _data_cache = {}
    _persisted_keys.clear()
    failed = []
    for guild in bot.guilds:
        if not await ensure_guild_loaded(guild.id):
            failed.append(guild.id)
    if failed:
        log.critical(f"[DATA] 🚨 {len(failed)} guild nạp lỗi, bị khoá ghi: {failed}")

    # Global nạp SAU guild (như bản gốc): _global_cache còn None = mọi guild bị AUTH_GATE
    # từ chối, nên không lệnh nào chạy khi cache guild chưa đủ. Phải THÀNH CÔNG (retry) mới
    # tiếp tục — nếu raise, bot giữ trạng thái "chưa sẵn sàng" và bot.py sẽ thử lại.
    _global_cache = await _with_retry(_mongo_load_global, "Nạp document global")
    _global_loaded = True

    # Giveaway cache — CHỈ bot_growth thật sự cần, nhưng nạp ở đây cho đơn giản (Phase 1).
    # Nếu 1 bot con không dùng giveaway, _giveaways_cache tồn tại vô hại (không ai đọc).
    _, col_gw = _get_mongo()
    try:
        giveaways = {}
        async for doc in col_gw.find({}):
            mid = str(doc.get("message_id", doc.get("_id", "")))
            giveaways[mid] = {k: v for k, v in doc.items() if k not in ("_id", "message_id")}
        set_giveaways_cache(giveaways)
    except Exception as e:
        log.warning(f"[DATA] ⚠️ Không load được giveaways: {e}")
        set_giveaways_cache({})

    guild_list = ", ".join(f"{g.id}(#{_data_cache[g.id].get('ticket', 0):03d})" for g in bot.guilds if g.id in _data_cache)
    print(f"[DATA] ✅ Đã kết nối MongoDB — {len(_data_cache)} guild(s): {guild_list}")
    log.info(f"[ADMIN] Admin cố định (env): {list(ADMIN_IDS)} · RUBY={ADMIN_RUBY_ID} · TUYTAM(cố định)={ADMIN_TUYTAM_ID} · TUYTAM_NOTIFY={TUYTAM_NOTIFY_ID}")
    _extras = get_all_extra_admins()
    log.info(f"[ADMIN] Admin phụ theo guild lúc khởi động: {_extras if _extras else '(chưa có guild nào có admin phụ)'}")

    _data_cache_ready.set()
