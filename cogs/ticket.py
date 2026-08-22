"""
cogs/ticket.py — Ticket system: panel, views, modals, close/done logic.
"""

import io
import asyncio
_ticket_create_lock = asyncio.Lock()
import logging
log = logging.getLogger(__name__)
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ui import Button, Select, TextInput

from core.data import (
    ADMIN_IDS, ADMIN_TUYTAM_ID,
    get_cfg_transcript_channel,
    get_cfg_category, get_cfg_support_role, get_cfg_seller_role,
    get_cfg_counter_channel,
    save_panel_channel_id,
    get_user_total_spent,
    add_user_spent, add_user_spent_server,
    subtract_user_spent, subtract_user_spent_server,
    get_buy_roles,
    save_ticket_record, get_user_ticket_history, get_monthly_stats,
    load_data, save_data, parse_amount, fmt_amount, is_staff_member,
    _uname_plain,
    save_seller_category,
    remove_seller_category, get_all_seller_categories,
    get_or_fetch_channel,
    get_ticket_role_ids, set_ticket_role_ids, get_all_ticket_multi_roles,
    get_ruby_shop_options, add_ruby_shop_option, remove_ruby_shop_option, rename_ruby_shop_option,
    get_cfg_done_role,
    get_cfg_builder_role, set_cfg_builder_role,
    GuildContextView as View,
    GuildContextModal as Modal,
    set_current_guild,
)
from cogs.logger import send_log

# BOT_VERSION được import từ bot.py khi cần — không hardcode lại ở đây

# ── Server keys cho mua/bán ──
SERVER_DONUT  = "donut"
SERVER_KING   = "kingmc"
SERVER_ONEMC  = "onemc"
SERVER_FF     = "ff"

SERVER_TABLE = {
    SERVER_DONUT:  {"label": "🍩 DonutSMP",  "color": 0xFF6B6B, "channel_prefix": "donut"},
    SERVER_KING:   {"label": "👑 KingMC",    "color": 0xF1C40F, "channel_prefix": "king"},
    SERVER_ONEMC:  {"label": "🎮 One MC",    "color": 0x2ECC71, "channel_prefix": "onemc"},
    SERVER_FF:     {"label": "🔥 Free Fire", "color": 0xE67E22, "channel_prefix": "ff"},
}

# ── Bảng SERVICE (không có giá) ──
SERVICE_TABLE = {
    "giveaway":  {"label": "🎁 Nhận Giveaway", "note": "Xác nhận & nhận thưởng giveaway", "color": 0xF1C40F, "type_label": "🎁 NHẬN GIVEAWAY",  "channel_prefix": "ticket"},
    "support":   {"label": "🆘 Hỗ Trợ",        "note": "Hỗ trợ mọi vấn đề",              "color": 0x3498DB, "type_label": "🆘 HỖ TRỢ",         "channel_prefix": "ticket"},
}

_ITEM_LABEL = {"money": "💰 Money", "skeleton": "💀 Skeleton", "elytra": "🦋 Elytra", "other": "📦 Khác"}
_ITEM_OPTIONS = [
    discord.SelectOption(label="💰 Money",    value="money",    description="Giao dịch tiền tệ trong game",   emoji="💰"),
    discord.SelectOption(label="💀 Skeleton", value="skeleton", description="Giao dịch skeleton",             emoji="💀"),
    discord.SelectOption(label="🦋 Elytra",   value="elytra",   description="Giao dịch Elytra",               emoji="🦋"),
    discord.SelectOption(label="📦 Khác",     value="other",    description="Item / dịch vụ khác",           emoji="📦"),
]

# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════
# Cache: (guild_id, user_id) → channel_id (ticket đang mở)
# FIX: trước đây key CHỈ có user_id, KHÔNG phân biệt guild. Với 1 user là member của
# NHIỀU guild bot đang phục vụ (đúng mục đích multi-guild của bot — xem AI_CONTEXT.md),
# có ticket mở ở guild A rồi thử mở ở guild B khiến has_ticket(guild_B, user) tra nhầm
# channel_id của guild A vào guild B → guild_B.get_channel(...) trả None (channel đó
# không thuộc guild B) → tưởng nhầm "ticket không còn tồn tại" → TỰ XOÁ LUÔN cache của
# guild A dù ticket ở đó vẫn đang mở bình thường! User sau đó có thể mở ticket THỨ 2 ở
# guild A (ticket đầu vẫn còn), phá vỡ luật "1 ticket/user" xuyên guild. Giờ key có thêm
# guild_id nên mỗi guild theo dõi độc lập hoàn toàn — đúng tinh thần "mỗi server data
# riêng, không dùng chung" của toàn bộ hệ thống multi-guild.
_open_tickets: dict[tuple[int, int], int] = {}

def _register_ticket(user_id: int, channel_id: int, guild_id: int):
    _open_tickets[(guild_id, user_id)] = channel_id

def _unregister_ticket(user_id: int, guild_id: int):
    _open_tickets.pop((guild_id, user_id), None)

async def has_ticket(guild, user) -> bool:
    """Kiểm tra user có ticket đang mở Ở ĐÚNG GUILD NÀY không — dùng cache O(1) thay vì
    quét toàn bộ kênh."""
    channel_id = _open_tickets.get((guild.id, user.id))
    if channel_id:
        ch = guild.get_channel(channel_id)
        if ch:
            return True
        # Kênh không còn tồn tại → dọn cache (CHỈ của guild này, không đụng guild khác)
        _unregister_ticket(user.id, guild.id)
    return False

async def read_counter_from_channel(bot) -> int:
    ch_id = get_cfg_counter_channel()
    if not ch_id: return 0
    channel = await get_or_fetch_channel(bot, ch_id)
    if not channel: return 0
    try:
        async for msg in channel.history(limit=1):
            if msg.content.startswith("ticket:"):
                return int(msg.content.split(":")[1])
    except Exception as _e:
        log.debug(f"[SILENT] {_e}")
    return 0

async def write_counter_to_channel(bot, number: int):
    ch_id = get_cfg_counter_channel()
    if not ch_id: return
    channel = await get_or_fetch_channel(bot, ch_id)
    if not channel: return
    try:
        await channel.purge(limit=5)
        await channel.send(f"ticket:{number:03d}")
    except Exception:
        pass

async def get_next_ticket_number(bot) -> str:
    async with _ticket_create_lock:
        channel_num = await read_counter_from_channel(bot)
        data = load_data()
        current = max(channel_num, data.get("ticket", 0))
        next_num = current + 1
        data["ticket"] = next_num
        save_data(data)
        asyncio.create_task(write_counter_to_channel(bot, next_num))
        return f"{next_num:03d}"

async def sync_ticket_counter(bot, guild: discord.Guild):
    data = load_data()
    max_num = data.get("ticket", 0)
    ch_num = await read_counter_from_channel(bot)
    if ch_num > max_num: max_num = ch_num
    for channel in guild.text_channels:
        if channel.name.startswith("ticket-"):
            try:
                n = int(channel.name.split("-")[-1])
                if n > max_num: max_num = n
            except ValueError: continue
    if max_num > data.get("ticket", 0):
        data["ticket"] = max_num
        save_data(data)
        asyncio.create_task(write_counter_to_channel(bot, max_num))
        print(f"[SYNC] Ticket counter đồng bộ → {max_num:03d}")

def _build_ticket_overwrites(guild, user, seller_id=None, role_group: str | None = None, role_id: int | None = None):
    """
    Ưu tiên role_id nếu được truyền vào (dùng cho Donut, King, AccPre).
    role_group: "seller" | "builder" | "admin" | None  — dùng khi không có role_id.
      - "seller"  → chỉ Seller Role vào kênh
      - "builder" → chỉ Builder Base Role vào kênh
      - "admin"   → chỉ Admin trong ADMIN_IDS vào kênh
      - None      → cả hai role + support (hành vi cũ)
    Admin luôn có full quyền bất kể role_group/role_id.
    """
    _staff_perm  = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, attach_files=True, embed_links=True, manage_channels=True, manage_permissions=True)
    _member_perm = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: _member_perm,
    }

    # Admin luôn full quyền
    for admin_id in ADMIN_IDS:
        m = guild.get_member(admin_id)
        if m:
            overwrites[m] = _staff_perm

    if role_id:
        # Chế độ mới: dùng role ID cụ thể (Donut, King, AccPre...)
        r = guild.get_role(role_id)
        if r:
            overwrites[r] = _staff_perm
    elif role_group == "seller":
        seller_role = guild.get_role(get_cfg_seller_role())
        if seller_role:
            overwrites[seller_role] = _staff_perm
    elif role_group == "builder":
        builder_role = guild.get_role(get_cfg_builder_role())
        if builder_role:
            overwrites[builder_role] = _staff_perm
    elif role_group == "admin":
        pass  # Chỉ ADMIN_IDS — đã thêm ở trên
    else:
        # Fallback: cả hai role + support
        support_role = guild.get_role(get_cfg_support_role())
        if support_role:
            overwrites[support_role] = _staff_perm
        seller_role = guild.get_role(get_cfg_seller_role())
        if seller_role:
            overwrites[seller_role] = _staff_perm
    return overwrites


def _build_ticket_overwrites_multi(guild, user, role_ids: list, seller_id: int | None = None):
    """Dùng list role IDs từ hệ thống mới (ticket_multi_roles).
    Nếu role_ids rỗng → fallback cả hai role + support.
    Admin IDs trong list được gán theo member, không phải role.
    """
    _staff_perm  = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, attach_files=True, embed_links=True, manage_channels=True, manage_permissions=True)
    _member_perm = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: _member_perm,
    }
    # Admin luôn full quyền
    for aid in ADMIN_IDS:
        m = guild.get_member(aid)
        if m:
            overwrites[m] = _staff_perm

    if role_ids:
        for rid in role_ids:
            if rid in ADMIN_IDS:
                m = guild.get_member(rid)
                if m:
                    overwrites[m] = _staff_perm
            else:
                r = guild.get_role(rid)
                if r:
                    overwrites[r] = _staff_perm
    else:
        # Fallback
        for rid in [get_cfg_support_role(), get_cfg_seller_role()]:
            r = guild.get_role(rid)
            if r:
                overwrites[r] = _staff_perm
        seller_role = guild.get_role(get_cfg_seller_role())
        if seller_role:
            overwrites[seller_role] = _staff_perm
        builder_role = guild.get_role(get_cfg_builder_role())
        if builder_role:
            overwrites[builder_role] = _staff_perm

    if seller_id:
        sm = guild.get_member(seller_id)
        if sm:
            overwrites[sm] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)

    return overwrites

# ══════════════════════════════════════════
# PANEL EMBED
# ══════════════════════════════════════════
def build_panel_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🏪  TuyTam Store",
        description="Chào mừng đến với **TuyTam Store**!\nNhấn nút bên dưới để tạo ticket giao dịch.",
        color=0x5865F2, timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🛒  Dịch vụ", value="› Mua / Bán Money, Skeleton, Elytra\n› 🎭 Acc Pre\n› 🎁 Nhận Giveaway\n› 🆘 Hỗ Trợ", inline=True)
    embed.add_field(name="📋  Ticket bao gồm", value="› Tạo kênh riêng tư\n› Staff hỗ trợ 24/7\n› Transcript sau giao dịch", inline=True)
    embed.add_field(name="⚠️  Lưu ý", value="› Không spam ticket\n› Ghi rõ số lượng & item\n› Thanh toán đúng giá niêm yết", inline=False)
    embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)
    if guild.icon: embed.set_thumbnail(url=guild.icon.url)
    return embed

