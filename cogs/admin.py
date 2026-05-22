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

from core.data import (
    ADMIN_IDS, get_cfg_category, get_cfg_support_role, get_cfg_seller_role,
    get_cfg_counter_channel, get_cfg_balance_channel, get_cfg_legit_channel,
    get_cfg_proof_channel, get_cfg_ai_channel, get_cfg_font, set_cfg_font,
    save_cfg, load_data, save_data, get_buy_roles, save_buy_roles,
    get_user_total_spent, add_user_spent, get_price_sections, save_price_sections,
    can_use_dangerous_cmd, parse_amount, fmt_amount, _uname, _uname_plain,
    QR_FILE, get_qr_path, save_qr_path, get_or_fetch_channel,
)

BOT_VERSION = "3.9.0"
BOT_UPDATED = "2026-05-23"

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

_setup_sessions: dict = {}

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
        if self.index >= len(sections): return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)
        sections[self.index]["name"]    = self.name_input.value.strip()
        sections[self.index]["content"] = self.content_input.value.strip()
        save_price_sections(sections)
        await interaction.response.send_message(f"✅ Đã cập nhật **{sections[self.index]['name']}**!", ephemeral=True)

class EditPriceSectionSelect(Select):
    def __init__(self):
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        options  = [discord.SelectOption(label=sec["name"][:100], value=str(i), description=f"Key: {sec['key']}") for i, sec in enumerate(sections)]
        super().__init__(placeholder="Chọn mục muốn sửa...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        idx      = int(self.values[0])
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        if idx >= len(sections): return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)
        await interaction.response.send_modal(EditPriceModal(sections[idx], idx))

class AddPriceSectionModal(Modal, title="➕ Thêm Mục Giá Mới"):
    key_input     = TextInput(label="Key (chữ thường, không dấu)", placeholder="vd: spotify", max_length=30)
    name_input    = TextInput(label="Tên mục (có thể chứa emoji)", placeholder="vd: 🎵  Spotify", max_length=100)
    content_input = TextInput(label="Nội dung", placeholder="> - **Gói 1 tháng: 30.000 VNĐ**", style=discord.TextStyle.paragraph, max_length=1024)

    async def on_submit(self, interaction: discord.Interaction):
        key      = self.key_input.value.strip().lower().replace(" ", "_")
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        if any(s["key"] == key for s in sections): return await interaction.response.send_message(f"❌ Key `{key}` đã tồn tại!", ephemeral=True)
        sections.append({"key": key, "name": self.name_input.value.strip(), "content": self.content_input.value.strip()})
        save_price_sections(sections)
        await interaction.response.send_message(f"✅ Đã thêm mục **{self.name_input.value.strip()}**!", ephemeral=True)

class DeletePriceSectionSelect(Select):
    def __init__(self):
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        options  = [discord.SelectOption(label=sec["name"][:100], value=str(i), description=f"Key: {sec['key']}") for i, sec in enumerate(sections)]
        super().__init__(placeholder="Chọn mục muốn xoá...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        idx      = int(self.values[0])
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        if idx >= len(sections): return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)
        removed = sections.pop(idx)
        save_price_sections(sections)
        await interaction.response.send_message(f"🗑️ Đã xoá mục **{removed['name']}**.", ephemeral=True)

class DeletePriceSectionView(View):
    def __init__(self): super().__init__(timeout=60); self.add_item(DeletePriceSectionSelect())

