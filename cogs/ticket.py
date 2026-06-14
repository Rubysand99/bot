"""
cogs/ticket.py — Ticket system: panel, views, modals, close/done logic.
"""

import os
import io
import asyncio
_ticket_create_lock = asyncio.Lock()
import logging
log = logging.getLogger(__name__)
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select

from core.data import (
    ADMIN_IDS, TRANSCRIPT_CHANNEL_ID,
    get_cfg_category, get_cfg_support_role, get_cfg_seller_role,
    get_cfg_counter_channel, get_cfg_proof_channel,
    get_panel_channel_id, save_panel_channel_id,
    get_buy_roles, get_user_total_spent,
    add_user_spent, add_user_spent_server,
    get_user_spent_by_server, get_user_spent_all_servers,
    save_ticket_record, get_user_ticket_history, get_monthly_stats,
    load_data, save_data, parse_amount, fmt_amount, is_staff_member,
    _uname, _uname_plain, can_use_dangerous_cmd,
    get_seller_category, save_seller_category,
    remove_seller_category, get_all_seller_categories,
    get_or_fetch_channel,
    get_ticket_type_role, set_ticket_type_role, get_all_ticket_type_roles,
    BUILDER_BASE_ROLE_ID as _BUILDER_ROLE_ID,
    get_ticket_role_id, set_ticket_role_id, get_all_ticket_role_ids,
    get_ticket_role_ids,
)
from cogs.logger import send_log

# BOT_VERSION được import từ bot.py khi cần — không hardcode lại ở đây

BUILDER_BASE_ROLE_ID = _BUILDER_ROLE_ID

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
# Cache: user_id → channel_id (ticket đang mở)
_open_tickets: dict[int, int] = {}

def _register_ticket(user_id: int, channel_id: int):
    _open_tickets[user_id] = channel_id

def _unregister_ticket(user_id: int):
    _open_tickets.pop(user_id, None)

async def has_ticket(guild, user) -> bool:
    """Kiểm tra user có ticket đang mở không — dùng cache O(1) thay vì quét toàn bộ kênh."""
    channel_id = _open_tickets.get(user.id)
    if channel_id:
        ch = guild.get_channel(channel_id)
        if ch:
            return True
        # Kênh không còn tồn tại → dọn cache
        _unregister_ticket(user.id)
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
        builder_role = guild.get_role(BUILDER_BASE_ROLE_ID)
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


def _build_ticket_overwrites_multi(guild, user, role_ids: list):
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
        builder_role = guild.get_role(BUILDER_BASE_ROLE_ID)
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

    transcript_ch = await get_or_fetch_channel(bot_instance, TRANSCRIPT_CHANNEL_ID)
    if transcript_ch:
        file2 = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")
        await transcript_ch.send(embed=embed, file=file2)

    # Dọn cache open ticket
    if user_id:
        _unregister_ticket(user_id)

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
    """Bước 1 (panel mới): chọn item trước, rồi mới chọn Mua/Bán."""
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
            server_label = SERVER_TABLE[self.server_key]["label"]
            view = View(timeout=60)
            view.add_item(_TradeModeSelect(self.server_key, item_key, item_label))
            await interaction.response.send_message(
                f"{server_label} — **{item_label}** — Bạn muốn mua hay bán?",
                view=view, ephemeral=True,
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
        _register_ticket(interaction.user.id, channel.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,               True),
                ("🏷️ Loại",      type_label,                    True),
                ("🌐 Server",     server_label,                  True),
                ("📦 Item",       item_label,                    True),
                ("👤 Người tạo", interaction.user.mention,       True),
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

        if role_id:
            ping_str = f"<@&{role_id}>"
        elif role_group == "builder":
            ping_str = f"<@&{BUILDER_BASE_ROLE_ID}>"
        elif role_group == "seller":
            ping_str = f"<@&{get_cfg_seller_role()}>"
        elif role_group == "admin":
            ping_str = " ".join(f"<@{aid}>" for aid in ADMIN_IDS)
        else:
            ping_str = f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id)
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

        if role_id:
            ping_str = f"<@&{role_id}>"
        elif role_group == "admin":
            ping_str = " ".join(f"<@{aid}>" for aid in ADMIN_IDS)
        else:
            ping_str = f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,               True),
                ("🏷️ Loại",      type_label,                    True),
                ("👤 Người tạo", interaction.user.mention,       True),
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

        if role_id:
            ping_str = f"<@&{role_id}>"
        elif role_group == "admin":
            ping_str = " ".join(f"<@{aid}>" for aid in ADMIN_IDS)
        else:
            ping_str = f"<@&{get_cfg_support_role()}>"

        await channel.send(f"{ping_str} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        _register_ticket(interaction.user.id, channel.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,               True),
                ("🏷️ Loại",      type_label,                    True),
                ("👤 Người tạo", interaction.user.mention,       True),
                ("🕐 Thời gian", created_at,                    True),
            ],
            user=interaction.user,
        )
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`")
        except Exception:
            pass

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
        _register_ticket(interaction.user.id, channel.id)
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,         True),
                ("🖥️ Server",    server_label,             True),
                ("👤 Người tạo", interaction.user.mention, True),
                ("🕐 Thời gian", created_at,               True),
            ],
            user=interaction.user,
        )
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`")
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


