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
    QR_FILE, get_qr_path, save_qr_path,
)

BOT_VERSION = "3.5.0"
BOT_UPDATED = "2026-05-16"

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
        embed.add_field(name="🎫 Ticket Category",    value=f"`{data.get('cfg_ticket_category','default')}`",         inline=True)
        embed.add_field(name="🛡️ Support Role",      value=ro("cfg_support_role",    1474572393908404305), inline=True)
        embed.add_field(name="🏪 Seller Role",       value=ro("cfg_seller_role",     0),                   inline=True)
        embed.add_field(name="💰 Balance Channel",   value=ch("cfg_balance_channel", 1464999465294369035), inline=True)
        embed.add_field(name="✅ Legit Channel",     value=ch("cfg_legit_channel",   0),                   inline=True)
        embed.add_field(name="📸 Proof Channel",    value=ch("cfg_proof_channel",   1469647159560241318), inline=True)
        embed.add_field(name="🤖 AI Channel",        value=ch("cfg_ai_channel",      0),                   inline=True)
        embed.add_field(name="🔤 Font server",       value=FONT_LABELS.get(data.get("cfg_font","normal"),"normal"), inline=True)
        embed.add_field(name="🖼️ QR Path",           value=f"`{data.get('qr_path','Chưa cài')}`",                   inline=False)
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

    @commands.command(name="qr")
    async def qr_cmd(self, ctx):
        import os
        qr_path = get_qr_path()
        if not qr_path or not os.path.exists(qr_path):
            return await ctx.reply(embed=discord.Embed(title="❌  Chưa Có Mã QR", description="Admin chưa cài mã QR.\nDùng `.settings` để thêm QR thanh toán.", color=0xED4245))
        embed = discord.Embed(title="📱  Mã QR Thanh Toán", description="> 🏦 **MB Bank** — HOVANBUT\n> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n> ⚠️ Ghi rõ nội dung: `[tên MC] mua [item]`", color=0x57F287, timestamp=datetime.now(timezone.utc))
        file = discord.File(qr_path, filename="qr.png"); embed.set_image(url="attachment://qr.png")
        await ctx.reply(embed=embed, file=file)

    # ── .help ──
    @commands.command(name="help", aliases=["h"])
    async def help_cmd(self, ctx, *, topic: str = None):
        embed = discord.Embed(title="📖 Danh Sách Lệnh — TuyTam Bot", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🎫 Ticket",    value="`.panel` `.close` `.done <tiền>` `.addnote`\n`.ticketinfo [@user]` `.thongke [MM/YYYY]`\n`/close` `/done` `/addnote`", inline=False)
        embed.add_field(name="💎 Point",     value="`.redeem <mã>` `.point [@user]` `.addpoint @user <số>`\n`.gencode [@user]` `.pointcfg` `.pointlog` `.buixong`\n`.shop` `.exchange <id>` `.addreward` `.delreward` `.clearshop`", inline=False)
        embed.add_field(name="🎲 Minigame",  value="`.bc open` — Bầu Cua nhiều người (4-6 người, 30s)\n`.bc cancel` — Hủy phiên\n`.setbaucua #kênh` — Cài kênh chơi\n`.bkb <búa|kéo|bao> [point]` — Búa Kéo Bao vs Bot\n`.rank [baucua|bkb]` — BXH | `.mgstats [@user]` — Thống kê", inline=False)
        embed.add_field(name="🤖 AI",        value="`.ai <câu hỏi>` `.ai tomtat` `.ai dich` `.ai phantich`\n`.aireset` `.mychat`\n`/ai` `/aireset` `/mychat`", inline=False)
        embed.add_field(name="📨 Invite",    value="`.invite [@user]` `.invitetop [n]` `.resetinvite [@user|all]`\n`/invite` `/invitetop` `/resetinvite`", inline=False)
        embed.add_field(name="🏪 Dịch vụ",  value="`.sv` — Xem bảng giá\n`.giaset` — Admin sửa bảng giá\n`/sv` `/giaset`", inline=False)
        embed.add_field(name="🎉 Giveaway",  value="`/giveaway` `/gend` `/greroll` `/gwlist`", inline=False)
        embed.add_field(name="🔨 Mod",       value="`.ban` `.unban` `.kick` `.mute` `.unmute`\n`.slowmode` `.lock` `.unlock`\n`.warn` `.warns` `.clearwarn`\n`.automod on/off/links/invites/spam`\n`.automod addword/delword/words`\n`.automod addrole/delrole/adduser/deluser/whitelist`\n`/ban` `/unban` `/kick` `/mute` `/unmute` `/warn`", inline=False)
        embed.add_field(name="⚙️ Admin",     value="`.st` `.botinfo` `.qr` `.ping`\n`.clear <n>` `.addrole` `.removerole`\n`.userinfo` `.serverinfo` `.emoji` `.delemoji`\n`.rename` `.setperm` `.mkchannel`\n`/clear` `/addrole` `/removerole` `/ping` `/userinfo` `/serverinfo`", inline=False)
        embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  Dùng . hoặc / trước mỗi lệnh")
        await ctx.reply(embed=embed)

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