def build_middleman_panel_embed(guild: discord.Guild) -> discord.Embed:
    """Panel riêng cho ticket Giao Dịch Trung Gian — embed mẫu theo #🤝・middleman."""
    embed = discord.Embed(
        title="🤝  AutoMM  •  Giao Dịch Trung Gian",
        description=(
            "Bot trung gian tự động — tiền/tài sản chỉ được xem là an toàn khi giao dịch "
            "được thực hiện dưới sự giám sát của staff.\n"
        ),
        color=0x57F287, timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="📋  Cách sử dụng",
        value=(
            "**1.** Nhấn **Tạo giao dịch** bên dưới\n"
            "**2.** Nhập ID (hoặc tên) tài khoản bạn muốn giao dịch cùng\n"
            "**3.** Ticket riêng tư được tạo, admin sẽ được thông báo hỗ trợ\n"
            "**4.** Hai bên thực hiện giao dịch dưới sự giám sát của staff\n"
            "**5.** Giao dịch xong → staff xác nhận & đóng ticket"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚠️  Lưu ý",
        value=(
            "-# Phí dịch vụ (nếu có) được áp dụng theo bảng phí hiện hành.\n"
            "-# Chỉ tạo giao dịch khi bạn thực sự muốn hoàn tất."
        ),
        inline=False,
    )
    embed.set_footer(text="TuyTam Store  •  Giao Dịch Trung Gian", icon_url=guild.icon.url if guild.icon else None)
    if guild.icon: embed.set_thumbnail(url=guild.icon.url)
    return embed

# ══════════════════════════════════════════
# TRANSCRIPT HTML
# ══════════════════════════════════════════
def build_transcript_html(channel_name, messages, info: dict = None):
    info = info or {}
    close_time_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")

    def row(icon, label, value):
        return f'<div class="info-row"><span class="info-icon">{icon}</span><span class="info-label">{label}</span><span class="info-value">{value}</span></div>'

    info_rows = ""
    if info.get("created_by_name"):
        av = info.get("created_by_avatar", "")
        av_tag = f'<img src="{av}" class="info-avatar" onerror="this.style.display=\'none\'">' if av else ""
        info_rows += f'<div class="info-row"><span class="info-icon">👤</span><span class="info-label">Người tạo</span><span class="info-value">{av_tag} {info["created_by_name"]} <span class="uid">(ID: {info.get("created_by_id","")})</span></span></div>'
    if info.get("closed_by_name"):
        info_rows += row("🔒", "Người đóng", f'{info["closed_by_name"]} <span class="uid">(ID: {info.get("closed_by_id","")})</span>')
    if info.get("ticket_type"): info_rows += row("🏷️", "Loại ticket", info["ticket_type"])
    if info.get("mc_name"):     info_rows += row("🎮", "Tên Minecraft", info["mc_name"])
    if info.get("item"):
        action = "Mua" if info.get("trade_type") == "sell" else ("Bán" if info.get("trade_type") == "buy" else "")
        info_rows += row("📦", "Giao dịch", f'{action} {info["item"]}' if action else info["item"])
    if info.get("created_at"): info_rows += row("🕐", "Thời gian tạo", info["created_at"])
    info_rows += row("🕑", "Thời gian đóng", close_time_str)
    info_rows += row("💬", "Số tin nhắn", f"{len(messages)} tin nhắn")

    rows = ""
    for msg in messages:
        avatar = msg.author.display_avatar.url if msg.author.display_avatar else ""
        raw = msg.content or ""
        content = (raw.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;") if raw else "<i style='color:#72767d'>(không có nội dung)</i>")
        attach_html = ""
        for att in msg.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                attach_html += f'<br><img src="{att.url}" class="attach-img" onerror="this.style.display=\'none\'">'
            else:
                attach_html += f'<br><a href="{att.url}" class="attach-link" target="_blank">📎 {att.filename}</a>'
        time_str = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
        is_bot = "bot-msg" if msg.author.bot else ""
        rows += f"""<div class="message {is_bot}"><img class="avatar" src="{avatar}" onerror="this.style.display='none'"><div class="content"><div class="msg-header"><span class="author">{msg.author.display_name}</span><span class="username">@{msg.author}</span>{"<span class='bot-badge'>BOT</span>" if msg.author.bot else ""}<span class="time">{time_str} UTC</span></div><div class="text">{content}{attach_html}</div></div></div>"""

    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>Transcript – {channel_name}</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#313338;font-family:'Segoe UI',Arial,sans-serif;color:#dcddde}}.header{{background:#1e1f22;border-bottom:2px solid #5865F2;padding:24px 32px}}.header-title{{display:flex;align-items:center;gap:12px;margin-bottom:16px}}.header-title h1{{color:#fff;font-size:22px}}.ticket-badge{{background:#5865F2;color:#fff;font-size:12px;padding:3px 10px;border-radius:12px;font-weight:600}}.info-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px}}.info-row{{display:flex;align-items:center;gap:8px;background:#2b2d31;border-radius:8px;padding:8px 12px}}.info-label{{color:#a3a6aa;font-size:12px;width:110px}}.info-value{{color:#fff;font-size:13px;font-weight:500;display:flex;align-items:center;gap:6px;flex-wrap:wrap}}.uid{{color:#a3a6aa;font-size:11px;font-weight:400}}.info-avatar{{width:20px;height:20px;border-radius:50%}}.messages{{padding:16px 32px}}.divider{{text-align:center;color:#a3a6aa;font-size:11px;margin:12px 0;border-top:1px solid #3f4147;padding-top:8px}}.message{{display:flex;gap:14px;padding:6px 10px;border-radius:8px;margin-bottom:1px}}.message:hover{{background:#2e3035}}.bot-msg{{opacity:.85}}.avatar{{width:40px;height:40px;border-radius:50%;flex-shrink:0;margin-top:2px}}.content{{display:flex;flex-direction:column;gap:2px;min-width:0}}.msg-header{{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap}}.author{{font-weight:700;color:#fff;font-size:14px}}.username{{color:#a3a6aa;font-size:11px}}.bot-badge{{background:#5865F2;color:#fff;font-size:10px;padding:1px 5px;border-radius:4px;font-weight:600}}.time{{color:#a3a6aa;font-size:11px}}.text{{font-size:14px;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:#dcddde}}.attach-img{{max-width:320px;max-height:240px;border-radius:6px;margin-top:6px}}.attach-link{{color:#00aff4;text-decoration:none;font-size:13px}}.footer{{text-align:center;color:#4f545c;font-size:12px;padding:20px;border-top:1px solid #3f4147;margin-top:16px}}</style>
</head><body><div class="header"><div class="header-title"><h1>📄 Transcript</h1><span class="ticket-badge">#{channel_name}</span></div><div class="info-grid">{info_rows}</div></div><div class="messages"><div class="divider">— Bắt đầu lịch sử tin nhắn —</div>{rows}<div class="divider">— Kết thúc — {len(messages)} tin nhắn —</div></div><div class="footer">TuyTam Store • Ticket System • Xuất lúc {close_time_str}</div></body></html>"""

# ══════════════════════════════════════════
# CLOSE TICKET LOGIC
# ══════════════════════════════════════════
async def _close_ticket(channel, bot_instance, closer: discord.Member = None):
    user_id = mc_name = trade_type = item_key = None
    ticket_name = channel.name

    if channel.topic:
        parts = channel.topic.split("|")
        try: user_id = int(parts[0]) if parts[0].isdigit() else None
        except Exception as _e:
            log.debug(f"[SILENT] {_e}")
        mc_name    = parts[1] if len(parts) > 1 and parts[1] not in ("service","") else None
        trade_type = parts[2] if len(parts) > 2 else None
        item_key   = parts[3] if len(parts) > 3 else None

    guild   = channel.guild
    creator = guild.get_member(user_id) if user_id else None
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    created_at_str = messages[0].created_at.strftime("%d/%m/%Y %H:%M:%S UTC") if messages else "Không rõ"

    item_label = None
    if item_key:
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
    close_time = datetime.now(timezone.utc)
    duration_str = "Không rõ"
    if messages:
        total_sec = int((close_time - messages[0].created_at.replace(tzinfo=timezone.utc)).total_seconds())
        h, m, s = total_sec // 3600, (total_sec % 3600) // 60, total_sec % 60
        duration_str = f"{h}g {m}p {s}s" if h else f"{m}p {s}s"

    embed = discord.Embed(title="📄 Ticket Đã Đóng", color=0xED4245, timestamp=close_time)
    embed.add_field(name="🎫 Ticket",    value=f"`{ticket_name}`", inline=True)
    embed.add_field(name="🏷️ Loại",     value=ticket_type_label,  inline=True)
    embed.add_field(name="💬 Tin nhắn", value=f"**{len(messages)}**", inline=True)
    embed.add_field(name="👤 Người tạo",  value=str(creator) if creator else f"`ID:{user_id}`", inline=True)
    embed.add_field(name="🔒 Người đóng", value=closer.mention if closer else "Hệ thống",        inline=True)
    embed.add_field(name="⏱️ Thời lượng", value=duration_str, inline=True)
    embed.add_field(name="🕐 Thời gian tạo",  value=created_at_str,                                      inline=True)
    embed.add_field(name="🕑 Thời gian đóng", value=close_time.strftime("%d/%m/%Y %H:%M:%S UTC"),        inline=True)
    if mc_name:    embed.add_field(name="🎮 Minecraft", value=f"`{mc_name}`", inline=True)
    if item_label: embed.add_field(name="📦 Item",       value=item_label,    inline=True)
    if creator:    embed.set_thumbnail(url=creator.display_avatar.url)
    embed.set_footer(text="TuyTam Store • Ticket System")

    transcript_ch = await get_or_fetch_channel(bot_instance, get_cfg_transcript_channel())
    if transcript_ch:
        file2 = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")
        await transcript_ch.send(embed=embed, file=file2)

    # Dọn cache open ticket
    if user_id:
        _unregister_ticket(user_id, channel.guild.id)

    # Dọn completed_key để tránh document MongoDB phình to
    channel_id = channel.id
    data = load_data()
    completed_key = f"completed_{channel_id}"
    if completed_key in data:
        del data[completed_key]
        save_data(data)

    await channel.delete()

    # LOG
    await send_log(
        bot_instance, "TICKET_CLOSE", f"Ticket Đóng — {ticket_name}",
        fields=[
            ("🎫 Ticket",      f"`{ticket_name}`",                                    True),
            ("🏷️ Loại",       ticket_type_label,                                     True),
            ("👤 Người tạo",  str(creator) if creator else f"`ID:{user_id}`",        True),
            ("🔒 Người đóng", str(closer) if closer else "Hệ thống",                 True),
            ("⏱️ Thời lượng", duration_str,                                          True),
            ("💬 Tin nhắn",   str(len(messages)),                                    True),
        ],
        user=closer,
    )



# ══════════════════════════════════════════
# ITEM SELECT
# ══════════════════════════════════════════
_ITEM_OPTIONS_BASIC = [
    discord.SelectOption(label="📦 Khác", value="other", description="Item / dịch vụ khác", emoji="📦"),
]
_SERVERS_WITH_ITEMS = {SERVER_DONUT, SERVER_KING}  # chỉ DonutSMP & KingMC có money/ske

class ItemSelect(Select):
    def __init__(self, trade_type: str, server_key: str = SERVER_DONUT):
        self.trade_type = trade_type
        self.server_key = server_key
        action  = "mua" if trade_type == "sell" else "bán"
        options = _ITEM_OPTIONS if server_key in _SERVERS_WITH_ITEMS else _ITEM_OPTIONS_BASIC
        super().__init__(placeholder=f"Bạn muốn {action} loại nào?", options=options, custom_id=f"item_select_{trade_type}_{server_key}")

    async def callback(self, interaction: discord.Interaction):
        try:
            item_key   = self.values[0]
            item_label = _ITEM_LABEL.get(item_key, item_key)
            await interaction.response.defer(ephemeral=True)
            await create_order_ticket(interaction, trade_type=self.trade_type, item_key=item_key, item_label=item_label, server_key=self.server_key)
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`")
            except Exception:
                pass

class ItemSelectView(View):
    def __init__(self, trade_type: str, server_key: str = SERVER_DONUT):
        super().__init__(timeout=60)
        self.add_item(ItemSelect(trade_type, server_key=server_key))


class _ItemPickSelect(Select):
    """Bước 1 (panel mới): chọn item → tạo ticket thẳng (không hỏi Mua/Bán)."""
    def __init__(self, server_key: str):
        self.server_key = server_key
        super().__init__(
            placeholder="Chọn loại item...",
            options=_ITEM_OPTIONS,  # Donut/King luôn full
            custom_id=f"item_pick_{server_key}",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            item_key   = self.values[0]
            item_label = _ITEM_LABEL.get(item_key, item_key)
            await interaction.response.defer(ephemeral=True)
            await create_order_ticket(
                interaction,
                trade_type="sell",  # mặc định: người dùng mua hàng
                item_key=item_key,
                item_label=item_label,
                server_key=self.server_key,
            )
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass


class _TradeModeSelect(Select):
    """Bước 2: chọn Mua hoặc Bán."""
    def __init__(self, server_key: str, item_key: str, item_label: str):
        self.server_key = server_key
        self.item_key   = item_key
        self.item_label = item_label
        super().__init__(
            placeholder="Mua hay Bán?",
            options=[
                discord.SelectOption(label="🛒 Mua", value="sell", description="Tôi muốn MUA item này"),
                discord.SelectOption(label="💸 Bán", value="buy",  description="Tôi muốn BÁN item này"),
            ],
            custom_id=f"trade_mode_{server_key}_{item_key}",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_order_ticket(
                interaction,
                trade_type=self.values[0],
                item_key=self.item_key,
                item_label=self.item_label,
                server_key=self.server_key,
            )
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass


class ItemPickView(View):
    """View bước 1: chọn item (cho Donut/KingMC từ panel mới)."""
    def __init__(self, server_key: str):
        super().__init__(timeout=60)
        self.add_item(_ItemPickSelect(server_key))

class ServerView(View):
    """Chọn server bằng nút thay vì Select menu."""
    def __init__(self, trade_type: str):
        super().__init__(timeout=60)
        self.trade_type = trade_type

    @discord.ui.button(label="🍩 DonutSMP", style=discord.ButtonStyle.green,  custom_id="server_btn_donut")
    async def btn_donut(self, interaction: discord.Interaction, button: Button):
        try:
            action = "mua" if self.trade_type == "sell" else "bán"
            await interaction.response.send_message(
                f"🍩 **DonutSMP — Bạn muốn {action} loại nào?**",
                view=ItemSelectView(trade_type=self.trade_type, server_key=SERVER_DONUT),
                ephemeral=True,
            )
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="👑 KingMC", style=discord.ButtonStyle.blurple, custom_id="server_btn_king")
    async def btn_king(self, interaction: discord.Interaction, button: Button):
        try:
            action = "mua" if self.trade_type == "sell" else "bán"
            await interaction.response.send_message(
                f"👑 **KingMC — Bạn muốn {action} loại nào?**",
                view=ItemSelectView(trade_type=self.trade_type, server_key=SERVER_KING),
                ephemeral=True,
            )
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="🎮 One MC", style=discord.ButtonStyle.green,  custom_id="server_btn_onemc")
    async def btn_onemc(self, interaction: discord.Interaction, button: Button):
        try:
            action = "mua" if self.trade_type == "sell" else "bán"
            await interaction.response.send_message(
                f"🎮 **One MC — Bạn muốn {action} loại nào?**",
                view=ItemSelectView(trade_type=self.trade_type, server_key=SERVER_ONEMC),
                ephemeral=True,
            )
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="🔥 Free Fire", style=discord.ButtonStyle.red, custom_id="server_btn_ff")
    async def btn_ff(self, interaction: discord.Interaction, button: Button):
        try:
            action = "mua" if self.trade_type == "sell" else "bán"
            await interaction.response.send_message(
                f"🔥 **Free Fire — Bạn muốn {action} loại nào?**",
                view=ItemSelectView(trade_type=self.trade_type, server_key=SERVER_FF),
                ephemeral=True,
            )
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

# Alias để không phá các chỗ khác đang dùng ServerSelectView
ServerSelectView = ServerView

class ServiceView(View):
    """Chọn dịch vụ bằng nút thay vì Select menu."""
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="🎁 Nhận Giveaway", style=discord.ButtonStyle.green,  custom_id="service_btn_giveaway")
    async def btn_giveaway(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_service_ticket(interaction, "giveaway")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="🆘 Hỗ Trợ", style=discord.ButtonStyle.blurple, custom_id="service_btn_support")
    async def btn_support(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_service_ticket(interaction, "support")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

# Alias
ServiceSelectView = ServiceView

# ══════════════════════════════════════════
# TICKET CREATION FUNCTIONS
# ══════════════════════════════════════════
async def create_order_ticket(interaction: discord.Interaction, trade_type: str, item_key: str = "other", item_label: str = "📦 Khác", seller_id: int | None = None, server_key: str = SERVER_DONUT):
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True)

        bot = interaction.client
        number     = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        server_info   = SERVER_TABLE.get(server_key, SERVER_TABLE[SERVER_DONUT])
        _key_slug     = {"money": "money", "skeleton": "skeleton", "other": "khac"}
        channel_name  = f"{server_info['channel_prefix']}-{_key_slug.get(item_key, 'ticket')}-{number}"

        color, type_label = (0x57F287, "🛒 MUA HÀNG") if trade_type == "sell" else (0xFEE75C, "💸 BÁN HÀNG")
        server_label = server_info["label"]

        # Đọc multi role IDs theo server_key
        _order_role_ids = get_ticket_role_ids(f"order_{server_key}")
        overwrites  = _build_ticket_overwrites_multi(guild, interaction.user, _order_role_ids)
        if _order_role_ids:
            ping_target = " ".join(
                f"<@{r}>" if r in ADMIN_IDS else f"<@&{r}>"
                for r in _order_role_ids
            )
        else:
            ping_target = f"<@{seller_id}>" if seller_id else f"<@&{get_cfg_support_role()}>"

        category = discord.utils.get(guild.categories, id=get_cfg_category())
        channel  = await guild.create_text_channel(
            name=channel_name, overwrites=overwrites, category=category,
            topic=f"{interaction.user.id}||{trade_type}|{item_key}|open|{server_key}"
        )

        embed = discord.Embed(
            title=f"{type_label}  •  {server_label}  •  {item_label}  •  #{number}",
            description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ xử lý giao dịch sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận",
            color=color, timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="🌐  Server",     value=server_label,             inline=True)
        embed.add_field(name="📦  Loại hàng",  value=item_label,               inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        await channel.send(f"{ping_target} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id, channel.guild.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,               True),
                ("🏷️ Loại",      type_label,                    True),
                ("🌐 Server",     server_label,                  True),
                ("📦 Item",       item_label,                    True),
                ("👤 Người tạo", _uname_plain(interaction.user),  True),
                ("🕐 Thời gian", created_at,                    True),
            ],
            user=interaction.user,
        )

    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`")
        except Exception:
            pass

async def create_service_ticket(interaction: discord.Interaction, service_key: str):
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở!", ephemeral=True)

        info   = SERVICE_TABLE[service_key]
        bot    = interaction.client
        number = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        # Ưu tiên role ID cụ thể, fallback sang role_group
        role_ids   = get_ticket_role_ids(service_key)
        overwrites = _build_ticket_overwrites_multi(guild, interaction.user, role_ids)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(name=f"ticket-{number}", overwrites=overwrites, category=category, topic=f"{interaction.user.id}||service|{service_key}|open")

        embed = discord.Embed(title=f"{info['type_label']}  •  #{number}", description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ hỗ trợ bạn sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận", color=info["color"], timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="📦  Dịch vụ",   value=info["label"],             inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        ping_str = " ".join(f"<@{r}>" if r in ADMIN_IDS else f"<@&{r}>" for r in role_ids) if role_ids else f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id, channel.guild.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`")
        except Exception:
            pass

async def create_accpre_ticket(interaction: discord.Interaction, trade_type: str):
    """Tạo ticket mua/bán tài khoản Pre."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True)

        bot        = interaction.client
        number     = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        color, type_label = (0xE74C3C, "🎭 MUA ACC PRE") if trade_type == "buy" else (0x9B59B6, "🎭 BÁN ACC PRE")
        channel_name = f"acc-{number}"

        # Đọc role ID cho acc_pre
        role_ids   = get_ticket_role_ids("acc_pre")
        overwrites = _build_ticket_overwrites_multi(guild, interaction.user, role_ids)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(
            name=channel_name, overwrites=overwrites, category=category,
            topic=f"{interaction.user.id}||{trade_type}|acc_pre|open|accpre"
        )

        embed = discord.Embed(
            title=f"{type_label}  •  #{number}",
            description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ xử lý sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận",
            color=color, timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="🎭  Loại",       value=type_label,               inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        ping_str = " ".join(f"<@{r}>" if r in ADMIN_IDS else f"<@&{r}>" for r in role_ids) if role_ids else f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id, channel.guild.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,               True),
                ("🏷️ Loại",      type_label,                    True),
                ("👤 Người tạo", _uname_plain(interaction.user),  True),
                ("🕐 Thời gian", created_at,                    True),
            ],
            user=interaction.user,
        )
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`")
        except Exception:
            pass


async def create_build_ticket(interaction: discord.Interaction, trade_type: str):
    """Tạo ticket mua/bán base Minecraft."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True)

        bot        = interaction.client
        number     = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        color, type_label = (0x1ABC9C, "🏗️ MUA BASE") if trade_type == "buy" else (0xF39C12, "🏗️ BÁN BASE")
        channel_name = f"build-{number}"

        role_ids   = get_ticket_role_ids("order_build")
        overwrites = _build_ticket_overwrites_multi(guild, interaction.user, role_ids)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(
            name=channel_name, overwrites=overwrites, category=category,
            topic=f"{interaction.user.id}||{trade_type}|build|open|build"
        )

        embed = discord.Embed(
            title=f"{type_label}  •  #{number}",
            description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ xử lý sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận",
            color=color, timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="🏗️  Loại",       value=type_label,               inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        ping_str = " ".join(f"<@{r}>" if r in ADMIN_IDS else f"<@&{r}>" for r in role_ids) if role_ids else f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id, channel.guild.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,               True),
                ("🏷️ Loại",      type_label,                    True),
                ("👤 Người tạo", _uname_plain(interaction.user),  True),
                ("🕐 Thời gian", created_at,                    True),
            ],
            user=interaction.user,
        )
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`")
        except Exception:
            pass

async def create_ruby_ticket(interaction: discord.Interaction, option_label: str):
    """Tạo ticket Mua Hàng — sau khi user chọn 1 dịch vụ từ danh sách do admin
    cấu hình thủ công (.rubyoption add), xem _RubyShopOptionSelect."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True)

        bot        = interaction.client
        number     = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        channel_name = f"muahang-{number}"

        role_ids   = get_ticket_role_ids("rubyshop")
        overwrites = _build_ticket_overwrites_multi(guild, interaction.user, role_ids)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(
            name=channel_name, overwrites=overwrites, category=category,
            topic=f"{interaction.user.id}||service|rubyshop|open|rubyshop",
        )

        embed = discord.Embed(
            title=f"🛒 TICKET MUA HÀNG  •  #{number}",
            description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ hỗ trợ bạn sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận",
            color=0xE91E8C, timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="👤  Người dùng",         value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",          value=created_at,               inline=True)
        embed.add_field(name="📦  Dịch vụ cần hỗ trợ", value=option_label,             inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        ping_str = " ".join(f"<@{r}>" if r in ADMIN_IDS else f"<@&{r}>" for r in role_ids) if role_ids else f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id, channel.guild.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,                True),
                ("📦 Dịch vụ",    option_label,                   True),
                ("👤 Người tạo", _uname_plain(interaction.user),  True),
                ("🕐 Thời gian", created_at,                     True),
            ],
            user=interaction.user, guild_id=guild.id,
        )
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`")
        except Exception: pass


