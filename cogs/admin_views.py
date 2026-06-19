"""
cogs/admin_views.py — UI Views, Modals, Selects cho AdminCog.
Tách từ admin.py để giảm kích thước file.
"""
"""
cogs/admin.py — Settings, setup server, sv/giaset, lệnh mod, slash mod commands.
"""

import re as _re
import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select

from cogs.logger import send_log
from core.data import (
    ADMIN_IDS, get_cfg_category, get_cfg_support_role, get_cfg_seller_role,
    get_cfg_counter_channel, get_cfg_legit_channel,
    get_cfg_proof_channel, get_cfg_ai_channel, get_cfg_font, set_cfg_font,
    save_cfg, load_data, save_data, get_buy_roles, save_buy_roles,
    get_user_total_spent, add_user_spent, get_price_sections, save_price_sections,
    can_use_dangerous_cmd, parse_amount, fmt_amount, _uname, _uname_plain,
    get_or_fetch_channel,
    get_ticket_type_role, set_ticket_type_role, get_all_ticket_type_roles,
    get_ticket_role_ids, set_ticket_role_ids, get_all_ticket_multi_roles,
    BUILDER_BASE_ROLE_ID,
)

BOT_VERSION = "4.0.0"
BOT_UPDATED = "2026-05-30"

# ══════════════════════════════════════════
# FONT UTILS
# ══════════════════════════════════════════
_FONT_MAPS = {
    "bold":           {**{chr(ord('A')+i): chr(0x1D400+i) for i in range(26)}, **{chr(ord('a')+i): chr(0x1D41A+i) for i in range(26)}, **{str(i): chr(0x1D7CE+i) for i in range(10)}},
    "bold_italic":    {**{chr(ord('A')+i): chr(0x1D468+i) for i in range(26)}, **{chr(ord('a')+i): chr(0x1D482+i) for i in range(26)}},
    "sans_bold":      {**{chr(ord('A')+i): chr(0x1D5D4+i) for i in range(26)}, **{chr(ord('a')+i): chr(0x1D5EE+i) for i in range(26)}, **{str(i): chr(0x1D7EC+i) for i in range(10)}},
    "script":         {**{chr(ord('A')+i): chr(0x1D4D0+i) for i in range(26)}, **{chr(ord('a')+i): chr(0x1D4EA+i) for i in range(26)}},
    "double":         {**{chr(ord('A')+i): chr(0x1D538+i) for i in range(26)}, **{chr(ord('a')+i): chr(0x1D552+i) for i in range(26)}},
    "math_bold_serif":{**{chr(ord('A')+i): chr(0x1D400+i) for i in range(26)}, **{chr(ord('a')+i): chr(0x1D41A+i) for i in range(26)}, **{str(i): chr(0x1D7CE+i) for i in range(10)}},
    "normal": {},
}
_FONT_MAPS["script"].update({"B":"ℬ","E":"ℰ","F":"ℱ","H":"ℋ","I":"ℐ","L":"ℒ","M":"ℳ","R":"ℛ","e":"ℯ","g":"ℊ","o":"ℴ"})
_FONT_MAPS["double"].update({"C":"ℂ","H":"ℍ","N":"ℕ","P":"ℙ","Q":"ℚ","R":"ℝ","Z":"ℤ"})

FONT_LABELS = {
    "normal": "Thường (giữ nguyên)",
    "bold": "𝐁𝐨𝐥𝐝  —  𝐐𝐮𝐢𝐞𝐭 𝐒𝐜𝐡𝐞𝐦𝐚𝐭𝐢𝐜𝐬",
    "bold_italic": "𝑩𝒐𝒍𝒅 𝑰𝒕𝒂𝒍𝒊𝒄  —  𝑸𝒖𝒊𝒆𝒕 𝑺𝒄𝒉𝒆𝒎𝒂𝒕𝒊𝒄𝒔",
    "sans_bold": "𝗦𝗮𝗻𝘀 𝗕𝗼𝗹𝗱  —  𝗤𝘂𝗶𝗲𝘁 𝗦𝗰𝗵𝗲𝗺𝗮𝘁𝗶𝗰𝘀",
    "script": "𝒮𝒸𝓇𝒾𝓅𝓉  —  𝒬𝓊𝒾ℯ𝓉 𝒮𝒸𝒽ℯ𝓂𝒶𝓉𝒾𝒸𝓈",
    "double": "𝔻𝕠𝕦𝕓𝕝𝕖  —  ℚ𝕦𝕚𝕖𝕥 𝕊𝕔𝕙𝕖𝕞𝕒𝕥𝕚𝕔𝕤",
    "math_bold_serif": "𝐌𝐚𝐭𝐡 𝐁𝐨𝐥𝐝 𝐒𝐞𝐫𝐢𝐟  —  𝐐𝐮𝐢𝐞𝐭 𝐒𝐜𝐡𝐞𝐦𝐚𝐭𝐢𝐜𝐬",
}

def _apply_font(text: str, font: str) -> str:
    if font == "normal" or font not in _FONT_MAPS: return text
    return "".join(_FONT_MAPS[font].get(c, c) for c in text)

def _strip_unicode_font(text: str) -> str:
    ranges = [(0x1D400,0x1D419,ord('A')),(0x1D41A,0x1D433,ord('a')),(0x1D468,0x1D481,ord('A')),(0x1D482,0x1D49B,ord('a')),(0x1D4D0,0x1D4E9,ord('A')),(0x1D4EA,0x1D503,ord('a')),(0x1D538,0x1D551,ord('A')),(0x1D552,0x1D56B,ord('a')),(0x1D5D4,0x1D5ED,ord('A')),(0x1D5EE,0x1D607,ord('a')),(0x1D7CE,0x1D7D7,ord('0')),(0x1D7EC,0x1D7F5,ord('0'))]
    special = {'ℬ':'B','ℰ':'E','ℱ':'F','ℋ':'H','ℐ':'I','ℒ':'L','ℳ':'M','ℛ':'R','ℯ':'e','ℊ':'g','ℴ':'o','ℂ':'C','ℍ':'H','ℕ':'N','ℙ':'P','ℚ':'Q','ℝ':'R','ℤ':'Z','\u212F':'e','\u210A':'g','\u2134':'o','\u212C':'B','\u2130':'E','\u2131':'F','\u210B':'H','\u2110':'I','\u2112':'L','\u2133':'M','\u211B':'R'}
    result = []
    for c in text:
        if c in special: result.append(special[c]); continue
        cp, converted = ord(c), False
        for start, end, base in ranges:
            if start <= cp <= end: result.append(chr(base + (cp - start))); converted = True; break
        if not converted: result.append(c)
    return ''.join(result)

def _detect_channel_parts(name: str):
    icon_m = _re.match(r'^((?:[\U00010000-\U0010FFFF]|[\u2600-\u26FF]|[\u2700-\u27BF]|[\U0001F300-\U0001F9FF])+)', name)
    icon   = icon_m.group(1) if icon_m else ""
    rest   = name[len(icon):].lstrip()
    sep    = ""
    sep_m  = _re.match(r'^([•·\-–—|])\s*', rest)
    if sep_m: sep = sep_m.group(1); rest = rest[sep_m.end():]
    rest_plain = _strip_unicode_font(rest)
    num_m = _re.search(r'[\-–](\d+)$', rest_plain)
    trailing_num, base_text = "", rest_plain
    if num_m: trailing_num = num_m.group(0); base_text = rest_plain[:num_m.start()]
    return {"icon": icon, "sep": sep, "base_text": base_text, "trailing_num": trailing_num, "original": name}

def _rebuild_name(parts: dict, new_base: str, font: str = "normal") -> str:
    styled = _apply_font(new_base, font)
    result = parts["icon"]
    if parts["icon"] and parts["sep"]: result += parts["sep"]
    return (result + styled + parts["trailing_num"]).strip()

# ══════════════════════════════════════════
# AUTO GIVE BUY ROLES
# ══════════════════════════════════════════
async def auto_give_buy_roles(guild: discord.Guild, member: discord.Member, total_spent: int):
    buy_roles = get_buy_roles()
    if not buy_roles: return None
    target_cfg = None
    for r in reversed(buy_roles):
        min_a = r.get("min_amount", 0)
        max_a = r.get("max_amount")
        if total_spent >= min_a and (max_a is None or total_spent < max_a):
            target_cfg = r; break
    for cfg in buy_roles:
        role = guild.get_role(cfg.get("role_id", 0))
        if not role: continue
        if target_cfg and cfg["role_id"] == target_cfg["role_id"]:
            if role not in member.roles:
                try: await member.add_roles(role, reason=f"Auto buyer role — {fmt_amount(total_spent)}")
                except Exception as e: print(f"[BUY_ROLE] Lỗi give {role.name}: {e}")
        else:
            if role in member.roles:
                try: await member.remove_roles(role, reason=f"Đổi buyer role — {fmt_amount(total_spent)}")
                except Exception as e: print(f"[BUY_ROLE] Lỗi xoá {role.name}: {e}")
    return target_cfg

# ══════════════════════════════════════════
# SV / GIASET
# ══════════════════════════════════════════
_DEFAULT_PRICE_SECTIONS = [
    {"key":"steam","name":"🎮  Steam","content":"**Giá stock:**\n> - **Dota 2 Immortal: 10.000 VNĐ**\n> - **CS:GO Prime: 20.000 VNĐ**"},
    {"key":"robux","name":"🟡  Roblox Robux","content":"**Giá stock:**\n> - **400 Robux: 25.000 VNĐ**\n> - **800 Robux: 45.000 VNĐ**"},
    {"key":"nitro","name":"💎  Discord Nitro","content":"**Giá stock:**\n> - **1 tháng: 35.000 VNĐ**\n> - **3 tháng: 90.000 VNĐ**"},
    {"key":"chatgpt","name":"🤖  ChatGPT Plus","content":"**Giá stock:**\n> - **1 tháng: 150.000 VNĐ**"},
    {"key":"capcut","name":"✂️  CapCut Pro","content":"**Giá stock:**\n> - **1 tháng: 15.000 VNĐ**"},
    {"key":"canva","name":"🎨  Canva","content":"**Giá stock:**\n> - **2 tháng pro: 15.000 VNĐ**"},
    {"key":"youtube","name":"▶️  YouTube Premium","content":"**Giá stock:**\n> - **15.000 VNĐ/Tháng**"},
]

def build_sv_embed() -> discord.Embed:
    sections = get_price_sections()
    if not sections: sections = _DEFAULT_PRICE_SECTIONS
    embed = discord.Embed(title="🏪  TuyTam Store — Bảng Giá", color=0x5865F2, timestamp=datetime.now(timezone.utc))
    for sec in sections:
        embed.add_field(name=sec["name"], value=sec["content"], inline=False)
    embed.set_footer(text="TuyTam Store  •  .sv để xem lại bất cứ lúc nào")
    return embed

class EditPriceModal(Modal):
    def __init__(self, section: dict, index: int):
        super().__init__(title=f"✏️ Sửa: {section['name'][:40]}")
        self.section = section; self.index = index
        self.name_input    = TextInput(label="Tên mục", default=section["name"], max_length=100)
        self.content_input = TextInput(label="Nội dung", default=section["content"], style=discord.TextStyle.paragraph, max_length=1024)
        self.add_item(self.name_input); self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        if self.index >= len(sections): return await interaction.response.send_message("❌ Mục không tồn tại.")
        sections[self.index]["name"]    = self.name_input.value.strip()
        sections[self.index]["content"] = self.content_input.value.strip()
        save_price_sections(sections)
        await interaction.response.send_message(f"✅ Đã cập nhật **{sections[self.index]['name']}**!")