class PriceManagerView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(EditPriceSectionSelect())

    @discord.ui.button(label="➕ Thêm mục mới", style=discord.ButtonStyle.success, row=1)
    async def add_section(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(AddPriceSectionModal())

    @discord.ui.button(label="🗑️ Xoá mục", style=discord.ButtonStyle.danger, row=1)
    async def del_section(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_message("Chọn mục muốn xoá:", view=DeletePriceSectionView(), ephemeral=True)

    @discord.ui.button(label="🔄 Reset về mặc định", style=discord.ButtonStyle.grey, row=1)
    async def reset_sections(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        save_price_sections(_DEFAULT_PRICE_SECTIONS)
        await interaction.response.send_message("✅ Đã reset bảng giá về mặc định!", ephemeral=True)

    @discord.ui.button(label="👁️ Xem trước .sv", style=discord.ButtonStyle.blurple, row=2)
    async def preview(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(embed=build_sv_embed(), ephemeral=True)

# ══════════════════════════════════════════
# SETTINGS VIEW
# ══════════════════════════════════════════
class SettingsView(View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=180)
        self.guild = guild

    async def _send_channel_select(self, interaction, cfg_key, title, description):
        options = [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id)) for ch in sorted(self.guild.text_channels, key=lambda c: c.position)[:25]]
        select  = ChannelConfigSelect(cfg_key=cfg_key, title=title, options=options)
        view    = View(timeout=60); view.add_item(select)
        await interaction.response.send_message(f"📌 **{description}**\nChọn kênh:", view=view, ephemeral=True)

    async def _send_role_select(self, interaction, cfg_key, title):
        options = [discord.SelectOption(label=r.name[:100], value=str(r.id)) for r in sorted(self.guild.roles, key=lambda r: -r.position) if r.name != "@everyone"][:25]
        select  = RoleConfigSelect(cfg_key=cfg_key, title=title, options=options)
        view    = View(timeout=60); view.add_item(select)
        await interaction.response.send_message(f"🏷️ **{title}**\nChọn role:", view=view, ephemeral=True)

    @discord.ui.button(label="📋 Log Channel",      style=discord.ButtonStyle.primary,   row=0)
    async def log(self,      i, b): await self._send_channel_select(i, "cfg_log_rudy",        "Log Rudy",         "Kênh log rudy — nhận toàn bộ hoạt động bot")
    @discord.ui.button(label="🎫 Ticket Category",  style=discord.ButtonStyle.secondary, row=0)
    async def cat(self,      i, b): await i.response.send_message("ℹ️ Category được cài qua ID trong code. Dùng `.settings` để xem ID hiện tại.", ephemeral=True)
    @discord.ui.button(label="🛡️ Support Role",     style=discord.ButtonStyle.secondary, row=0)
    async def support(self,  i, b): await self._send_role_select(i, "cfg_support_role",   "Support Role")
    @discord.ui.button(label="🏪 Seller Role",      style=discord.ButtonStyle.secondary, row=1)
    async def seller(self,   i, b): await self._send_role_select(i, "cfg_seller_role",    "Seller Role")
    @discord.ui.button(label="💰 Balance Channel",  style=discord.ButtonStyle.secondary, row=1)
    async def balance(self,  i, b): await self._send_channel_select(i, "cfg_balance_channel", "Balance Channel",  "Kênh nhận +/- tiền tự động")
    @discord.ui.button(label="✅ Legit Channel",    style=discord.ButtonStyle.secondary, row=1)
    async def legit(self,    i, b): await self._send_channel_select(i, "cfg_legit_channel",   "Legit Channel",    "Kênh nhận +1legit tự động")
    @discord.ui.button(label="📸 Proof Channel",   style=discord.ButtonStyle.secondary, row=2)
    async def proof(self,    i, b): await self._send_channel_select(i, "cfg_proof_channel",   "Proof Channel",    "Kênh nhận done tự động")
    @discord.ui.button(label="🤖 AI Channel",       style=discord.ButtonStyle.secondary, row=2)
    async def ai(self,       i, b): await self._send_channel_select(i, "cfg_ai_channel",      "AI Channel",       "Kênh AI tự động trả lời mọi tin nhắn")
    @discord.ui.button(label="🖼️ Cập nhật QR",     style=discord.ButtonStyle.primary,   row=3)
    async def qr(self,       i, b):
        if i.user.id not in ADMIN_IDS: return await i.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await i.response.send_modal(SetQRModal())

class ChannelConfigSelect(Select):
    def __init__(self, cfg_key, title, options):
        super().__init__(placeholder=f"Chọn kênh cho {title}...", options=options)
        self.cfg_key = cfg_key; self.title = title

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        ch_id = int(self.values[0])
        save_cfg(self.cfg_key, ch_id)
        await interaction.response.send_message(f"✅ Đã cài **{self.title}** → <#{ch_id}>", ephemeral=True)

class RoleConfigSelect(Select):
    def __init__(self, cfg_key, title, options):
        super().__init__(placeholder=f"Chọn role cho {title}...", options=options)
        self.cfg_key = cfg_key; self.title = title

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        role_id = int(self.values[0])
        save_cfg(self.cfg_key, role_id)
        await interaction.response.send_message(f"✅ Đã cài **{self.title}** → <@&{role_id}>", ephemeral=True)

class SetQRModal(Modal):
    def __init__(self): super().__init__(title="🖼️ Cập Nhật Ảnh QR")
    url_input = TextInput(label="URL ảnh QR (để trống nếu đính kèm file)", placeholder="https://i.imgur.com/abc123.png", required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        import urllib.request
        url = self.url_input.value.strip()
        if url:
            try:
                qr_path = QR_FILE
                urllib.request.urlretrieve(url, qr_path)
                save_qr_path(qr_path)
                embed = discord.Embed(title="✅  Đã Cập Nhật QR", description="Mã QR mới đã được lưu từ URL.", color=0x57F287, timestamp=datetime.now(timezone.utc))
                embed.set_image(url=url)
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                return await interaction.response.send_message(f"❌ Không tải được ảnh từ URL: `{e}`", ephemeral=True)
        await interaction.response.send_message("📎 Hãy **đính kèm ảnh QR** vào tin nhắn tiếp theo trong vòng **60 giây**.", ephemeral=True)
        def check(m): return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and len(m.attachments) > 0
        import asyncio
        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=60)
            att = msg.attachments[0]
            if not att.content_type or not att.content_type.startswith("image/"): return await interaction.followup.send("❌ File không phải ảnh!", ephemeral=True)
            qr_path = QR_FILE
            await att.save(qr_path); save_qr_path(qr_path)
            try: await msg.delete()
            except: pass
            embed = discord.Embed(title="✅  Đã Cập Nhật QR", description="Mã QR mới đã được lưu!\nDùng `.qr` để kiểm tra.", color=0x57F287, timestamp=datetime.now(timezone.utc))
            await interaction.followup.send(embed=embed, ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Hết thời gian!", ephemeral=True)

# ══════════════════════════════════════════
# SETUP — MAIN MENU
# ══════════════════════════════════════════
class SetupMainView(View):
    def __init__(self, ctx):
        super().__init__(timeout=180)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="📋 Kênh", style=discord.ButtonStyle.primary, row=0)
    async def btn_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_setup_channel_embed(),
            view=SetupChannelView(interaction),
            ephemeral=True,
        )

    @discord.ui.button(label="🗂️ Danh mục", style=discord.ButtonStyle.primary, row=0)
    async def btn_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_setup_category_embed(),
            view=SetupCategoryView(interaction),
            ephemeral=True,
        )

    @discord.ui.button(label="🏷️ Role", style=discord.ButtonStyle.primary, row=0)
    async def btn_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_setup_role_embed(),
            view=SetupRoleView(interaction),
            ephemeral=True,
        )

    @discord.ui.button(label="⚙️ Server", style=discord.ButtonStyle.success, row=0)
    async def btn_server(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=_setup_server_embed(interaction.guild),
            view=SetupServerView(interaction),
            ephemeral=True,
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
        opts = [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
                for ch in sorted(interaction.guild.channels, key=lambda c: c.position)
                if not isinstance(ch, discord.CategoryChannel)][:25]
        if not opts: return await interaction.response.send_message("❌ Không có kênh nào.", ephemeral=True)
        v = View(timeout=60); v.add_item(_DeleteChannelSelect(opts))
        await interaction.response.send_message("🗑️ Chọn kênh cần xoá:", view=v, ephemeral=True)

    @discord.ui.button(label="✏️ Đổi tên",    style=discord.ButtonStyle.secondary, row=0)
    async def rename(self, interaction, _):
        opts = [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
                for ch in sorted(interaction.guild.channels, key=lambda c: c.position)
                if not isinstance(ch, discord.CategoryChannel)][:25]
        if not opts: return await interaction.response.send_message("❌ Không có kênh nào.", ephemeral=True)
        v = View(timeout=60); v.add_item(_RenameChannelSelect(opts))
        await interaction.response.send_message("✏️ Chọn kênh cần đổi tên:", view=v, ephemeral=True)

    @discord.ui.button(label="🔤 Font tên",   style=discord.ButtonStyle.secondary, row=1)
    async def font(self, interaction, _):
        opts = [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
                for ch in sorted(interaction.guild.channels, key=lambda c: c.position)
                if not isinstance(ch, discord.CategoryChannel)][:25]
        if not opts: return await interaction.response.send_message("❌ Không có kênh nào.", ephemeral=True)
        v = View(timeout=60); v.add_item(_FontChannelSelect(opts))
        await interaction.response.send_message("🔤 Chọn kênh cần đổi font:", view=v, ephemeral=True)

    @discord.ui.button(label="📋 Clone kênh", style=discord.ButtonStyle.secondary, row=1)
    async def clone(self, interaction, _):
        opts = [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
                for ch in sorted(interaction.guild.channels, key=lambda c: c.position)
                if not isinstance(ch, discord.CategoryChannel)][:25]
        if not opts: return await interaction.response.send_message("❌ Không có kênh nào.", ephemeral=True)
        v = View(timeout=60); v.add_item(_CloneChannelSelect(opts))
        await interaction.response.send_message("📋 Chọn kênh cần clone:", view=v, ephemeral=True)


class CreateChannelModal(discord.ui.Modal, title="➕ Tạo Kênh Mới"):
    name_input = TextInput(label="Tên kênh", placeholder="vd: 💬・general", max_length=100)
    type_input = TextInput(label="Loại (text/voice/stage/forum)", placeholder="text", default="text", max_length=10)
    private_input = TextInput(label="Private? (yes/no)", placeholder="no", default="no", max_length=3)
    category_input = TextInput(label="Tên hoặc ID category (để trống = không có)", required=False, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        ch_type_key = self.type_input.value.strip().lower()
        if ch_type_key not in _CHANNEL_TYPE_MAP:
            return await interaction.response.send_message(
                "❌ Loại kênh không hợp lệ. Dùng: `text`, `voice`, `stage`, `forum`.", ephemeral=True
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
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền tạo kênh.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Lỗi: {e}", ephemeral=True)


class _DeleteChannelSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn kênh cần xoá…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.", ephemeral=True)
        name = ch.name
        try:
            await ch.delete(reason=f"Setup xoá bởi {interaction.user}")
            await interaction.response.send_message(f"🗑️ Đã xoá kênh `#{name}`.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền xoá kênh.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


class _RenameChannelSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn kênh cần đổi tên…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.", ephemeral=True)
        await interaction.response.send_modal(_RenameChannelModal(ch))

class _RenameChannelModal(discord.ui.Modal):
    def __init__(self, ch):
        super().__init__(title=f"✏️ Đổi tên: #{ch.name[:40]}")
        self.ch = ch
        self.new_name = TextInput(label="Tên mới", placeholder="Nhập tên mới…", max_length=100)
        self.add_item(self.new_name)
    async def on_submit(self, interaction: discord.Interaction):
        parts = _detect_channel_parts(self.ch.name)
        font  = get_cfg_font()
        final = _rebuild_name(parts, self.new_name.value.strip(), font)
        old   = self.ch.name
        try:
            await self.ch.edit(name=final, reason=f"Setup rename bởi {interaction.user}")
            await interaction.response.send_message(f"✅ `#{old}` → `#{final}`", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


class _FontChannelSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn kênh cần đổi font…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.", ephemeral=True)
        font_opts = [discord.SelectOption(label=lbl[:100], value=key) for key, lbl in FONT_LABELS.items()]
        v = View(timeout=60); v.add_item(_ApplyFontChannelSelect(ch, font_opts))
        await interaction.response.send_message(f"🔤 Chọn font cho `#{ch.name}`:", view=v, ephemeral=True)

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
                f"✅ Font `{FONT_LABELS.get(font, font)}` → `#{old}` đã đổi thành `#{final}`", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


class _CloneChannelSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn kênh cần clone…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.", ephemeral=True)
        try:
            cloned = await ch.clone(reason=f"Setup clone bởi {interaction.user}")
            await interaction.response.send_message(
                f"📋 Đã clone `#{ch.name}` → {cloned.mention}", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


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
        if not opts: return await interaction.response.send_message("❌ Không có category nào.", ephemeral=True)
        v = View(timeout=60); v.add_item(_DeleteCategorySelect(opts))
        await interaction.response.send_message("🗑️ Chọn category cần xoá:", view=v, ephemeral=True)

    @discord.ui.button(label="✏️ Đổi tên / Font", style=discord.ButtonStyle.secondary, row=0)
    async def rename(self, interaction, _):
        opts = [discord.SelectOption(label=c.name[:100], value=str(c.id)) for c in interaction.guild.categories][:25]
        if not opts: return await interaction.response.send_message("❌ Không có category nào.", ephemeral=True)
        v = View(timeout=60); v.add_item(_RenameCategorySelect(opts))
        await interaction.response.send_message("✏️ Chọn category cần đổi tên:", view=v, ephemeral=True)

    @discord.ui.button(label="📂 Di chuyển kênh", style=discord.ButtonStyle.secondary, row=1)
    async def move(self, interaction, _):
        ch_opts = [discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
                   for ch in sorted(interaction.guild.channels, key=lambda c: c.position)
                   if not isinstance(ch, discord.CategoryChannel)][:25]
        if not ch_opts: return await interaction.response.send_message("❌ Không có kênh nào.", ephemeral=True)
        v = View(timeout=60); v.add_item(_MoveChannelSelect(ch_opts))
        await interaction.response.send_message("📂 Chọn kênh cần di chuyển:", view=v, ephemeral=True)


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
            await interaction.response.send_message(f"📂 Đã tạo category **{cat.name}**!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


class _DeleteCategorySelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn category cần xoá…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        cat = interaction.guild.get_channel(int(self.values[0]))
        if not cat: return await interaction.response.send_message("❌ Không tìm thấy.", ephemeral=True)
        name = cat.name
        try:
            await cat.delete(reason=f"Setup xoá category bởi {interaction.user}")
            await interaction.response.send_message(f"🗑️ Đã xoá category `{name}`.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


class _RenameCategorySelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn category cần đổi tên…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        cat = interaction.guild.get_channel(int(self.values[0]))
        if not cat: return await interaction.response.send_message("❌ Không tìm thấy.", ephemeral=True)
        await interaction.response.send_modal(_RenameCategoryModal(cat))

class _RenameCategoryModal(discord.ui.Modal):
    def __init__(self, cat):
        super().__init__(title=f"✏️ Đổi tên: {cat.name[:40]}")
        self.cat = cat
        self.new_name = TextInput(label="Tên mới", max_length=100)
        self.font_input = TextInput(label="Font (normal/bold/italic/sans_bold/script/double)", default="normal", max_length=20)
        self.add_item(self.new_name); self.add_item(self.font_input)
    async def on_submit(self, interaction: discord.Interaction):
        font  = self.font_input.value.strip().lower()
        if font not in _FONT_MAPS: font = "normal"
        parts = _detect_channel_parts(self.cat.name)
        final = _rebuild_name(parts, self.new_name.value.strip(), font)
        old   = self.cat.name
        try:
            await self.cat.edit(name=final, reason=f"Setup rename category bởi {interaction.user}")
            await interaction.response.send_message(f"✅ `{old}` → `{final}`", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


class _MoveChannelSelect(Select):
    def __init__(self, ch_opts): super().__init__(placeholder="Chọn kênh cần di chuyển…", options=ch_opts)
    async def callback(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.values[0]))
        if not ch: return await interaction.response.send_message("❌ Không tìm thấy kênh.", ephemeral=True)
        cat_opts = [discord.SelectOption(label=c.name[:100], value=str(c.id)) for c in interaction.guild.categories][:25]
        cat_opts.insert(0, discord.SelectOption(label="(Không có category)", value="0"))
        v = View(timeout=60); v.add_item(_MoveToCategorySelect(ch, cat_opts))
        await interaction.response.send_message(f"📂 Chọn category đích cho `#{ch.name}`:", view=v, ephemeral=True)

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
                f"📂 Đã di chuyển `#{self.ch.name}` → `{dest}`", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


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
        if not opts: return await interaction.response.send_message("❌ Không có role.", ephemeral=True)
        v = View(timeout=60); v.add_item(_DeleteRoleSelect(opts))
        await interaction.response.send_message("🗑️ Chọn role cần xoá:", view=v, ephemeral=True)

    @discord.ui.button(label="✅ Gán role",   style=discord.ButtonStyle.secondary, row=0)
    async def give(self, interaction, _): await interaction.response.send_modal(AssignRoleModal(action="give"))

    @discord.ui.button(label="❌ Gỡ role",   style=discord.ButtonStyle.secondary, row=1)
    async def take(self, interaction, _): await interaction.response.send_modal(AssignRoleModal(action="take"))


class CreateRoleModal(discord.ui.Modal, title="➕ Tạo Role Mới"):
    name_input    = TextInput(label="Tên role", max_length=100)
    color_input   = TextInput(label="Màu hex (vd: #FF5733, để trống = mặc định)", required=False, max_length=7)
    hoist_input   = TextInput(label="Hiển thị riêng? (yes/no)", default="no",  max_length=3)
    mention_input = TextInput(label="Có thể @mention? (yes/no)",  default="no",  max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        color = discord.Color.default()
        if self.color_input.value.strip():
            try: color = discord.Color(int(self.color_input.value.strip().lstrip("#"), 16))
            except: pass
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
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền tạo role.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


class _DeleteRoleSelect(Select):
    def __init__(self, opts): super().__init__(placeholder="Chọn role cần xoá…", options=opts)
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if not role: return await interaction.response.send_message("❌ Không tìm thấy role.", ephemeral=True)
        name = role.name
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ Role này cao hơn hoặc bằng role của bot.", ephemeral=True)
        try:
            await role.delete(reason=f"Setup xoá role bởi {interaction.user}")
            await interaction.response.send_message(f"🗑️ Đã xoá role `{name}`.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


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
            return await interaction.response.send_message(f"❌ Không tìm thấy member `{self.member_input.value}`.", ephemeral=True)
        # Resolve role
        raw_r = self.role_input.value.strip()
        role = None
        try: role = guild.get_role(int(raw_r))
        except ValueError:
            role = discord.utils.find(lambda r: r.name.lower() == raw_r.lower(), guild.roles)
        if not role:
            return await interaction.response.send_message(f"❌ Không tìm thấy role `{raw_r}`.", ephemeral=True)
        if role >= guild.me.top_role:
            return await interaction.response.send_message("❌ Role này cao hơn hoặc bằng role của bot.", ephemeral=True)
        try:
            if self.action == "give":
                await member.add_roles(role, reason=f"Setup gán role bởi {interaction.user}")
                await interaction.response.send_message(
                    f"✅ Đã gán {role.mention} cho {member.mention}.", ephemeral=True
                )
            else:
                await member.remove_roles(role, reason=f"Setup gỡ role bởi {interaction.user}")
                await interaction.response.send_message(
                    f"✅ Đã gỡ {role.mention} khỏi {member.mention}.", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)


# ══════════════════════════════════════════
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
        if not opts: return await interaction.response.send_message("❌ Không có kênh.", ephemeral=True)
        v = View(timeout=60); v.add_item(_ServerChannelSelect("cfg_welcome_channel", "Welcome Channel", opts))
        await interaction.response.send_message("👋 Chọn kênh **Welcome**:", view=v, ephemeral=True)

    @discord.ui.button(label="👋 Goodbye Channel", style=discord.ButtonStyle.secondary, row=0)
    async def goodbye(self, interaction, _):
        opts = self._ch_select(interaction.guild, "Goodbye")
        if not opts: return await interaction.response.send_message("❌ Không có kênh.", ephemeral=True)
        v = View(timeout=60); v.add_item(_ServerChannelSelect("cfg_goodbye_channel", "Goodbye Channel", opts))
        await interaction.response.send_message("👋 Chọn kênh **Goodbye**:", view=v, ephemeral=True)

    @discord.ui.button(label="📋 Log Channel", style=discord.ButtonStyle.secondary, row=0)
    async def log(self, interaction, _):
        opts = self._ch_select(interaction.guild, "Log")
        if not opts: return await interaction.response.send_message("❌ Không có kênh.", ephemeral=True)
        v = View(timeout=60); v.add_item(_ServerChannelSelect("cfg_log_rudy", "Log Channel", opts))
        await interaction.response.send_message("📋 Chọn kênh **Log**:", view=v, ephemeral=True)

    @discord.ui.button(label="🎭 Auto-role Join", style=discord.ButtonStyle.secondary, row=1)
    async def autorole(self, interaction, _):
        opts = self._role_select(interaction.guild)
        if not opts: return await interaction.response.send_message("❌ Không có role.", ephemeral=True)
        v = View(timeout=60); v.add_item(_ServerRoleSelect("cfg_autorole_join", "Auto-role khi Join", opts))
        await interaction.response.send_message("🎭 Chọn role **tự động gán** khi member join:", view=v, ephemeral=True)

    @discord.ui.button(label="🔤 Đặt Prefix Bot", style=discord.ButtonStyle.primary, row=1)
    async def prefix(self, interaction, _): await interaction.response.send_modal(SetPrefixModal())

    @discord.ui.button(label="👁️ Xem trạng thái", style=discord.ButtonStyle.blurple, row=2)
    async def view_status(self, interaction, _):
        await interaction.response.send_message(
            embed=_setup_server_embed(interaction.guild), ephemeral=True
        )


class _ServerChannelSelect(Select):
    def __init__(self, cfg_key, title, opts):
        super().__init__(placeholder=f"Chọn kênh cho {title}…", options=opts)
        self.cfg_key = cfg_key; self.title = title
    async def callback(self, interaction: discord.Interaction):
        ch_id = int(self.values[0])
        save_cfg(self.cfg_key, ch_id)
        await interaction.response.send_message(
            f"✅ Đã cài **{self.title}** → <#{ch_id}>", ephemeral=True
        )

class _ServerRoleSelect(Select):
    def __init__(self, cfg_key, title, opts):
        super().__init__(placeholder=f"Chọn role cho {title}…", options=opts)
        self.cfg_key = cfg_key; self.title = title
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        save_cfg(self.cfg_key, role_id)
        await interaction.response.send_message(
            f"✅ Đã cài **{self.title}** → <@&{role_id}>", ephemeral=True
        )

class SetPrefixModal(discord.ui.Modal, title="🔤 Đặt Prefix Bot"):
    prefix_input = TextInput(label="Prefix mới", placeholder="vd: ! hoặc ? hoặc .", max_length=5)
    async def on_submit(self, interaction: discord.Interaction):
        prefix = self.prefix_input.value.strip()
        if not prefix: return await interaction.response.send_message("❌ Prefix không được để trống.", ephemeral=True)
        save_cfg("cfg_prefix", prefix)
        await interaction.response.send_message(f"✅ Prefix bot đã đổi thành `{prefix}`.", ephemeral=True)


# ══════════════════════════════════════════
# COG
# ══════════════════════════════════════════
class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── .settings ──
    @commands.command(name="settings", aliases=["setting", "caidat", "st"])
    async def settings_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return
        data = load_data()
        embed = discord.Embed(title="⚙️  Bot Settings — TuyTam Store", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        def ch(k, d): c = data.get(k, d); return f"<#{c}>" if c else "Chưa cài"
        def ro(k, d): r = data.get(k, d); return f"<@&{r}>" if r else "Chưa cài"
        embed.add_field(name="📋 Log Channel (Rudy)", value=ch("cfg_log_rudy", 0),                                    inline=True)
        embed.add_field(name="🎫 Ticket Category",    value=ch("cfg_ticket_category", 0),                              inline=True)
        embed.add_field(name="🛡️ Support Role",      value=ro("cfg_support_role",    1474572393908404305), inline=True)
        embed.add_field(name="🏪 Seller Role",       value=ro("cfg_seller_role",     0),                   inline=True)
        embed.add_field(name="💰 Balance Channel",   value=ch("cfg_balance_channel", 1464999465294369035), inline=True)
        embed.add_field(name="✅ Legit Channel",     value=ch("cfg_legit_channel",   0),                   inline=True)
        embed.add_field(name="📸 Proof Channel",    value=ch("cfg_proof_channel",   1469647159560241318), inline=True)
        embed.add_field(name="🤖 AI Channel",        value=ch("cfg_ai_channel",      0),                   inline=True)
        embed.add_field(name="🔤 Font server",       value=FONT_LABELS.get(data.get("cfg_font","normal"),"normal"), inline=True)
        qr_val = data.get("qr_path") or "Chưa cài"
        embed.add_field(name="🖼️ QR Path",           value=f"`{qr_val}`",                                              inline=False)
        embed.set_footer(text=f"Nhấn nút bên dưới để thay đổi  •  Yêu cầu bởi {ctx.author}")
        await ctx.reply(embed=embed, view=SettingsView(ctx.guild))

    # ── .sv / .giaset ──
    @commands.command(name="sv", aliases=["dichvu", "service"])
    async def sv_cmd(self, ctx):
        await ctx.send(embed=build_sv_embed())

    @commands.command(name="giaset", aliases=["setgia", "pricemanager", "priceset"])
    async def giaset_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        embed = discord.Embed(title="⚙️  Quản Lý Bảng Giá — .sv", description=f"Hiện có **{len(sections)} mục** trong bảng giá.\nChọn mục từ dropdown để **sửa**, hoặc dùng nút bên dưới.\n\n" + "\n".join(f"`{i+1}.` {s['name']}" for i, s in enumerate(sections)), color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="💡 Hướng dẫn", value="Hỗ trợ đầy đủ **Discord markdown**:\n› `**bold**`, `~~gạch~~`, `> blockquote`\n› Emoji server: `<:tên:id>`\n› `### Tiêu đề nhỏ`", inline=False)
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Timeout 2 phút")
        await ctx.reply(embed=embed, view=PriceManagerView())

    # ── .clear ──
    @commands.command(name="clear", aliases=["purge", "xoa"])
    async def clear_cmd(self, ctx, amount: int = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Bạn không có quyền.")
        if amount is None: return await ctx.reply("❌ Dùng: `.clear <số lượng>` (tối đa 500)")
        amount = max(1, min(amount, 500))
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🗑️ Đã xoá **{len(deleted)-1}** tin nhắn.", delete_after=5)

    # ── .addrole / .removerole ──
    @commands.command(name="addrole", aliases=["giverole"])
    async def addrole_cmd(self, ctx, member: discord.Member = None, role: discord.Role = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Bạn không có quyền.")
        if not member or not role: return await ctx.reply("❌ Dùng: `.addrole @user @role`")
        if role >= ctx.guild.me.top_role: return await ctx.reply("❌ Role này cao hơn role của bot.")
        await member.add_roles(role, reason=f"Bởi {ctx.author}")
        embed = discord.Embed(title="✅ Đã Thêm Role", color=0x57F287)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
        await ctx.reply(embed=embed)

    @commands.command(name="removerole", aliases=["takerole"])
    async def removerole_cmd(self, ctx, member: discord.Member = None, role: discord.Role = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Bạn không có quyền.")
        if not member or not role: return await ctx.reply("❌ Dùng: `.removerole @user @role`")
        await member.remove_roles(role, reason=f"Bởi {ctx.author}")
        embed = discord.Embed(title="✅ Đã Xoá Role", color=0xFEE75C)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
        await ctx.reply(embed=embed)

    # ── .emoji / .delemoji ──
    @commands.command(name="emoji")
    async def emoji_cmd(self, ctx, *, args: str = None):
        if not can_use_dangerous_cmd(ctx.author.id, "emoji"): return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not args:
            return await ctx.reply("❌ Dùng: `.emoji <emoji1> <emoji2>...` để copy emoji từ server khác.\nHoặc `.emoji` để vào chế độ chờ ảnh upload.")
        import aiohttp
        matches = _re.findall(r"<(a?):([^:>]+):(\d+)>", args)
        if not matches: return await ctx.reply("❌ Không tìm thấy emoji hợp lệ.")
        prog = await ctx.reply(f"⏳ Đang thêm **{len(matches)}** emoji...")
        added, failed = [], []
        async with aiohttp.ClientSession() as session:
            for animated, name, emoji_id in matches:
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}?quality=lossless"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status != 200: raise Exception(f"HTTP {r.status}")
                        data = await r.read()
                    em = await ctx.guild.create_custom_emoji(name=name[:32], image=data, reason=f"Bởi {ctx.author}")
                    added.append(str(em))
                except Exception as e:
                    failed.append(f"`{name}` — {e}")
                await asyncio.sleep(1.5)
        lines = []
        if added:   lines.append(f"✅ Đã thêm **{len(added)}**:\n{' '.join(added)[:900]}")
        if failed:  lines.append(f"❌ Thất bại **{len(failed)}**:\n" + "\n".join(failed[:10]))
        await prog.edit(content="\n\n".join(lines) if lines else "Không có emoji nào được thêm.")

    @commands.command(name="delemoji")
    async def delemoji_cmd(self, ctx, *, args: str = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Chỉ admin.")
        if not args: return await ctx.reply("❌ Dùng: `.delemoji <emoji1> <emoji2>...`")
        matches = _re.findall(r"<a?:[^:>]+:(\d+)>", args)
        if not matches: return await ctx.reply("❌ Không tìm thấy emoji hợp lệ.")
        deleted, failed = [], []
        for eid_str in matches:
            eid = int(eid_str)
            em  = discord.utils.get(ctx.guild.emojis, id=eid)
            if not em: failed.append(f"`{eid}`"); continue
            try: await em.delete(reason=f"Bởi {ctx.author}"); deleted.append(f"`:{em.name}:`")
            except Exception as e: failed.append(f"`:{em.name}:` — {e}")
        lines = []
        if deleted: lines.append(f"✅ Đã xoá **{len(deleted)}** emoji:\n{' '.join(deleted)}")
        if failed:  lines.append(f"❌ Thất bại **{len(failed)}**:\n{' '.join(failed[:10])}")
        await ctx.reply("\n\n".join(lines) if lines else "Không có emoji nào được xoá.")

    # ── .rename / .setperm / .mkchannel / .setup ──
    @commands.command(name="rename")
    async def rename_cmd(self, ctx, channel: discord.abc.GuildChannel = None, *, new_name: str = None):
        if not can_use_dangerous_cmd(ctx.author.id, "rename"): return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not channel or not new_name: return await ctx.reply("❌ Dùng: `.rename #kênh tên-mới`")
        parts = _detect_channel_parts(channel.name)
        font  = _setup_sessions.get(ctx.guild.id, {}).get("font", "normal")
        final = _rebuild_name(parts, new_name, font)
        try: await channel.edit(name=final, reason=f"Rename bởi {ctx.author}"); await ctx.reply(f"✅ `{channel.name}` → `{final}`")
        except discord.Forbidden: await ctx.reply("❌ Bot thiếu quyền.")
        except Exception as e: await ctx.reply(f"❌ {e}")

    @commands.command(name="setperm")
    async def setperm_cmd(self, ctx, channel: discord.TextChannel = None, role: discord.Role = None, *, flags: str = ""):
        if not can_use_dangerous_cmd(ctx.author.id, "setperm"): return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not channel or not role: return await ctx.reply("❌ Dùng: `.setperm #kênh @role xem=true gửi=false`")
        overwrite = channel.overwrites_for(role)
        flag_map  = {"xem":"read_messages","gửi":"send_messages","đọc":"read_messages","view":"read_messages","send":"send_messages","manage":"manage_messages","ql":"manage_messages","reaction":"add_reactions","embed":"embed_links","file":"attach_files"}
        changes   = []
        for part in flags.split():
            if "=" not in part: continue
            k, v = part.split("=", 1)
            attr = flag_map.get(k.lower().strip())
            if not attr: continue
            val  = True if v.lower() in ("true","1","yes","on") else (False if v.lower() in ("false","0","no","off") else None)
            setattr(overwrite, attr, val)
            changes.append(f"{k}={'✅' if val else ('❌' if val is False else '↩️ default')}")
        if not changes: return await ctx.reply("❌ Không có flag hợp lệ. VD: `xem=true gửi=false`")
        try: await channel.set_permissions(role, overwrite=overwrite, reason=f"setperm bởi {ctx.author}"); await ctx.reply(f"✅ Đã sửa quyền `#{channel.name}` cho {role.mention}:\n" + "\n".join(f"  › {c}" for c in changes))
        except discord.Forbidden: await ctx.reply("❌ Bot thiếu quyền Manage Channels.")
        except Exception as e: await ctx.reply(f"❌ {e}")

    @commands.command(name="mkchannel", aliases=["mkch", "taokenh"])
    async def mkchannel_cmd(self, ctx, *, args: str = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Chỉ admin.")
        if not args: return await ctx.reply("❌ Dùng: `.mkchannel text <tên>` hoặc `.mkchannel voice <tên>` hoặc `.mkchannel category <tên>`")
        parts = args.strip().split(None, 1)
        if len(parts) < 2: return await ctx.reply("❌ Thiếu tên kênh.")
        ch_type  = parts[0].lower()
        raw_name = parts[1].strip().strip('"').strip("'")
        if ch_type not in ("text","voice","category","t","v","c"): return await ctx.reply("❌ Loại kênh không hợp lệ.")
        font       = get_cfg_font()
        ch_parts   = _detect_channel_parts(raw_name)
        styled     = _rebuild_name(ch_parts, ch_parts["base_text"], font)
        category   = ctx.channel.category
        try:
            if ch_type in ("text","t"):     new_ch = await ctx.guild.create_text_channel(name=styled, category=category, reason=f"Tạo bởi {ctx.author}"); icon = "📝"
            elif ch_type in ("voice","v"):  new_ch = await ctx.guild.create_voice_channel(name=styled, category=category, reason=f"Tạo bởi {ctx.author}"); icon = "🔊"
            else:                           new_ch = await ctx.guild.create_category(name=styled, reason=f"Tạo bởi {ctx.author}"); icon = "📂"
            embed = discord.Embed(title=f"{icon} Đã tạo kênh thành công!", color=0x57F287, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Tên gốc",    value=f"`{raw_name}`",    inline=True)
            embed.add_field(name="Tên đã tạo", value=new_ch.mention,     inline=True)
            embed.add_field(name="Font",       value=FONT_LABELS.get(font, font), inline=True)
            await ctx.reply(embed=embed)
        except discord.Forbidden: await ctx.reply("❌ Bot thiếu quyền tạo kênh.")
        except Exception as e: await ctx.reply(f"❌ Lỗi: {e}")

    # ── .setup ──
    @commands.command(name="setup", aliases=["sv_setup", "serversetup"])
    async def setup_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền dùng lệnh này.")
        embed = discord.Embed(
            title="🔧  Setup Server — TuyTam Bot",
            description=(
                "Chọn nhóm chức năng bạn muốn thiết lập.\n"
                "Dùng các nút bên dưới để điều hướng."
            ),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="📋 Quản lý kênh",    value="Tạo / Xoá / Đổi tên / Font / Clone kênh", inline=True)
        embed.add_field(name="🗂️ Quản lý danh mục", value="Tạo / Xoá / Đổi tên / Di chuyển kênh",    inline=True)
        embed.add_field(name="🏷️ Quản lý role",    value="Tạo / Xoá / Gán role cho member",           inline=True)
        embed.add_field(name="⚙️ Setup server",     value="Welcome / Log / Auto-role / Prefix",        inline=True)
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Timeout 3 phút")
        await ctx.reply(embed=embed, view=SetupMainView(ctx))

    # ── .botinfo / .qr ──
    @commands.command(name="botinfo")
    async def botinfo_cmd(self, ctx):
        import platform
        embed = discord.Embed(title=f"🤖  {self.bot.user.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",        value=f"`{self.bot.user.id}`",                             inline=True)
        embed.add_field(name="🌐 Servers",   value=f"**{len(self.bot.guilds)}**",                       inline=True)
        embed.add_field(name="🏓 Latency",   value=f"**{round(self.bot.latency*1000)}ms**",             inline=True)
        embed.add_field(name="🐍 Python",    value=f"`{platform.python_version()}`",                   inline=True)
        embed.add_field(name="📦 discord.py",value=f"`{discord.__version__}`",                         inline=True)
        embed.add_field(name="📋 Version",   value=f"`v{BOT_VERSION}`",                                inline=True)
        if self.bot.user.avatar: embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System")
        await ctx.reply(embed=embed)

    # ── .help ──
    @commands.command(name="help", aliases=["h"])
    async def help_cmd(self, ctx, *, topic: str = None):
        TOPICS = {
            "ticket": {
                "emoji": "🎫", "title": "Ticket",
                "fields": [
                    ("📋 Lệnh cơ bản",
                     "`.panel` — Đăng panel mua/bán\n"
                     "`.close` — Đóng ticket hiện tại\n"
                     "`.done <tiền>` — Hoàn thành đơn (chỉ admin)\n"
                     "`.addnote <ghi chú>` — Thêm ghi chú vào ticket", False),
                    ("📊 Thống kê",
                     "`.ticketinfo [@user]` — Xem lịch sử ticket của user\n"
                     "`.thongke [MM/YYYY]` — Thống kê doanh thu theo tháng", False),
                    ("🔷 Slash commands",
                     "`/close` `/done` `/addnote`", False),
                ]
            },
            "point": {
                "emoji": "💎", "title": "Point",
                "fields": [
                    ("👤 User",
                     "`.redeem <mã>` — Nhập mã đổi point\n"
                     "`.point [@user]` — Xem point của bản thân / người khác\n"
                     "`.shop` — Xem danh sách quà đổi\n"
                     "`.exchange <id>` — Đổi quà bằng point", False),
                    ("🛡️ Admin",
                     "`.addpoint @user <số>` — Cộng point cho user\n"
                     "`.setpoint <ID> <số>` — Set point chính xác theo ID\n"
                     "`.pointall` — Thống kê point toàn server (top 20)\n"
                     "`.gencode [@user]` — Tạo mã point\n"
                     "`.pointcfg` — Cấu hình hệ thống point\n"
                     "`.pointlog` — Xem log point\n"
                     "`.buixong` — Reset trạng thái\n"
                     "`.addreward` `.delreward` `.clearshop` — Quản lý quà", False),
                ]
            },
            "minigame": {
                "emoji": "🎲", "title": "Minigame",
                "fields": [
                    ("🦀 Bầu Cua (nhiều người)",
                     "`.bc open` — Mở phiên cược (4-6 người, 30s)\n"
                     "`.bc cancel` — Hủy phiên đang mở\n"
                     "`.setbaucua #kênh` — Cài kênh chơi Bầu Cua\n"
                     "Tỉ lệ: x1→+0.9pt | x2→+1.8pt | x3→+2.7pt | Thua→-1pt", False),
                    ("✂️ Búa Kéo Bao",
                     "`.bkb <búa|kéo|bao> [point]` — Chơi vs Bot\n"
                     "Thắng nhận x0.9 point cược", False),
                    ("📊 Xếp hạng & Thống kê",
                     "`.rank [baucua|bkb]` — Bảng xếp hạng\n"
                     "`.mgstats [@user]` — Thống kê cá nhân", False),
                ]
            },
            "ai": {
                "emoji": "🤖", "title": "AI Chat",
                "fields": [
                    ("💬 Lệnh",
                     "`.ai <câu hỏi>` — Hỏi AI\n"
                     "`.ai tomtat` — Tóm tắt đoạn hội thoại\n"
                     "`.ai dich` — Dịch văn bản\n"
                     "`.ai phantich` — Phân tích nội dung\n"
                     "`.aireset` — Reset lịch sử chat với AI\n"
                     "`.mychat` — Xem lịch sử chat của bạn", False),
                    ("🔷 Slash commands",
                     "`/ai` `/aireset` `/mychat`", False),
                ]
            },
            "invite": {
                "emoji": "📨", "title": "Invite",
                "fields": [
                    ("📋 Lệnh",
                     "`.invite [@user]` — Xem thống kê invite của bản thân / người khác\n"
                     "`.invitetop [n]` — Top người invite nhiều nhất (mặc định top 10)\n"
                     "`.resetinvite [@user|all]` — Reset invite của 1 người hoặc tất cả (admin)", False),
                    ("🔷 Slash commands",
                     "`/invite` `/invitetop` `/resetinvite`", False),
                ]
            },
            "dichvu": {
                "emoji": "🏪", "title": "Dịch Vụ",
                "fields": [
                    ("📋 Lệnh",
                     "`.sv` — Xem bảng giá dịch vụ\n"
                     "`.giaset` — Admin chỉnh sửa bảng giá\n"
                     "`/sv` `/giaset`", False),
                ]
            },
            "giveaway": {
                "emoji": "🎉", "title": "Giveaway",
                "fields": [
                    ("📋 Slash commands",
                     "`/giveaway` — Tạo giveaway mới\n"
                     "`/gend <message_id>` — Kết thúc giveaway sớm\n"
                     "`/greroll <message_id>` — Quay số lại\n"
                     "`/gwlist <message_id>` — Xem danh sách người tham gia", False),
                ]
            },
            "mod": {
                "emoji": "🔨", "title": "Mod",
                "fields": [
                    ("⚖️ Xử lý thành viên",
                     "`.ban @user [lý do]` — Ban vĩnh viễn\n"
                     "`.unban <user_id>` — Unban\n"
                     "`.kick @user [lý do]` — Kick khỏi server\n"
                     "`.mute @user <thời gian> [lý do]` — Timeout (vd: 10m, 1h, 1d)\n"
                     "`.unmute @user` — Gỡ timeout", False),
                    ("⚠️ Cảnh cáo",
                     "`.warn @user [lý do]` — Cảnh cáo user\n"
                     "`.warns [@user]` — Xem danh sách cảnh cáo\n"
                     "`.clearwarn @user` — Xóa toàn bộ cảnh cáo", False),
                    ("🔧 Kênh",
                     "`.slowmode <giây>` — Cài chế độ chậm (0 = tắt)\n"
                     "`.lock [#kênh]` — Khóa kênh\n"
                     "`.unlock [#kênh]` — Mở khóa kênh", False),
                    ("🛡️ AutoMod",
                     "`.automod on/off` — Bật/tắt automod\n"
                     "`.automod links/invites/spam` — Bật/tắt lọc link, invite, spam\n"
                     "`.automod addword/delword/words` — Quản lý từ cấm\n"
                     "`.automod addrole/delrole` — Role bypass automod\n"
                     "`.automod adduser/deluser` — User bypass automod\n"
                     "`.automod whitelist` — Xem danh sách bypass", False),
                    ("🔷 Slash commands",
                     "`/ban` `/unban` `/kick` `/mute` `/unmute` `/warn`", False),
                ]
            },
            "admin": {
                "emoji": "⚙️", "title": "Admin",
                "fields": [
                    ("🛠️ Quản lý server",
                     "`.st` — Cài đặt bot\n"
                     "`.setup` — Setup server (kênh / category / role / server)\n"
                     "`.botinfo` — Thông tin bot\n"
                     "`.ping` — Kiểm tra độ trễ\n"
                     "`.clear <n>` — Xóa n tin nhắn\n"
                     "`.addrole @user @role` — Thêm role\n"
                     "`.removerole @user @role` — Xóa role\n"
                     "`.userinfo [@user]` — Thông tin thành viên\n"
                     "`.serverinfo` — Thông tin server\n"
                     "`.backfill [số]` — Quét lại kênh legit, thả ✅ cho tin bị bỏ sót (mặc định 25)", False),
                    ("🎨 Emoji & Kênh",
                     "`.emoji <url/file> <tên>` — Thêm emoji\n"
                     "`.delemoji <tên>` — Xóa emoji\n"
                     "`.rename #kênh <tên mới>` — Đổi tên kênh\n"
                     "`.setperm #kênh @role <quyền>` — Cài quyền kênh\n"
                     "`.mkchannel <text|voice|category> <tên>` — Tạo kênh\n"
                     "`.sellerchannel <text|voice|category> <tên>` — Tạo kênh (seller)", False),
                    ("💳 QR",
                     "`.qr [@user]` — Xem mã QR thanh toán\n"
                     "`/qr` — Slash tương đương", False),
                    ("🔷 Slash commands",
                     "`/clear` `/addrole` `/removerole` `/ping`\n"
                     "`/userinfo` `/serverinfo` `/botinfo`", False),
                ]
            },
        }

        # Normalize topic aliases
        ALIASES = {
            "ticket": "ticket", "vé": "ticket",
            "point": "point", "điểm": "point", "pts": "point",
            "minigame": "minigame", "game": "minigame", "mini": "minigame", "mg": "minigame",
            "ai": "ai",
            "invite": "invite", "inv": "invite",
            "dichvu": "dichvu", "dịch vụ": "dichvu", "dv": "dichvu", "sv": "dichvu",
            "giveaway": "giveaway", "gw": "giveaway",
            "mod": "mod",
            "admin": "admin", "adm": "admin",
        }

        if topic:
            key = ALIASES.get(topic.lower().strip())
            if not key:
                topics_list = " | ".join(f"`{k}`" for k in ["ticket", "point", "minigame", "ai", "invite", "dichvu", "giveaway", "mod", "admin"])
                return await ctx.reply(f"❌ Không tìm thấy mục `{topic}`.\nCác mục hợp lệ: {topics_list}")
            t = TOPICS[key]
            embed = discord.Embed(
                title=f"{t['emoji']}  Help — {t['title']}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc)
            )
            for name, value, inline in t["fields"]:
                embed.add_field(name=name, value=value, inline=inline)
            embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  .help để về trang chính")
            return await ctx.reply(embed=embed)

        # Embed tổng quan
        embed = discord.Embed(
            title="📖  Danh Sách Lệnh — TuyTam Bot",
            description="Dùng `.help <mục>` để xem chi tiết từng phần.\nVí dụ: `.help mod` | `.help ticket` | `.help admin`",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🎫 Ticket",    value="`.panel` `.close` `.done` `.addnote`\n`.ticketinfo` `.thongke`", inline=True)
        embed.add_field(name="💎 Point",     value="`.redeem` `.point` `.shop` `.exchange`\n`.addpoint` `.setpoint` `.pointall`", inline=True)
        embed.add_field(name="🎲 Minigame",  value="`.bc open` `.bc cancel` `.setbaucua`\n`.bkb` `.rank` `.mgstats`", inline=True)
        embed.add_field(name="🤖 AI",        value="`.ai` `.aireset` `.mychat`\n`/ai` `/aireset`", inline=True)
        embed.add_field(name="📨 Invite",    value="`.invite` `.invitetop` `.resetinvite`\n`/invite` `/invitetop`", inline=True)
        embed.add_field(name="🏪 Dịch vụ",  value="`.sv` `.giaset`\n`/sv` `/giaset`", inline=True)
        embed.add_field(name="🎉 Giveaway",  value="`/giveaway` `/gend`\n`/greroll` `/gwlist`", inline=True)
        embed.add_field(name="🔨 Mod",       value="`.ban` `.kick` `.mute` `.warn`\n`.slowmode` `.lock` `.automod`", inline=True)
        embed.add_field(name="⚙️ Admin",     value="`.st` `.setup` `.clear` `.addrole` `.emoji`\n`.rename` `.mkchannel` `.qr`", inline=True)
        embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  .help <mục> để xem chi tiết")
        await ctx.reply(embed=embed)

    # ── .backfill ──
    @commands.command(name="backfill")
    async def backfill_cmd(self, ctx, limit: int = 25):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền dùng lệnh này.")
        from core.data import get_cfg_legit_channel
        import re as _re
        IGNORED = {628400349979344919}

        legit_ch_id = get_cfg_legit_channel()
        if not legit_ch_id:
            return await ctx.reply("❌ Chưa cài Legit Channel. Vào `.st` để cài trước.")

        channel = await get_or_fetch_channel(self.bot, legit_ch_id)
        if not channel:
            return await ctx.reply(f"❌ Không tìm thấy kênh legit (ID: `{legit_ch_id}`).")

        limit = max(1, min(limit, 100))
        msg_status = await ctx.reply(f"🔍 Đang quét **{limit}** tin nhắn gần nhất trong {channel.mention}...")

        # Thu thập các tin nhắn bị bỏ sót (chưa có ✅), sắp xếp từ cũ → mới
        missed = []
        scanned = 0
        try:
            msgs = []
            async for msg in channel.history(limit=limit):
                msgs.append(msg)
            msgs.reverse()  # cũ → mới để xử lý đúng thứ tự

            for msg in msgs:
                if msg.author.bot: continue
                if msg.author.id in IGNORED: continue
                if not _re.match(r"^\+1\s*legit\b", msg.content.strip(), _re.IGNORECASE): continue
                scanned += 1
                already = any(r.emoji == "✅" and r.me for r in msg.reactions)
                if not already:
                    missed.append(msg)
        except Exception as e:
            return await msg_status.edit(content=f"❌ Lỗi khi quét: `{e}`")

        # Xử lý từng tin bị bỏ sót: thả reaction + đổi tên kênh +1
        fixed = 0
        name_before = channel.name
        for msg in missed:
            try:
                await msg.add_reaction("✅")
            except Exception:
                pass
            # Đổi tên kênh +1
            try:
                name = channel.name
                match = _re.search(r"-(\d+)$", name)
                new_num = (int(match.group(1)) + 1) if match else 1
                base = name[:match.start()] if match else name
                new_name = f"{base}-{new_num}"
                await channel.edit(name=new_name, reason=f"Backfill +1 legit bởi {ctx.author}")
                fixed += 1
            except Exception:
                pass

        name_after = channel.name
        embed = discord.Embed(
            title="✅ Backfill Legit Hoàn Tất",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🔍 Quét", value=f"**{limit}** tin nhắn", inline=True)
        embed.add_field(name="📝 Khớp +1legit", value=f"**{scanned}** tin", inline=True)
        embed.add_field(name="✅ Đã xử lý", value=f"**{fixed}** tin bị bỏ sót", inline=True)
        embed.add_field(name="📌 Kênh", value=f"`{name_before}` → `{name_after}`", inline=False)
        await msg_status.edit(content=None, embed=embed)

    # ── PREFIX commands cho các slash ──
    @commands.command(name="ping")
    async def ping_cmd(self, ctx):
        lat    = round(self.bot.latency * 1000)
        color  = 0x57F287 if lat < 100 else (0xFEE75C if lat < 200 else 0xED4245)
        status = "Tốt 🟢" if lat < 100 else ("Bình thường 🟡" if lat < 200 else "Chậm 🔴")
        embed  = discord.Embed(title="🏓 Pong!", description=f"Độ trễ: **{lat}ms** — {status}", color=color)
        await ctx.reply(embed=embed)

    @commands.command(name="userinfo", aliases=["ui", "whois"])
    async def userinfo_cmd(self, ctx, member: discord.Member = None):
        m     = member or ctx.author
        roles = [r.mention for r in m.roles if r.name != "@everyone"]
        embed = discord.Embed(title=f"👤  {m}", color=m.color if m.color.value else 0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",         value=f"`{m.id}`",                                                         inline=True)
        embed.add_field(name="🤖 Bot",        value="✅" if m.bot else "❌",                                               inline=True)
        embed.add_field(name="📅 Tạo acc",    value=f"<t:{int(m.created_at.timestamp())}:D>",                             inline=True)
        embed.add_field(name="📥 Vào server", value=f"<t:{int(m.joined_at.timestamp())}:D>" if m.joined_at else "N/A",   inline=True)
        embed.add_field(name="🏷️ Roles",      value=" ".join(roles[-10:]) if roles else "Không có",                      inline=False)
        embed.set_thumbnail(url=m.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name="serverinfo", aliases=["si", "server"])
    async def serverinfo_cmd(self, ctx):
        g    = ctx.guild
        bots = sum(1 for m in g.members if m.bot)
        embed = discord.Embed(title=f"🏠  {g.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",         value=f"`{g.id}`",                                              inline=True)
        embed.add_field(name="👑 Owner",      value=g.owner.mention if g.owner else "N/A",                    inline=True)
        embed.add_field(name="📅 Tạo lúc",   value=f"<t:{int(g.created_at.timestamp())}:D>",                 inline=True)
        embed.add_field(name="👥 Thành viên", value=f"👤 {g.member_count - bots}  🤖 {bots}",                 inline=True)
        embed.add_field(name="💬 Kênh",      value=f"📝 {len(g.text_channels)}  🔊 {len(g.voice_channels)}", inline=True)
        if g.icon: embed.set_thumbnail(url=g.icon.url)
        await ctx.reply(embed=embed)

    @commands.command(name="giaset2", aliases=["priceset2"])
    async def giaset2_prefix(self, ctx):
        """Alias prefix cho /giaset — giống .giaset"""
        await self.giaset_cmd(ctx)

    # ── Slash mod commands ──
    @app_commands.command(name="clear", description="Xoá tin nhắn trong kênh")
    @app_commands.describe(amount="Số tin nhắn cần xoá (1-500)")
    async def slash_clear(self, interaction: discord.Interaction, amount: int):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if amount < 1 or amount > 500: return await interaction.response.send_message("❌ Số lượng phải từ 1 đến 500.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Đã xoá **{len(deleted)}** tin nhắn.", ephemeral=True)

    @app_commands.command(name="addrole", description="Thêm role cho thành viên")
    @app_commands.describe(member="Thành viên", role="Role cần thêm")
    async def slash_addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if role >= interaction.guild.me.top_role: return await interaction.response.send_message("❌ Role này cao hơn role của bot.", ephemeral=True)
        await member.add_roles(role, reason=f"Bởi {interaction.user}")
        embed = discord.Embed(title="✅ Đã Thêm Role", color=0x57F287)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="removerole", description="Xoá role của thành viên")
    @app_commands.describe(member="Thành viên", role="Role cần xoá")
    async def slash_removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        await member.remove_roles(role, reason=f"Bởi {interaction.user}")
        embed = discord.Embed(title="✅ Đã Xoá Role", color=0xFEE75C)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ping", description="Kiểm tra độ trễ bot")
    async def slash_ping(self, interaction: discord.Interaction):
        lat   = round(self.bot.latency * 1000)
        color = 0x57F287 if lat < 100 else (0xFEE75C if lat < 200 else 0xED4245)
        status = "Tốt 🟢" if lat < 100 else ("Bình thường 🟡" if lat < 200 else "Chậm 🔴")
        embed = discord.Embed(title="🏓 Pong!", description=f"Độ trễ: **{lat}ms** — {status}", color=color)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Xem thông tin thành viên")
    @app_commands.describe(member="Thành viên (để trống = bản thân)")
    async def slash_userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        m     = member or interaction.user
        roles = [r.mention for r in m.roles if r.name != "@everyone"]
        embed = discord.Embed(title=f"👤  {m}", color=m.color if m.color.value else 0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",        value=f"`{m.id}`",                                                inline=True)
        embed.add_field(name="🤖 Bot",       value="✅" if m.bot else "❌",                                    inline=True)
        embed.add_field(name="📅 Tạo acc",   value=f"<t:{int(m.created_at.timestamp())}:D>",                  inline=True)
        embed.add_field(name="📥 Vào server",value=f"<t:{int(m.joined_at.timestamp())}:D>" if m.joined_at else "N/A", inline=True)
        embed.add_field(name="🏷️ Roles",     value=" ".join(roles[-10:]) if roles else "Không có",            inline=False)
        embed.set_thumbnail(url=m.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Xem thông tin server")
    async def slash_serverinfo(self, interaction: discord.Interaction):
        g     = interaction.guild
        bots  = sum(1 for m in g.members if m.bot)
        embed = discord.Embed(title=f"🏠  {g.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",        value=f"`{g.id}`",                                              inline=True)
        embed.add_field(name="👑 Owner",     value=g.owner.mention if g.owner else "N/A",                    inline=True)
        embed.add_field(name="📅 Tạo lúc",  value=f"<t:{int(g.created_at.timestamp())}:D>",                 inline=True)
        embed.add_field(name="👥 Thành viên",value=f"👤 {g.member_count - bots}  🤖 {bots}",                 inline=True)
        embed.add_field(name="💬 Kênh",     value=f"📝 {len(g.text_channels)}  🔊 {len(g.voice_channels)}", inline=True)
        if g.icon: embed.set_thumbnail(url=g.icon.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Xem thông tin bot")
    async def slash_botinfo(self, interaction: discord.Interaction):
        import platform
        embed = discord.Embed(title=f"🤖  {self.bot.user.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏓 Latency",  value=f"**{round(self.bot.latency*1000)}ms**", inline=True)
        embed.add_field(name="🌐 Servers",  value=f"**{len(self.bot.guilds)}**",            inline=True)
        embed.add_field(name="📋 Version",  value=f"`v{BOT_VERSION}`",                     inline=True)
        if self.bot.user.avatar: embed.set_thumbnail(url=self.bot.user.avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="qr", description="Gửi mã QR thanh toán")
    async def slash_qr(self, interaction: discord.Interaction):
        import os
        qr_path = get_qr_path()
        if not qr_path or not os.path.exists(qr_path): return await interaction.response.send_message("❌ Chưa có QR! Admin cài qua `.settings`.", ephemeral=True)
        file  = discord.File(qr_path, filename="qr.png")
        embed = discord.Embed(title="📱  Mã QR Thanh Toán", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.description = "> 🏦 **MB Bank** — `0702557706` — HOVANBUT\n> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n> ⚠️ Ghi rõ: `[tên MC] mua [item]`"
        embed.set_image(url="attachment://qr.png")
        await interaction.response.send_message(embed=embed, file=file)

    # ── Error handler ──
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound): pass
        elif isinstance(error, commands.MissingPermissions): await ctx.reply("❌ Bạn không có quyền thực hiện lệnh này.")


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
