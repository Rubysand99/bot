"""
core/data.py — Accessor riêng cho từng tính năng (cfg_*, seller, ticket, giveaway,
shop_orders, dangerous cmd overrides...) của bot NÀY (bot chính / bot_core, tuỳ tên bạn
đặt cho thư mục bot đầu tiên).

⚠️ Hạ tầng dùng CHUNG cho mọi bot (contextvar, Mongo cache engine, AUTH_GATE, admin,
GuildContextView/Modal, init_data_cache) đã CHUYỂN sang shared/data.py — file này giờ
CHỈ còn phần accessor đặc thù, import lại phần hạ tầng từ shared/ ở khối dưới đây.

Nếu cần thêm hạ tầng MỚI dùng chung cho ≥2 bot: thêm vào shared/data.py, KHÔNG thêm vào
đây. Nếu chỉ 1 bot cần: thêm thẳng vào đây (hoặc data_ext.py riêng của bot đó khi đã
tách bot thật — xem AI_CONTEXT_SHARED.md).
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
import discord

from shared.data import (
    LEGACY_MAIN_GUILD_ID,
    set_current_guild, reset_current_guild, get_current_guild_id,
    is_data_cache_ready, wait_data_cache_ready,
    GuildContextView, GuildContextModal,
    ADMIN_IDS, ADMIN_RUBY_ID, ADMIN_TUYTAM_ID,
    MONGO_URI, get_db,
    load_data, save_data, load_global_data, save_global_data, save_cfg,
    get_authorized_guilds, is_guild_authorized, add_authorized_guild,
    remove_authorized_guild, set_guild_authorized,
    get_extra_admins, add_extra_admin, remove_extra_admin, is_admin,
    ensure_guild_loaded, init_data_cache,
    get_giveaways_cache, set_giveaways_cache,
    get_ticket_lock, flush_to_mongo, flush_global_to_mongo, save_data_and_wait,
    peek_guild_cache, poke_guild_cache_field, peek_global_cache,
    _get_mongo,  # re-export: cogs/invite.py + cogs/admin.py vẫn "from core.data import _get_mongo"
)

log = logging.getLogger("core.data")

# ══════════════════════════════════════════
# CONFIG GETTERS / SETTERS
# ══════════════════════════════════════════
def get_cfg_log_rudy()        -> int: return load_data().get("cfg_log_rudy", 0)
def get_cfg_font()            -> str: return load_data().get("cfg_font", "normal")
def get_cfg_category()        -> int: return load_data().get("cfg_ticket_category", 0)
def get_cfg_stock_category()  -> int: return load_data().get("cfg_stock_category",  0)
def get_cfg_sold_category()   -> int: return load_data().get("cfg_sold_category",   0)

def get_cfg_sold_detection_enabled() -> bool:
    """Bật/tắt qua `.sold on`/`.sold off` (cogs/admin.py). Mặc định TRUE — tính
    năng auto-sold đã chạy sẵn từ trước, default phải giữ y bật để KHÔNG âm thầm
    tắt mất đối với guild nào chưa từng gọi `.sold off`/`.sold on` lần nào."""
    return load_data().get("cfg_sold_detection_enabled", True)

def set_cfg_sold_detection_enabled(enabled: bool) -> None:
    save_cfg("cfg_sold_detection_enabled", enabled)
def get_cfg_done_role()       -> int: return load_data().get("cfg_done_role",       0)
def get_cfg_transcript_channel() -> int: return load_data().get("cfg_transcript_channel", 0)
def get_cfg_builder_role()    -> int: return load_data().get("cfg_builder_role",    0)
def get_cfg_welcome_channel() -> int: return load_data().get("cfg_welcome_channel", 0)
def get_cfg_verify_extra_roles() -> list: return list(load_data().get("cfg_verify_extra_roles", []))

def get_guild_prefix(guild_id: int) -> str:
    """FIX: SetPrefixModal (cogs/admin_views.py) lưu "cfg_prefix" và báo THÀNH CÔNG cho
    admin, nhưng KHÔNG có gì từng đọc lại field này — bot.py hardcode command_prefix="."
    (chuỗi tĩnh) nên đổi prefix trước đây không có tác dụng gì, dù bot báo đổi thành công.
    Hàm này để bot.py dùng làm command_prefix CALLABLE (đọc TRỰC TIẾP qua peek_guild_cache(),
    KHÔNG qua load_data()/contextvar — hàm callable này chạy RẤT SỚM trong pipeline xử lý
    message của discord.py, trước khi before_invoke kịp set_current_guild()). Luôn có
    fallback "." an toàn nếu chưa load cache hoặc guild chưa cấu hình gì."""
    try:
        d = peek_guild_cache(guild_id)
        if d:
            p = d.get("cfg_prefix", ".")
            return p if p else "."
    except Exception:
        pass
    return "."
def get_cfg_support_role()    -> int: return load_data().get("cfg_support_role", 0)
def get_cfg_seller_role()     -> int: return load_data().get("cfg_seller_role", 0)

def get_cfg_seller_roles() -> list[int]:
    """TOÀN BỘ role được coi là "seller" — gồm role "chính" (cfg_seller_role, cấu hình
    qua `.st`, giữ nguyên KHÔNG đổi UI đó) CỘNG các role PHỤ thêm qua `.addsellerrole`
    (cfg_seller_roles_extra). Dùng hàm NÀY ở mọi nơi cần check/gán quyền seller — không
    dùng riêng get_cfg_seller_role() nữa (giờ chỉ còn là 1 THÀNH PHẦN của danh sách này,
    vẫn giữ hàm cũ để tương thích chỗ nào còn đọc trực tiếp role "chính")."""
    data = load_data()
    primary = data.get("cfg_seller_role", 0)
    extra = data.get("cfg_seller_roles_extra", [])
    seen, out = set(), []
    for rid in ([primary] if primary else []) + list(extra):
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out

async def add_cfg_seller_role(role_id: int) -> bool:
    """Thêm 1 role seller PHỤ cho guild đang thao tác. Trả về True nếu MỚI thêm — False
    nếu role_id đã nằm trong danh sách seller (role chính HOẶC đã là role phụ) từ trước."""
    if role_id in get_cfg_seller_roles():
        return False
    guild_id = get_current_guild_id()
    if guild_id is None:
        log.error("[DATA] ❌ add_cfg_seller_role() được gọi mà KHÔNG có guild context.")
        return False
    data = load_data()
    lst = data.setdefault("cfg_seller_roles_extra", [])
    lst.append(role_id)
    await save_data_and_wait(data)
    return True

async def remove_cfg_seller_role(role_id: int) -> bool:
    """Xoá 1 role seller khỏi danh sách PHỤ (cfg_seller_roles_extra) của guild đang thao
    tác. Trả về True nếu có xoá thật. KHÔNG xoá được role "chính" (cfg_seller_role) qua
    hàm này — role đó vẫn đổi qua `.st` như cũ."""
    guild_id = get_current_guild_id()
    if guild_id is None:
        log.error("[DATA] ❌ remove_cfg_seller_role() được gọi mà KHÔNG có guild context.")
        return False
    data = load_data()
    lst = data.get("cfg_seller_roles_extra", [])
    if role_id not in lst:
        return False
    lst.remove(role_id)
    data["cfg_seller_roles_extra"] = lst
    await save_data_and_wait(data)
    return True

def get_cfg_counter_channel() -> int: return load_data().get("cfg_counter_channel", 0)
def get_cfg_legit_channel()   -> int: return load_data().get("cfg_legit_channel", 0)
def get_cfg_proof_channel()   -> int: return load_data().get("cfg_proof_channel", 0)
def get_cfg_ai_channel()      -> int: return load_data().get("cfg_ai_channel", 0)
def get_cfg_legit_emoji()     -> str: return load_data().get("cfg_legit_emoji", "✅")
def get_cfg_vouch_emoji()     -> str: return load_data().get("cfg_vouch_emoji", "✅")
def get_cfg_giveaway_require_verify() -> bool:
    """Bắt buộc verify (role Verify) mới được bấm 🎉 Tham gia giveaway hay không.
    Mặc định True — GIỮ ĐÚNG hành vi cũ trước khi có toggle này (check verify vốn
    luôn bật cứng trong cogs/giveaway.py: GiveawayView.join). Bật/tắt qua `.gwverify`."""
    return bool(load_data().get("cfg_giveaway_require_verify", True))

def set_cfg_font(font: str):
    data = load_data(); data["cfg_font"] = font; save_data(data)

def set_cfg_legit_emoji(emoji: str):
    save_cfg("cfg_legit_emoji", emoji.strip())

def set_cfg_vouch_emoji(emoji: str):
    save_cfg("cfg_vouch_emoji", emoji.strip())

def set_cfg_giveaway_require_verify(enabled: bool):
    save_cfg("cfg_giveaway_require_verify", bool(enabled))

def set_cfg_done_role(role_id: int):
    save_cfg("cfg_done_role", int(role_id))

def set_cfg_transcript_channel(channel_id: int):
    save_cfg("cfg_transcript_channel", int(channel_id))

def set_cfg_builder_role(role_id: int):
    save_cfg("cfg_builder_role", int(role_id))

def set_cfg_welcome_channel(channel_id: int):
    save_cfg("cfg_welcome_channel", int(channel_id))

def set_cfg_verify_extra_roles(role_ids: list):
    save_cfg("cfg_verify_extra_roles", [int(r) for r in role_ids])

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

# ── Embed templates (.embed → nút "💾 Lưu làm mẫu" / .embeduse) ──
def get_embed_templates() -> dict:
    return load_data().get("embed_templates", {})

def get_embed_template(name: str) -> dict | None:
    return get_embed_templates().get(name)

def save_embed_template(name: str, payload: dict):
    data = load_data()
    data.setdefault("embed_templates", {})
    data["embed_templates"][name] = payload
    save_data(data)

def delete_embed_template(name: str) -> bool:
    data = load_data()
    templates = data.get("embed_templates", {})
    if name not in templates:
        return False
    del templates[name]
    save_data(data)
    return True

# ── Ruby Shop — danh sách dịch vụ do admin cấu hình thủ công (.rubyoption),
#    hiện ra cho user chọn trước khi ticket #ruby-shop được tạo ──
def get_ruby_shop_options() -> list[str]:
    return load_data().get("ruby_shop_options", [])

def add_ruby_shop_option(name: str) -> bool:
    """True nếu thêm mới; False nếu trùng tên (không phân biệt hoa/thường)."""
    data = load_data()
    opts = data.setdefault("ruby_shop_options", [])
    if any(o.lower() == name.lower() for o in opts):
        return False
    if len(opts) >= 25:  # Discord Select menu tối đa 25 lựa chọn
        raise ValueError("Đã đạt tối đa 25 lựa chọn (giới hạn Select menu của Discord).")
    opts.append(name)
    save_data(data)
    return True

def remove_ruby_shop_option(name: str) -> bool:
    data = load_data()
    opts = data.get("ruby_shop_options", [])
    match = next((o for o in opts if o.lower() == name.lower()), None)
    if not match:
        return False
    opts.remove(match)
    save_data(data)
    return True

def rename_ruby_shop_option(old_name: str, new_name: str) -> bool:
    """Đổi tên 1 lựa chọn, giữ nguyên vị trí trong danh sách.
    True nếu tìm thấy old_name; raise ValueError nếu new_name trùng lựa chọn khác."""
    data = load_data()
    opts = data.get("ruby_shop_options", [])
    idx = next((i for i, o in enumerate(opts) if o.lower() == old_name.lower()), None)
    if idx is None:
        return False
    if any(o.lower() == new_name.lower() for i, o in enumerate(opts) if i != idx):
        raise ValueError(f"tên mới '{new_name}' đã trùng với 1 lựa chọn khác")
    opts[idx] = new_name
    save_data(data)
    return True

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
# [v4.18.0] Chuyển sang load_global_data()/save_global_data() — xem giải thích ở
# _default_data_global() phía trên. KHÔNG cần guild context để đọc/ghi các hàm này.
# {channel_id_str: {seller_id, channel_name, old_name, guild_id, time,
#                    tuytam_message_id, ruby_message_id, escalated}}
def add_pending_sold_price(channel_id: int, seller_id: int, channel_name: str, old_name: str, guild_id: int):
    data = load_global_data()
    data.setdefault("_pending_sold_price", {})
    data["_pending_sold_price"][str(channel_id)] = {
        "seller_id":         seller_id,
        "channel_name":      channel_name,
        "old_name":          old_name,
        "guild_id":          guild_id,
        "time":              datetime.now(timezone.utc).isoformat(),
        "tuytam_message_id": None,
        "ruby_message_id":   None,
        "escalated":         False,
    }
    save_global_data(data)

def get_pending_sold_price(channel_id: int) -> dict | None:
    return load_global_data().get("_pending_sold_price", {}).get(str(channel_id))

def get_all_pending_sold_price() -> dict:
    """Trả về toàn bộ pending {channel_id_str: doc} — dùng khi resume sau restart."""
    return dict(load_global_data().get("_pending_sold_price", {}))

def set_pending_sold_dm(channel_id: int, *, tuytam_message_id: int = None, ruby_message_id: int = None):
    """Lưu message_id của DM (TuyTam và/hoặc Ruby) để resume persistent view sau restart."""
    data = load_global_data()
    pending = data.setdefault("_pending_sold_price", {})
    doc = pending.get(str(channel_id))
    if not doc:
        return
    if tuytam_message_id is not None:
        doc["tuytam_message_id"] = tuytam_message_id
    if ruby_message_id is not None:
        doc["ruby_message_id"] = ruby_message_id
    pending[str(channel_id)] = doc
    save_global_data(data)

def mark_pending_sold_escalated(channel_id: int):
    data = load_global_data()
    pending = data.setdefault("_pending_sold_price", {})
    doc = pending.get(str(channel_id))
    if not doc:
        return
    doc["escalated"] = True
    pending[str(channel_id)] = doc
    save_global_data(data)

def remove_pending_sold_price(channel_id: int):
    data = load_global_data()
    data.setdefault("_pending_sold_price", {})
    data["_pending_sold_price"].pop(str(channel_id), None)
    save_global_data(data)

# ── Resolved sold price — lưu kết quả sau khi 1 admin đã điền giá ──
# Cho phép admin còn lại (bấm nút trễ) biết đơn đã được ai xử lý + giá bao nhiêu.
# {channel_id_str: {amount, resolved_by (user_id), old_name, time}} — tự dọn sau 7 ngày
def mark_pending_sold_resolved(channel_id: int, amount: int, resolved_by: int, old_name: str):
    data = load_global_data()
    data.setdefault("_resolved_sold_price", {})
    data["_resolved_sold_price"][str(channel_id)] = {
        "amount":      amount,
        "resolved_by": resolved_by,
        "old_name":    old_name,
        "time":        datetime.now(timezone.utc).isoformat(),
    }
    save_global_data(data)

def get_resolved_sold_price(channel_id: int) -> dict | None:
    return load_global_data().get("_resolved_sold_price", {}).get(str(channel_id))

# [FIX v4.11.5] Comment phía trên ghi "tự dọn sau 7 ngày" từ trước nhưng
# chưa từng có code dọn thật — dict lớn dần vô hạn. Gọi hàm này 1 lần/ngày
# từ daily_report_task trong logger.py — giờ KHÔNG cần guild context nữa (global).
def cleanup_resolved_sold_price(max_age_days: int = 7) -> int:
    """Xóa các entry resolved_sold_price cũ hơn max_age_days. Trả về số entry đã xóa."""
    data = load_global_data()
    resolved = data.get("_resolved_sold_price", {})
    if not resolved:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    to_delete = []
    for ch_id, rec in resolved.items():
        try:
            t = datetime.fromisoformat(rec.get("time", ""))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t < cutoff:
                to_delete.append(ch_id)
        except Exception:
            to_delete.append(ch_id)   # time không đọc được → coi như rác, dọn luôn
    if not to_delete:
        return 0
    for ch_id in to_delete:
        del resolved[ch_id]
    data["_resolved_sold_price"] = resolved
    save_global_data(data)
    return len(to_delete)

# ── Pending sold BUYER — chờ admin TuyTam/Ruby cho biết tài khoản Discord nào đã
# mua đơn sold-stock này, để cộng tiền (+role) cho đúng buyer giống lệnh .done.
# [v4.18.0] Global từ đầu — cùng lý do với pending_sold_price ở trên.
# {channel_id_str: {seller_id, amount, channel_name, old_name, guild_id, time,
#                    tuytam_message_id, ruby_message_id, escalated}}
def add_pending_sold_buyer(channel_id: int, seller_id: int, amount: int, channel_name: str,
                            old_name: str, guild_id: int):
    data = load_global_data()
    data.setdefault("_pending_sold_buyer", {})
    data["_pending_sold_buyer"][str(channel_id)] = {
        "seller_id":         seller_id,
        "amount":            amount,
        "channel_name":      channel_name,
        "old_name":          old_name,
        "guild_id":          guild_id,
        "time":              datetime.now(timezone.utc).isoformat(),
        "tuytam_message_id": None,
        "ruby_message_id":   None,
        "escalated":         False,
    }
    save_global_data(data)

def get_pending_sold_buyer(channel_id: int) -> dict | None:
    return load_global_data().get("_pending_sold_buyer", {}).get(str(channel_id))

def get_all_pending_sold_buyer() -> dict:
    return dict(load_global_data().get("_pending_sold_buyer", {}))

def set_pending_sold_buyer_dm(channel_id: int, *, tuytam_message_id: int = None, ruby_message_id: int = None):
    data = load_global_data()
    pending = data.setdefault("_pending_sold_buyer", {})
    doc = pending.get(str(channel_id))
    if not doc:
        return
    if tuytam_message_id is not None:
        doc["tuytam_message_id"] = tuytam_message_id
    if ruby_message_id is not None:
        doc["ruby_message_id"] = ruby_message_id
    pending[str(channel_id)] = doc
    save_global_data(data)

def mark_pending_sold_buyer_escalated(channel_id: int):
    data = load_global_data()
    pending = data.setdefault("_pending_sold_buyer", {})
    doc = pending.get(str(channel_id))
    if not doc:
        return
    doc["escalated"] = True
    pending[str(channel_id)] = doc
    save_global_data(data)

def remove_pending_sold_buyer(channel_id: int):
    data = load_global_data()
    data.setdefault("_pending_sold_buyer", {})
    data["_pending_sold_buyer"].pop(str(channel_id), None)
    save_global_data(data)

async def get_ticket_number(guild_id: int) -> str:
    """FIX: async + Lock đảm bảo không bao giờ tạo 2 ticket trùng số.
    Mỗi guild đếm ticket riêng (guild_id bắt buộc truyền vào từ nơi gọi, VD ctx.guild.id).
    Lock cũng tách riêng theo guild (get_ticket_lock(guild_id), shared/data.py) — 2 server tạo ticket
    cùng lúc không còn phải xếp hàng chờ nhau dù chẳng liên quan gì đến nhau."""
    async with get_ticket_lock(guild_id):
        data = load_data()
        data["ticket"] = data.get("ticket", 0) + 1
        num = data["ticket"]
        # FIX: update cache TRƯỚC khi await Mongo (không phải sau). `await col.update_one`
        # bên dưới là 1 điểm yield — trong lúc chờ, 1 coroutine KHÁC (vd sửa danh sách
        # seller) có thể load_data() (đọc số ticket CŨ, vì cache chưa kịp cập nhật) rồi
        # save_data() — ghi đè NGUYÊN cache guild này bằng bản có số ticket cũ, làm cache
        # "tụt" lại → lần .newticket kế tiếp sinh trùng số. Cập nhật cache trước khi có
        # điểm yield nào đóng hẳn cửa sổ race này.
        poke_guild_cache_field(guild_id, "ticket", num)
        col = get_db()["bot_data"]
        try:
            await col.update_one({"_id": f"guild_{guild_id}"}, {"$set": {"ticket": num}}, upsert=True)
        except Exception as e:
            log.error(f"[DATA] ❌ Lỗi cập nhật ticket counter (guild {guild_id}): {e}")
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

def subtract_user_spent(user_id: int, amount: int) -> int:
    """Trừ tiền khỏi tổng chi tiêu chung — dùng khi `.done` bị dùng nhầm. Không cho âm
    (floor 0), vì "đã tiêu -X" không có nghĩa. Trả về tổng MỚI sau khi trừ."""
    data = load_data()
    data.setdefault("user_total_spent", {})
    key = str(user_id)
    current = data["user_total_spent"].get(key, 0)
    data["user_total_spent"][key] = max(0, current - amount)
    save_data(data)
    return data["user_total_spent"][key]

def subtract_user_spent_server(user_id: int, amount: int, server_key: str) -> dict:
    """Trừ tiền khỏi CẢ tổng chung VÀ tổng theo server — bản đối xứng của
    add_user_spent_server(), dùng khi `.done` bị dùng nhầm. Trả về dict
    {"total": int, "server_total": int}.

    FIX (v4.42.1): bản cũ floor-0 RIÊNG cho từng field bằng cùng `amount` gốc — nếu
    tổng theo server (cur_srv) đang THẤP hơn tổng chung (cur_total, chuyện bình
    thường vì server_total là 1 tập con của total) và amount > cur_srv, tổng chung bị
    trừ đủ `amount` còn tổng server chỉ trừ được phần nó có rồi floor ở 0 — 2 số lệch
    nhau và KHÔNG BAO GIỜ tự khớp lại. Giờ tính `actual = min(amount, cur_srv)` một
    lần rồi áp DÙNG CHUNG cho cả 2 field, đảm bảo tổng theo server luôn khớp tổng
    chung (server_total mãi mãi <= total)."""
    data = load_data()
    uid  = str(user_id)

    data.setdefault("user_total_spent", {})
    cur_total = data["user_total_spent"].get(uid, 0)

    data.setdefault("user_spent_by_server", {})
    data["user_spent_by_server"].setdefault(uid, {})
    cur_srv = data["user_spent_by_server"][uid].get(server_key, 0)

    actual = min(amount, cur_srv)
    data["user_total_spent"][uid] = max(0, cur_total - actual)
    data["user_spent_by_server"][uid][server_key] = cur_srv - actual

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
    return dict(get_giveaways_cache())

def _save_giveaway_section(giveaways: dict):
    """Giveaway KHÔNG đi qua load_data()/save_data() (vốn giờ tách theo guild) vì active_giveaways
    ở cogs/giveaway.py là 1 dict phẳng chứa giveaway của MỌI guild, phân biệt bằng message_id.
    Nếu đi qua save_data() sẽ vô tình ghi giveaway của cả 2 server lẫn vào document của guild
    đang xử lý tại thời điểm gọi. col_gw (collection riêng) mới là nguồn lưu trữ chính thức.
    Cache thật (_giveaways_cache) giờ sống ở shared/data.py — dùng get/set_giveaways_cache()
    làm cầu nối, vì shared/data.py cũng là nơi init_data_cache() nạp nó lúc on_ready."""
    serializable = {
        str(mid): {k: list(v) if isinstance(v, set) else v for k, v in gw.items()}
        for mid, gw in giveaways.items()
    }
    set_giveaways_cache(serializable)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_sync_giveaways_to_mongo(serializable))
    except RuntimeError:
        pass
    except Exception as e:
        log.error(f"[DATA] ❌ Lỗi sync giveaway: {e}")

async def _sync_giveaways_to_mongo(giveaways: dict):
    col_gw = get_db()["giveaways"]
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
    # FIX: dùng is_admin() thay vì check thẳng `member.id in ADMIN_IDS` — giờ admin phụ
    # thêm qua `.ad` (guild-scoped, xem is_admin() ở trên) cũng được tính là staff, không
    # chỉ 2 admin cố định ADMIN_RUBY_ID/ADMIN_TUYTAM_ID như trước.
    if is_admin(member): return True
    guild = member.guild
    sr = guild.get_role(get_cfg_support_role())
    if sr and sr in member.roles: return True
    # FIX: check TOÀN BỘ role seller (chính + phụ, xem get_cfg_seller_roles()) thay vì
    # chỉ 1 role seller "chính" như trước — hỗ trợ nhiều role seller cùng lúc.
    for rid in get_cfg_seller_roles():
        r = guild.get_role(rid)
        if r and r in member.roles: return True
    bbr = guild.get_role(get_cfg_builder_role())
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
    col = get_db()["bot_data"]
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
        _gc = peek_global_cache()
        if _gc is not None:
            _gc.setdefault("_ip_records", {})[ip.replace(".", "_")] = users
        return users
    except Exception as e:
        log.error(f"[DATA] ❌ atomic_register_ip lỗi: {e}")
        # Fallback: in-memory
        _gc = peek_global_cache()
        if _gc is not None:
            recs = _gc.setdefault("_ip_records", {})
            ip_key = ip.replace(".", "_")
            if ip_key not in recs:
                recs[ip_key] = []
            if user_id not in recs[ip_key]:
                recs[ip_key].append(user_id)
            return recs[ip_key]
        return [user_id]


# ══════════════════════════════════════════
# SHOP QR (tính năng thử nghiệm — bật/tắt qua .st)
# ĐỔI KIẾN TRÚC: trước đây 1 bank DUY NHẤT dùng chung cho cả guild (shop_orders_cfg).
# Giờ MỖI SELLER tự `.shopbank` đăng ký bank CỦA RIÊNG họ (shop_orders_banks, key =
# user_id) — `.done` do seller nào gõ thì QR dùng đúng bank seller đó, tiền vào thẳng
# tài khoản người xử lý đơn, không qua 1 TK chung nữa.
# ══════════════════════════════════════════
def get_cfg_shop_orders_enabled() -> bool:
    return load_data().get("cfg_shop_orders_enabled", False)

def set_cfg_shop_orders_enabled(enabled: bool) -> None:
    save_cfg("cfg_shop_orders_enabled", enabled)

# ══════════════════════════════════════════
# HOÁ ĐƠN CÔNG KHAI (build_receipt_embed ở shop_orders.py)
# cfg_receipt_style: "embed" (mặc định, đã làm) | "image" (Phần 2 — CHƯA implement).
# Tạo sẵn field này để lúc làm xong bản ảnh chỉ cần thêm nhánh xử lý + nút chọn ở .st,
# không phải đổi schema/migrate data cũ.
# ══════════════════════════════════════════
DEFAULT_RECEIPT_THANKYOU = (
    "✨ Cảm ơn quý khách đã tin tưởng và giao dịch tại **{shop}**!\n"
    "Đơn hàng đã được xác nhận thanh toán & bàn giao thành công."
)

def get_cfg_receipt_style() -> str:
    return load_data().get("cfg_receipt_style", "embed")

def set_cfg_receipt_style(style: str) -> None:
    save_cfg("cfg_receipt_style", style)

def get_cfg_receipt_thankyou() -> str:
    """Lời cảm ơn hiển thị đầu hóa đơn công khai — admin tự sửa qua nút "🧾 Sửa Lời Cảm
    Ơn Hoá Đơn" trong `.st`. Hỗ trợ placeholder {shop} → thay bằng tên server lúc gửi
    (thay bằng str.replace, KHÔNG dùng .format() — tránh vỡ nếu admin gõ dính dấu {})."""
    return load_data().get("cfg_receipt_thankyou", DEFAULT_RECEIPT_THANKYOU)

def set_cfg_receipt_thankyou(text: str) -> None:
    save_cfg("cfg_receipt_thankyou", text)

def get_shop_orders_bank(user_id: int) -> dict | None:
    """Bank riêng của 1 seller. None nếu seller đó chưa từng `.shopbank`."""
    return load_data().get("shop_orders_banks", {}).get(str(user_id))

def save_shop_orders_bank(user_id: int, **fields) -> None:
    """Upsert — gõ lại `.shopbank` là cập nhật đúng bank của CHÍNH seller đó, không tạo trùng."""
    data = load_data()
    banks = data.setdefault("shop_orders_banks", {})
    doc = dict(banks.get(str(user_id), {}))
    doc.update(fields)
    banks[str(user_id)] = doc
    data["shop_orders_banks"] = banks
    save_data(data)

def get_all_shop_orders_banks() -> dict:
    """Toàn bộ bank đã đăng ký trong guild — dùng cho `.listbank`."""
    return load_data().get("shop_orders_banks", {})

def delete_shop_orders_bank(user_id: int) -> bool:
    """Xoá bank đã đăng ký của 1 seller (thêm nhầm/sai thông tin). Trả về True nếu có
    xoá thật (đã tồn tại trước đó), False nếu seller đó vốn chưa đăng ký gì."""
    data = load_data()
    banks = data.get("shop_orders_banks", {})
    if str(user_id) not in banks:
        return False
    del banks[str(user_id)]
    data["shop_orders_banks"] = banks
    save_data(data)
    return True

def has_ticket_access(member: discord.Member) -> bool:
    """"seller" theo yêu cầu gốc: có role nằm trong danh sách role của BẤT KỲ loại
    ticket nào (ticket_multi_roles) → coi là seller. CHỈ dùng để mở khoá
    `.shopbank`/`.listbank` — KHÔNG cấp thêm quyền xem ticket loại nào cả, quyền xem
    ticket vẫn do đúng cấu hình role riêng từng loại (get_ticket_role_ids) quyết định,
    không đổi gì ở đó."""
    if is_admin(member):  # FIX: gồm cả admin phụ theo guild (.ad), không chỉ ADMIN_IDS cố định
        return True
    member_role_ids = {r.id for r in member.roles}
    for role_ids in get_all_ticket_multi_roles().values():
        if member_role_ids.intersection(role_ids):
            return True
    return False


# ══════════════════════════════════════════
# SHOP PENDING ORDERS — GLOBAL, không tách theo guild (xem _default_data_global()).
# Webhook thanh toán (SePay...) gọi vào KHÔNG có guild context sẵn — phải tra global
# theo ref_code trước, lấy guild_id trong record rồi mới set_current_guild() đúng
# guild của đơn đó để làm tiếp (đọc cfg, gửi tin...) — cùng lý do/pattern với
# _pending_sold_price phía trên.
# ══════════════════════════════════════════
def save_pending_shop_order(ref_code: str, **fields) -> None:
    data = load_global_data()
    orders = data.setdefault("_shop_pending_orders", {})
    orders[ref_code] = {**fields, "ref_code": ref_code}
    data["_shop_pending_orders"] = orders
    save_global_data(data)

def get_pending_shop_order(ref_code: str) -> dict | None:
    return load_global_data().get("_shop_pending_orders", {}).get(ref_code)

def pop_pending_shop_order(ref_code: str) -> dict | None:
    """Lấy ra + xoá luôn — gọi khi đã khớp thanh toán xong, tránh khớp lại lần 2."""
    data = load_global_data()
    orders = data.get("_shop_pending_orders", {})
    doc = orders.pop(ref_code, None)
    if doc is not None:
        data["_shop_pending_orders"] = orders
        save_global_data(data)
    return doc

def find_pending_shop_order_by_content(content: str) -> dict | None:
    """SePay trả `content` thô — có thể kèm text khác quanh mã (ngân hàng tự thêm/bớt
    khoảng trắng, có khi in hoa hết). Tìm ref_code nào xuất hiện dạng substring trong
    content, không phân biệt hoa/thường, thay vì đòi khớp tuyệt đối."""
    content_upper = (content or "").upper()
    if not content_upper:
        return None
    for ref_code, doc in load_global_data().get("_shop_pending_orders", {}).items():
        if ref_code.upper() in content_upper:
            return doc
    return None

def is_webhook_id_processed(webhook_id) -> bool:
    """SePay có thể bắn trùng 1 giao dịch nhiều lần (retry) — chống xử lý 2 lần."""
    return str(webhook_id) in load_global_data().get("_shop_processed_webhook_ids", {})

def mark_webhook_id_processed(webhook_id) -> None:
    data = load_global_data()
    ids = data.setdefault("_shop_processed_webhook_ids", {})
    ids[str(webhook_id)] = datetime.now(timezone.utc).isoformat()
    # Dọn bớt id cũ hơn 7 ngày — SePay chỉ retry tối đa 5 tiếng (xem docs), giữ 7 ngày
    # là dư an toàn mà không để dict phình vô hạn theo thời gian.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    for wid, ts in list(ids.items()):
        try:
            if datetime.fromisoformat(ts) < cutoff:
                ids.pop(wid, None)
        except Exception:
            pass
    data["_shop_processed_webhook_ids"] = ids
    save_global_data(data)

def get_cfg_queue_channel() -> int:
    return load_data().get("cfg_queue_channel", 0)

def get_next_shop_order_number() -> str:
    """Tăng & trả về số hoá đơn tiếp theo (theo guild) — dùng khi đánh dấu 'Hoàn thành'
    trong hàng đợi shop_orders để dựng hóa đơn kiểu #2349 gửi vào kênh proof."""
    data = load_data()
    next_num = data.get("shop_order_counter", 0) + 1
    data["shop_order_counter"] = next_num
    save_data(data)
    return str(next_num)

def set_shop_order_counter(number: int) -> None:
    """Cho phép admin chỉnh số hoá đơn bắt đầu (vd để khớp với hệ thống cũ)."""
    data = load_data()
    data["shop_order_counter"] = number
    save_data(data)

def save_cfg_queue_channel(channel_id: int) -> None:
    save_cfg("cfg_queue_channel", channel_id)


async def get_ip_users_mongo(ip: str) -> list[int]:
    """Đọc trực tiếp từ MongoDB (không qua cache) — dùng khi check collision."""
    col = get_db()["bot_data"]
    key = f"_ip_records.{ip.replace('.', '_')}"
    try:
        doc = await col.find_one({"_id": "main"}, {key: 1})
        return (doc or {}).get("_ip_records", {}).get(ip.replace(".", "_"), [])
    except Exception as e:
        log.error(f"[DATA] ❌ get_ip_users_mongo lỗi: {e}")
        # Fallback cache global
        _gc = peek_global_cache()
        if _gc is not None:
            return _gc.get("_ip_records", {}).get(ip.replace(".", "_"), [])
        return []
