"""
cogs/ticket.py — Ticket system: panel, views, modals, close/done logic.
"""

import os
import io
import asyncio
_ticket_create_lock = asyncio.Lock()
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select

from core.data import (
    ADMIN_IDS, TRANSCRIPT_CHANNEL_ID,
    get_cfg_category, get_cfg_support_role, get_cfg_seller_role,
    get_cfg_counter_channel, get_cfg_proof_channel, get_cfg_balance_channel,
    get_panel_channel_id, save_panel_channel_id,
    get_buy_roles, get_user_total_spent,
    add_user_spent,
    save_ticket_record, get_user_ticket_history, get_monthly_stats,
    load_data, save_data, parse_amount, fmt_amount, is_staff_member,
    _uname, _uname_plain, can_use_dangerous_cmd,
    get_seller_category, save_seller_category,
    remove_seller_category, get_all_seller_categories,
    get_or_fetch_channel,
)
from cogs.logger import send_log

BOT_VERSION = "3.3.5"

BUILDER_BASE_ROLE_ID = 1484158340849205308

# ── Bảng SERVICE (không có giá) ──
SERVICE_TABLE = {
    "orderbase": {"label": "🏯 Order Base",    "note": "Đặt thiết kế base theo yêu cầu",  "color": 0xE67E22, "type_label": "🏯 ORDER BASE",    "channel_prefix": "base"},
    "modfixlag": {"label": "⚡ Mod Fix Lag",   "note": "Hỗ trợ cài mod tối ưu FPS",       "color": 0x1ABC9C, "type_label": "⚡ MOD FIX LAG",   "channel_prefix": "mod"},
    "giveaway":  {"label": "🎁 Nhận Giveaway", "note": "Xác nhận & nhận thưởng giveaway", "color": 0xF1C40F, "type_label": "🎁 NHẬN GIVEAWAY",  "channel_prefix": "ticket"},
    "support":   {"label": "🆘 Hỗ Trợ",        "note": "Hỗ trợ mọi vấn đề",              "color": 0x3498DB, "type_label": "🆘 HỖ TRỢ",         "channel_prefix": "ticket"},
}

_ITEM_LABEL = {"money": "💰 Money", "skeleton": "💀 Skeleton", "other": "📦 Khác"}
_ITEM_OPTIONS = [
    discord.SelectOption(label="💰 Money",    value="money",    description="Giao dịch tiền tệ trong game",   emoji="💰"),
    discord.SelectOption(label="💀 Skeleton", value="skeleton", description="Giao dịch skeleton",             emoji="💀"),
    discord.SelectOption(label="📦 Khác",     value="other",    description="Item / dịch vụ khác",           emoji="📦"),
]

# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════
async def has_ticket(guild, user):
    for channel in guild.text_channels:
        if channel.topic and str(user.id) in channel.topic:
            return True
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
    except: pass
    return 0

async def write_counter_to_channel(bot, number: int):
    ch_id = get_cfg_counter_channel()
    if not ch_id: return
    channel = await get_or_fetch_channel(bot, ch_id)
    if not channel: return
    try:
        await channel.purge(limit=5)
        await channel.send(f"ticket:{number:03d}")
    except: pass

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

def _build_ticket_overwrites(guild, user, seller_id=None):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    for admin_id in ADMIN_IDS:
        m = guild.get_member(admin_id)
        if m: overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
    support_role = guild.get_role(get_cfg_support_role())
    if support_role: overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
    seller_role = guild.get_role(get_cfg_seller_role())
    if seller_role: overwrites[seller_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, attach_files=True, embed_links=True, manage_channels=True, manage_permissions=True)
    builder_base_role = guild.get_role(BUILDER_BASE_ROLE_ID)
    if builder_base_role: overwrites[builder_base_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, attach_files=True, embed_links=True, manage_channels=True, manage_permissions=True)
    if seller_id:
        sm = guild.get_member(seller_id)
        if sm: overwrites[sm] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
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
    embed.add_field(name="🛒  Dịch vụ", value="› Mua / Bán Money, Skeleton, Elytra\n› 🏯 Order Base\n› ⚡ Mod Fix Lag\n› 🎁 Nhận Giveaway\n› 🆘 Hỗ Trợ", inline=True)
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
        content = discord.utils.escape_mentions(raw).replace("<","&lt;").replace(">","&gt;") if raw else "<i style='color:#72767d'>(không có nội dung)</i>"
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
        except: pass
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
# MODALS