class EditPriceSectionSelect(Select):
    def __init__(self):
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        options  = [discord.SelectOption(label=sec["name"][:100], value=str(i), description=f"Key: {sec['key']}") for i, sec in enumerate(sections)]
        super().__init__(placeholder="Chọn mục muốn sửa...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        idx      = int(self.values[0])
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        if idx >= len(sections): return await interaction.response.send_message("❌ Mục không tồn tại.")
        await interaction.response.send_modal(EditPriceModal(sections[idx], idx))

class AddPriceSectionModal(Modal, title="➕ Thêm Mục Giá Mới"):
    key_input     = TextInput(label="Key (chữ thường, không dấu)", placeholder="vd: spotify", max_length=30)
    name_input    = TextInput(label="Tên mục (có thể chứa emoji)", placeholder="vd: 🎵  Spotify", max_length=100)
    content_input = TextInput(label="Nội dung", placeholder="> - **Gói 1 tháng: 30.000 VNĐ**", style=discord.TextStyle.paragraph, max_length=1024)

    async def on_submit(self, interaction: discord.Interaction):
        key      = self.key_input.value.strip().lower().replace(" ", "_")
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        if any(s["key"] == key for s in sections): return await interaction.response.send_message(f"❌ Key `{key}` đã tồn tại!")
        sections.append({"key": key, "name": self.name_input.value.strip(), "content": self.content_input.value.strip()})
        save_price_sections(sections)
        await interaction.response.send_message(f"✅ Đã thêm mục **{self.name_input.value.strip()}**!")

class DeletePriceSectionSelect(Select):
    def __init__(self):
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        options  = [discord.SelectOption(label=sec["name"][:100], value=str(i), description=f"Key: {sec['key']}") for i, sec in enumerate(sections)]
        super().__init__(placeholder="Chọn mục muốn xoá...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        idx      = int(self.values[0])
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        if idx >= len(sections): return await interaction.response.send_message("❌ Mục không tồn tại.")
        removed = sections.pop(idx)
        save_price_sections(sections)
        await interaction.response.send_message(f"🗑️ Đã xoá mục **{removed['name']}**.")

class DeletePriceSectionView(View):
    def __init__(self): super().__init__(timeout=60); self.add_item(DeletePriceSectionSelect())

class PriceManagerView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(EditPriceSectionSelect())

    @discord.ui.button(label="➕ Thêm mục mới", style=discord.ButtonStyle.success, row=1)
    async def add_section(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.")
        await interaction.response.send_modal(AddPriceSectionModal())

    @discord.ui.button(label="🗑️ Xoá mục", style=discord.ButtonStyle.danger, row=1)
    async def del_section(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.")
        await interaction.response.send_message("Chọn mục muốn xoá:", view=DeletePriceSectionView())

    @discord.ui.button(label="🔄 Reset về mặc định", style=discord.ButtonStyle.grey, row=1)
    async def reset_sections(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.")
        save_price_sections(_DEFAULT_PRICE_SECTIONS)
        await interaction.response.send_message("✅ Đã reset bảng giá về mặc định!")

    @discord.ui.button(label="👁️ Xem trước .sv", style=discord.ButtonStyle.blurple, row=2)
    async def preview(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(embed=build_sv_embed())

# ══════════════════════════════════════════
# SETTINGS VIEW
# ══════════════════════════════════════════
class SettingsView(View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=180)
        self.guild = guild

    async def _send_channel_select(self, interaction, cfg_key, title, description):
        channels = sorted(interaction.guild.text_channels, key=lambda c: c.position)

        if len(channels) <= 25:
            options = [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id)) for ch in channels]
            select = ChannelConfigSelect(cfg_key=cfg_key, title=title, options=options)
            view   = View(timeout=60); view.add_item(select)
            return await interaction.response.send_message(f"📌 **{description}**\nChọn kênh:", view=view)

        # >25 kênh: phân trang theo category
        groups: dict[str, list] = {}
        for ch in channels:
            cat_name = ch.category.name if ch.category else "(Không có category)"
            groups.setdefault(cat_name, []).append(ch)

        # Tạo class động để truyền cfg_key/title vào callback
        class _PagedCfgChannelSelect(Select):
            def __init__(self_inner, opts):
                super().__init__(placeholder=f"Chọn kênh cho {title}…", options=opts)
                self_inner.cfg_key = cfg_key
                self_inner.title   = title
            async def callback(self_inner, inter: discord.Interaction):
                if inter.user.id not in ADMIN_IDS:
                    return await inter.response.send_message("❌ Chỉ admin.")
                ch_id = int(self_inner.values[0])
                save_cfg(self_inner.cfg_key, ch_id)
                await inter.response.send_message(f"✅ Đã cài **{self_inner.title}** → <#{ch_id}>")

        v = View(timeout=60)
        v.add_item(_PagedChannelCategorySelect(
            groups, _PagedCfgChannelSelect,
            placeholder="Chọn nhóm kênh…",
        ))
        await interaction.response.send_message(
            f"📌 **{description}**\nServer có **{len(channels)}** kênh — chọn nhóm trước:", view=v
        )

    async def _send_role_select(self, interaction, cfg_key, title):
        options = [discord.SelectOption(label=r.name[:100], value=str(r.id)) for r in sorted(self.guild.roles, key=lambda r: -r.position) if r.name != "@everyone"][:25]
        select  = RoleConfigSelect(cfg_key=cfg_key, title=title, options=options)
        view    = View(timeout=60); view.add_item(select)
        await interaction.response.send_message(f"🏷️ **{title}**\nChọn role:", view=view)

    async def _send_category_select(self, interaction, cfg_key, title, description):
        categories = [ch for ch in interaction.guild.channels if isinstance(ch, discord.CategoryChannel)]
        categories.sort(key=lambda c: c.position)
        if not categories:
            return await interaction.response.send_message("❌ Server không có category nào.", ephemeral=True)

        class _CategorySelect(Select):
            def __init__(self_inner):
                opts = [
                    discord.SelectOption(label=cat.name[:100], value=str(cat.id))
                    for cat in categories[:25]
                ]
                super().__init__(placeholder=f"Chọn category cho {title}…", options=opts)
            async def callback(self_inner, inter: discord.Interaction):
                if inter.user.id not in ADMIN_IDS:
                    return await inter.response.send_message("❌ Chỉ admin.", ephemeral=True)
                cat_id = int(self_inner.values[0])
                save_cfg(cfg_key, cat_id)
                cat = inter.guild.get_channel(cat_id)
                cat_name = cat.name if cat else f"ID:{cat_id}"
                await inter.response.send_message(f"✅ Đã cài **{title}** → **{cat_name}**")

        v = View(timeout=60)
        v.add_item(_CategorySelect())
        await interaction.response.send_message(f"📁 **{description}**\nChọn category:", view=v)

    @discord.ui.button(label="📋 Log Channel",      style=discord.ButtonStyle.primary,   row=0)
    async def log(self,      i, b): await self._send_channel_select(i, "cfg_log_rudy",        "Log Rudy",         "Kênh log rudy — nhận toàn bộ hoạt động bot")
    @discord.ui.button(label="🎫 Ticket Category",  style=discord.ButtonStyle.secondary, row=0)
    async def cat(self,      i, b): await self._send_category_select(i, "cfg_ticket_category", "Ticket Category",  "Category chứa các ticket")
    @discord.ui.button(label="🛡️ Support Role",     style=discord.ButtonStyle.secondary, row=0)
    async def support(self,  i, b): await self._send_role_select(i, "cfg_support_role",   "Support Role")
    @discord.ui.button(label="🏪 Seller Role",      style=discord.ButtonStyle.secondary, row=1)
    async def seller(self,   i, b): await self._send_role_select(i, "cfg_seller_role",    "Seller Role")
    @discord.ui.button(label="✅ Legit Channel",    style=discord.ButtonStyle.secondary, row=1)
    async def legit(self,    i, b): await self._send_channel_select(i, "cfg_legit_channel",   "Legit Channel",    "Kênh nhận +1legit tự động")
    @discord.ui.button(label="📸 Proof Channel",   style=discord.ButtonStyle.secondary, row=2)
    async def proof(self,    i, b): await self._send_channel_select(i, "cfg_proof_channel",   "Proof Channel",    "Kênh nhận done tự động")
    @discord.ui.button(label="🤖 AI Channel",       style=discord.ButtonStyle.secondary, row=2)
    async def ai(self,       i, b): await self._send_channel_select(i, "cfg_ai_channel",      "AI Channel",       "Kênh AI tự động trả lời mọi tin nhắn")
    @discord.ui.button(label="🎫 Ticket Roles",     style=discord.ButtonStyle.primary,   row=3)
    async def ticket_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_message(
            embed=_build_ticket_roles_embed(),
            view=TicketRoleConfigView(),
            ephemeral=True,
        )


def _build_ticket_roles_embed(guild: discord.Guild | None = None) -> discord.Embed:
    """Embed hiển thị config ticket → roles hiện tại."""
    multi = get_all_ticket_multi_roles()

    def _tag(key: str) -> str:
        ids = multi.get(key, [])
        if not ids:
            return "*(chưa cài)*"
        # Admin IDs
        admin_tags = [f"<@{i}>" for i in ids if i in ADMIN_IDS]
        role_tags  = [f"<@&{i}>" for i in ids if i not in ADMIN_IDS]
        parts = admin_tags + role_tags
        return " ".join(parts) if parts else "*(chưa cài)*"

    svc_lines = [
        f"🎁 Nhận Giveaway → {_tag('giveaway')}",
        f"🆘 Hỗ Trợ        → {_tag('support')}",
    ]
    order_lines = [
        f"🍩 DonutSMP  → {_tag('order_donut')}",
        f"👑 KingMC    → {_tag('order_kingmc')}",
        f"🎮 One MC    → {_tag('order_onemc')}",
        f"🔥 Free Fire → {_tag('order_ff')}",
        f"🏗️ Build      → {_tag('order_build')}",
        f"🎭 Acc Pre   → {_tag('acc_pre')}",
    ]
    admin_lines = [f"<@{aid}> `(ID: {aid})`" for aid in ADMIN_IDS]

    embed = discord.Embed(title="🎫 Cấu Hình Role Theo Loại Ticket", color=0x5865F2)
    embed.add_field(name="🎮 Dịch Vụ",  value="\n".join(svc_lines),   inline=False)
    embed.add_field(name="🛒 Mua / Bán", value="\n".join(order_lines), inline=False)
    embed.add_field(
        name="👑 Admin IDs (luôn vào được mọi ticket)",
        value="\n".join(admin_lines) if admin_lines else "*(chưa có)*",
        inline=False,
    )
    embed.set_footer(text="Chọn loại ticket bên dưới để gán role")
    return embed


# Bảng hiển thị tên đẹp cho cả 6 loại (dùng trong Select)
_ALL_TICKET_OPTIONS = [
    # service
    ("giveaway",       "🎁 Nhận Giveaway", "Dịch vụ"),
    ("support",        "🆘 Hỗ Trợ",        "Dịch vụ"),
    # order — DonutSMP & KingMC (có money/ske)
    ("order_donut",    "🍩 Mua/Bán DonutSMP", "Mua/Bán"),
    ("order_kingmc",   "👑 Mua/Bán KingMC",   "Mua/Bán"),
    # order — OneMC & FreeFire (chỉ Khác)
    ("order_onemc",    "🎮 Mua/Bán One MC",   "Mua/Bán"),
    ("order_ff",       "🔥 Mua/Bán Free Fire","Mua/Bán"),
    # order — Build base
    ("order_build",    "🏗️ Mua/Bán Base",     "Mua/Bán"),
    # acc pre
    ("acc_pre",        "🎭 Acc Pre",           "Mua/Bán"),
]


# ─── helpers ────────────────────────────────────────────────────────────────
_TICKET_GROUPS = [
    ("🎮 Dịch Vụ", [
        ("giveaway",    "🎁 Nhận Giveaway"),
        ("support",     "🆘 Hỗ Trợ"),
    ]),
    ("🛒 Mua / Bán", [
        ("order_donut",  "🍩 DonutSMP"),
        ("order_kingmc", "👑 KingMC"),
        ("order_onemc",  "🎮 One MC"),
        ("order_ff",     "🔥 Free Fire"),
        ("order_build",  "🏗️ Build"),
        ("acc_pre",      "🎭 Acc Pre"),
    ]),
]

_TICKET_KEY_LABEL = {k: lbl for _, items in _TICKET_GROUPS for k, lbl in items}


class TicketRoleConfigView(View):
    """Bước 1: chọn loại ticket, chia theo nhóm."""
    def __init__(self):
        super().__init__(timeout=120)
        for group_label, items in _TICKET_GROUPS:
            options = [
                discord.SelectOption(label=lbl, value=key, description=group_label)
                for key, lbl in items
            ]
            self.add_item(_TicketTypeSelect(options, group_label))


class _TicketTypeSelect(Select):
    """Dropdown chọn loại ticket trong 1 nhóm."""
    def __init__(self, options: list, group_label: str):
        super().__init__(
            placeholder=f"Nhóm: {group_label}",
            options=options,
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        ticket_key  = self.values[0]
        ticket_label = _TICKET_KEY_LABEL.get(ticket_key, ticket_key)
        current_ids  = get_ticket_role_ids(ticket_key)

        # Lấy danh sách role trong server, phân trang 25 role/trang
        roles = [r for r in interaction.guild.roles if not r.is_default()]
        roles.sort(key=lambda r: -r.position)

        await interaction.response.send_message(
            embed=_build_role_picker_embed(ticket_label, current_ids, interaction.guild),
            view=_RolePickerView(ticket_key, ticket_label, roles, current_ids, page=0),
            ephemeral=True,
        )


def _build_role_picker_embed(
    ticket_label: str,
    current_ids: list,
    guild: discord.Guild,
) -> discord.Embed:
    if current_ids:
        tags = []
        for rid in current_ids:
            if rid in ADMIN_IDS:
                tags.append(f"<@{rid}> *(Admin ID)*")
            else:
                tags.append(f"<@&{rid}>")
        assigned = "\n".join(tags)
    else:
        assigned = "*(chưa có)*"

    embed = discord.Embed(
        title=f"🏷️ Gán role — {ticket_label}",
        description=(
            f"**Role hiện tại:**\n{assigned}\n\n"
            "Chọn **Admin IDs** hoặc role trong server bên dưới.\n"
            "Có thể chọn **nhiều role** trong 1 trang, bấm nhiều trang để thêm tiếp.\n"
            "✅ Bấm **Lưu** để xác nhận. ❌ **Xoá hết** để reset."
        ),
        color=0x5865F2,
    )
    return embed


class _RolePickerView(View):
    """Phân trang role trong server + multi-select + nút lưu/xoá."""
    PAGE_SIZE = 23  # 23 role/trang + 1 option Admin IDs + còn chỗ cho select

    def __init__(self, ticket_key: str, ticket_label: str, roles: list,
                 current_ids: list, page: int = 0):
        super().__init__(timeout=180)
        self.ticket_key   = ticket_key
        self.ticket_label = ticket_label
        self.roles        = roles
        self.pending_ids  = list(current_ids)  # đang chọn (chưa lưu)
        self.page         = page
        self.total_pages  = max(1, -(-len(roles) // self.PAGE_SIZE))  # ceil div
        self._build_components()

    def _build_components(self):
        self.clear_items()

        # ── Role Select (trang hiện tại) ──────────────────────────────
        start = self.page * self.PAGE_SIZE
        page_roles = self.roles[start : start + self.PAGE_SIZE]

        options = [
            discord.SelectOption(
                label="👑 Admin IDs",
                value="__admin__",
                description="Thêm tất cả Admin ID vào danh sách",
                default="__admin__" in [str(i) for i in self.pending_ids],
            )
        ]
        for r in page_roles:
            options.append(discord.SelectOption(
                label=r.name[:100],
                value=str(r.id),
                description=f"ID: {r.id}",
                default=r.id in self.pending_ids,
            ))

        select = Select(
            placeholder=f"Chọn role — trang {self.page+1}/{self.total_pages}",
            options=options,
            min_values=0,
            max_values=len(options),
            custom_id="role_picker_select",
        )
        select.callback = self._on_select
        self.add_item(select)

        # ── Nút điều hướng ────────────────────────────────────────────
        prev_btn = Button(label="◀ Trang trước", style=discord.ButtonStyle.grey,
                          disabled=self.page == 0, custom_id="role_prev", row=1)
        prev_btn.callback = self._on_prev
        self.add_item(prev_btn)

        next_btn = Button(label="Trang sau ▶", style=discord.ButtonStyle.grey,
                          disabled=self.page >= self.total_pages - 1,
                          custom_id="role_next", row=1)
        next_btn.callback = self._on_next
        self.add_item(next_btn)

        # ── Nút hành động ─────────────────────────────────────────────
        save_btn = Button(label="✅ Lưu", style=discord.ButtonStyle.green,
                          custom_id="role_save", row=2)
        save_btn.callback = self._on_save
        self.add_item(save_btn)

        clear_btn = Button(label="❌ Xoá hết", style=discord.ButtonStyle.red,
                           custom_id="role_clear", row=2)
        clear_btn.callback = self._on_clear
        self.add_item(clear_btn)

    async def _on_select(self, interaction: discord.Interaction):
        """Merge lựa chọn trang này vào pending_ids."""
        selected_vals = self.view_select_values(interaction) if hasattr(self, "view_select_values") else []
        # lấy values từ component trực tiếp
        for comp in interaction.data.get("components", [{}])[0].get("components", []):
            if comp.get("custom_id") == "role_picker_select":
                selected_vals = comp.get("values", [])
                break
        else:
            # fallback: lấy từ interaction.data trực tiếp (flat structure)
            selected_vals = interaction.data.get("values", [])

        # Role trên trang này
        start = self.page * self.PAGE_SIZE
        page_role_ids = {str(r.id) for r in self.roles[start: start + self.PAGE_SIZE]}
        page_role_ids.add("__admin__")

        # Bỏ các id của trang hiện tại khỏi pending, rồi thêm lại những cái được chọn
        if "__admin__" in selected_vals:
            # thêm tất cả ADMIN_IDS
            admin_ids_set = set(ADMIN_IDS)
        else:
            admin_ids_set = set()

        # Xoá admin ids cũ nếu không chọn __admin__ nữa
        self.pending_ids = [i for i in self.pending_ids if i not in ADMIN_IDS]
        self.pending_ids.extend(admin_ids_set)

        # Xoá role trang hiện tại, thêm lại những cái được tick
        page_int_ids = {int(v) for v in page_role_ids if v != "__admin__" and v.isdigit()}
        self.pending_ids = [i for i in self.pending_ids if i not in page_int_ids]
        for v in selected_vals:
            if v != "__admin__" and v.isdigit():
                self.pending_ids.append(int(v))

        self._build_components()
        await interaction.response.edit_message(
            embed=_build_role_picker_embed(self.ticket_label, self.pending_ids, interaction.guild),
            view=self,
        )

    async def _on_prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._build_components()
        await interaction.response.edit_message(
            embed=_build_role_picker_embed(self.ticket_label, self.pending_ids, interaction.guild),
            view=self,
        )

    async def _on_next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._build_components()
        await interaction.response.edit_message(
            embed=_build_role_picker_embed(self.ticket_label, self.pending_ids, interaction.guild),
            view=self,
        )

    async def _on_save(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        unique_ids = list(dict.fromkeys(self.pending_ids))  # dedup, giữ thứ tự
        set_ticket_role_ids(self.ticket_key, unique_ids)
        if unique_ids:
            tags = []
            for rid in unique_ids:
                tags.append(f"<@{rid}>" if rid in ADMIN_IDS else f"<@&{rid}>")
            desc = "\n".join(tags)
        else:
            desc = "*(trống)*"
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"✅ Đã lưu — {self.ticket_label}",
                description=desc,
                color=0x57F287,
            ),
            view=None,
        )

    async def _on_clear(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        self.pending_ids = []
        set_ticket_role_ids(self.ticket_key, [])
        self._build_components()
        await interaction.response.edit_message(
            embed=_build_role_picker_embed(self.ticket_label, [], interaction.guild),
            view=self,
        )

class ChannelConfigSelect(Select):
    def __init__(self, cfg_key, title, options):
        super().__init__(placeholder=f"Chọn kênh cho {title}...", options=options)
        self.cfg_key = cfg_key; self.title = title

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.")
        ch_id = int(self.values[0])
        save_cfg(self.cfg_key, ch_id)
        await interaction.response.send_message(f"✅ Đã cài **{self.title}** → <#{ch_id}>")

class RoleConfigSelect(Select):
    def __init__(self, cfg_key, title, options):
        super().__init__(placeholder=f"Chọn role cho {title}...", options=options)
        self.cfg_key = cfg_key; self.title = title

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.")
        role_id = int(self.values[0])
        save_cfg(self.cfg_key, role_id)
        await interaction.response.send_message(f"✅ Đã cài **{self.title}** → <@&{role_id}>")


# ══════════════════════════════════════════
# SETUP — MAIN MENU
# ══════════════════════════════════════════
class SetupMainView(View):
    def __init__(self, ctx):
        super().__init__(timeout=180)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("❌ Chỉ admin.")
            return False
        return True

    @discord.ui.button(label="📋 Kênh", style=discord.ButtonStyle.primary, row=0)
    async def btn_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_setup_channel_embed(),
            view=SetupChannelView(interaction),
           
        )

    @discord.ui.button(label="🗂️ Danh mục", style=discord.ButtonStyle.primary, row=0)
    async def btn_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_setup_category_embed(),
            view=SetupCategoryView(interaction),
           
        )

    @discord.ui.button(label="🏷️ Role", style=discord.ButtonStyle.primary, row=0)
    async def btn_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_setup_role_embed(),
            view=SetupRoleView(interaction),
           
        )

    @discord.ui.button(label="⚙️ Server", style=discord.ButtonStyle.success, row=0)
    async def btn_server(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_setup_server_embed(interaction.guild),
            view=SetupServerView(interaction),
           
        )


# ─── helpers ───────────────────────────────

def _setup_channel_embed() -> discord.Embed:
    return discord.Embed(
        title="📋 Quản Lý Kênh",
        description=(
            "**Tạo kênh** — text / voice / stage / forum (public hoặc private)\n"
            "**Xoá kênh** — chọn kênh cần xoá\n"
            "**Đổi tên** — đổi tên kênh bất kỳ\n"
            "**Font tên** — áp dụng Unicode font (bold, italic, gothic…)\n"
            "**Clone kênh** — tạo bản sao với cùng cấu hình quyền"
        ),
        color=0x5865F2,
    )

def _setup_category_embed() -> discord.Embed:
    return discord.Embed(
        title="🗂️ Quản Lý Danh Mục",
        description=(
            "**Tạo category** — đặt tên, tuỳ chọn font\n"
            "**Xoá category** — chọn từ danh sách\n"
            "**Đổi tên / Font** — đổi tên hoặc font của category\n"
            "**Di chuyển kênh** — chuyển kênh vào category khác"
        ),
        color=0x5865F2,
    )

def _setup_role_embed() -> discord.Embed:
    return discord.Embed(
        title="🏷️ Quản Lý Role",
        description=(
            "**Tạo role** — chọn màu, hoist, mentionable\n"
            "**Xoá role** — chọn từ danh sách\n"
            "**Gán / Gỡ role** — cho một thành viên cụ thể"
        ),
        color=0x5865F2,
    )

def _setup_server_embed(guild: discord.Guild) -> discord.Embed:
    data = load_data()
    def ch(k): c = data.get(k); return f"<#{c}>" if c else "Chưa cài"
    def ro(k): r = data.get(k); return f"<@&{r}>" if r else "Chưa cài"
    embed = discord.Embed(title="⚙️ Setup Server", color=0x5865F2)
    embed.add_field(name="👋 Welcome Channel",  value=ch("cfg_welcome_channel"),  inline=True)
    embed.add_field(name="👋 Goodbye Channel",  value=ch("cfg_goodbye_channel"),  inline=True)
    embed.add_field(name="📋 Log Channel",       value=ch("cfg_log_rudy"),          inline=True)
    embed.add_field(name="🎭 Auto-role Join",    value=ro("cfg_autorole_join"),     inline=True)
    embed.add_field(name="🔤 Prefix Bot",        value=f"`{data.get('cfg_prefix', '.')}`", inline=True)
    return embed


# ══════════════════════════════════════════
# SETUP — CHANNEL
# ══════════════════════════════════════════
_CHANNEL_TYPE_MAP = {
    "text":  (discord.ChannelType.text,  "📝"),
    "voice": (discord.ChannelType.voice, "🔊"),
    "stage": (discord.ChannelType.stage_voice, "🎙️"),
    "forum": (discord.ChannelType.forum, "💬"),
}

class SetupChannelView(View):
    def __init__(self, src_interaction):
        super().__init__(timeout=180)
        self.src = src_interaction

    @discord.ui.button(label="➕ Tạo kênh",   style=discord.ButtonStyle.success,   row=0)
    async def create(self, interaction, _):  await interaction.response.send_modal(CreateChannelModal())

    @discord.ui.button(label="🗑️ Xoá kênh",  style=discord.ButtonStyle.danger,    row=0)
    async def delete(self, interaction, _):
        await _send_channel_select_paged(interaction, _DeleteChannelSelect, "🗑️ Chọn kênh cần xoá:")

    @discord.ui.button(label="✏️ Đổi tên",    style=discord.ButtonStyle.secondary, row=0)
    async def rename(self, interaction, _):
        await _send_channel_select_paged(interaction, _RenameChannelSelect, "✏️ Chọn kênh cần đổi tên:")

    @discord.ui.button(label="🔤 Font tên",   style=discord.ButtonStyle.secondary, row=1)
    async def font(self, interaction, _):
        await _send_channel_select_paged(interaction, _FontChannelSelect, "🔤 Chọn kênh cần đổi font:")

    @discord.ui.button(label="📋 Clone kênh", style=discord.ButtonStyle.secondary, row=1)
    async def clone(self, interaction, _):
        await _send_channel_select_paged(interaction, _CloneChannelSelect, "📋 Chọn kênh cần clone:")

    @discord.ui.button(label="🌐 Font tất cả kênh", style=discord.ButtonStyle.primary, row=2)
    async def font_all(self, interaction, _):
        current_font = get_cfg_font()
        embed = discord.Embed(
            title="🌐 Đổi Font Tất Cả Kênh & Category",
            description=(
                f"Font hiện tại của server: **{FONT_LABELS.get(current_font, current_font)}**\n\n"
                "⚠️ Thao tác này sẽ đổi tên **toàn bộ kênh và category** trong server.\n"
                "Discord rate-limit ~2 request/giây — server lớn có thể mất vài phút.\n\n"
                "Chọn font muốn áp dụng:"
            ),
            color=0xFEE75C,
        )
        font_opts = [discord.SelectOption(label=lbl[:100], value=key) for key, lbl in FONT_LABELS.items()]
        v = View(timeout=120)
        v.add_item(_FontAllSelect(font_opts))
        await interaction.response.send_message(embed=embed, view=v)


class CreateChannelModal(discord.ui.Modal, title="➕ Tạo Kênh Mới"):
    name_input = TextInput(label="Tên kênh", placeholder="vd: 💬・general", max_length=100)
    type_input = TextInput(label="Loại (text/voice/stage/forum)", placeholder="text", default="text", max_length=10)
    private_input = TextInput(label="Private? (yes/no)", placeholder="no", default="no", max_length=3)
    category_input = TextInput(label="Tên hoặc ID category (để trống = không có)", required=False, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        ch_type_key = self.type_input.value.strip().lower()
        if ch_type_key not in _CHANNEL_TYPE_MAP:
            return await interaction.response.send_message(
                "❌ Loại kênh không hợp lệ. Dùng: `text`, `voice`, `stage`, `forum`."
            )
        _, icon = _CHANNEL_TYPE_MAP[ch_type_key]
        is_private = self.private_input.value.strip().lower() in ("yes", "y", "true", "1")
        cat_input   = self.category_input.value.strip() if self.category_input.value else ""
        category    = None
        if cat_input:
            category = discord.utils.find(
                lambda c: c.name.lower() == cat_input.lower() or str(c.id) == cat_input,
                interaction.guild.categories,
            )

        font  = get_cfg_font()
        parts = _detect_channel_parts(self.name_input.value.strip())
        name  = _rebuild_name(parts, parts["base_text"], font)

        overwrites = {}
        if is_private:
            overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            overwrites[interaction.guild.me]           = discord.PermissionOverwrite(view_channel=True)

        try:
            if ch_type_key == "text":
                ch = await interaction.guild.create_text_channel(name=name, category=category, overwrites=overwrites, reason=f"Setup bởi {interaction.user}")
            elif ch_type_key == "voice":
                ch = await interaction.guild.create_voice_channel(name=name, category=category, overwrites=overwrites, reason=f"Setup bởi {interaction.user}")
            elif ch_type_key == "stage":
                ch = await interaction.guild.create_stage_channel(name=name, category=category, overwrites=overwrites, reason=f"Setup bởi {interaction.user}")
            else:  # forum
                ch = await interaction.guild.create_forum(name=name, category=category, reason=f"Setup bởi {interaction.user}")
            embed = discord.Embed(title=f"{icon} Đã tạo kênh!", color=0x57F287)
            embed.add_field(name="Kênh",    value=ch.mention,    inline=True)
            embed.add_field(name="Loại",    value=ch_type_key,   inline=True)
            embed.add_field(name="Private", value="✅" if is_private else "❌", inline=True)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền tạo kênh.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Lỗi: {e}")


class _DeleteChannelSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn kênh cần xoá…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.")
        name = ch.name
        try:
            await ch.delete(reason=f"Setup xoá bởi {interaction.user}")
            await interaction.response.send_message(f"🗑️ Đã xoá kênh `#{name}`.")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền xoá kênh.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


class _RenameChannelSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn kênh cần đổi tên…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.")
        await interaction.response.send_modal(_RenameChannelModal(ch))

class _RenameChannelModal(discord.ui.Modal):
    def __init__(self, ch):
        super().__init__(title=f"✏️ Đổi tên: #{ch.name[:40]}")
        self.ch = ch
        parts = _detect_channel_parts(ch.name)
        self.new_name  = TextInput(label="Tên mới", placeholder="Nhập tên mới…", max_length=100)
        self.new_icon  = TextInput(
            label="Icon mới (để trống = giữ nguyên)",
            placeholder=f"Icon hiện tại: {parts['icon'] or '(không có)'}",
            required=False,
            max_length=10,
        )
        self.add_item(self.new_name)
        self.add_item(self.new_icon)
    async def on_submit(self, interaction: discord.Interaction):
        parts    = _detect_channel_parts(self.ch.name)
        font     = get_cfg_font()
        icon_raw = self.new_icon.value.strip()
        if icon_raw:
            parts["icon"] = icon_raw
        final = _rebuild_name(parts, self.new_name.value.strip(), font)
        old   = self.ch.name
        try:
            await self.ch.edit(name=final, reason=f"Setup rename bởi {interaction.user}")
            await interaction.response.send_message(f"✅ `#{old}` → `#{final}`")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


class _FontChannelSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn kênh cần đổi font…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.")
        font_opts = [discord.SelectOption(label=lbl[:100], value=key) for key, lbl in FONT_LABELS.items()]
        v = View(timeout=60); v.add_item(_ApplyFontChannelSelect(ch, font_opts))
        await interaction.response.send_message(f"🔤 Chọn font cho `#{ch.name}`:", view=v)

class _ApplyFontChannelSelect(Select):
    def __init__(self, ch, opts):
        super().__init__(placeholder="Chọn font…", options=opts)
        self.ch = ch
    async def callback(self, interaction: discord.Interaction):
        font  = self.values[0]
        parts = _detect_channel_parts(self.ch.name)
        final = _rebuild_name(parts, parts["base_text"], font)
        old   = self.ch.name
        try:
            await self.ch.edit(name=final, reason=f"Setup font bởi {interaction.user}")
            await interaction.response.send_message(
                f"✅ Font `{FONT_LABELS.get(font, font)}` → `#{old}` đã đổi thành `#{final}`"
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


class _CloneChannelSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn kênh cần clone…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.")
        try:
            cloned = await ch.clone(reason=f"Setup clone bởi {interaction.user}")
            await interaction.response.send_message(
                f"📋 Đã clone `#{ch.name}` → {cloned.mention}"
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


# ══════════════════════════════════════════
# PAGED CHANNEL SELECT — Giải pháp >25 kênh
# ══════════════════════════════════════════

def _group_channels_by_category(guild: discord.Guild, exclude_categories=False):
    """
    Trả về dict: {category_label: [channel, ...]}
    Key đặc biệt "(Không có category)" cho kênh không thuộc category nào.
    """
    groups: dict[str, list] = {}
    for ch in sorted(guild.channels, key=lambda c: c.position):
        if isinstance(ch, discord.CategoryChannel):
            continue
        cat_name = ch.category.name if ch.category else "(Không có category)"
        groups.setdefault(cat_name, []).append(ch)
    return groups


def _make_category_page_opts(groups: dict) -> list[discord.SelectOption]:
    """Tạo options chọn category (tối đa 25)."""
    opts = []
    for cat_name, channels in groups.items():
        opts.append(discord.SelectOption(
            label=cat_name[:100],
            value=cat_name,
            description=f"{len(channels)} kênh",
        ))
    return opts[:25]


class _PagedChannelCategorySelect(Select):
    """
    Bước 1: chọn category.
    Bước 2: hiện Select kênh trong category đó → gọi next_select_cls(channel_opts).
    """
    def __init__(self, groups: dict, next_select_cls, placeholder="Chọn nhóm kênh…"):
        self.groups = groups
        self.next_select_cls = next_select_cls
        opts = _make_category_page_opts(groups)
        super().__init__(placeholder=placeholder, options=opts)

    async def callback(self, interaction: discord.Interaction):
        cat_name = self.values[0]
        channels = self.groups.get(cat_name, [])
        ch_opts = [
            discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
            for ch in channels
        ][:25]
        if not ch_opts:
            return await interaction.response.send_message("❌ Không có kênh nào trong nhóm này.")
        v = View(timeout=60)
        v.add_item(self.next_select_cls(ch_opts))
        await interaction.response.send_message(
            f"📂 **{cat_name}** — Chọn kênh:", view=v
        )


async def _send_channel_select_paged(
    interaction: discord.Interaction,
    next_select_cls,
    prompt: str,
    filter_fn=None,
):
    """
    Helper dùng chung: nếu ≤25 kênh → Select thẳng.
    Nếu >25 kênh → chọn category trước, rồi chọn kênh.
    filter_fn(ch) → True nếu muốn include kênh đó.
    """
    channels = sorted(interaction.guild.channels, key=lambda c: c.position)
    channels = [ch for ch in channels if not isinstance(ch, discord.CategoryChannel)]
    if filter_fn:
        channels = [ch for ch in channels if filter_fn(ch)]

    if not channels:
        return await interaction.response.send_message("❌ Không có kênh nào.")

    if len(channels) <= 25:
        opts = [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id)) for ch in channels]
        v = View(timeout=60)
        v.add_item(next_select_cls(opts))
        return await interaction.response.send_message(prompt, view=v)

    # >25: nhóm theo category
    groups: dict[str, list] = {}
    for ch in channels:
        cat_name = ch.category.name if ch.category else "(Không có category)"
        groups.setdefault(cat_name, []).append(ch)

    v = View(timeout=60)
    v.add_item(_PagedChannelCategorySelect(groups, next_select_cls, placeholder="Chọn nhóm kênh…"))
    await interaction.response.send_message(
        f"📂 Server có **{len(channels)}** kênh — chọn nhóm trước:\n{prompt}", view=v
    )


class _FontAllSelect(Select):
    """Chọn font → áp dụng cho toàn bộ kênh + category trong server."""
    def __init__(self, opts):
        super().__init__(placeholder="Chọn font muốn áp dụng cho tất cả kênh…", options=opts)

    async def callback(self, interaction: discord.Interaction):
        font = self.values[0]
        guild = interaction.guild

        # Lưu font mới vào config
        set_cfg_font(font)

        # Đếm trước
        all_channels = [ch for ch in guild.channels]
        total = len(all_channels)

        await interaction.response.send_message(
            f"⏳ Đang đổi font **{FONT_LABELS.get(font, font)}** cho **{total}** kênh & category…\n"
            "Có thể mất vài phút do rate-limit Discord.",
           
        )

        ok = 0
        failed = 0
        # Category trước, sau đó kênh thường (tránh rename trùng trong lúc chạy)
        ordered = sorted(all_channels, key=lambda c: (0 if isinstance(c, discord.CategoryChannel) else 1, c.position))
        for ch in ordered:
            parts = _detect_channel_parts(ch.name)
            new_name = _rebuild_name(parts, parts["base_text"], font)
            if new_name == ch.name:
                ok += 1
                continue
            try:
                await ch.edit(name=new_name, reason=f"Font all → {font} bởi {interaction.user}")
                ok += 1
            except discord.Forbidden:
                failed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.55)  # ~1.8 req/s, dưới ngưỡng rate-limit Discord

        embed = discord.Embed(
            title="✅ Đổi Font Hoàn Tất",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Font mới",      value=FONT_LABELS.get(font, font), inline=False)
        embed.add_field(name="✅ Thành công", value=f"**{ok}** kênh",            inline=True)
        embed.add_field(name="❌ Thất bại",   value=f"**{failed}** kênh",        inline=True)
        embed.set_footer(text=f"Thực hiện bởi {interaction.user}")
        await interaction.followup.send(embed=embed)


# ══════════════════════════════════════════
# SETUP — CATEGORY
# ══════════════════════════════════════════
class SetupCategoryView(View):
    def __init__(self, src):
        super().__init__(timeout=180)
        self.src = src

    @discord.ui.button(label="➕ Tạo category",   style=discord.ButtonStyle.success,   row=0)
    async def create(self, interaction, _): await interaction.response.send_modal(CreateCategoryModal())

    @discord.ui.button(label="🗑️ Xoá category",  style=discord.ButtonStyle.danger,    row=0)
    async def delete(self, interaction, _):
        opts = [discord.SelectOption(label=c.name[:100], value=str(c.id)) for c in interaction.guild.categories][:25]
        if not opts: return await interaction.response.send_message("❌ Không có category nào.")
        v = View(timeout=60); v.add_item(_DeleteCategorySelect(opts))
        await interaction.response.send_message("🗑️ Chọn category cần xoá:", view=v)

    @discord.ui.button(label="✏️ Đổi tên / Font", style=discord.ButtonStyle.secondary, row=0)
    async def rename(self, interaction, _):
        opts = [discord.SelectOption(label=c.name[:100], value=str(c.id)) for c in interaction.guild.categories][:25]
        if not opts: return await interaction.response.send_message("❌ Không có category nào.")
        v = View(timeout=60); v.add_item(_RenameCategorySelect(opts))
        await interaction.response.send_message("✏️ Chọn category cần đổi tên:", view=v)

    @discord.ui.button(label="📂 Di chuyển kênh", style=discord.ButtonStyle.secondary, row=1)
    async def move(self, interaction, _):
        await _send_channel_select_paged(interaction, _MoveChannelSelect, "📂 Chọn kênh cần di chuyển:")


class CreateCategoryModal(discord.ui.Modal, title="➕ Tạo Category"):
    name_input = TextInput(label="Tên category", placeholder="vd: 📁 GENERAL", max_length=100)
    font_input = TextInput(label="Font (normal/bold/italic/sans_bold/script/double)", default="normal", max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        font  = self.font_input.value.strip().lower()
        if font not in _FONT_MAPS: font = "normal"
        parts = _detect_channel_parts(self.name_input.value.strip())
        name  = _rebuild_name(parts, parts["base_text"], font)
        try:
            cat = await interaction.guild.create_category(name=name, reason=f"Setup bởi {interaction.user}")
            await interaction.response.send_message(f"📂 Đã tạo category **{cat.name}**!")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


class _DeleteCategorySelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn category cần xoá…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        cat = interaction.guild.get_channel(int(self.values[0]))
        if not cat: return await interaction.response.send_message("❌ Không tìm thấy.")
        name = cat.name
        try:
            await cat.delete(reason=f"Setup xoá category bởi {interaction.user}")
            await interaction.response.send_message(f"🗑️ Đã xoá category `{name}`.")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


class _RenameCategorySelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn category cần đổi tên…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        cat = interaction.guild.get_channel(int(self.values[0]))
        if not cat: return await interaction.response.send_message("❌ Không tìm thấy.")
        await interaction.response.send_modal(_RenameCategoryModal(cat))

class _RenameCategoryModal(discord.ui.Modal):
    def __init__(self, cat):
        super().__init__(title=f"✏️ Đổi tên: {cat.name[:40]}")
        self.cat = cat
        parts = _detect_channel_parts(cat.name)
        self.new_name   = TextInput(label="Tên mới", max_length=100)
        self.new_icon   = TextInput(
            label="Icon mới (để trống = giữ nguyên)",
            placeholder=f"Icon hiện tại: {parts['icon'] or '(không có)'}",
            required=False,
            max_length=10,
        )
        self.font_input = TextInput(label="Font (normal/bold/italic/sans_bold/script/double)", default="normal", max_length=20)
        self.add_item(self.new_name); self.add_item(self.new_icon); self.add_item(self.font_input)
    async def on_submit(self, interaction: discord.Interaction):
        font  = self.font_input.value.strip().lower()
        if font not in _FONT_MAPS: font = "normal"
        parts    = _detect_channel_parts(self.cat.name)
        icon_raw = self.new_icon.value.strip()
        if icon_raw:
            parts["icon"] = icon_raw
        final = _rebuild_name(parts, self.new_name.value.strip(), font)
        old   = self.cat.name
        try:
            await self.cat.edit(name=final, reason=f"Setup rename category bởi {interaction.user}")
            await interaction.response.send_message(f"✅ `{old}` → `{final}`")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


class _MoveChannelSelect(Select):
    def __init__(self, ch_opts): super().__init__(placeholder="Chọn kênh cần di chuyển…", options=ch_opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.")
        cat_opts = [discord.SelectOption(label=c.name[:100], value=str(c.id)) for c in interaction.guild.categories][:25]
        cat_opts.insert(0, discord.SelectOption(label="(Không có category)", value="0"))
        v = View(timeout=60); v.add_item(_MoveToCategorySelect(ch, cat_opts))
        await interaction.response.send_message(f"📂 Chọn category đích cho `#{ch.name}`:", view=v)

class _MoveToCategorySelect(Select):
    def __init__(self, ch, opts):
        super().__init__(placeholder="Chọn category đích…", options=opts)
        self.ch = ch
    async def callback(self, interaction: discord.Interaction):
        val = int(self.values[0])
        cat = interaction.guild.get_channel(val) if val != 0 else None
        try:
            await self.ch.edit(category=cat, reason=f"Setup move bởi {interaction.user}")
            dest = cat.name if cat else "không có category"
            await interaction.response.send_message(
                f"📂 Đã di chuyển `#{self.ch.name}` → `{dest}`"
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


# ══════════════════════════════════════════
# SETUP — ROLE
# ══════════════════════════════════════════
class SetupRoleView(View):
    def __init__(self, src):
        super().__init__(timeout=180)
        self.src = src

    @discord.ui.button(label="➕ Tạo role",   style=discord.ButtonStyle.success,   row=0)
    async def create(self, interaction, _): await interaction.response.send_modal(CreateRoleModal())

    @discord.ui.button(label="🗑️ Xoá role",  style=discord.ButtonStyle.danger,    row=0)
    async def delete(self, interaction, _):
        opts = [discord.SelectOption(label=r.name[:100], value=str(r.id))
                for r in sorted(interaction.guild.roles, key=lambda r: -r.position)
                if r.name != "@everyone"][:25]
        if not opts: return await interaction.response.send_message("❌ Không có role.")
        v = View(timeout=60); v.add_item(_DeleteRoleSelect(opts))
        await interaction.response.send_message("🗑️ Chọn role cần xoá:", view=v)

    @discord.ui.button(label="✅ Gán role",   style=discord.ButtonStyle.secondary, row=0)
    async def give(self, interaction, _): await interaction.response.send_modal(AssignRoleModal(action="give"))

    @discord.ui.button(label="❌ Gỡ role",   style=discord.ButtonStyle.secondary, row=1)
    async def take(self, interaction, _): await interaction.response.send_modal(AssignRoleModal(action="take"))

    @discord.ui.button(label="🛒 Buy Roles", style=discord.ButtonStyle.primary, row=1)
    async def buy_roles_btn(self, interaction: discord.Interaction, _):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.")
        await interaction.response.send_message(
            embed=_buy_roles_embed(),
            view=BuyRolesView(),
           
        )

    @discord.ui.button(label="🔐 Quyền Role", style=discord.ButtonStyle.secondary, row=2)
    async def set_perm_btn(self, interaction: discord.Interaction, _):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await RolePermFlow.start(interaction)


class CreateRoleModal(discord.ui.Modal, title="➕ Tạo Role Mới"):
    name_input    = TextInput(label="Tên role", max_length=100)
    color_input   = TextInput(label="Màu hex (vd: #FF5733, để trống = mặc định)", required=False, max_length=7)
    hoist_input   = TextInput(label="Hiển thị riêng? (yes/no)", default="no",  max_length=3)
    mention_input = TextInput(label="Có thể @mention? (yes/no)",  default="no",  max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        color = discord.Color.default()
        if self.color_input.value.strip():
            try: color = discord.Color(int(self.color_input.value.strip().lstrip("#"), 16))
            except Exception as _e:
                log.debug(f"[SILENT] {_e}")
        hoist       = self.hoist_input.value.strip().lower() in ("yes", "y", "true", "1")
        mentionable = self.mention_input.value.strip().lower() in ("yes", "y", "true", "1")
        try:
            role = await interaction.guild.create_role(
                name=self.name_input.value.strip(),
                color=color, hoist=hoist, mentionable=mentionable,
                reason=f"Setup tạo role bởi {interaction.user}",
            )
            embed = discord.Embed(title="✅ Đã tạo role!", color=role.color)
            embed.add_field(name="Role",      value=role.mention,          inline=True)
            embed.add_field(name="Màu",       value=str(role.color),       inline=True)
            embed.add_field(name="Hoist",     value="✅" if hoist else "❌", inline=True)
            embed.add_field(name="Mentionable", value="✅" if mentionable else "❌", inline=True)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền tạo role.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


class _DeleteRoleSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn role cần xoá…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if not role: return await interaction.response.send_message("❌ Không tìm thấy role.")
        name = role.name
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ Role này cao hơn hoặc bằng role của bot.")
        try:
            await role.delete(reason=f"Setup xoá role bởi {interaction.user}")
            await interaction.response.send_message(f"🗑️ Đã xoá role `{name}`.")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


class AssignRoleModal(discord.ui.Modal):
    member_input = TextInput(label="User ID hoặc mention (@user)", max_length=30)
    role_input   = TextInput(label="Role ID hoặc tên role",        max_length=100)

    def __init__(self, action: str):
        self.action = action
        super().__init__(title="✅ Gán Role" if action == "give" else "❌ Gỡ Role")
        self.add_item(self.member_input)
        self.add_item(self.role_input)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        # Resolve member
        raw_m = self.member_input.value.strip().lstrip("<@!").rstrip(">")
        try: member = guild.get_member(int(raw_m)) or await guild.fetch_member(int(raw_m))
        except: member = None
        if not member:
            return await interaction.response.send_message(f"❌ Không tìm thấy member `{self.member_input.value}`.")
        # Resolve role
        raw_r = self.role_input.value.strip()
        role = None
        try: role = guild.get_role(int(raw_r))
        except ValueError:
            role = discord.utils.find(lambda r: r.name.lower() == raw_r.lower(), guild.roles)
        if not role:
            return await interaction.response.send_message(f"❌ Không tìm thấy role `{raw_r}`.")
        if role >= guild.me.top_role:
            return await interaction.response.send_message("❌ Role này cao hơn hoặc bằng role của bot.")
        try:
            if self.action == "give":
                await member.add_roles(role, reason=f"Setup gán role bởi {interaction.user}")
                await interaction.response.send_message(
                    f"✅ Đã gán {role.mention} cho {member.mention}."
                )
            else:
                await member.remove_roles(role, reason=f"Setup gỡ role bởi {interaction.user}")
                await interaction.response.send_message(
                    f"✅ Đã gỡ {role.mention} khỏi {member.mention}."
                )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}")


# ══════════════════════════════════════════
# ══════════════════════════
# SETUP — BUY ROLES
# ══════════════════════════
def _buy_roles_embed() -> discord.Embed:
    buy_roles = get_buy_roles()
    embed = discord.Embed(title="🛒 Quản Lý Buy Roles", color=0x5865F2)
    if not buy_roles:
        embed.description = "Chưa có tier nào. Nhấn **➕ Thêm tier** đả bắt đầu."
    else:
        lines = []
        for i, r in enumerate(buy_roles):
            min_a = fmt_amount(r.get("min_amount", 0))
            max_a = fmt_amount(r["max_amount"]) if r.get("max_amount") else "∞"
            lines.append(f"`{i+1}.` <@&{r['role_id']}> — **{min_a} → {max_a}**")
        embed.description = "\n".join(lines)
    embed.set_footer(text="Tier cao hơn sẽ thay thế tier thấp hơn tự động")
    return embed


class BuyRolesView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="➕ Thêm tier", style=discord.ButtonStyle.success, row=0)
    async def add(self, interaction: discord.Interaction, _):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.")
        await interaction.response.send_modal(AddBuyRoleModal())

    @discord.ui.button(label="🗑️ Xóa tier", style=discord.ButtonStyle.danger, row=0)
    async def delete(self, interaction: discord.Interaction, _):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.")
        buy_roles = get_buy_roles()
        if not buy_roles:
            return await interaction.response.send_message("❌ Chưa có tier nào.")
        opts = [
            discord.SelectOption(
                label=f"Tier {i+1}: {fmt_amount(r.get('min_amount',0))} → {fmt_amount(r['max_amount']) if r.get('max_amount') else '∞'}"[:100],
                description=f"Role ID: {r['role_id']}",
                value=str(i),
            )
            for i, r in enumerate(buy_roles)
        ]
        v = View(timeout=60)
        v.add_item(_DeleteBuyRoleSelect(opts))
        await interaction.response.send_message("🗑️ Chọn tier cần xóa:", view=v)

    @discord.ui.button(label="👁️ Xem lại", style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction: discord.Interaction, _):
        await interaction.response.send_message(embed=_buy_roles_embed())

    @discord.ui.button(label="🔍 Auto Detect", style=discord.ButtonStyle.primary, row=1)
    async def auto_detect(self, interaction: discord.Interaction, _):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.")
        import re
        # Format: "Buyer Xk-Yk", "Buyer Xtr-Ytr", "Buyer Xm-Ym", max có thể bỏ trống (∞)
        pattern = re.compile(
            r"buyer\s+([0-9]+(?:[.,][0-9]+)?[ktm]r?)\s*[-–]\s*([0-9]+(?:[.,][0-9]+)?[ktm]r?|\u221e)?",
            re.IGNORECASE
        )
        buy_roles = get_buy_roles() or []
        existing_ids = {r["role_id"] for r in buy_roles}
        added = []
        skipped = []

        for role in interaction.guild.roles:
            m = pattern.search(role.name)
            if not m:
                continue
            if role.id in existing_ids:
                skipped.append(role.name)
                continue
            min_amount = parse_amount(m.group(1))
            max_raw    = m.group(2) or ""
            max_amount = None if (not max_raw or max_raw == "∞") else parse_amount(max_raw)
            if min_amount is None:
                continue
            buy_roles.append({"role_id": role.id, "min_amount": min_amount, "max_amount": max_amount})
            added.append(f"{role.mention} ({fmt_amount(min_amount)} → {fmt_amount(max_amount) if max_amount else '∞'})")

        if not added and not skipped:
            return await interaction.response.send_message("❌ Không tìm thấy role nào có tên dạng `Buyer Xk-Yk`.")

        buy_roles.sort(key=lambda r: r.get("min_amount", 0))
        save_buy_roles(buy_roles)

        lines = []
        if added:
            lines.append(f"✅ Đã thêm **{len(added)}** tier:\n" + "\n".join(added))
        if skipped:
            lines.append(f"⏭️ Bỏ qua **{len(skipped)}** role đã có:\n" + "\n".join(skipped))
        await interaction.response.send_message("\n\n".join(lines))


class AddBuyRoleModal(discord.ui.Modal, title="➕ Thêm Buy Role Tier"):
    role_input = TextInput(label="Role ID", max_length=25)
    min_input  = TextInput(label="Chi tiêu tối thiểu (VNĐ)", placeholder="vd: 50k / 1.5tr / 100000", max_length=15)
    max_input  = TextInput(label="Chi tiêu tối đa (VNĐ, để trống = ∞)", placeholder="vd: 500k / 2tr", required=False, max_length=15)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_input.value.strip())
            role = interaction.guild.get_role(role_id)
            if not role:
                return await interaction.response.send_message("❌ Không tìm thấy role với ID đó.")
        except ValueError:
            return await interaction.response.send_message("❌ Role ID không hợp lệ.")

        min_amount = parse_amount(self.min_input.value)
        if min_amount is None:
            return await interaction.response.send_message(
                "❌ Số tiền tối thiểu không hợp lệ.\n💡 Ví dụ: `50k`, `1.5tr`, `100000`")

        max_amount = None
        if self.max_input.value.strip():
            max_amount = parse_amount(self.max_input.value)
            if max_amount is None:
                return await interaction.response.send_message(
                    "❌ Số tiền tối đa không hợp lệ.\n💡 Ví dụ: `500k`, `2tr`, `500000`")
            if max_amount <= min_amount:
                return await interaction.response.send_message("❌ Tối đa phải lớn hơn tối thiểu.")

        buy_roles = get_buy_roles() or []
        if any(r["role_id"] == role_id for r in buy_roles):
            return await interaction.response.send_message(f"❌ Role {role.mention} đã tồn tại trong danh sách.")

        buy_roles.append({"role_id": role_id, "min_amount": min_amount, "max_amount": max_amount})
        buy_roles.sort(key=lambda r: r.get("min_amount", 0))
        save_buy_roles(buy_roles)

        max_str = fmt_amount(max_amount) if max_amount else "∞"
        await interaction.response.send_message(
            f"✅ Đã thêm tier: {role.mention} — **{fmt_amount(min_amount)} → {max_str}**",
           
        )


class _DeleteBuyRoleSelect(Select):
    def __init__(self, opts):
        super().__init__(placeholder="Chọn tier cần xóa…", options=opts)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.")
        idx = int(self.values[0])
        buy_roles = get_buy_roles()
        if idx >= len(buy_roles):
            return await interaction.response.send_message("❌ Tier không tồn tại.")
        removed = buy_roles.pop(idx)
        save_buy_roles(buy_roles)
        max_str = fmt_amount(removed["max_amount"]) if removed.get("max_amount") else "∞"
        await interaction.response.send_message(
            f"🗑️ Đã xóa tier <@&{removed['role_id']}> "
            f"({fmt_amount(removed.get('min_amount', 0))} → {max_str}).",
           
        )


# SETUP — SERVER
# ══════════════════════════════════════════
class SetupServerView(View):
    def __init__(self, src):
        super().__init__(timeout=180)
        self.src = src

    def _ch_select(self, guild, placeholder):
        return [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
                for ch in sorted(guild.text_channels, key=lambda c: c.position)][:25]

    def _role_select(self, guild):
        return [discord.SelectOption(label=r.name[:100], value=str(r.id))
                for r in sorted(guild.roles, key=lambda r: -r.position) if r.name != "@everyone"][:25]

    @discord.ui.button(label="👋 Welcome Channel", style=discord.ButtonStyle.secondary, row=0)
    async def welcome(self, interaction, _):
        opts = self._ch_select(interaction.guild, "Welcome")
        if not opts: return await interaction.response.send_message("❌ Không có kênh.")
        v = View(timeout=60); v.add_item(_ServerChannelSelect("cfg_welcome_channel", "Welcome Channel", opts))
        await interaction.response.send_message("👋 Chọn kênh **Welcome**:", view=v)

    @discord.ui.button(label="👋 Goodbye Channel", style=discord.ButtonStyle.secondary, row=0)
    async def goodbye(self, interaction, _):
        opts = self._ch_select(interaction.guild, "Goodbye")
        if not opts: return await interaction.response.send_message("❌ Không có kênh.")
        v = View(timeout=60); v.add_item(_ServerChannelSelect("cfg_goodbye_channel", "Goodbye Channel", opts))
        await interaction.response.send_message("👋 Chọn kênh **Goodbye**:", view=v)

    @discord.ui.button(label="📋 Log Channel", style=discord.ButtonStyle.secondary, row=0)
    async def log(self, interaction, _):
        opts = self._ch_select(interaction.guild, "Log")
        if not opts: return await interaction.response.send_message("❌ Không có kênh.")
        v = View(timeout=60); v.add_item(_ServerChannelSelect("cfg_log_rudy", "Log Channel", opts))
        await interaction.response.send_message("📋 Chọn kênh **Log**:", view=v)

    @discord.ui.button(label="🎭 Auto-role Join", style=discord.ButtonStyle.secondary, row=1)
    async def autorole(self, interaction, _):
        opts = self._role_select(interaction.guild)
        if not opts: return await interaction.response.send_message("❌ Không có role.")
        v = View(timeout=60); v.add_item(_ServerRoleSelect("cfg_autorole_join", "Auto-role khi Join", opts))
        await interaction.response.send_message("🎭 Chọn role **tự động gán** khi member join:", view=v)

    @discord.ui.button(label="🔤 Đặt Prefix Bot", style=discord.ButtonStyle.primary, row=1)
    async def prefix(self, interaction, _): await interaction.response.send_modal(SetPrefixModal())

    @discord.ui.button(label="👁️ Xem trạng thái", style=discord.ButtonStyle.blurple, row=2)
    async def view_status(self, interaction, _):
        await interaction.response.send_message(
            embed=_setup_server_embed(interaction.guild)
        )


class _ServerChannelSelect(Select):
    def __init__(self, cfg_key, title, opts):
        super().__init__(placeholder=f"Chọn kênh cho {title}…", options=opts)
        self.cfg_key = cfg_key; self.title = title
    async def callback(self, interaction: discord.Interaction):
        ch_id = int(self.values[0])
        save_cfg(self.cfg_key, ch_id)
        await interaction.response.send_message(
            f"✅ Đã cài **{self.title}** → <#{ch_id}>"
        )

class _ServerRoleSelect(Select):
    def __init__(self, cfg_key, title, opts):
        super().__init__(placeholder=f"Chọn role cho {title}…", options=opts)
        self.cfg_key = cfg_key; self.title = title
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        save_cfg(self.cfg_key, role_id)
        await interaction.response.send_message(
            f"✅ Đã cài **{self.title}** → <@&{role_id}>"
        )

class SetPrefixModal(discord.ui.Modal, title="🔤 Đặt Prefix Bot"):
    prefix_input = TextInput(label="Prefix mới", placeholder="vd: ! hoặc ? hoặc .", max_length=5)
    async def on_submit(self, interaction: discord.Interaction):
        prefix = self.prefix_input.value.strip()
        if not prefix: return await interaction.response.send_message("❌ Prefix không được để trống.")
        save_cfg("cfg_prefix", prefix)
        await interaction.response.send_message(f"✅ Prefix bot đã đổi thành `{prefix}`.")


# ══════════════════════════════════════════
# MKCHANNEL — VIEW + MODAL
# ══════════════════════════════════════════
_CH_TYPE_OPTIONS = [
    discord.SelectOption(label="📝  Text Channel",   value="text",     description="Kênh chat thông thường"),
    discord.SelectOption(label="🔊  Voice Channel",  value="voice",    description="Kênh thoại"),
    discord.SelectOption(label="🎙️  Stage Channel",  value="stage",    description="Kênh sân khấu"),
    discord.SelectOption(label="💬  Forum Channel",  value="forum",    description="Kênh diễn đàn"),
    discord.SelectOption(label="📂  Category",       value="category", description="Tạo danh mục mới"),
]

_MK_PRIVACY_OPTIONS = [
    discord.SelectOption(label="🌐  Public",  value="public",  description="Mọi người đều xem được", default=True),
    discord.SelectOption(label="🔒  Private", value="private", description="Ẩn với @everyone, chỉ bot + admin thấy"),
]

_MK_LOCK_OPTIONS = [
    discord.SelectOption(label="🔓  Mở (không khoá)",  value="off", description="@everyone gửi tin nhắn bình thường", default=True),
    discord.SelectOption(label="🔐  Khoá (read-only)", value="on",  description="@everyone chỉ xem, không gửi được"),
]


def _build_mk_overwrites(
    guild: discord.Guild,
    privacy: str,
    lock: str,
) -> dict:
    """
    Tạo overwrites dựa trên privacy + lock:
      privacy=public  → @everyone xem được
      privacy=private → @everyone ẩn (view_channel=False)
      lock=on         → @everyone send_messages=False (chỉ khi public; private đã ẩn hết)
    Bot + admin luôn có quyền đầy đủ.
    """
    from core.data import ADMIN_IDS as _ADMIN_IDS
    ow: dict = {}

    everyone = guild.default_role
    if privacy == "private":
        ow[everyone] = discord.PermissionOverwrite(view_channel=False)
    elif lock == "on":
        ow[everyone] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
    # else: public + unlocked → không cần overwrite @everyone

    # Bot luôn full quyền
    ow[guild.me] = discord.PermissionOverwrite(
        view_channel=True, send_messages=True,
        manage_channels=True, manage_messages=True,
    )
    # Admin members
    for aid in _ADMIN_IDS:
        m = guild.get_member(aid)
        if m:
            ow[m] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                manage_channels=True, manage_messages=True,
            )
    return ow


class MkChannelView(View):
    """
    Bước 1: chọn loại kênh, danh mục, quyền truy cập, trạng thái khoá.
    Bước 2: nhấn Tiếp tục → modal nhập tên + số lượng.
    """
    def __init__(self, ctx, cat_opts: list):
        super().__init__(timeout=120)
        self.ctx      = ctx
        self.ch_type  = "text"
        self.cat_id   = 0
        self.privacy  = "public"
        self.lock     = "off"

        type_sel    = _MkTypeSelect(_CH_TYPE_OPTIONS)
        cat_sel     = _MkCatSelect(cat_opts)
        privacy_sel = _MkPrivacySelect(_MK_PRIVACY_OPTIONS)
        lock_sel    = _MkLockSelect(_MK_LOCK_OPTIONS)

        for s in (type_sel, cat_sel, privacy_sel, lock_sel):
            s.view_ref = self

        self.add_item(type_sel)
        self.add_item(cat_sel)
        self.add_item(privacy_sel)
        self.add_item(lock_sel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Chỉ người gõ lệnh mới dùng được.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Tiếp tục →", style=discord.ButtonStyle.primary, row=4)
    async def proceed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            MkChannelModal(self.ch_type, self.cat_id, self.privacy, self.lock)
        )


class _MkTypeSelect(Select):
    def __init__(self, opts):
        super().__init__(placeholder="① Loại kênh…", options=opts, row=0)
        self.view_ref = None
    async def callback(self, interaction: discord.Interaction):
        if self.view_ref: self.view_ref.ch_type = self.values[0]
        await interaction.response.defer()


class _MkCatSelect(Select):
    def __init__(self, opts):
        super().__init__(placeholder="② Danh mục chứa kênh…", options=opts, row=1)
        self.view_ref = None
    async def callback(self, interaction: discord.Interaction):
        if self.view_ref: self.view_ref.cat_id = int(self.values[0])
        await interaction.response.defer()


class _MkPrivacySelect(Select):
    def __init__(self, opts):
        super().__init__(placeholder="③ Quyền truy cập…", options=opts, row=2)
        self.view_ref = None
    async def callback(self, interaction: discord.Interaction):
        if self.view_ref: self.view_ref.privacy = self.values[0]
        await interaction.response.defer()


class _MkLockSelect(Select):
    def __init__(self, opts):
        super().__init__(placeholder="④ Khoá gửi tin nhắn…", options=opts, row=3)
        self.view_ref = None
    async def callback(self, interaction: discord.Interaction):
        if self.view_ref: self.view_ref.lock = self.values[0]
        await interaction.response.defer()


class MkChannelModal(discord.ui.Modal, title="➕ Tạo Kênh Mới"):
    name_input = TextInput(
        label="Tên kênh",
        placeholder="vd: ✔️•5k+roblox  hoặc  💬・general",
        max_length=100,
    )
    count_input = TextInput(
        label="Số lượng kênh cần tạo (1–20)",
        placeholder="1",
        default="1",
        max_length=2,
    )

    def __init__(self, ch_type: str, cat_id: int, privacy: str = "public", lock: str = "off"):
        super().__init__()
        self.ch_type = ch_type
        self.cat_id  = cat_id
        self.privacy = privacy
        self.lock    = lock

    async def on_submit(self, interaction: discord.Interaction):
        # Validate số lượng
        try:
            count = int(self.count_input.value.strip())
            if count < 1 or count > 20:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Số lượng phải từ 1 đến 20.", ephemeral=True)

        raw_name = self.name_input.value.strip()
        font     = get_cfg_font()
        parts    = _detect_channel_parts(raw_name)
        styled   = _rebuild_name(parts, parts["base_text"], font)

        # Resolve category
        category = interaction.guild.get_channel(self.cat_id) if self.cat_id else None
        if category and not isinstance(category, discord.CategoryChannel):
            category = None

        # Overwrites
        overwrites = _build_mk_overwrites(interaction.guild, self.privacy, self.lock)

        _TYPE_ICON = {
            "text": "📝", "voice": "🔊", "stage": "🎙️",
            "forum": "💬", "category": "📂",
        }
        type_icon = _TYPE_ICON.get(self.ch_type, "📝")

        await interaction.response.defer(ephemeral=True)

        created = []
        failed  = 0
        for _ in range(count):
            try:
                if self.ch_type == "text":
                    ch = await interaction.guild.create_text_channel(
                        name=styled, category=category, overwrites=overwrites,
                        reason=f"mkchannel bởi {interaction.user}",
                    )
                elif self.ch_type == "voice":
                    ch = await interaction.guild.create_voice_channel(
                        name=styled, category=category, overwrites=overwrites,
                        reason=f"mkchannel bởi {interaction.user}",
                    )
                elif self.ch_type == "stage":
                    ch = await interaction.guild.create_stage_channel(
                        name=styled, category=category, overwrites=overwrites,
                        reason=f"mkchannel bởi {interaction.user}",
                    )
                elif self.ch_type == "forum":
                    ch = await interaction.guild.create_forum(
                        name=styled, category=category, overwrites=overwrites,
                        reason=f"mkchannel bởi {interaction.user}",
                    )
                else:  # category
                    ch = await interaction.guild.create_category(
                        name=styled, overwrites=overwrites,
                        reason=f"mkchannel bởi {interaction.user}",
                    )
                created.append(ch)
                if count > 1:
                    await asyncio.sleep(0.55)
            except discord.Forbidden:
                failed += 1
            except Exception:
                failed += 1

        # Labels hiển thị
        privacy_lbl = "🔒 Private" if self.privacy == "private" else "🌐 Public"
        lock_lbl    = "🔐 Khoá (read-only)" if self.lock == "on" else "🔓 Mở"

        # Kết quả
        embed = discord.Embed(
            title=f"{type_icon} Tạo Kênh Hoàn Tất",
            color=0x57F287 if not failed else 0xFEE75C,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Loại",        value=self.ch_type,                      inline=True)
        embed.add_field(name="Font",        value=FONT_LABELS.get(font, font),        inline=True)
        embed.add_field(name="Danh mục",    value=category.name if category else "—", inline=True)
        embed.add_field(name="Quyền",       value=privacy_lbl,                        inline=True)
        embed.add_field(name="Khoá",        value=lock_lbl,                           inline=True)
        embed.add_field(name="✅ Đã tạo",   value=f"**{len(created)}** kênh",         inline=True)
        if failed:
            embed.add_field(name="❌ Thất bại", value=f"**{failed}** kênh",           inline=True)
        if created:
            mentions = "  ".join(
                ch.mention if hasattr(ch, "mention") and not isinstance(ch, discord.CategoryChannel)
                else f"`{ch.name}`"
                for ch in created[:10]
            )
            if len(created) > 10:
                mentions += f"  … (+{len(created)-10})"
            embed.add_field(name="Kênh đã tạo", value=mentions, inline=False)
        embed.set_footer(text=f"Bởi {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=False)


# ══════════════════════════════════════════
# ROLE PERM FLOW
# ══════════════════════════════════════════

# Danh sách các quyền hỗ trợ (tên hiển thị, tên attr trong PermissionOverwrite)
_PERM_LIST = [
    ("Xem kênh",            "view_channel"),
    ("Gửi tin nhắn",        "send_messages"),
    ("Đọc lịch sử",         "read_message_history"),
    ("Đính kèm file",       "attach_files"),
    ("Thêm reaction",       "add_reactions"),
    ("Dùng slash command",  "use_application_commands"),
    ("Nhúng link",          "embed_links"),
    ("Đề cập @everyone",    "mention_everyone"),
    ("Quản lý tin nhắn",    "manage_messages"),
    ("Kết nối voice",       "connect"),
    ("Nói trong voice",     "speak"),
    ("Dùng VAD",            "use_voice_activation"),
    ("Stream",              "stream"),
    ("Ưu tiên phát biểu",   "priority_speaker"),
    ("Tắt mic người khác",  "mute_members"),
    ("Tắt tai người khác",  "deafen_members"),
    ("Di chuyển members",   "move_members"),
    ("Quản lý kênh",        "manage_channels"),
    ("Quản lý webhooks",    "manage_webhooks"),
    ("Quản lý threads",     "manage_threads"),
    ("Tạo public thread",   "create_public_threads"),
    ("Tạo private thread",  "create_private_threads"),
    ("Gửi trong thread",    "send_messages_in_threads"),
]


def _perm_list_embed(title: str, note: str = "") -> discord.Embed:
    lines = []
    for i, (name, _) in enumerate(_PERM_LIST, 1):
        lines.append(f"`{i:>2}.` {name}")
    # Chia 2 cột
    half = (len(lines) + 1) // 2
    col1 = "\n".join(lines[:half])
    col2 = "\n".join(lines[half:])
    embed = discord.Embed(title=title, color=0x5865F2)
    embed.add_field(name="\u200b", value=col1, inline=True)
    embed.add_field(name="\u200b", value=col2, inline=True)
    if note:
        embed.set_footer(text=note)
    return embed


def _build_page_embeds(items: list, title_fn, desc: str, total_label: str) -> list[discord.Embed]:
    """Tạo list embed phân trang, mỗi trang 20 item."""
    PAGE = 20
    total_pages = max(1, (len(items) + PAGE - 1) // PAGE)
    embeds = []
    for page in range(total_pages):
        chunk = items[page * PAGE:(page + 1) * PAGE]
        start = page * PAGE + 1
        lines = [f"`{start + j:>3}.` {title_fn(items[page * PAGE + j], page * PAGE + j)}" for j, _ in enumerate(chunk)]
        half  = (len(lines) + 1) // 2
        title = title_fn.__doc__ or "Chọn"
        embed = discord.Embed(
            title       = f"{title} (trang {page+1}/{total_pages})" if total_pages > 1 else title,
            description = desc,
            color       = 0x5865F2,
        )
        embed.add_field(name="\u200b", value="\n".join(lines[:half]) or "—",      inline=True)
        embed.add_field(name="\u200b", value="\n".join(lines[half:]) or "\u200b", inline=True)
        embed.set_footer(text=f"Trang {page+1}/{total_pages}  •  {total_label}")
        embeds.append(embed)
    return embeds


class _PageView(View):
    """Embed phân trang với nút ◀ / ▶. Gọi wait() để chờ admin xong."""

    def __init__(self, embeds: list[discord.Embed], author_id: int):
        super().__init__(timeout=120)
        self.embeds    = embeds
        self.author_id = author_id
        self.page      = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= len(self.embeds) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, _):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)


def _role_list_embeds(guild: discord.Guild) -> tuple[list[discord.Embed], list]:
    roles = [r for r in sorted(guild.roles, key=lambda r: -r.position) if r.name != "@everyone"]
    def fmt(r, i): return r.mention
    PAGE = 20
    total_pages = max(1, (len(roles) + PAGE - 1) // PAGE)
    embeds = []
    for page in range(total_pages):
        chunk = roles[page * PAGE:(page + 1) * PAGE]
        start = page * PAGE + 1
        lines = [f"`{start + j:>3}.` {r.mention}" for j, r in enumerate(chunk)]
        half  = (len(lines) + 1) // 2
        embed = discord.Embed(
            title       = f"🏷️ Chọn Role" + (f" (trang {page+1}/{total_pages})" if total_pages > 1 else ""),
            description = "Nhập số thứ tự, cách nhau bởi dấu phẩy.\nVí dụ: `1, 3, 5`",
            color       = 0x5865F2,
        )
        embed.add_field(name="\u200b", value="\n".join(lines[:half]) or "—",      inline=True)
        embed.add_field(name="\u200b", value="\n".join(lines[half:]) or "\u200b", inline=True)
        embed.set_footer(text=f"Tổng {len(roles)} role  •  Trang {page+1}/{total_pages}")
        embeds.append(embed)
    return embeds, roles


def _channel_list_embeds(guild: discord.Guild) -> tuple[list[discord.Embed], list]:
    channels = [c for c in guild.channels
                if isinstance(c, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel, discord.StageChannel))]
    channels = sorted(channels, key=lambda c: (c.category.position if c.category else -1, c.position))
    PAGE = 20
    total_pages = max(1, (len(channels) + PAGE - 1) // PAGE)
    embeds = []
    for page in range(total_pages):
        chunk = channels[page * PAGE:(page + 1) * PAGE]
        start = page * PAGE + 1
        lines = [f"`{start + j:>3}.` {c.mention}" for j, c in enumerate(chunk)]
        half  = (len(lines) + 1) // 2
        embed = discord.Embed(
            title       = f"📋 Chọn Kênh" + (f" (trang {page+1}/{total_pages})" if total_pages > 1 else ""),
            description = "Nhập số thứ tự, cách nhau bởi dấu phẩy.\nVí dụ: `1, 2, 4`\nGõ `all` để chọn tất cả.",
            color       = 0x5865F2,
        )
        embed.add_field(name="\u200b", value="\n".join(lines[:half]) or "—",      inline=True)
        embed.add_field(name="\u200b", value="\n".join(lines[half:]) or "\u200b", inline=True)
        embed.set_footer(text=f"Tổng {len(channels)} kênh  •  Trang {page+1}/{total_pages}")
        embeds.append(embed)
    return embeds, channels


def _parse_indices(text: str, max_len: int) -> list[int] | None:
    """Parse '1, 3, 5' → [0, 2, 4]. Trả None nếu lỗi."""
    indices = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        try:
            n = int(part)
            if not (1 <= n <= max_len):
                return None
            indices.append(n - 1)
        except ValueError:
            return None
    return indices


class RolePermFlow:
    """
    Flow nhiều bước qua chat message:
    1. Gửi list role (paginator) → admin reply số
    2. Gửi list kênh (paginator) → admin reply số / all
    3. Gửi list quyền muốn BẬT → admin reply số / none
    4. Gửi list quyền muốn TẮT → admin reply số / none
    5. Xác nhận → apply
    """

    @staticmethod
    async def start(interaction: discord.Interaction):
        guild   = interaction.guild
        channel = interaction.channel
        bot     = interaction.client

        def check_author(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        async def wait_reply():
            """Chờ message từ admin."""
            try:
                msg = await bot.wait_for("message", check=check_author, timeout=120)
                return msg.content.strip()
            except asyncio.TimeoutError:
                await channel.send("⏱️ Hết thời gian chờ. Vui lòng chạy lại lệnh setup.")
                return None

        # ── Bước 1: chọn role ──
        role_embeds, roles = _role_list_embeds(guild)
        pv_role = _PageView(role_embeds, interaction.user.id)
        await interaction.response.send_message(embed=role_embeds[0], view=pv_role)

        raw = await wait_reply()
        if raw is None: return
        pv_role.stop()
        idxs = _parse_indices(raw, len(roles))
        if not idxs:
            return await channel.send("❌ Số không hợp lệ. Vui lòng chạy lại.")
        selected_roles = [roles[i] for i in idxs]

        # ── Bước 2: chọn kênh ──
        ch_embeds, channels = _channel_list_embeds(guild)
        pv_ch = _PageView(ch_embeds, interaction.user.id)
        await channel.send(embed=ch_embeds[0], view=pv_ch)

        raw = await wait_reply()
        if raw is None: return
        pv_ch.stop()
        if raw.lower() == "all":
            selected_channels = channels
        else:
            idxs = _parse_indices(raw, len(channels))
            if not idxs:
                return await channel.send("❌ Số không hợp lệ. Vui lòng chạy lại.")
            selected_channels = [channels[i] for i in idxs]

        # ── Bước 3: quyền BẬT ──
        allow_embed = _perm_list_embed(
            "✅ Chọn quyền muốn BẬT",
            "Nhập số thứ tự. VD: 1, 2, 5  hoặc  none để bỏ qua"
        )
        await channel.send(embed=allow_embed)
        raw = await wait_reply()
        if raw is None: return
        if raw.lower() == "none":
            allow_perms = []
        else:
            idxs = _parse_indices(raw, len(_PERM_LIST))
            if not idxs:
                return await channel.send("❌ Số không hợp lệ. Vui lòng chạy lại.")
            allow_perms = [_PERM_LIST[i] for i in idxs]

        # ── Bước 4: quyền TẮT ──
        deny_embed = _perm_list_embed(
            "❌ Chọn quyền muốn TẮT",
            "Nhập số thứ tự. VD: 3, 4  hoặc  none để bỏ qua"
        )
        await channel.send(embed=deny_embed)
        raw = await wait_reply()
        if raw is None: return
        if raw.lower() == "none":
            deny_perms = []
        else:
            idxs = _parse_indices(raw, len(_PERM_LIST))
            if not idxs:
                return await channel.send("❌ Số không hợp lệ. Vui lòng chạy lại.")
            deny_perms = [_PERM_LIST[i] for i in idxs]

        # Kiểm tra conflict
        allow_attrs = {a for _, a in allow_perms}
        deny_attrs  = {a for _, a in deny_perms}
        conflict    = allow_attrs & deny_attrs
        if conflict:
            names = ", ".join(n for n, a in _PERM_LIST if a in conflict)
            return await channel.send(f"❌ Quyền vừa BẬT vừa TẮT: **{names}**. Vui lòng chạy lại.")

        if not allow_perms and not deny_perms:
            return await channel.send("❌ Bạn chưa chọn quyền nào. Vui lòng chạy lại.")

        # ── Bước 5: xác nhận ──
        role_mentions  = " ".join(r.mention for r in selected_roles)
        ch_mentions    = " ".join(c.mention for c in selected_channels[:10])
        if len(selected_channels) > 10:
            ch_mentions += f" … (+{len(selected_channels)-10})"
        allow_names = ", ".join(n for n, _ in allow_perms) if allow_perms else "*(không có)*"
        deny_names  = ", ".join(n for n, _ in deny_perms)  if deny_perms  else "*(không có)*"

        confirm_embed = discord.Embed(title="⚠️ Xác nhận áp dụng quyền", color=0xF1C40F)
        confirm_embed.add_field(name="🏷️ Role",       value=role_mentions, inline=False)
        confirm_embed.add_field(name="📋 Kênh",        value=ch_mentions,   inline=False)
        confirm_embed.add_field(name="✅ Quyền BẬT",  value=allow_names,   inline=False)
        confirm_embed.add_field(name="❌ Quyền TẮT",  value=deny_names,    inline=False)
        confirm_embed.set_footer(text="Gõ  confirm  để áp dụng, hoặc  cancel  để huỷ.")
        await channel.send(embed=confirm_embed)

        raw = await wait_reply()
        if raw is None: return
        if raw.lower() != "confirm":
            return await channel.send("🚫 Đã huỷ.")

        # ── Apply ──
        progress = await channel.send(f"⏳ Đang áp dụng quyền cho **{len(selected_channels)}** kênh…")
        success, failed = 0, 0
        for ch in selected_channels:
            for role in selected_roles:
                try:
                    existing  = ch.overwrites_for(role)
                    overwrite = discord.PermissionOverwrite.from_pair(
                        existing.pair()[0], existing.pair()[1]
                    )
                    for _, attr in allow_perms:
                        setattr(overwrite, attr, True)
                    for _, attr in deny_perms:
                        setattr(overwrite, attr, False)
                    await ch.set_permissions(role, overwrite=overwrite,
                                             reason=f"RolePermFlow bởi {interaction.user}")
                    success += 1
                except Exception:
                    failed += 1

        result_embed = discord.Embed(title="✅ Hoàn tất áp dụng quyền", color=0x57F287)
        result_embed.add_field(name="🏷️ Role",      value=role_mentions,  inline=False)
        result_embed.add_field(name="✅ Thành công", value=f"**{success}** lượt", inline=True)
        if failed:
            result_embed.add_field(name="❌ Thất bại", value=f"**{failed}** lượt", inline=True)
        result_embed.add_field(name="✅ Bật",  value=allow_names, inline=False)
        result_embed.add_field(name="❌ Tắt",  value=deny_names,  inline=False)
        result_embed.set_footer(text=f"Bởi {interaction.user}")
        await progress.delete()
        await channel.send(embed=result_embed)


# ══════════════════════════════════════════
# COG
# ══════════════════════════════════════════