class TicketPanel(View):
    """Panel chính — tất cả nút trong 1 embed, không timeout (persistent)."""
    def __init__(self):
        super().__init__(timeout=None)

    # ── Hàng 1: Donut & KingMC (chọn item → Mua/Bán) ─────────────────
    @discord.ui.button(label="🍩 DonutSMP", style=discord.ButtonStyle.green,  custom_id="panel_donut", row=0)
    async def btn_donut(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "🍩 **DonutSMP — Chọn loại item:**",
                view=ItemPickView(SERVER_DONUT), ephemeral=True,
            )
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="👑 KingMC", style=discord.ButtonStyle.blurple, custom_id="panel_kingmc", row=0)
    async def btn_kingmc(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "👑 **KingMC — Chọn loại item:**",
                view=ItemPickView(SERVER_KING), ephemeral=True,
            )
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    # ── Hàng 2: OneMC, FreeFire (tạo ticket thẳng) ────────────────────
    @discord.ui.button(label="🔥 Free Fire", style=discord.ButtonStyle.red,    custom_id="panel_ff",    row=1)
    async def btn_ff(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_direct_order_ticket(interaction, SERVER_FF)
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    # ── Hàng 3: AccPre, Build (popup Mua/Bán) ─────────────────────────
    @discord.ui.button(label="🎭 Acc Pre", style=discord.ButtonStyle.blurple, custom_id="panel_accpre", row=2)
    async def btn_accpre(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "🎭 **Bạn muốn mua hay bán Acc Pre?**", view=AccPreView(), ephemeral=True,
            )
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="🏗️ Build",   style=discord.ButtonStyle.grey,   custom_id="panel_build",  row=2)
    async def btn_build(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message(
                "🏗️ **Bạn muốn mua hay bán Base?**", view=BuildView(), ephemeral=True,
            )
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    # ── Hàng 4: Dịch vụ (Giveaway, Hỗ Trợ — tạo ticket thẳng) ───────
    @discord.ui.button(label="🎁 Nhận Giveaway", style=discord.ButtonStyle.green,  custom_id="panel_giveaway", row=3)
    async def btn_giveaway(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_direct_service_ticket(interaction, "giveaway")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

    @discord.ui.button(label="🆘 Hỗ Trợ", style=discord.ButtonStyle.blurple, custom_id="panel_support", row=3)
    async def btn_support(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_direct_service_ticket(interaction, "support")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except Exception: pass

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

    @commands.command()
    async def panel(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return
        await ctx.send(embed=build_panel_embed(ctx.guild), view=TicketPanel())
        await ctx.message.delete()

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
    async def done_cmd(self, ctx, amount_str: str = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Chỉ admin mới có quyền hoàn thành đơn.")
        if not (ctx.channel.topic and "|" in ctx.channel.topic): return await ctx.reply("❌ Đây không phải kênh ticket.")
        if not amount_str: return await ctx.reply("❌ Thiếu số tiền! Ví dụ: `.done 50k`, `.done 1tr5`")

        amount = parse_amount(amount_str)
        if amount is None or amount <= 0:
            return await ctx.reply(f"❌ Số tiền `{amount_str}` không hợp lệ!")

        # Parse topic: user_id||trade_type|item_key|status[|server_key]
        parts = ctx.channel.topic.split("|")
        try: user_id = int(parts[0]) if parts[0].isdigit() else None
        except Exception: user_id = None
        if not user_id: return await ctx.reply("❌ Không đọc được thông tin buyer từ ticket.")

        trade_type = parts[2] if len(parts) > 2 else None
        item_key   = parts[3] if len(parts) > 3 else None
        server_key = parts[5] if len(parts) > 5 else None  # slot 5: donut / kingmc / accpre / None

        if trade_type not in ("sell", "buy"):
            return await ctx.reply("ℹ️ Ticket dịch vụ / hỗ trợ không tính vào đơn mua hàng.")

        buyer = ctx.guild.get_member(user_id)
        if not buyer: return await ctx.reply(f"❌ Không tìm thấy buyer (ID: `{user_id}`).")

        data = load_data()
        completed_key = f"completed_{ctx.channel.id}"
        if data.get(completed_key):
            total = get_user_total_spent(user_id)
            return await ctx.reply(f"⚠️ Đơn này đã hoàn thành rồi!\nBuyer: {buyer.mention} — tổng: **{fmt_amount(total)}**")

        data[completed_key] = True
        save_data(data)

        # Cộng tiền theo server (nếu có server_key) VÀ vào tổng chung
        if server_key:
            totals     = add_user_spent_server(user_id, amount, server_key)
            new_total  = totals["total"]
            srv_total  = totals["server_total"]
        else:
            new_total = add_user_spent(user_id, amount)
            srv_total = None

        # Label server để hiển thị
        SERVER_LABELS = {
            "donut":  "🍩 DonutSMP",
            "kingmc": "👑 KingMC",
            "onemc":  "🎮 One MC",
            "ff":     "🔥 Free Fire",
            "accpre": "🎭 Acc Pre",
        }
        server_label = SERVER_LABELS.get(server_key, None)

        # Lưu lịch sử đơn
        try:    opened_at = ctx.channel.created_at.isoformat()
        except: opened_at = datetime.now(timezone.utc).isoformat()

        save_ticket_record({
            "ticket_name": ctx.channel.name,
            "user_id":     user_id,
            "username":    _uname_plain(buyer),
            "amount":      amount,
            "server_key":  server_key or "unknown",
            "opened_at":   opened_at,
            "closed_at":   datetime.now(timezone.utc).isoformat(),
            "staff":       _uname_plain(ctx.author),
            "staff_id":    ctx.author.id,
        })

        from cogs.admin import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(ctx.guild, buyer, new_total)

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
        embed.set_footer(text=f"Xác nhận bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

        log_fields = [
            ("👤 Buyer",        buyer.mention,        True),
            ("💵 Đơn này",      fmt_amount(amount),   True),
            ("💰 Tổng chung",   fmt_amount(new_total), True),
        ]
        if server_label and srv_total is not None:
            log_fields.append((f"📊 {server_label}", fmt_amount(srv_total), True))
        log_fields += [
            ("🎫 Ticket",        ctx.channel.mention, True),
            ("✍️ Xác nhận bởi", ctx.author.mention,  True),
        ]
        await send_log(
            ctx.bot, "TICKET_DONE", f"Hoàn Thành Đơn — {ctx.channel.name}",
            fields=log_fields,
            user=ctx.author,
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

    @discord.app_commands.command(name="done", description="Hoàn thành đơn hàng trong ticket")
    @discord.app_commands.describe(amount="Số tiền giao dịch, vd: 50k, 1tr5, 200000")
    async def slash_done(self, interaction: discord.Interaction, amount: str):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin mới có quyền hoàn thành đơn.", ephemeral=True)
        if not (interaction.channel.topic and "|" in interaction.channel.topic):
            return await interaction.response.send_message("❌ Đây không phải kênh ticket.", ephemeral=True)
        parsed = parse_amount(amount)
        if not parsed or parsed <= 0:
            return await interaction.response.send_message(f"❌ Số tiền `{amount}` không hợp lệ!", ephemeral=True)
        parts = interaction.channel.topic.split("|")
        try: user_id = int(parts[0]) if parts[0].isdigit() else None
        except Exception: user_id = None
        if not user_id:
            return await interaction.response.send_message("❌ Không đọc được thông tin buyer.", ephemeral=True)
        trade_type = parts[2] if len(parts) > 2 else None
        if trade_type not in ("sell", "buy"):
            return await interaction.response.send_message("ℹ️ Ticket dịch vụ không tính đơn hàng.", ephemeral=True)
        buyer = interaction.guild.get_member(user_id)
        if not buyer:
            return await interaction.response.send_message(f"❌ Không tìm thấy buyer (ID: `{user_id}`).", ephemeral=True)
        data = load_data()
        completed_key = f"completed_{interaction.channel.id}"
        if data.get(completed_key):
            total = get_user_total_spent(user_id)
            return await interaction.response.send_message(f"⚠️ Đơn này đã hoàn thành rồi!\nTổng: **{fmt_amount(total)}**", ephemeral=True)
        data[completed_key] = True
        save_data(data)
        new_total = add_user_spent(user_id, parsed)
        from cogs.admin import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(interaction.guild, buyer, new_total)
        embed = discord.Embed(title="✅ Hoàn Thành Đơn", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Buyer",       value=buyer.mention,                    inline=True)
        embed.add_field(name="💵 Đơn này",     value=f"**{fmt_amount(parsed)}**",      inline=True)
        embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(new_total)}**",   inline=True)
        if role_cfg:
            role_obj = interaction.guild.get_role(role_cfg.get("role_id", 0))
            embed.add_field(name="🏆 Role", value=role_obj.mention if role_obj else role_cfg.get("label","?"), inline=False)
        embed.set_footer(text=f"Xác nhận bởi {_uname_plain(interaction.user)}")
        await interaction.response.send_message(embed=embed)
        await send_log(
            self.bot, "TICKET_DONE", f"Hoàn Thành Đơn — {interaction.channel.name}",
            fields=[
                ("👤 Buyer",       buyer.mention,         True),
                ("💵 Đơn này",     fmt_amount(parsed),    True),
                ("💰 Tổng",        fmt_amount(new_total), True),
                ("🎫 Ticket",      interaction.channel.mention, True),
                ("✍️ Xác nhận",    interaction.user.mention,   True),
            ],
            user=interaction.user,
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
            from collections import Counter
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
    # ADMIN: GÁN ROLE CHO TỪNG LOẠI TICKET
    # ══════════════════════════════════════════
    @commands.command(name="setrole")
    async def setrole_cmd(self, ctx, ticket_key: str = None, *, value: str = None):
        """
        Gán role (hoặc group cũ) cho từng loại ticket.

        Dùng @role  → gán role ID cụ thể (ưu tiên, ghi đè group cũ).
        Dùng group  → gán group string cũ: seller / builder / admin / none
        Dùng reset  → xóa cả role ID lẫn group.

        Keys hợp lệ: order_donut, order_kingmc, order_onemc, order_ff, order_build, acc_pre, giveaway, support

        Ví dụ:
          .setrole order_donut @DonutStaff
          .setrole support builder
          .setrole acc_pre reset
        """
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền.")

        VALID_KEYS = ["order_donut", "order_kingmc", "order_onemc", "order_ff", "order_build", "acc_pre", "giveaway", "support"]
        VALID_GROUPS = ["seller", "builder", "admin", "none"]
        KEY_LABELS = {
            "order_donut":  "🍩 Mua/Bán DonutSMP",
            "order_kingmc": "👑 Mua/Bán KingMC",
            "order_onemc":  "🎮 Mua/Bán One MC",
            "order_ff":     "🔥 Mua/Bán Free Fire",
            "order_build":  "🏗️ Mua/Bán Base",
            "acc_pre":      "🎭 Acc Pre",
            "giveaway":     "🎁 Nhận Giveaway",
            "support":      "🆘 Hỗ Trợ",
        }

        if not ticket_key:
            keys_str = "\n".join(f"`{k}` — {KEY_LABELS[k]}" for k in VALID_KEYS)
            return await ctx.reply(
                "❌ Thiếu thông tin!\n"
                "**Cú pháp:**\n"
                "`.setrole <key> @role` — gán role Discord cụ thể\n"
                "`.setrole <key> seller|builder|admin` — dùng group cũ\n"
                "`.setrole <key> reset` — xóa cấu hình\n\n"
                f"**Keys hợp lệ:**\n{keys_str}"
            )

        ticket_key = ticket_key.lower()
        if ticket_key not in VALID_KEYS:
            return await ctx.reply(f"❌ Key `{ticket_key}` không hợp lệ! Dùng `.setrole` để xem danh sách.")

        if not value:
            return await ctx.reply("❌ Thiếu giá trị! Ví dụ: `.setrole order_donut @DonutStaff`")

        label = KEY_LABELS.get(ticket_key, ticket_key)

        # Reset cả 2 hệ thống
        if value.strip().lower() == "reset":
            set_ticket_role_id(ticket_key, None)
            set_ticket_type_role(ticket_key, None)
            return await ctx.reply(f"✅ Đã xóa cấu hình role cho **{label}** (`{ticket_key}`).")

        # Group string cũ (seller / builder / admin / none)
        if value.strip().lower() in VALID_GROUPS:
            group = value.strip().lower()
            g = None if group == "none" else group
            set_ticket_type_role(ticket_key, g)
            set_ticket_role_id(ticket_key, None)   # xóa role ID nếu có
            embed = discord.Embed(title="⚙️ Đã Gán Group Ticket", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="🏷️ Loại ticket", value=label,              inline=True)
            embed.add_field(name="👥 Group",        value=f"`{group}`",       inline=True)
            embed.add_field(name="🔑 Key",          value=f"`{ticket_key}`",  inline=True)
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

        set_ticket_role_id(ticket_key, role.id)
        set_ticket_type_role(ticket_key, None)   # xóa group cũ nếu có

        embed = discord.Embed(title="⚙️ Đã Gán Role Ticket", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏷️ Loại ticket", value=label,             inline=True)
        embed.add_field(name="👥 Role",         value=role.mention,      inline=True)
        embed.add_field(name="🔑 Key",          value=f"`{ticket_key}`", inline=True)
        embed.set_footer(text=f"Cài bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    @commands.command(name="listroles")
    async def listroles_cmd(self, ctx):
        """Xem role / group đang gán cho từng loại ticket."""
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền.")

        KEY_LABELS = {
            "order_donut":  "🍩 Mua/Bán DonutSMP",
            "order_kingmc": "👑 Mua/Bán KingMC",
            "order_onemc":  "🎮 Mua/Bán One MC",
            "order_ff":     "🔥 Mua/Bán Free Fire",
            "order_build":  "🏗️ Mua/Bán Base",
            "acc_pre":      "🎭 Acc Pre",
            "giveaway":     "🎁 Nhận Giveaway",
            "support":      "🆘 Hỗ Trợ",
        }
        all_ids    = get_all_ticket_role_ids()
        all_groups = get_all_ticket_type_roles()

        lines = []
        for key, label in KEY_LABELS.items():
            rid   = all_ids.get(key)
            group = all_groups.get(key)
            if rid:
                role = ctx.guild.get_role(int(rid))
                val  = (role.mention if role else f"`ID:{rid}` *(không tìm thấy)*") + "  *(role ID)*"
            elif group:
                val = f"`{group}` *(group)*"
            else:
                val = "*(chưa gán — dùng fallback mặc định)*"
            lines.append(f"{label}\n╰ {val}")

        embed = discord.Embed(
            title="📋 Role / Group Từng Loại Ticket",
            description="\n\n".join(lines),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(
            text="Role ID ưu tiên hơn group  •  Dùng .setrole <key> @role|group|reset để chỉnh"
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