# ══════════════════════════════════════════
# ITEM SELECT
# ══════════════════════════════════════════
class ItemSelect(Select):
    def __init__(self, trade_type: str):
        self.trade_type = trade_type
        action = "mua" if trade_type == "sell" else "bán"
        super().__init__(placeholder=f"Bạn muốn {action} loại nào?", options=_ITEM_OPTIONS, custom_id=f"item_select_{trade_type}")

    async def callback(self, interaction: discord.Interaction):
        try:
            item_key   = self.values[0]
            item_label = _ITEM_LABEL.get(item_key, item_key)
            await interaction.response.defer(ephemeral=True)
            await create_order_ticket(interaction, trade_type=self.trade_type, item_key=item_key, item_label=item_label)
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`")
            except: pass

class ItemSelectView(View):
    def __init__(self, trade_type: str):
        super().__init__(timeout=60)
        self.add_item(ItemSelect(trade_type))

class ServiceSelect(Select):
    def __init__(self):
        options = [discord.SelectOption(label=info["label"], value=key, description=info["note"]) for key, info in SERVICE_TABLE.items()]
        super().__init__(placeholder="Chọn dịch vụ bạn cần...", options=options, custom_id="service_select")

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            await create_service_ticket(interaction, self.values[0])
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`")
            except: pass

class ServiceSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(ServiceSelect())

# ══════════════════════════════════════════
# TICKET CREATION FUNCTIONS
# ══════════════════════════════════════════
async def create_order_ticket(interaction: discord.Interaction, trade_type: str, item_key: str = "other", item_label: str = "📦 Khác", seller_id: int | None = None):
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.")

        bot = interaction.client
        number     = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        _key_slug  = {"money": "money", "skeleton": "skeleton", "other": "khac"}
        channel_name = f"{_key_slug.get(item_key, 'ticket')}-{number}"

        color, type_label = (0x57F287, "🛒 MUA HÀNG") if trade_type == "sell" else (0xFEE75C, "💸 BÁN HÀNG")

        overwrites = _build_ticket_overwrites(guild, interaction.user, seller_id)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=category, topic=f"{interaction.user.id}||{trade_type}|{item_key}|open")

        embed = discord.Embed(title=f"{type_label}  •  {item_label}  •  #{number}", description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ xử lý giao dịch sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận", color=color, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="📦  Loại hàng",  value=item_label,               inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        ping_target = f"<@{seller_id}>" if seller_id else f"<@&{get_cfg_support_role()}>"
        await channel.send(f"{ping_target} | {interaction.user.mention}", embed=embed, view=TicketButtons())
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}")

        await send_log(
            interaction.client, "TICKET_CREATE", f"Ticket Tạo — {channel_name}",
            fields=[
                ("🎫 Kênh",       channel.mention,               True),
                ("🏷️ Loại",      type_label,                    True),
                ("📦 Item",       item_label,                    True),
                ("👤 Người tạo", interaction.user.mention,       True),
                ("🕐 Thời gian", created_at,                    True),
            ],
            user=interaction.user,
        )

    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`")
        except: pass

async def create_service_ticket(interaction: discord.Interaction, service_key: str):
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở!")

        info   = SERVICE_TABLE[service_key]
        bot    = interaction.client
        number = await get_next_ticket_number(bot)
        created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

        overwrites = _build_ticket_overwrites(guild, interaction.user)
        category   = discord.utils.get(guild.categories, id=get_cfg_category())
        channel    = await guild.create_text_channel(name=f"ticket-{number}", overwrites=overwrites, category=category, topic=f"{interaction.user.id}||service|{service_key}|open")

        embed = discord.Embed(title=f"{info['type_label']}  •  #{number}", description=f"Xin chào {interaction.user.mention}! 👋\nStaff sẽ hỗ trợ bạn sớm nhất có thể.\n🟡 **Trạng thái:** Đang chờ staff nhận", color=info["color"], timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤  Người dùng", value=interaction.user.mention, inline=True)
        embed.add_field(name="🕐  Thời gian",  value=created_at,               inline=True)
        embed.add_field(name="📦  Dịch vụ",   value=info["label"],             inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System", icon_url=guild.icon.url if guild.icon else None)

        await channel.send(f"<@&{get_cfg_support_role()}> | {interaction.user.mention}", embed=embed, view=TicketButtons())
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}")
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`")
        except: pass