async def create_middleman_ticket(interaction: discord.Interaction, partner_id: str):
    """Tạo ticket Giao Dịch Trung Gian — sau khi user nhấn 'Tạo giao dịch' trên panel
    #🤝・middleman và nhập ID tài khoản muốn giao dịch (xem MiddlemanAccountModal).
    Hoạt động như 1 ticket mua hàng bình thường: tạo kênh riêng tư + ping staff,
    NGOẠI TRỪ luôn ping thêm admin TuyTam (ADMIN_TUYTAM_ID) vì đây là giao dịch cần
    admin trực tiếp đứng ra làm trung gian."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True)

        bot        = interaction.client
        number     = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        channel_name = f"mm-{number}"

        role_ids   = get_ticket_role_ids("middleman")
        overwrites = _build_ticket_overwrites_multi(guild, interaction.user, role_ids)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(
            name=channel_name, overwrites=overwrites, category=category,
            topic=f"{interaction.user.id}||service|middleman|open|middleman",
        )

        embed = discord.Embed(
            title=f"🤝 GIAO DỊCH TRUNG GIAN  •  #{number}",
            description=f"Xin chào {interaction.user.mention}! 👋\nAdmin sẽ hỗ trợ làm trung gian giao dịch sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận",
            color=0x57F287, timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="👤  Người tạo",              value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",               value=created_at,               inline=True)
        embed.add_field(name="🎯  ID tài khoản giao dịch",  value=f"`{partner_id}`",        inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Giao Dịch Trung Gian", icon_url=guild.icon.url if guild.icon else None)

        # Ping role được gán (nếu có) + LUÔN ping thêm admin TuyTam
        ping_ids = list(role_ids)
        if ADMIN_TUYTAM_ID and ADMIN_TUYTAM_ID not in ping_ids:
            ping_ids.append(ADMIN_TUYTAM_ID)
        if ping_ids:
            ping_str = " ".join(f"<@{r}>" if r in ADMIN_IDS else f"<@&{r}>" for r in ping_ids)
        else:
            ping_str = f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id, channel.guild.id)
        await interaction.followup.send(f"✅ Ticket giao dịch trung gian đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",              channel.mention,               True),
                ("🎯 Tài khoản GD",      f"`{partner_id}`",             True),
                ("👤 Người tạo",         _uname_plain(interaction.user), True),
                ("🕐 Thời gian",         created_at,                    True),
            ],
            user=interaction.user, guild_id=guild.id,
        )
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`", ephemeral=True)
        except Exception: pass


async def create_direct_order_ticket(interaction: discord.Interaction, server_key: str):
    """Tạo ticket mua/bán thẳng không qua chọn item (OneMC, FreeFire)."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True)
        bot        = interaction.client
        number     = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        server_info  = SERVER_TABLE.get(server_key, {"label": server_key, "color": 0x5865F2, "channel_prefix": server_key})
        server_label = server_info["label"]
        prefix       = server_info["channel_prefix"]
        color        = server_info["color"]
        channel_name = f"{prefix}-{number}"

        role_ids   = get_ticket_role_ids(f"order_{server_key}")
        overwrites = _build_ticket_overwrites_multi(guild, interaction.user, role_ids)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(
            name=channel_name, overwrites=overwrites, category=category,
            topic=f"{interaction.user.id}||order|other|open|{server_key}"
        )

        embed = discord.Embed(
            title=f"🎫 Ticket {server_label}  •  #{number}",
            description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ xử lý sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận",
            color=color, timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="🖥️  Server",     value=server_label,             inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        if role_ids:
            ping = " ".join(f"<@{r}>" if r in ADMIN_IDS else f"<@&{r}>" for r in role_ids)
        else:
            ping = f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id, channel.guild.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,         True),
                ("🖥️ Server",    server_label,             True),
                ("👤 Người tạo", _uname_plain(interaction.user), True),
                ("🕐 Thời gian", created_at,               True),
            ],
            user=interaction.user,
        )
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`")
        except Exception: pass


async def create_listing_ticket(interaction: discord.Interaction, ign: str, price: str, cape: str,
                                 note: str, source_link: str | None):
    """Tạo ticket mua khi khách bấm nút 🛒 Mua trên 1 listing sản phẩm (cogs/listings.py).
    source_link: mention của thread (nếu listing đăng trong kênh Forum) hoặc jump_url của tin nhắn
    listing gốc (nếu đăng trong kênh Text thường) — None nếu không xác định được."""
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True)

        bot        = interaction.client
        number     = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        channel_name = f"mua-{number}"

        role_ids   = list(dict.fromkeys(get_ticket_role_ids("listing") + get_ticket_role_ids("listing_manage")))
        overwrites = _build_ticket_overwrites_multi(guild, interaction.user, role_ids)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(
            name=channel_name, overwrites=overwrites, category=category,
            topic=f"{interaction.user.id}||buy|listing|open|listing",
        )

        embed = discord.Embed(
            title=f"🛒 MUA SẢN PHẨM  •  #{number}",
            description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ xử lý sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận",
            color=0x2ECC71, timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="👤  Người mua",     value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",      value=created_at,               inline=True)
        embed.add_field(name="📦  Sản phẩm",       value=ign or "?",               inline=True)
        embed.add_field(name="💰  Giá niêm yết",   value=price or "?",             inline=True)
        if cape:
            embed.add_field(name="👕  Cape", value=cape, inline=True)
        if note:
            embed.add_field(name="📝  Ghi chú", value=note, inline=False)
        if source_link:
            embed.add_field(name="🔗  Listing gốc", value=source_link, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        ping_str = " ".join(f"<@{r}>" if r in ADMIN_IDS else f"<@&{r}>" for r in role_ids) if role_ids else f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id, channel.guild.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,               True),
                ("📦 Sản phẩm",   ign or "?",                    True),
                ("👤 Người tạo", _uname_plain(interaction.user),  True),
                ("🕐 Thời gian", created_at,                    True),
            ],
            user=interaction.user, guild_id=guild.id,
        )
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`", ephemeral=True)
        except Exception: pass


