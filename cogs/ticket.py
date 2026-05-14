"""
cogs/ticket.py — Ticket system: panel, views, modals, close/done logic.
"""

import os
import io
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select

from core.data import (
    ADMIN_IDS, FEEDBACK_CHANNEL_ID, TRANSCRIPT_CHANNEL_ID,
    get_cfg_category, get_cfg_support_role, get_cfg_seller_role,
    get_cfg_counter_channel, get_cfg_proof_channel, get_cfg_balance_channel,
    get_sellers, get_panel_channel_id, save_panel_channel_id,
    get_qr_path, save_qr_path, get_buy_roles, get_user_total_spent,
    add_user_spent, get_ticket_note, add_ticket_note, save_rating,
    load_data, save_data, parse_amount, fmt_amount, is_staff_member,
    _uname, _uname_plain, can_use_dangerous_cmd, QR_FILE,
)

BOT_VERSION = "3.3.5"

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
    channel = bot.get_channel(ch_id)
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
    channel = bot.get_channel(ch_id)
    if not channel: return
    try:
        await channel.purge(limit=5)
        await channel.send(f"ticket:{number:03d}")
    except: pass

async def get_next_ticket_number(bot) -> str:
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

    transcript_ch = bot_instance.get_channel(TRANSCRIPT_CHANNEL_ID)
    if transcript_ch:
        file2 = discord.File(io.BytesIO(html.encode("utf-8")), filename=f"transcript-{channel.name}.html")
        await transcript_ch.send(embed=embed, file=file2)

    notes = get_ticket_note(channel.id)
    if notes and transcript_ch:
        note_text = "\n".join([f"**{n['author']}:** {n['note']}" for n in notes])
        note_embed = discord.Embed(title="📝 Ghi Chú Nội Bộ", description=note_text, color=0xFEE75C, timestamp=datetime.now(timezone.utc))
        note_embed.set_footer(text=f"Ticket: {ticket_name}")
        await transcript_ch.send(embed=note_embed)

    await channel.delete()

    if creator:
        try:
            rate_embed = discord.Embed(
                title="⭐ Đánh Giá Dịch Vụ",
                description=f"Ticket `{ticket_name}` của bạn đã được đóng.\nHãy đánh giá dịch vụ để giúp chúng tôi cải thiện!",
                color=0xF1C40F, timestamp=datetime.now(timezone.utc)
            )
            await creator.send(embed=rate_embed, view=RatingView(ticket_name, creator.id))
        except discord.Forbidden:
            pass