# ══════════════════════════════════════════
# PANEL VIEW
# ══════════════════════════════════════════
class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Mua hàng", emoji="🛒", style=discord.ButtonStyle.green, custom_id="panel_buy")
    async def buy(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message("🛒 **Bạn muốn mua loại nào?**", view=ItemSelectView(trade_type="sell"), ephemeral=True)
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except: pass

    @discord.ui.button(label="Bán hàng", emoji="💸", style=discord.ButtonStyle.blurple, custom_id="panel_sell")
    async def sell(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message("💸 **Bạn muốn bán loại nào?**", view=ItemSelectView(trade_type="buy"), ephemeral=True)
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except: pass

    @discord.ui.button(label="Dịch Vụ", emoji="🎮", style=discord.ButtonStyle.grey, custom_id="panel_service")
    async def service(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_message("🎮 **Bạn cần dịch vụ nào?**", view=ServiceSelectView(), ephemeral=True)
        except Exception as e:
            try: await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except: pass

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
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
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
        if not is_staff_member(ctx.author): return await ctx.reply("❌ Bạn không có quyền.")
        if not (ctx.channel.topic and "|" in ctx.channel.topic): return await ctx.reply("❌ Đây không phải kênh ticket.")
        if not amount_str: return await ctx.reply("❌ Thiếu số tiền! Ví dụ: `.done 50k`, `.done 1tr5`")

        amount = parse_amount(amount_str)
        if amount is None or amount <= 0:
            return await ctx.reply(f"❌ Số tiền `{amount_str}` không hợp lệ!")

        parts = ctx.channel.topic.split("|")
        try: user_id = int(parts[0]) if parts[0].isdigit() else None
        except: user_id = None
        if not user_id: return await ctx.reply("❌ Không đọc được thông tin buyer từ ticket.")

        trade_type = parts[2] if len(parts) > 2 else None
        if trade_type not in ("sell", "buy"): return await ctx.reply("ℹ️ Ticket dịch vụ / hỗ trợ không tính vào đơn mua hàng.")

        buyer = ctx.guild.get_member(user_id)
        if not buyer: return await ctx.reply(f"❌ Không tìm thấy buyer (ID: `{user_id}`).")

        data = load_data()
        completed_key = f"completed_{ctx.channel.id}"
        if data.get(completed_key):
            total = get_user_total_spent(user_id)
            return await ctx.reply(f"⚠️ Đơn này đã hoàn thành rồi!\nBuyer: {buyer.mention} — tổng: **{fmt_amount(total)}**")

        data[completed_key] = True
        save_data(data)

        new_total = add_user_spent(user_id, amount)

        # Lưu lịch sử đơn
        parts2 = ctx.channel.topic.split("|")
        opened_at = None
        try:
            # topic format: user_id||trade_type|item_key|open
            # lấy created_at của channel làm opened_at
            opened_at = ctx.channel.created_at.isoformat()
        except Exception:
            opened_at = datetime.now(timezone.utc).isoformat()
        save_ticket_record({
            "ticket_name": ctx.channel.name,
            "user_id":     user_id,
            "username":    _uname_plain(buyer),
            "amount":      amount,
            "opened_at":   opened_at,
            "closed_at":   datetime.now(timezone.utc).isoformat(),
            "staff":       _uname_plain(ctx.author),
            "staff_id":    ctx.author.id,
        })

        from cogs.admin import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(ctx.guild, buyer, new_total)
        buy_roles = get_buy_roles()

        embed = discord.Embed(title="✅ Hoàn Thành Đơn", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Buyer",       value=buyer.mention,                  inline=True)
        embed.add_field(name="💵 Đơn này",     value=f"**{fmt_amount(amount)}**",    inline=True)
        embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(new_total)}**", inline=True)
        if role_cfg:
            role_obj = ctx.guild.get_role(role_cfg.get("role_id", 0))
            embed.add_field(name="🏆 Role hiện tại", value=role_obj.mention if role_obj else f"**{role_cfg.get('label','?')}**", inline=False)
        embed.set_footer(text=f"Xác nhận bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

        await send_log(
            ctx.bot, "TICKET_DONE", f"Hoàn Thành Đơn — {ctx.channel.name}",
            fields=[
                ("👤 Buyer",        buyer.mention,                  True),
                ("💵 Đơn này",      fmt_amount(amount),             True),
                ("💰 Tổng đã mua",  fmt_amount(new_total),          True),
                ("🎫 Ticket",       ctx.channel.mention,            True),
                ("✍️ Xác nhận bởi", ctx.author.mention,             True),
            ],
            user=ctx.author,
        )

    @commands.command(name="orderbase")
    async def orderbase_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return
        try: await ctx.message.delete()
        except: pass
        embed = discord.Embed(
            title="# Nhận Làm Base Village Trong <:emoji_17:1483684359415267449>",
            description="**Giá Chỉ Từ 20-35m Tùy Theo Base Mà Ae Chọn**\n\n**Cam Kết:**\n<:emoji_17:1483684359415267449> •Tự Tìm Chỗ Xây Base Lun Nhé Ae\n<:emoji_17:1483684359415267449> •Base Có Chỗ Nhân Giống Village\n<:emoji_17:1483684359415267449> •Bảo Hành 8h Kể Từ Khi Mua\n<:emoji_17:1483684359415267449> •Nếu Bị Raid Trong Giờ Bảo Hành Sẽ Đc Hoàn Tiền\n\n**Nên Ae Yên Tâm Mà Thuê** ✅\n\n**Ai Muốn Có 1 Base Village Tuyệt Vời Mà Còn Rẻ Thì Hãy Tạo <#1464415587378659564> Để Có 1 Base Xịn Nhé**",
            color=0xE67E22, timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="💰 DoанBaoNgoc-Stock  •  TuyTam Store")
        await ctx.send("<@&1464411190808805540> sorry ping", embed=embed)

    # ── SLASH COMMANDS ──
    @discord.app_commands.command(name="close", description="Đóng ticket hiện tại")
    async def slash_close(self, interaction: discord.Interaction):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        if not (interaction.channel.topic and "|" in interaction.channel.topic):
            return await interaction.response.send_message("❌ Đây không phải kênh ticket.")
        await interaction.response.send_message("🔒 Đang đóng ticket...")
        await _close_ticket(interaction.channel, self.bot, closer=interaction.user)

    @discord.app_commands.command(name="done", description="Hoàn thành đơn hàng trong ticket")
    @discord.app_commands.describe(amount="Số tiền giao dịch, vd: 50k, 1tr5, 200000")
    async def slash_done(self, interaction: discord.Interaction, amount: str):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.")
        if not (interaction.channel.topic and "|" in interaction.channel.topic):
            return await interaction.response.send_message("❌ Đây không phải kênh ticket.")
        parsed = parse_amount(amount)
        if not parsed or parsed <= 0:
            return await interaction.response.send_message(f"❌ Số tiền `{amount}` không hợp lệ!")
        parts = interaction.channel.topic.split("|")
        try: user_id = int(parts[0]) if parts[0].isdigit() else None
        except: user_id = None
        if not user_id:
            return await interaction.response.send_message("❌ Không đọc được thông tin buyer.")
        trade_type = parts[2] if len(parts) > 2 else None
        if trade_type not in ("sell", "buy"):
            return await interaction.response.send_message("ℹ️ Ticket dịch vụ không tính đơn hàng.")
        buyer = interaction.guild.get_member(user_id)
        if not buyer:
            return await interaction.response.send_message(f"❌ Không tìm thấy buyer (ID: `{user_id}`).")
        data = load_data()
        completed_key = f"completed_{interaction.channel.id}"
        if data.get(completed_key):
            total = get_user_total_spent(user_id)
            return await interaction.response.send_message(f"⚠️ Đơn này đã hoàn thành rồi!\nTổng: **{fmt_amount(total)}**")
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
    @commands.command(name="thongke", aliases=["tk", "stats"])
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
        embed.set_footer(text=f"Tạo bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════════
    # ADMIN: GÁN CATEGORY CHO SELLER (.setsl)
    # ══════════════════════════════════════════
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