async def create_direct_service_ticket(interaction: discord.Interaction, service_key: str):
    """Tạo ticket dịch vụ thẳng (Giveaway, Hỗ Trợ) không qua popup."""
    await create_service_ticket(interaction, service_key)


# ══════════════════════════════════════════
# PANEL VIEW
# ══════════════════════════════════════════
class BuildView(View):
    """Popup chọn Mua Base / Bán Base sau khi nhấn nút Build."""
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="🛒 Mua Base", style=discord.ButtonStyle.green,  custom_id="build_buy")
    async def buy_build(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_build_ticket(interaction, trade_type="buy")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="💸 Bán Base", style=discord.ButtonStyle.blurple, custom_id="build_sell")
    async def sell_build(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_build_ticket(interaction, trade_type="sell")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass


class AccPreView(View):
    """Hiện sau khi nhấn nút Acc Pre — chọn Mua hoặc Bán."""
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="🛒 Mua Acc Pre", style=discord.ButtonStyle.green,  custom_id="accpre_buy")
    async def buy_acc(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_accpre_ticket(interaction, trade_type="buy")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="💸 Bán Acc Pre", style=discord.ButtonStyle.blurple, custom_id="accpre_sell")
    async def sell_acc(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_accpre_ticket(interaction, trade_type="sell")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass


class _RubyShopOptionSelect(Select):
    """Bước chọn dịch vụ trước khi tạo ticket Mua Hàng — options đến từ danh
    sách admin tự thêm bằng `.rubyoption add <tên>` (core/data.py:
    get_ruby_shop_options), KHÔNG hardcode trong code."""
    def __init__(self, options: list[str]):
        self._labels = options
        opts = [
            discord.SelectOption(label=label[:100], value=str(i))
            for i, label in enumerate(options)
        ]
        super().__init__(placeholder="Chọn dịch vụ cần hỗ trợ...", options=opts, custom_id="rubyshop_option_select")

    async def callback(self, interaction: discord.Interaction):
        try:
            idx = int(self.values[0])
            label = self._labels[idx] if 0 <= idx < len(self._labels) else self.values[0]
            await interaction.response.defer(ephemeral=True)
            await create_ruby_ticket(interaction, label)
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass


class RubyShopOptionView(View):
    """View bước 1 khi bấm nút 🛒 Ticket Mua Hàng trên panel — chọn dịch vụ cần hỗ trợ
    trước khi ticket thật sự được tạo."""
    def __init__(self, options: list[str]):
        super().__init__(timeout=60)
        self.add_item(_RubyShopOptionSelect(options))


# ══════════════════════════════════════════
# MIDDLEMAN (GIAO DỊCH TRUNG GIAN) — panel riêng, xem build_middleman_panel_embed
# ══════════════════════════════════════════
class MiddlemanAccountModal(Modal, title="🤝 Tạo Giao Dịch Trung Gian"):
    """Modal hỏi ID tài khoản muốn giao dịch cùng — bước duy nhất trước khi tạo
    ticket, sau đó hoạt động y hệt 1 ticket mua hàng bình thường (xem
    create_middleman_ticket)."""
    partner_input = TextInput(
        label="ID tài khoản muốn giao dịch",
        placeholder="Nhập ID Discord hoặc username của đối tác giao dịch...",
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_middleman_ticket(interaction, self.partner_input.value.strip())
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass


class MiddlemanPanelView(View):
    """Panel PERSISTENT riêng cho Giao Dịch Trung Gian — chỉ 1 nút 'Tạo giao dịch',
    gửi bằng lệnh `.mmpanel` (xem TicketCog.mmpanel_cmd). Cần add_view() lúc
    on_ready (bot.py) để nút vẫn hoạt động sau khi bot restart."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Tạo giao dịch", emoji="➕", style=discord.ButtonStyle.green, custom_id="panel_middleman_create")
    async def create_transaction(self, interaction: discord.Interaction, button: Button):
        try:
            if await has_ticket(interaction.guild, interaction.user):
                return await interaction.response.send_message(
                    "❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True
                )
            await interaction.response.send_modal(MiddlemanAccountModal())
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass


# ══════════════════════════════════════════
# PANEL BUTTONS — cấu hình bật/tắt theo từng guild
# ══════════════════════════════════════════
# key → (label, style, custom_id, row) — nguồn duy nhất định nghĩa 7 nút của panel chính.
PANEL_BUTTON_DEFS = {
    "donut":    ("🍩 DonutSMP",       discord.ButtonStyle.green,   "panel_donut",    0),
    "kingmc":   ("👑 KingMC",          discord.ButtonStyle.blurple, "panel_kingmc",   0),
    "ff":       ("🔥 Free Fire",       discord.ButtonStyle.red,     "panel_ff",       1),
    "accpre":   ("🎭 Acc Pre",         discord.ButtonStyle.blurple, "panel_accpre",   2),
    "build":    ("🏗️ Build",          discord.ButtonStyle.grey,    "panel_build",    2),
    "rubyshop": ("🛒 Ticket Mua Hàng", discord.ButtonStyle.grey,    "panel_rubyshop", 2),
    "giveaway": ("🎁 Nhận Giveaway",   discord.ButtonStyle.green,   "panel_giveaway", 3),
    "support":  ("🆘 Hỗ Trợ",          discord.ButtonStyle.blurple, "panel_support",  3),
}
PANEL_BUTTON_LABELS = {k: v[0] for k, v in PANEL_BUTTON_DEFS.items()}

def get_panel_buttons_cfg() -> dict:
    """Trả về {key: True/False} cho guild hiện tại (context đã được set bởi caller).
    Mặc định BẬT nếu chưa cấu hình gì (không phá panel cũ khi mới nâng cấp bot)."""
    cfg = load_data().get("cfg_panel_buttons", {})
    return {key: cfg.get(key, True) for key in PANEL_BUTTON_DEFS}

def set_panel_button_enabled(key: str, enabled: bool) -> None:
    data = load_data()
    cfg = data.setdefault("cfg_panel_buttons", {})
    cfg[key] = enabled
    save_data(data)


class TicketPanel(View):
    """Panel chính — nút được dựng ĐỘNG theo cấu hình bật/tắt riêng của từng guild.

    guild_id=None  → dựng ĐỦ cả 7 nút (dùng lúc bot khởi động để đăng ký handler cho
                      mọi custom_id có thể tồn tại trong các message panel cũ — xem bot.py
                      on_ready: bot.add_view(TicketPanel())). KHÔNG liên quan tới việc nút
                      có thực sự hiển thị trong 1 message cụ thể hay không.
    guild_id=<id>  → chỉ dựng các nút đang BẬT của guild đó (dùng khi gửi panel thật qua
                      lệnh .panel).
    """
    def __init__(self, guild_id: int | None = None):
        super().__init__(timeout=None)
        cfg = get_panel_buttons_cfg() if guild_id is not None else {k: True for k in PANEL_BUTTON_DEFS}

        for key, (label, style, custom_id, row) in PANEL_BUTTON_DEFS.items():
            if not cfg.get(key, True):
                continue
            btn = Button(label=label, style=style, custom_id=custom_id, row=row)
            btn.callback = self._make_callback(key)
            self.add_item(btn)

    def _make_callback(self, key: str):
        handlers = {
            "donut":    self._h_donut,
            "kingmc":   self._h_kingmc,
            "ff":       self._h_ff,
            "accpre":   self._h_accpre,
            "build":    self._h_build,
            "rubyshop": self._h_rubyshop,
            "giveaway": self._h_giveaway,
            "support":  self._h_support,
        }
        return handlers[key]

    async def _h_donut(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message(
                "🍩 **DonutSMP — Chọn loại item:**",
                view=ItemPickView(SERVER_DONUT), ephemeral=True,
            )
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    async def _h_kingmc(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message(
                "👑 **KingMC — Chọn loại item:**",
                view=ItemPickView(SERVER_KING), ephemeral=True,
            )
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    async def _h_ff(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_direct_order_ticket(interaction, SERVER_FF)
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    async def _h_accpre(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_accpre_ticket(interaction, trade_type="buy")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    async def _h_build(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_build_ticket(interaction, trade_type="buy")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    async def _h_rubyshop(self, interaction: discord.Interaction):
        try:
            options = get_ruby_shop_options()
            if not options:
                return await interaction.response.send_message(
                    "❌ Ticket Mua Hàng hiện chưa có dịch vụ nào được thiết lập. Vui lòng liên hệ staff "
                    "hoặc admin thêm bằng `.rubyoption add <tên dịch vụ>`.",
                    ephemeral=True,
                )
            await interaction.response.send_message(
                "🛒 **Ticket Mua Hàng — Bạn cần hỗ trợ về dịch vụ gì?**",
                view=RubyShopOptionView(options), ephemeral=True,
            )
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    async def _h_giveaway(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_direct_service_ticket(interaction, "giveaway")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    async def _h_support(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_direct_service_ticket(interaction, "support")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass


class PanelButtonToggleView(View):
    """UI cho lệnh .panelbuttons — 1 nút bấm / loại ticket, bấm để bật/tắt.
    Không cần persistent (timeout mặc định), admin dùng xong ngay trong phiên."""
    def __init__(self, ctx):
        super().__init__(timeout=180)
        self.ctx = ctx
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        cfg = get_panel_buttons_cfg()
        for i, (key, (label, _style, _cid, row)) in enumerate(PANEL_BUTTON_DEFS.items()):
            enabled = cfg.get(key, True)
            btn = Button(
                label=f"{'🟢' if enabled else '🔴'} {label}",
                style=discord.ButtonStyle.green if enabled else discord.ButtonStyle.grey,
                custom_id=f"toggle_panelbtn_{key}",
                row=row,
            )
            btn.callback = self._make_toggle_callback(key)
            self.add_item(btn)

    def _make_toggle_callback(self, key: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id not in ADMIN_IDS:
                return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
            cfg = get_panel_buttons_cfg()
            new_state = not cfg.get(key, True)
            set_panel_button_enabled(key, new_state)
            self._build_buttons()
            await interaction.response.edit_message(view=self)
            await send_log(
                self.ctx.bot, "SETTINGS", f"Panel button {'BẬT' if new_state else 'TẮT'}: {PANEL_BUTTON_LABELS[key]}",
                fields=[("👤 Admin", str(interaction.user), True)],
                user=interaction.user,
                guild_id=interaction.guild_id,
            )
        return callback


# ══════════════════════════════════════════
# TICKET BUTTONS
# ══════════════════════════════════════════
class TicketButtons(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Đóng ticket", emoji="🔒", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Không có quyền.", ephemeral=True)
        await interaction.response.defer()
        await _close_ticket(interaction.channel, interaction.client, closer=interaction.user)

    @discord.ui.button(label="Hoàn thành đơn", emoji="✅", style=discord.ButtonStyle.green, custom_id="complete_order")
    async def complete_order(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin mới có quyền hoàn thành đơn.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(
            f"⚠️ {interaction.user.mention} — hãy dùng lệnh `.done <số tiền>` để hoàn thành đơn.\nVí dụ: `.done 50k`, `.done 1tr5`, `.done 200000`",
            delete_after=20
        )

# ══════════════════════════════════════════
# COG
# ══════════════════════════════════════════
class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._relay_webhook_cache: dict[int, discord.Webhook] = {}

    # ── Admin message relay (xoá tin admin gửi trong ticket, gửi lại y chang qua webhook) ──
    async def _get_relay_webhook(self, channel: discord.TextChannel) -> discord.Webhook | None:
        wh = self._relay_webhook_cache.get(channel.id)
        if wh:
            return wh
        try:
            hooks = await channel.webhooks()
            wh = discord.utils.get(hooks, name="TuyTam-Relay")
            if not wh:
                wh = await channel.create_webhook(name="TuyTam-Relay", reason="Ticket admin message relay")
            self._relay_webhook_cache[channel.id] = wh
            return wh
        except Exception as _e:
            log.debug(f"[SILENT] {_e}")
            return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bỏ qua tin của bot / webhook (kể cả webhook relay của chính bot)
        if message.author.bot or message.webhook_id:
            return
        if message.author.id not in ADMIN_IDS:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        # Chỉ áp dụng trong kênh ticket (topic có dạng user_id||...)
        if not (message.channel.topic and "|" in message.channel.topic):
            return
        # FIX: listener này chạy Task riêng do discord.py tự dispatch, không thừa hưởng
        # guild context set ở on_message chính (bot.py). Thiếu dòng này khiến
        # load_data() bên dưới luôn đọc default (True) thay vì cấu hình thật của guild.
        if message.guild:
            set_current_guild(message.guild.id)
        # AUTH_GATE — server chưa được admin ủy quyền qua .as → bỏ qua (xem bot.py + AI_CONTEXT.md)
        if message.guild:
            from core.data import is_guild_authorized
            if not is_guild_authorized(message.guild.id):
                return
        # Bỏ qua nếu tính năng đang bị tắt qua .st
        if not load_data().get("cfg_ticket_relay", True):
            return
        # Bỏ qua nếu đây là command (.close, .done, ...)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        if not message.content and not message.attachments:
            return

        webhook = await self._get_relay_webhook(message.channel)
        if not webhook:
            return  # Không tạo được webhook (thiếu quyền Manage Webhooks...) → giữ nguyên tin gốc

        files = []
        try:
            for att in message.attachments:
                files.append(await att.to_file())
        except Exception as _e:
            log.debug(f"[SILENT] {_e}")

        # Tên webhook cố định "Ruby bot", avatar luôn dùng avatar của chính bot
        relay_name   = "Ruby bot"
        relay_avatar = self.bot.user.display_avatar.url

        try:
            await webhook.send(
                content=message.content or None,
                username=relay_name,
                avatar_url=relay_avatar,
                files=files,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
            )
        except Exception as _e:
            log.debug(f"[SILENT] relay send fail: {_e}")
            return

        try:
            await message.delete()
        except Exception as _e:
            log.debug(f"[SILENT] {_e}")

    @commands.command()
    async def panel(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return
        await ctx.send(embed=build_panel_embed(ctx.guild), view=TicketPanel(ctx.guild.id))
        await ctx.message.delete()

    # (Lệnh `.transcriptchannel` đã gộp vào `.st` — nút "📄 Transcript Channel", xem cogs/admin_views.py: SettingsView)

    @commands.command(name="mmpanel", aliases=["middlemanpanel"])
    async def mmpanel_cmd(self, ctx):
        """Gửi panel Giao Dịch Trung Gian (AutoMM) vào kênh hiện tại."""
        if ctx.author.id not in ADMIN_IDS: return
        await ctx.send(embed=build_middleman_panel_embed(ctx.guild), view=MiddlemanPanelView())
        await ctx.message.delete()

    @commands.command(name="panelbuttons", aliases=["panelbtn", "ticketbuttons"])
    async def panelbuttons_cmd(self, ctx):
        """Bật/tắt từng nút của panel ticket — lưu riêng theo server (guild)."""
        if ctx.author.id not in ADMIN_IDS: return
        embed = discord.Embed(
            title="⚙️ Bật/Tắt Nút Panel Ticket",
            description=(
                "Bấm vào từng nút bên dưới để bật (🟢) hoặc tắt (🔴).\n"
                "Sau khi đổi, chạy lại `.panel` để gửi panel mới với các nút đã cập nhật "
                "(panel đã gửi trước đó sẽ **không** tự đổi)."
            ),
            color=0x5865F2,
        )
        await ctx.send(embed=embed, view=PanelButtonToggleView(ctx))

    @commands.command()
    async def setpanel(self, ctx, channel: discord.TextChannel = None):
        if ctx.author.id not in ADMIN_IDS: return
        if channel is None: return await ctx.reply("❌ Thiếu kênh! Ví dụ: `.setpanel #shop`")
        save_panel_channel_id(channel.id)
        embed = discord.Embed(title="⚙️  Đã Cài Đặt Panel Channel", description=f"Bot sẽ gửi panel ticket vào {channel.mention}.", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.set_footer(text=f"Cài bởi {ctx.author}")
        await ctx.reply(embed=embed)

    @commands.command()
    async def close(self, ctx):
        if not is_staff_member(ctx.author): return await ctx.reply("❌ Bạn không có quyền.")
        if not (ctx.channel.topic and "|" in ctx.channel.topic): return await ctx.reply("❌ Đây không phải kênh ticket.")
        await _close_ticket(ctx.channel, self.bot, closer=ctx.author)

    @commands.command(name="done")
    async def done_cmd(self, ctx, *, args: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền hoàn thành đơn.")
        if not args:
            return await ctx.reply(
                "❌ Thiếu thông tin!\n"
                "Trong ticket: `.done 50k`\n"
                "Ngoài ticket: `.done @user 50k`"
            )

        # Parse buyer + amount
        buyer = None
        amount_str = args.strip()
        if ctx.message.mentions:
            buyer = ctx.message.mentions[0]
            # Bỏ mọi dạng mention khỏi chuỗi để lấy amount
            amount_str = amount_str.replace(buyer.mention, "").replace(f"<@!{buyer.id}>", "").replace(f"<@{buyer.id}>", "").strip()

        is_ticket = bool(ctx.channel.topic and "|" in ctx.channel.topic)

        if not buyer:
            if not is_ticket:
                return await ctx.reply("❌ Ngoài kênh ticket, cần mention user: `.done @user 50k`")
            # Đọc buyer từ topic
            parts = ctx.channel.topic.split("|")
            try:
                user_id = int(parts[0]) if parts[0].isdigit() else None
            except Exception:
                user_id = None
            if not user_id:
                return await ctx.reply("❌ Không đọc được thông tin buyer từ ticket.")
            buyer = ctx.guild.get_member(user_id)
            if not buyer:
                return await ctx.reply(f"❌ Không tìm thấy buyer (ID: `{user_id}`).")

        if not amount_str:
            return await ctx.reply("❌ Thiếu số tiền! Ví dụ: `.done 50k`, `.done @user 1tr5`")

        amount = parse_amount(amount_str)
        if amount is None or amount <= 0:
            return await ctx.reply(f"❌ Số tiền `{amount_str}` không hợp lệ!")

        # Xác định server_key / trade_type — ÁP DỤNG CHO MỌI TRƯỜNG HỢP trong ticket
        # (kể cả khi có @mention buyer tường minh). FIX: trước đây chỉ check khi KHÔNG
        # có mention (`is_ticket and not ctx.message.mentions`) — nghĩa là gõ
        # `.done @buyer 50k` NGAY TRONG 1 ticket hỗ trợ/dịch vụ vẫn lọt qua được, bỏ qua
        # hẳn việc kiểm tra "có phải ticket bán hàng không". Giờ chỉ cần đang ở TRONG
        # ticket là bị chặn nếu không phải loại sell/buy, không quan tâm có mention hay
        # không. Dùng `.done @user 50k` NGOÀI ticket (is_ticket=False) vẫn không đổi.
        server_key = None
        trade_type = None
        if is_ticket:
            parts = ctx.channel.topic.split("|")
            trade_type = parts[2] if len(parts) > 2 else None
            server_key = parts[5] if len(parts) > 5 else None
            if trade_type not in ("sell", "buy"):
                return await ctx.reply("ℹ️ Ticket dịch vụ / hỗ trợ không tính vào đơn mua hàng.")

        data = load_data()
        if is_ticket and not ctx.message.mentions:
            completed_key = f"completed_{ctx.channel.id}"
        else:
            completed_key = f"completed_msg_{ctx.message.id}"
        if data.get(completed_key):
            total = get_user_total_spent(buyer.id)
            return await ctx.reply(f"⚠️ Đơn này đã hoàn thành rồi!\nBuyer: {buyer.mention} — tổng: **{fmt_amount(total)}**")

        data[completed_key] = True
        save_data(data)

        # Cộng tiền theo server (nếu có server_key) VÀ vào tổng chung
        if server_key:
            totals     = add_user_spent_server(buyer.id, amount, server_key)
            new_total  = totals["total"]
            srv_total  = totals["server_total"]
        else:
            new_total = add_user_spent(buyer.id, amount)
            srv_total = None

        # Label server để hiển thị
        SERVER_LABELS = {
            "donut":  "🍩 DonutSMP",
            "kingmc": "👑 KingMC",
            "onemc":  "🎮 One MC",
            "ff":     "🔥 Free Fire",
            "accpre": "🎭 Acc Pre",
            "listing": "🛒 Sản phẩm",
        }
        server_label = SERVER_LABELS.get(server_key, None)

        # Lưu lịch sử đơn
        try:
            opened_at = ctx.channel.created_at.isoformat()
        except Exception:
            opened_at = datetime.now(timezone.utc).isoformat()

        save_ticket_record({
            "ticket_name": ctx.channel.name if is_ticket else f"manual-done-{ctx.message.id}",
            "user_id":     buyer.id,
            "username":    _uname_plain(buyer),
            "amount":      amount,
            "server_key":  server_key or "unknown",
            "opened_at":   opened_at,
            "closed_at":   datetime.now(timezone.utc).isoformat(),
            "staff":       _uname_plain(ctx.author),
            "staff_id":    ctx.author.id,
        })

        from cogs.admin_views import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(ctx.guild, buyer, new_total)

        # Tặng role "Đã Mua Hàng" — đọc theo guild qua get_cfg_done_role() (per-guild,
        # cấu hình qua `.st` → nút "🎖️ Done Role"), không còn hardcode ID chung cho mọi
        # guild như trước (xem CHANGELOG).
        done_role = ctx.guild.get_role(get_cfg_done_role())
        done_role_given = False
        if done_role:
            try:
                if done_role not in buyer.roles:
                    await buyer.add_roles(done_role, reason=f"Hoàn thành đơn — xác nhận bởi {_uname_plain(ctx.author)}")
                done_role_given = True
            except Exception as _e:
                log.warning(f"[DONE] Không thể give role {get_cfg_done_role()} cho {buyer}: {_e}")

        embed = discord.Embed(title="✅ Hoàn Thành Đơn", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Buyer",       value=buyer.mention,               inline=True)
        embed.add_field(name="💵 Đơn này",     value=f"**{fmt_amount(amount)}**", inline=True)
        embed.add_field(name="💰 Tổng chung",  value=f"**{fmt_amount(new_total)}**", inline=True)

        if server_label and srv_total is not None:
            embed.add_field(
                name=f"📊 Tổng {server_label}",
                value=f"**{fmt_amount(srv_total)}**",
                inline=True,
            )

        if role_cfg:
            role_obj = ctx.guild.get_role(role_cfg.get("role_id", 0))
            embed.add_field(
                name="🏆 Role hiện tại",
                value=role_obj.mention if role_obj else f"**{role_cfg.get('label','?')}**",
                inline=False,
            )

        if done_role:
            embed.add_field(
                name="🎖️ Role tặng",
                value=f"{done_role.mention} {'✅' if done_role_given else '*(đã có sẵn)*'}",
                inline=False,
            )
        else:
            # FIX: trước đây hardcode số ID cũ (1515393691206811901) trong text lỗi —
            # sót lại từ trước khi DONE_ROLE_ID được chuyển thành cfg_done_role per-guild
            # (xem CHANGELOG). Guild khác cấu hình role KHÁC thì lỗi vẫn hiện đúng số ID
            # đó, không liên quan gì đến role họ thật sự đã đặt — rất khó hiểu. Giờ hiện
            # đúng ID đang cấu hình cho guild này.
            embed.add_field(name="🎖️ Role tặng", value=f"⚠️ Chưa cài / role `{get_cfg_done_role()}` không tồn tại — dùng `.st` → nút \"🎖️ Done Role\" để cấu hình", inline=False)

        embed.set_footer(text=f"Xác nhận bởi {_uname_plain(ctx.author)}")

        from cogs.shop_orders import build_payment_qr_embed, send_to_queue
        qr_embed, qr_ref_code, qr_note = build_payment_qr_embed(
            ctx.author, buyer, amount, ctx.guild.id, ctx.channel.id
        )
        # FIX: trước đây LUÔN gửi embed "Hoàn Thành Đơn" rồi mới gửi thêm QR bên dưới —
        # 2 embed liên tiếp, thừa. Giờ nếu ctx.author (người gõ .done) đã `.shopbank` —
        # tức tạo được QR — gửi THẲNG QR thay cho embed Hoàn Thành Đơn, vì QR mới là thứ
        # khách cần thấy để trả tiền. Tổng chi tiêu/role tặng ở trên vẫn được LƯU/GẮN
        # bình thường, chỉ không hiện lại trong tin nhắn này — xem qua `.bxh`/`.st` nếu
        # cần lại. Chưa `.shopbank` (hoặc tính năng đang tắt) thì giữ hành vi CŨ nguyên vẹn.
        if qr_embed:
            await ctx.reply(embed=qr_embed)
        else:
            await ctx.reply(embed=embed)
            if qr_note:
                # Seller chưa `.shopbank` → không có QR nên không có webhook nào tự xác
                # nhận được cho đơn này — giữ hành vi CŨ (gửi hàng đợi ngay), staff tự
                # bấm "Hoàn thành" tay như trước khi có QR, tránh đơn "biến mất" khỏi
                # hàng đợi.
                await ctx.send(qr_note)
                await send_to_queue(self.bot, ctx.author, buyer, ctx.channel, amount, "")

        log_fields = [
            ("👤 Buyer",        _uname_plain(buyer),  True),
            ("💵 Đơn này",      fmt_amount(amount),   True),
            ("💰 Tổng chung",   fmt_amount(new_total), True),
        ]
        if server_label and srv_total is not None:
            log_fields.append((f"📊 {server_label}", fmt_amount(srv_total), True))
        log_fields += [
            ("🎫 Kênh",        ctx.channel.mention, True),
            ("✍️ Xác nhận bởi", _uname_plain(ctx.author),  True),
        ]
        await send_log(
            ctx.bot, "TICKET_DONE", f"Hoàn Thành Đơn — {ctx.channel.name}",
            fields=log_fields,
            user=ctx.author,
            guild_id=ctx.guild.id,
        )

    # ── .undone — trừ tiền đã tiêu khi lỡ .done nhầm (nhầm người / nhầm số tiền) ──
    @commands.command(name="undone", aliases=["donesub", "trutien"])
    async def undone_cmd(self, ctx, *, args: str = None):
        """Trừ tiền đã tiêu của user — dùng khi lỡ `.done` nhầm (nhầm người, nhầm số tiền).
        Trong ticket: `.undone 50k` (đọc buyer từ topic, tự mở lại được `.done` trong kênh này).
        Ngoài ticket: `.undone @user 50k`"""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền chỉnh sửa đơn.")
        if not args:
            return await ctx.reply(
                "❌ Thiếu thông tin!\n"
                "Trong ticket: `.undone 50k`\n"
                "Ngoài ticket: `.undone @user 50k`"
            )

        # Parse buyer + amount — logic giống hệt .done, để hành vi nhất quán/dễ nhớ
        buyer = None
        amount_str = args.strip()
        if ctx.message.mentions:
            buyer = ctx.message.mentions[0]
            amount_str = amount_str.replace(buyer.mention, "").replace(f"<@!{buyer.id}>", "").replace(f"<@{buyer.id}>", "").strip()

        is_ticket = bool(ctx.channel.topic and "|" in ctx.channel.topic)

        if not buyer:
            if not is_ticket:
                return await ctx.reply("❌ Ngoài kênh ticket, cần mention user: `.undone @user 50k`")
            parts = ctx.channel.topic.split("|")
            try:
                user_id = int(parts[0]) if parts[0].isdigit() else None
            except Exception:
                user_id = None
            if not user_id:
                return await ctx.reply("❌ Không đọc được thông tin buyer từ ticket.")
            buyer = ctx.guild.get_member(user_id)
            if not buyer:
                return await ctx.reply(f"❌ Không tìm thấy buyer (ID: `{user_id}`).")

        if not amount_str:
            return await ctx.reply("❌ Thiếu số tiền! Ví dụ: `.undone 50k`, `.undone @user 1tr5`")

        amount = parse_amount(amount_str)
        if amount is None or amount <= 0:
            return await ctx.reply(f"❌ Số tiền `{amount_str}` không hợp lệ!")

        # server_key — chỉ xác định khi trong ticket và không mention, giống .done
        server_key = None
        if is_ticket and not ctx.message.mentions:
            parts = ctx.channel.topic.split("|")
            trade_type = parts[2] if len(parts) > 2 else None
            server_key = parts[5] if len(parts) > 5 else None
            if trade_type not in ("sell", "buy"):
                return await ctx.reply("ℹ️ Ticket dịch vụ / hỗ trợ không tính vào đơn mua hàng — không có gì để trừ.")

        old_total = get_user_total_spent(buyer.id)

        if server_key:
            totals    = subtract_user_spent_server(buyer.id, amount, server_key)
            new_total = totals["total"]
            srv_total = totals["server_total"]
        else:
            new_total = subtract_user_spent(buyer.id, amount)
            srv_total = None

        # Số thực trừ được có thể < amount yêu cầu nếu tổng hiện tại không đủ (floor ở 0)
        actual_subtracted = old_total - new_total

        # Nếu đang ở ĐÚNG kênh ticket của buyer này (không mention) → mở lại được .done,
        # để admin sửa số tiền đúng mà không cần tạo ticket mới.
        reopened = False
        if is_ticket and not ctx.message.mentions:
            completed_key = f"completed_{ctx.channel.id}"
            data = load_data()
            if data.get(completed_key):
                data[completed_key] = False
                save_data(data)
                reopened = True

        # Đồng bộ lại buy-role theo tổng MỚI — auto_give_buy_roles() đã tự add ĐÚNG tier
        # và remove tier không còn đạt, không cần logic riêng ở đây.
        from cogs.admin_views import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(ctx.guild, buyer, new_total)

        SERVER_LABELS = {
            "donut":  "🍩 DonutSMP", "kingmc": "👑 KingMC", "onemc": "🎮 One MC",
            "ff":     "🔥 Free Fire", "accpre": "🎭 Acc Pre", "listing": "🛒 Sản phẩm",
        }
        server_label = SERVER_LABELS.get(server_key, None)

        embed = discord.Embed(title="↩️ Đã Trừ Tiền (Sửa Đơn Nhầm)", color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Buyer", value=buyer.mention, inline=True)
        subtract_note = f"**{fmt_amount(actual_subtracted)}**"
        if actual_subtracted < amount:
            subtract_note += f" *(yêu cầu {fmt_amount(amount)}, đã chặn ở 0 — tổng không đủ để trừ hết)*"
        embed.add_field(name="➖ Đã trừ", value=subtract_note, inline=True)
        embed.add_field(name="💰 Tổng chung", value=f"{fmt_amount(old_total)} → **{fmt_amount(new_total)}**", inline=True)
        if server_label and srv_total is not None:
            embed.add_field(name=f"📊 Tổng {server_label}", value=f"**{fmt_amount(srv_total)}**", inline=True)
        if role_cfg:
            role_obj = ctx.guild.get_role(role_cfg.get("role_id", 0))
            embed.add_field(name="🏆 Role hiện tại", value=role_obj.mention if role_obj else f"**{role_cfg.get('label','?')}**", inline=False)
        elif get_buy_roles():
            embed.add_field(name="🏆 Role hiện tại", value="*(dưới mức tier thấp nhất — đã gỡ hết role mua hàng nếu có)*", inline=False)
        if reopened:
            embed.add_field(name="🔓 Ticket", value="Đã mở lại — có thể `.done` lại đúng số tiền trong kênh này.", inline=False)
        embed.set_footer(text=f"Sửa bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

        log_fields = [
            ("👤 Buyer",      _uname_plain(buyer), True),
            ("➖ Đã trừ",      fmt_amount(actual_subtracted), True),
            ("💰 Tổng chung", f"{fmt_amount(old_total)} → {fmt_amount(new_total)}", True),
        ]
        if server_label and srv_total is not None:
            log_fields.append((f"📊 {server_label}", fmt_amount(srv_total), True))
        log_fields += [
            ("🎫 Kênh",    ctx.channel.mention, True),
            ("✍️ Sửa bởi", _uname_plain(ctx.author), True),
        ]
        await send_log(
            ctx.bot, "TICKET_UNDONE", f"Trừ Tiền (Sửa Đơn Nhầm) — {ctx.channel.name}",
            fields=log_fields,
            user=ctx.author,
            guild_id=ctx.guild.id,
        )

    # ── SLASH COMMANDS ──
    @discord.app_commands.command(name="close", description="Đóng ticket hiện tại")
    async def slash_close(self, interaction: discord.Interaction):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if not (interaction.channel.topic and "|" in interaction.channel.topic):
            return await interaction.response.send_message("❌ Đây không phải kênh ticket.", ephemeral=True)
        await interaction.response.send_message("🔒 Đang đóng ticket...", ephemeral=True)
        await _close_ticket(interaction.channel, self.bot, closer=interaction.user)

    @discord.app_commands.command(name="done", description="Hoàn thành đơn hàng (trong ticket hoặc ngoài ticket)")
    @discord.app_commands.describe(
        amount="Số tiền giao dịch, vd: 50k, 1tr5, 200000",
        user="Buyer (bỏ trống nếu dùng trong ticket — tự đọc từ topic)",
    )
    async def slash_done(self, interaction: discord.Interaction, amount: str, user: discord.Member = None):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin mới có quyền hoàn thành đơn.", ephemeral=True)

        parsed = parse_amount(amount)
        if not parsed or parsed <= 0:
            return await interaction.response.send_message(f"❌ Số tiền `{amount}` không hợp lệ!", ephemeral=True)

        is_ticket = bool(interaction.channel.topic and "|" in interaction.channel.topic)
        buyer = user

        if not buyer:
            if not is_ticket:
                return await interaction.response.send_message(
                    "❌ Ngoài kênh ticket, cần chọn **user** trong option.", ephemeral=True
                )
            parts = interaction.channel.topic.split("|")
            try:
                user_id = int(parts[0]) if parts[0].isdigit() else None
            except Exception:
                user_id = None
            if not user_id:
                return await interaction.response.send_message("❌ Không đọc được thông tin buyer.", ephemeral=True)
            buyer = interaction.guild.get_member(user_id)
            if not buyer:
                return await interaction.response.send_message(f"❌ Không tìm thấy buyer (ID: `{user_id}`).", ephemeral=True)

        # Xác định server_key / trade_type — ÁP DỤNG CHO MỌI TRƯỜNG HỢP trong ticket, kể
        # cả khi chọn sẵn user param (cùng lý do/fix với .done gõ tay — xem comment ở đó).
        server_key = None
        trade_type = None
        if is_ticket:
            parts = interaction.channel.topic.split("|")
            trade_type = parts[2] if len(parts) > 2 else None
            server_key = parts[5] if len(parts) > 5 else None
            if trade_type not in ("sell", "buy"):
                return await interaction.response.send_message("ℹ️ Ticket dịch vụ không tính đơn hàng.", ephemeral=True)

        data = load_data()
        if is_ticket and not user:
            completed_key = f"completed_{interaction.channel.id}"
        else:
            completed_key = f"completed_msg_{interaction.id}"
        if data.get(completed_key):
            total = get_user_total_spent(buyer.id)
            return await interaction.response.send_message(
                f"⚠️ Đơn này đã hoàn thành rồi!\nTổng: **{fmt_amount(total)}**", ephemeral=True
            )
        data[completed_key] = True
        save_data(data)

        if server_key:
            totals    = add_user_spent_server(buyer.id, parsed, server_key)
            new_total = totals["total"]
            srv_total = totals["server_total"]
        else:
            new_total = add_user_spent(buyer.id, parsed)
            srv_total = None

        SERVER_LABELS = {
            "donut":  "🍩 DonutSMP",
            "kingmc": "👑 KingMC",
            "onemc":  "🎮 One MC",
            "ff":     "🔥 Free Fire",
            "accpre": "🎭 Acc Pre",
            "listing": "🛒 Sản phẩm",
        }
        server_label = SERVER_LABELS.get(server_key, None)

        save_ticket_record({
            "ticket_name": interaction.channel.name if is_ticket else f"slash-done-{interaction.id}",
            "user_id":     buyer.id,
            "username":    _uname_plain(buyer),
            "amount":      parsed,
            "server_key":  server_key or "unknown",
            "opened_at":   datetime.now(timezone.utc).isoformat(),
            "closed_at":   datetime.now(timezone.utc).isoformat(),
            "staff":       _uname_plain(interaction.user),
            "staff_id":    interaction.user.id,
        })

        from cogs.admin_views import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(interaction.guild, buyer, new_total)

        embed = discord.Embed(title="✅ Hoàn Thành Đơn", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Buyer",       value=buyer.mention,                    inline=True)
        embed.add_field(name="💵 Đơn này",     value=f"**{fmt_amount(parsed)}**",      inline=True)
        embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(new_total)}**",   inline=True)

        if server_label and srv_total is not None:
            embed.add_field(name=f"📊 Tổng {server_label}", value=f"**{fmt_amount(srv_total)}**", inline=True)

        if role_cfg:
            role_obj = interaction.guild.get_role(role_cfg.get("role_id", 0))
            embed.add_field(name="🏆 Role", value=role_obj.mention if role_obj else role_cfg.get("label","?"), inline=False)
        embed.set_footer(text=f"Xác nhận bởi {_uname_plain(interaction.user)}")

        from cogs.shop_orders import build_payment_qr_embed, send_to_queue
        qr_embed, qr_ref_code, qr_note = build_payment_qr_embed(
            interaction.user, buyer, parsed, interaction.guild.id, interaction.channel.id
        )
        # FIX: cùng logic với .done gõ tay — interaction.user đã `.shopbank` (tạo được
        # QR) thì gửi THẲNG QR làm phản hồi chính, thay vì embed "Hoàn Thành Đơn" trước
        # rồi mới followup QR như cũ (2 tin nhắn liên tiếp, thừa).
        if qr_embed:
            await interaction.response.send_message(embed=qr_embed)
        else:
            await interaction.response.send_message(embed=embed)
            if qr_note:
                await interaction.followup.send(qr_note)
                await send_to_queue(self.bot, interaction.user, buyer, interaction.channel, parsed, "")
        await send_log(
            self.bot, "TICKET_DONE", f"Hoàn Thành Đơn — {interaction.channel.name}",
            fields=[
                ("👤 Buyer",       _uname_plain(buyer),   True),
                ("💵 Đơn này",     fmt_amount(parsed),    True),
                ("💰 Tổng",        fmt_amount(new_total), True),
                ("🎫 Kênh",        interaction.channel.mention, True),
                ("✍️ Xác nhận",    _uname_plain(interaction.user),   True),
            ],
            user=interaction.user,
            guild_id=interaction.guild_id,
        )

    # ══════════════════════════════════════════
    # TICKET INFO
    # ══════════════════════════════════════════
    @commands.command(name="ticketinfo", aliases=["tinfo"])
    async def ticketinfo_cmd(self, ctx, member: discord.Member = None):
        if not is_staff_member(ctx.author): return await ctx.reply("❌ Bạn không có quyền.")
        target = member or ctx.author
        history = get_user_ticket_history(target.id)
        total_spent = get_user_total_spent(target.id)

        embed = discord.Embed(
            title=f"🎫 Lịch Sử Đơn — {target.display_name}",
            color=0x5865F2, timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="👤 User",        value=target.mention,                    inline=True)
        embed.add_field(name="📦 Tổng đơn",    value=f"**{len(history)}** đơn",         inline=True)
        embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(total_spent)}**",  inline=True)

        if history:
            # Hiện 5 đơn gần nhất
            recent = history[-5:][::-1]
            lines = []
            for t in recent:
                closed = t.get("closed_at", "")
                try:
                    dt  = datetime.fromisoformat(closed)
                    tstr = dt.strftime("%d/%m/%Y")
                except Exception:
                    tstr = "?"
                lines.append(f"`{tstr}` — **{fmt_amount(t.get('amount',0))}** — `{t.get('ticket_name','?')}` — xác nhận: {t.get('staff','?')}")
            embed.add_field(name="📋 5 đơn gần nhất", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="📋 Lịch sử", value="*(Chưa có đơn nào)*", inline=False)

        embed.set_footer(text=f"Tra cứu bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════════
    # THỐNG KÊ THEO THÁNG
    # ══════════════════════════════════════════
    @commands.command(name="thongke", aliases=["tk"])
    async def thongke_cmd(self, ctx, month_str: str = None):
        if not is_staff_member(ctx.author): return await ctx.reply("❌ Bạn không có quyền.")
        now = datetime.now(timezone.utc)
        year, month = now.year, now.month

        if month_str:
            try:
                parts = month_str.split("/")
                if len(parts) == 2:
                    month, year = int(parts[0]), int(parts[1])
                else:
                    month = int(parts[0])
            except Exception:
                return await ctx.reply("❌ Sai định dạng! Dùng `.thongke` hoặc `.thongke 04/2025`")

        stats = get_monthly_stats(year, month)
        records = stats["records"]

        month_label = f"Tháng {month:02d}/{year}"
        color = 0x57F287 if records else 0x95a5a6

        embed = discord.Embed(
            title=f"📊 Thống Kê — {month_label}",
            color=color, timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="📦 Tổng đơn",   value=f"**{stats['total_orders']}** đơn",          inline=True)
        embed.add_field(name="💰 Tổng tiền",  value=f"**{fmt_amount(stats['total_amount'])}**",   inline=True)

        if records:
            avg = stats["total_amount"] // stats["total_orders"]
            embed.add_field(name="📈 Trung bình/đơn", value=f"**{fmt_amount(avg)}**", inline=True)

            # Top 3 buyer
            buyer_totals: dict[int, int] = {}
            for t in records:
                uid = t.get("user_id")
                buyer_totals[uid] = buyer_totals.get(uid, 0) + t.get("amount", 0)
            top3 = sorted(buyer_totals.items(), key=lambda x: x[1], reverse=True)[:3]
            top_lines = []
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, amt) in enumerate(top3):
                top_lines.append(f"{medals[i]} <@{uid}> — **{fmt_amount(amt)}**")
            embed.add_field(name="🏆 Top Buyer", value="\n".join(top_lines), inline=False)

            # 5 đơn gần nhất
            recent = records[-5:][::-1]
            lines = []
            for t in recent:
                try:
                    dt   = datetime.fromisoformat(t.get("closed_at",""))
                    tstr = dt.strftime("%d/%m %H:%M")
                except Exception:
                    tstr = "?"
                lines.append(f"`{tstr}` <@{t.get('user_id','?')}> — **{fmt_amount(t.get('amount',0))}**")
            embed.add_field(name="📋 5 đơn gần nhất", value="\n".join(lines), inline=False)
        else:
            embed.description = f"*(Không có đơn nào trong {month_label})*"

        embed.set_footer(text=f"Tra cứu bởi {_uname_plain(ctx.author)}  •  Dùng .thongke MM/YYYY để xem tháng khác")
        await ctx.reply(embed=embed)


    # ══════════════════════════════════════════
    # ADMIN: GÁN CATEGORY CHO SELLER (.setsl)
    # ══════════════════════════════════════════
    # ══════════════════════════════════════════
    # ADMIN: DANH SÁCH DỊCH VỤ TICKET MUA HÀNG (.rubyoption)
    # ══════════════════════════════════════════
    @commands.command(name="rubyoption", aliases=["rbopt"])
    async def rubyoption_cmd(self, ctx, *, args: str = None):
        """
        Quản lý danh sách dịch vụ hiện ra cho user chọn trước khi tạo ticket
        Ticket Mua Hàng (nút 🛒 Ticket Mua Hàng trên panel).

        `.rubyoption add <tên>`               — thêm 1 lựa chọn
        `.rubyoption remove <tên>`             — xoá 1 lựa chọn
        `.rubyoption edit <tên cũ> -> <tên mới>` — đổi tên 1 lựa chọn
        `.rubyoption list`                     — xem danh sách hiện tại

        Gộp nhiều thao tác trong 1 lệnh, phân tách bằng dấu phẩy:
        `.rubyoption add A, add B, remove C, edit D -> E`
        """
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")

        if not args or args.strip().lower() == "list":
            if args and args.strip().lower() == "list":
                options = get_ruby_shop_options()
                embed = discord.Embed(
                    title="🛒 Danh sách dịch vụ Ticket Mua Hàng", color=0xE91E8C, timestamp=datetime.now(timezone.utc)
                )
                embed.description = "\n".join(f"{i+1}. {o}" for i, o in enumerate(options)) if options \
                    else "*(chưa có lựa chọn nào — dùng `.rubyoption add <tên>` để thêm)*"
                embed.set_footer(text=f"{len(options)}/25 lựa chọn")
                return await ctx.reply(embed=embed)

            options = get_ruby_shop_options()
            listing = "\n".join(f"• {o}" for o in options) if options else "*(chưa có lựa chọn nào)*"
            return await ctx.reply(
                "❌ Thiếu thao tác!\n"
                "**Cú pháp:**\n"
                "`.rubyoption add <tên>` — thêm lựa chọn\n"
                "`.rubyoption remove <tên>` — xoá lựa chọn\n"
                "`.rubyoption edit <tên cũ> -> <tên mới>` — đổi tên lựa chọn\n"
                "`.rubyoption list` — xem danh sách\n"
                "-# Gộp nhiều thao tác cùng lúc, cách nhau bằng dấu phẩy:\n"
                "-# `.rubyoption add A, add B, remove C, edit D -> E`\n\n"
                f"**Hiện có {len(options)} lựa chọn:**\n{listing}"
            )

        # ── Gộp nhiều thao tác: tách theo dấu phẩy, mỗi đoạn là 1 thao tác riêng ──
        segments = [s.strip() for s in args.split(",") if s.strip()]
        results: list[str] = []

        for seg in segments:
            parts = seg.split(None, 1)
            action = parts[0].strip().lower() if parts else ""
            rest   = parts[1].strip() if len(parts) > 1 else ""

            if action == "list":
                results.append("ℹ️ Dùng `.rubyoption list` riêng để xem danh sách.")
                continue

            if action == "add":
                if not rest:
                    results.append("❌ `add` thiếu tên dịch vụ."); continue
                try:
                    added = add_ruby_shop_option(rest)
                except ValueError as e:
                    results.append(f"❌ `add {rest}` — {e}"); continue
                results.append(f"✅ Thêm **{rest}**" if added else f"⚠️ **{rest}** đã tồn tại, bỏ qua")

            elif action in ("remove", "del", "delete"):
                if not rest:
                    results.append("❌ `remove` thiếu tên dịch vụ."); continue
                ok = remove_ruby_shop_option(rest)
                results.append(f"🗑️ Xoá **{rest}**" if ok else f"❌ Không tìm thấy **{rest}** để xoá")

            elif action in ("edit", "rename"):
                if "->" not in rest:
                    results.append(f"❌ `edit {rest}` — cần dạng `edit tên cũ -> tên mới`"); continue
                old_name, new_name = (p.strip() for p in rest.split("->", 1))
                if not old_name or not new_name:
                    results.append("❌ `edit` thiếu tên cũ hoặc tên mới."); continue
                try:
                    ok = rename_ruby_shop_option(old_name, new_name)
                except ValueError as e:
                    results.append(f"❌ `edit {old_name}` — {e}"); continue
                results.append(f"✏️ Đổi **{old_name}** → **{new_name}**" if ok
                                else f"❌ Không tìm thấy **{old_name}** để đổi tên")

            else:
                results.append(f"❌ Không hiểu thao tác `{action}` trong `{seg}` (dùng add/remove/edit)")

        msg = "\n".join(results) or "❌ Không có thao tác nào hợp lệ."
        await ctx.reply(msg[:1990])

    # ══════════════════════════════════════════
    # ADMIN: GÁN ROLE CHO TỪNG LOẠI TICKET
    # ══════════════════════════════════════════
    @commands.command(name="setrole")
    async def setrole_cmd(self, ctx, ticket_key: str = None, *, value: str = None):
        """
        Gán role cho từng loại ticket. Ghi thẳng vào hệ thống multi-role
        (field `ticket_multi_roles`) — cùng field mà UI `.st` dùng, và là
        field DUY NHẤT được đọc lúc tạo ticket để cấp quyền.

        [FIX v4.11.4] Trước bản này .setrole ghi vào field `ticket_role_ids`
        / `ticket_type_roles` — 2 field không hề được đọc ở đâu khi cấp
        quyền ticket thật (xem ticket.py dòng ~606-815, chỉ đọc
        `ticket_multi_roles`). Lệnh từng báo "✅ thành công" nhưng vô tác dụng.

        Dùng @role      → thêm role vào danh sách multi-role của key đó.
        Dùng seller     → thêm role seller đang cấu hình (get_cfg_seller_role).
        Dùng builder    → thêm role builder mặc định (cfg_builder_role, cấu hình qua .st).
        Dùng admin      → không cần gán gì, admin luôn có quyền sẵn (bỏ qua).
        Dùng none/reset → xóa toàn bộ danh sách role của key đó.

        ⚠️ Danh sách rỗng KHÔNG có nghĩa "chỉ admin" — ticket sẽ tự fallback
        về role support/seller/builder mặc định (xem _build_ticket_overwrites_multi).

        Keys hợp lệ: order_donut, order_kingmc, order_onemc, order_ff, order_build, acc_pre, rubyshop, giveaway, support

        Ví dụ:
          .setrole order_donut @DonutStaff
          .setrole support builder
          .setrole acc_pre reset
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền.")

        VALID_KEYS = ["order_donut", "order_kingmc", "order_onemc", "order_ff", "order_build", "acc_pre", "rubyshop", "middleman", "giveaway", "support"]
        KEY_LABELS = {
            "order_donut":  "🍩 Mua/Bán DonutSMP",
            "order_kingmc": "👑 Mua/Bán KingMC",
            "order_onemc":  "🎮 Mua/Bán One MC",
            "order_ff":     "🔥 Mua/Bán Free Fire",
            "order_build":  "🏗️ Mua/Bán Base",
            "acc_pre":      "🎭 Acc Pre",
            "rubyshop":     "🛒 Ticket Mua Hàng",
            "middleman":    "🤝 Giao Dịch Trung Gian",
            "giveaway":     "🎁 Nhận Giveaway",
            "support":      "🆘 Hỗ Trợ",
        }

        if not ticket_key:
            keys_str = "\n".join(f"`{k}` — {KEY_LABELS[k]}" for k in VALID_KEYS)
            return await ctx.reply(
                "❌ Thiếu thông tin!\n"
                "**Cú pháp:**\n"
                "`.setrole <key> @role` — thêm role vào multi-role\n"
                "`.setrole <key> seller|builder` — thêm role seller/builder mặc định\n"
                "`.setrole <key> reset` — xóa toàn bộ role đã gán\n\n"
                f"**Keys hợp lệ:**\n{keys_str}"
            )

        ticket_key = ticket_key.lower()
        if ticket_key not in VALID_KEYS:
            return await ctx.reply(f"❌ Key `{ticket_key}` không hợp lệ! Dùng `.setrole` để xem danh sách.")

        if not value:
            return await ctx.reply("❌ Thiếu giá trị! Ví dụ: `.setrole order_donut @DonutStaff`")

        label = KEY_LABELS.get(ticket_key, ticket_key)
        value_l = value.strip().lower()

        if value_l in ("reset", "none"):
            set_ticket_role_ids(ticket_key, [])
            return await ctx.reply(
                f"✅ Đã xóa toàn bộ role gán cho **{label}** (`{ticket_key}`).\n"
                "-# Ticket loại này sẽ dùng fallback mặc định (support/seller/builder)."
            )

        if value_l == "admin":
            return await ctx.reply(
                "ℹ️ Không cần gán gì — admin (`ADMIN_IDS`) luôn có quyền full trên mọi ticket, "
                "bất kể cấu hình role. Dùng `.setrole {} reset` nếu muốn xóa role khác đang gán.".format(ticket_key)
            )

        if value_l in ("seller", "builder"):
            role_id = get_cfg_seller_role() if value_l == "seller" else get_cfg_builder_role()
            role = ctx.guild.get_role(role_id)
            if not role:
                return await ctx.reply(f"❌ Không tìm thấy role `{value_l}` (ID `{role_id}`) trong server.")
            current = get_ticket_role_ids(ticket_key)
            if role.id not in current:
                current.append(role.id)
            set_ticket_role_ids(ticket_key, current)
            embed = discord.Embed(title="⚙️ Đã Gán Role Ticket", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="🏷️ Loại ticket", value=label,             inline=True)
            embed.add_field(name="👥 Role",         value=role.mention,      inline=True)
            embed.add_field(name="🔑 Key",          value=f"`{ticket_key}`", inline=True)
            embed.set_footer(text=f"Cài bởi {_uname_plain(ctx.author)}")
            return await ctx.reply(embed=embed)

        # Role mention / ID
        role = None
        if ctx.message.role_mentions:
            role = ctx.message.role_mentions[0]
        else:
            try:
                rid  = int(value.strip().strip("<@&>"))
                role = ctx.guild.get_role(rid)
            except Exception:
                pass

        if not role:
            return await ctx.reply(
                f"❌ Không nhận ra `{value}` là role hay group hợp lệ.\n"
                f"Group hợp lệ: `seller`, `builder`, `admin`, `none`\n"
                "Hoặc mention trực tiếp `@Role`."
            )

        current = get_ticket_role_ids(ticket_key)
        if role.id not in current:
            current.append(role.id)
        set_ticket_role_ids(ticket_key, current)

        embed = discord.Embed(title="⚙️ Đã Gán Role Ticket", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏷️ Loại ticket", value=label,             inline=True)
        embed.add_field(name="👥 Role",         value=role.mention,      inline=True)
        embed.add_field(name="🔑 Key",          value=f"`{ticket_key}`", inline=True)
        embed.set_footer(text=f"Cài bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    @commands.command(name="listroles")
    async def listroles_cmd(self, ctx):
        """Xem role đang gán cho từng loại ticket (đọc đúng field dùng để cấp quyền thật)."""
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")

        KEY_LABELS = {
            "order_donut":  "🍩 Mua/Bán DonutSMP",
            "order_kingmc": "👑 Mua/Bán KingMC",
            "order_onemc":  "🎮 Mua/Bán One MC",
            "order_ff":     "🔥 Mua/Bán Free Fire",
            "order_build":  "🏗️ Mua/Bán Base",
            "acc_pre":      "🎭 Acc Pre",
            "rubyshop":     "🛒 Ticket Mua Hàng",
            "middleman":    "🤝 Giao Dịch Trung Gian",
            "giveaway":     "🎁 Nhận Giveaway",
            "support":      "🆘 Hỗ Trợ",
        }
        all_multi = get_all_ticket_multi_roles()

        lines = []
        for key, label in KEY_LABELS.items():
            role_ids = all_multi.get(key) or []
            if role_ids:
                mentions = []
                for rid in role_ids:
                    role = ctx.guild.get_role(int(rid))
                    mentions.append(role.mention if role else f"`ID:{rid}` *(không tìm thấy)*")
                val = ", ".join(mentions)
            else:
                val = "*(chưa gán — dùng fallback mặc định: support/seller/builder)*"
            lines.append(f"{label}\n╰ {val}")

        embed = discord.Embed(
            title="📋 Role Từng Loại Ticket",
            description="\n\n".join(lines),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(
            text="Dùng .setrole <key> @role|seller|builder|reset để chỉnh"
        )
        await ctx.reply(embed=embed)

    @commands.command(name="setsl")
    async def setsl_cmd(self, ctx, seller: discord.Member = None, category: discord.CategoryChannel = None):
        """
        .setsl <@seller | seller_id> #category
        Admin gán category riêng cho từng seller.
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền.")

        if not seller:
            return await ctx.reply(
                "❌ Thiếu thông tin!\n"
                "Cú pháp: `.setsl @seller #danh-mục`\n"
                "Ví dụ: `.setsl @TuyTam #Shop-TuyTam`"
            )

        if not category:
            return await ctx.reply(
                "❌ Thiếu danh mục!\n"
                "Cú pháp: `.setsl @seller #danh-mục`"
            )

        save_seller_category(seller.id, category.id)

        # Xem category hiện tại của tất cả seller để hiển thị
        all_cats = get_all_seller_categories()
        lines = []
        for uid_str, cid in all_cats.items():
            cat = discord.utils.get(ctx.guild.categories, id=cid)
            cat_name = cat.name if cat else f"`ID:{cid}`"
            lines.append(f"<@{uid_str}> → **{cat_name}**")

        embed = discord.Embed(
            title="⚙️ Đã gán Category cho Seller",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="👤 Seller",    value=seller.mention,    inline=True)
        embed.add_field(name="📁 Category",  value=category.name,     inline=True)
        embed.add_field(name="🆔 Category ID", value=f"`{category.id}`", inline=True)
        if lines:
            embed.add_field(
                name="📋 Tất cả seller đã gán",
                value="\n".join(lines) or "*(chưa có)*",
                inline=False,
            )
        embed.set_footer(text=f"Cài bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    @commands.command(name="removesl")
    async def removesl_cmd(self, ctx, seller: discord.Member = None):
        """Admin xóa category của một seller."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền.")
        if not seller:
            return await ctx.reply("❌ Thiếu seller! Ví dụ: `.removesl @seller`")

        remove_seller_category(seller.id)
        await ctx.reply(f"✅ Đã xóa category của {seller.mention}.")

    @commands.command(name="listsl")
    async def listsl_cmd(self, ctx):
        """Admin xem danh sách seller → category."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền.")

        all_cats = get_all_seller_categories()
        if not all_cats:
            return await ctx.reply("*(Chưa có seller nào được gán category)*")

        lines = []
        for uid_str, cid in all_cats.items():
            cat = discord.utils.get(ctx.guild.categories, id=cid)
            cat_name = cat.name if cat else f"`ID:{cid}`"
            lines.append(f"<@{uid_str}> → **{cat_name}**")

        embed = discord.Embed(
            title="📋 Danh Sách Seller → Category",
            description="\n".join(lines),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Tra cứu bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)




async def setup(bot):
    await bot.add_cog(TicketCog(bot))