# ══════════════════════════════════════════
# RATING MODAL / VIEW
# ══════════════════════════════════════════
class RatingModal(Modal):
    def __init__(self, ticket_name: str, user_id: int):
        super().__init__(title="⭐ Đánh Giá Dịch Vụ")
        self.ticket_name = ticket_name
        self.user_id = user_id
        self.bot_ref = None  # set bởi RatingView

    stars_input = TextInput(label="Số sao (1-5)", placeholder="Nhập số từ 1 đến 5", min_length=1, max_length=1)
    comment     = TextInput(label="Nhận xét (tuỳ chọn)", placeholder="Dịch vụ tốt, staff nhiệt tình...", style=discord.TextStyle.paragraph, required=False, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars = int(self.stars_input.value)
            if stars < 1 or stars > 5: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Số sao không hợp lệ! Nhập từ 1 đến 5.", ephemeral=True)
        save_rating(self.ticket_name, self.user_id, stars)
        star_display = "⭐" * stars + "☆" * (5 - stars)
        log = interaction.client.get_channel(FEEDBACK_CHANNEL_ID)
        if log:
            embed = discord.Embed(title="⭐ Đánh Giá Mới", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Ticket",    value=f"`{self.ticket_name}`",  inline=True)
            embed.add_field(name="User",      value=f"<@{self.user_id}>",     inline=True)
            embed.add_field(name="Đánh giá", value=star_display,             inline=True)
            if self.comment.value: embed.add_field(name="Nhận xét", value=self.comment.value, inline=False)
            await log.send(embed=embed)
        await interaction.response.send_message(f"✅ Cảm ơn bạn đã đánh giá! {star_display}", ephemeral=True)

class RatingView(View):
    def __init__(self, ticket_name: str, user_id: int):
        super().__init__(timeout=300)
        self.ticket_name = ticket_name
        self.user_id     = user_id

    @discord.ui.button(label="⭐ Đánh giá dịch vụ", style=discord.ButtonStyle.blurple)
    async def rate(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Chỉ người tạo ticket mới được đánh giá.", ephemeral=True)
        await interaction.response.send_modal(RatingModal(self.ticket_name, self.user_id))

# ══════════════════════════════════════════
# MODALS
# ══════════════════════════════════════════
class AddStaffModal(Modal):
    def __init__(self):
        super().__init__(title="📎 Thêm Staff vào Ticket")
    user_id_input = TextInput(label="ID của Staff", placeholder="Nhập User ID", min_length=15, max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid    = int(self.user_id_input.value.strip())
            member = interaction.guild.get_member(uid)
            if not member:
                return await interaction.response.send_message("❌ Không tìm thấy member này.", ephemeral=True)
            overwrite = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
            await interaction.channel.set_permissions(member, overwrite=overwrite)
            await interaction.response.send_message(f"✅ Đã thêm {member.mention} vào ticket!")
        except ValueError:
            await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

class NoteModal(Modal):
    def __init__(self, channel_id: int):
        super().__init__(title="📝 Thêm Ghi Chú Nội Bộ")
        self.channel_id = channel_id
    note_input = TextInput(label="Nội dung ghi chú", placeholder="Ghi chú chỉ staff thấy...", style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        add_ticket_note(self.channel_id, str(interaction.user), self.note_input.value)
        embed = discord.Embed(title="📝 Ghi Chú Nội Bộ", description=self.note_input.value, color=0xFEE75C, timestamp=datetime.now(timezone.utc))
        embed.set_footer(text=f"Bởi {interaction.user} • Chỉ staff thấy")
        await interaction.response.send_message(embed=embed)

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
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
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
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
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
            return await interaction.followup.send("❌ Bạn đang có ticket mở! Vui lòng đóng ticket cũ trước.", ephemeral=True)

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
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)

    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra khi tạo ticket: `{e}`", ephemeral=True)
        except: pass

async def create_service_ticket(interaction: discord.Interaction, service_key: str):
    guild = interaction.guild
    try:
        if await has_ticket(guild, interaction.user):
            return await interaction.followup.send("❌ Bạn đang có ticket mở!", ephemeral=True)

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
        await interaction.followup.send(f"✅ Ticket đã tạo! Vào đây: {channel.mention}", ephemeral=True)
    except Exception as e:
        try: await interaction.followup.send(f"❌ Có lỗi xảy ra: `{e}`", ephemeral=True)
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

    @discord.ui.button(label="Mua", emoji="🛒", style=discord.ButtonStyle.blurple, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        try:
            for item in self.children:
                if item.custom_id == "claim_ticket":
                    item.disabled = True; item.label = f"Claimed: {_uname_plain(interaction.user)}"; item.emoji = "✅"; break
            await interaction.response.defer()
            await interaction.message.edit(view=self)
            await interaction.followup.send(f"✅ {interaction.user.mention} đã nhận ticket này!")
        except Exception as e:
            try: await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)
            except: pass

    @discord.ui.button(label="Add Staff", emoji="📎", style=discord.ButtonStyle.grey, custom_id="add_staff")
    async def add_staff(self, interaction: discord.Interaction, button: Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        await interaction.response.send_modal(AddStaffModal())

    @discord.ui.button(label="Ghi chú", emoji="📝", style=discord.ButtonStyle.grey, custom_id="add_note")
    async def add_note(self, interaction: discord.Interaction, button: Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        await interaction.response.send_modal(NoteModal(interaction.channel.id))

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

    @discord.ui.button(label="Gửi QR", emoji="📱", style=discord.ButtonStyle.green, custom_id="send_qr")
    async def send_qr(self, interaction: discord.Interaction, button: Button):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        qr_path = get_qr_path()
        if not qr_path or not os.path.exists(qr_path):
            return await interaction.response.send_message("❌ Chưa có QR! Admin cài QR qua `.settings` trước.", ephemeral=True)
        file  = discord.File(qr_path, filename="qr.png")
        embed = discord.Embed(title="📱  Mã QR Thanh Toán", description="> 🏦 **MB Bank** — `0702557706` — HOVANBUT\n> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n> ⚠️ Ghi rõ nội dung: `[tên MC] mua [item]`", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.set_image(url="attachment://qr.png")
        embed.set_footer(text=f"Gửi bởi {_uname_plain(interaction.user)}")
        await interaction.response.send_message(embed=embed, file=file)

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

        from cogs.admin import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(ctx.guild, buyer, new_total)
        buy_roles = get_buy_roles()

        embed = discord.Embed(title="✅ Hoàn Thành Đơn", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Buyer",       value=buyer.mention,               inline=True)
        embed.add_field(name="💵 Đơn này",     value=f"**{fmt_amount(amount)}**", inline=True)
        embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(new_total)}**", inline=True)
        if role_cfg:
            role_obj = ctx.guild.get_role(role_cfg.get("role_id", 0))
            embed.add_field(name="🏆 Role hiện tại", value=role_obj.mention if role_obj else f"**{role_cfg.get('label','?')}**", inline=False)
        embed.set_footer(text=f"Xác nhận bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    @commands.command(name="addnote")
    async def addnote_cmd(self, ctx, *, note: str = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Bạn không có quyền.")
        if not (ctx.channel.topic and "|" in ctx.channel.topic): return await ctx.reply("❌ Đây không phải kênh ticket.")
        if not note: return await ctx.reply("❌ Thiếu nội dung! Ví dụ: `.addnote khách đã chuyển tiền`")
        add_ticket_note(ctx.channel.id, str(ctx.author), note)
        embed = discord.Embed(title="📝 Ghi Chú Nội Bộ", description=note, color=0xFEE75C, timestamp=datetime.now(timezone.utc))
        embed.set_footer(text=f"Bởi {ctx.author} • Chỉ staff thấy")
        await ctx.reply(embed=embed)
        try: await ctx.message.delete()
        except: pass

    @commands.command(name="ratings")
    async def ratings_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return
        data    = load_data()
        ratings = data.get("ratings", [])
        if not ratings: return await ctx.reply("Chưa có đánh giá nào.")
        total = len(ratings)
        avg   = sum(r["stars"] for r in ratings) / total
        dist  = {i: sum(1 for r in ratings if r["stars"] == i) for i in range(1, 6)}
        bar   = ""
        for s in range(5, 0, -1):
            count  = dist[s]
            filled = int((count / total) * 10) if total > 0 else 0
            bar += f"{'⭐'*s}: {'█'*filled}{'░'*(10-filled)} {count}\n"
        embed = discord.Embed(title="⭐ Thống Kê Đánh Giá", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Tổng đánh giá", value=str(total),           inline=True)
        embed.add_field(name="Trung bình",    value=f"{avg:.1f} ⭐",      inline=True)
        embed.add_field(name="Phân bố",       value=f"```{bar}```",       inline=False)
        await ctx.reply(embed=embed)

    @commands.command(name="addseller")
    async def addseller_cmd(self, ctx, user_id: str = None, *, username: str = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
        if not user_id or not username: return await ctx.reply("❌ Cú pháp: `.addseller <ID> <tên hiển thị>`")
        try: seller_id = int(user_id.strip())
        except ValueError: return await ctx.reply("❌ ID không hợp lệ!")
        sellers = get_sellers()
        if any(s["id"] == seller_id for s in sellers): return await ctx.reply(f"❌ Seller ID `{seller_id}` đã có rồi!")
        sellers.append({"id": seller_id, "label": username.strip()})
        from core.data import save_sellers
        save_sellers(sellers)
        embed = discord.Embed(title="✅ Đã Thêm Seller", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏷️ Tên hiển thị", value=f"**{username.strip()}**",   inline=True)
        embed.add_field(name="📋 Tổng sellers",  value=f"**{len(sellers)}** người", inline=True)
        await ctx.reply(embed=embed)

    @commands.command(name="removeseller", aliases=["delseller", "xoaseller"])
    async def removeseller_cmd(self, ctx, *, target: str = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
        if not target: return await ctx.reply("❌ Cú pháp: `.removeseller <ID hoặc tên>`")
        sellers = get_sellers()
        found   = next((s for s in sellers if str(s["id"]) == target.strip() or s["label"].lower() == target.strip().lower()), None)
        if not found: return await ctx.reply(f"❌ Không tìm thấy seller `{target}`.")
        sellers.remove(found)
        from core.data import save_sellers
        save_sellers(sellers)
        embed = discord.Embed(title="🗑️ Đã Xoá Seller", color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏷️ Seller đã xoá", value=f"**{found['label']}** (`{found['id']}`)", inline=False)
        await ctx.reply(embed=embed)

    @commands.command(name="listseller", aliases=["sellers", "danhsachseller"])
    async def listseller_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
        sellers = get_sellers()
        embed   = discord.Embed(title="📋 Danh Sách Seller", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        if sellers:
            lines = [f"`{i+1}.` **{s['label']}** — <@{s['id']}>" for i, s in enumerate(sellers)]
            embed.description = "\n".join(lines)
            embed.set_footer(text=f"Tổng: {len(sellers)} seller")
        else:
            embed.description = "*(Chưa có seller nào)*\nThêm bằng `.addseller <ID> <tên>`"
        await ctx.reply(embed=embed)

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


async def setup(bot):
    await bot.add_cog(TicketCog(bot))