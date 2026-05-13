# cogs/settings.py — .settings, DangerousCommandsView, ChangeChannelModal
from config import *

class ChangeChannelModal(Modal):
    def __init__(self, field_key: str, field_label: str):
        super().__init__(title=f"🔧 Đổi {field_label}")
        self.field_key = field_key
        self.field_label = field_label
        self.id_input = TextInput(
            label=f"ID {field_label}",
            placeholder="Dán ID vào đây (chuột phải → Copy ID)",
            min_length=15, max_length=20
        )
        self.add_item(self.id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_id = int(self.id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

        save_cfg(self.field_key, new_id)
        embed = discord.Embed(
            title="✅  Đã Cập Nhật",
            description=f"**{self.field_label}** → `{new_id}`",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Cập nhật bởi {interaction.user}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= SETTINGS VIEW =================
class SettingsView(View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="📂 Ticket Category", style=discord.ButtonStyle.grey, row=0)
    async def change_category(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_ticket_category", "Ticket Category"))

    @discord.ui.button(label="🛡️ Support Role", style=discord.ButtonStyle.grey, row=0)
    async def change_role(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_support_role", "Support Role ID"))

    @discord.ui.button(label="🏷️ Seller Role", style=discord.ButtonStyle.grey, row=0)
    async def change_seller_role(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_seller_role", "Seller Role ID"))

    @discord.ui.button(label="🔢 Counter Channel", style=discord.ButtonStyle.grey, row=1)
    async def change_counter(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_counter_channel", "Counter Channel"))

    @discord.ui.button(label="📱 Đổi QR", style=discord.ButtonStyle.blurple, row=1)
    async def change_qr(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(SetQRModal())

    @discord.ui.button(label="👁️ Xem QR", style=discord.ButtonStyle.grey, row=1)
    async def view_qr(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        qr_path = get_qr_path()
        if not qr_path or not os.path.exists(qr_path):
            return await interaction.response.send_message("❌ Chưa có QR nào được lưu.", ephemeral=True)
        file = discord.File(qr_path, filename="qr.png")
        embed = discord.Embed(title="📱 QR Hiện Tại", color=0x5865F2)
        embed.set_image(url="attachment://qr.png")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @discord.ui.button(label="💰 Balance Channel", style=discord.ButtonStyle.green, row=2)
    async def change_balance(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_balance_channel", "Balance Channel"))

    @discord.ui.button(label="✅ Legit Channel", style=discord.ButtonStyle.green, row=2)
    async def change_legit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_legit_channel", "Legit Channel"))

    @discord.ui.button(label="📌 Panel Channel", style=discord.ButtonStyle.green, row=2)
    async def change_panel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("panel_channel_id", "Panel Channel"))

    @discord.ui.button(label="🔖 Proof Channel", style=discord.ButtonStyle.blurple, row=3)
    async def change_proof(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_proof_channel", "Proof Channel"))

    @discord.ui.button(label="🏆 Role Mua Hàng", style=discord.ButtonStyle.blurple, row=4)
    async def change_buy_roles(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await _show_buy_role_panel(interaction)

    @discord.ui.button(label="🔒 Lệnh Nguy Hiểm", style=discord.ButtonStyle.danger, row=4)
    async def dangerous_cmds(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message(
                "❌ Chỉ admin mới chỉnh được phân quyền lệnh nguy hiểm.", ephemeral=True
            )
        embed = _build_dangerous_embed()
        await interaction.response.send_message(embed=embed, view=DangerousCommandsView(), ephemeral=True)

    @discord.ui.button(label="🤖 AI Channel", style=discord.ButtonStyle.blurple, row=4)
    async def change_ai_channel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(ChangeChannelModal("cfg_ai_channel", "AI Chat Channel"))

# ================= DANGEROUS COMMANDS SETTINGS =================
# Danh sách lệnh nguy hiểm — tất cả ADMIN_IDS đều dùng được
# Lưu vào section CFG với key "dangerous_cmd_overrides"
# Format: {"cmd_name": "admin"}

DANGEROUS_CMDS = {
    "createchannel": "🏗️ Tạo kênh",
    "deletechannel": "🗑️ Xoá kênh",
    "balreset":      "💸 Reset số dư",
    "balset":        "💰 Đặt số dư",
    "setup":         "⚙️ Setup server",
    "setperm":       "🔐 Sửa quyền kênh",
    "rename":        "✏️ Đổi tên kênh",
    "emoji":         "😀 Thêm emoji",
}

def get_dangerous_overrides() -> dict:
    cfg = _get_section("CFG")
    return cfg.get("dangerous_cmd_overrides", {})

def save_dangerous_overrides(overrides: dict):
    cfg = _get_section("CFG").copy()
    cfg["dangerous_cmd_overrides"] = overrides
    _set_section("CFG", cfg)

def can_use_dangerous_cmd(user_id: int, cmd_name: str) -> bool:
    return user_id in ADMIN_IDS

class DangerousCommandsView(View):
    """Panel chọn quyền từng lệnh nguy hiểm — admin mở được."""
    def __init__(self):
        super().__init__(timeout=180)
        self._build_buttons()

    def _build_buttons(self):
        overrides = get_dangerous_overrides()
        for i, (cmd, label) in enumerate(DANGEROUS_CMDS.items()):
            level = overrides.get(cmd, "admin")
            is_admin_only = (level == "admin")
            btn = discord.ui.Button(
                label=f"{label}: 🟢 Admin",
                style=discord.ButtonStyle.success,
                custom_id=f"dcmd_{cmd}",
                row=i // 3
            )
            btn.callback = self._make_callback(cmd)
            self.add_item(btn)

        close_btn = discord.ui.Button(
            label="❌ Đóng",
            style=discord.ButtonStyle.grey,
            custom_id="dcmd_close",
            row=len(DANGEROUS_CMDS) // 3 + 1
        )
        close_btn.callback = self._close_callback
        self.add_item(close_btn)

    def _make_callback(self, cmd: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id not in ADMIN_IDS:
                return await interaction.response.send_message("❌ Chỉ admin mới chỉnh được.", ephemeral=True)
            overrides = get_dangerous_overrides()
            overrides[cmd] = "admin"
            save_dangerous_overrides(overrides)
            new_view = DangerousCommandsView()
            embed = _build_dangerous_embed()
            await interaction.response.edit_message(embed=embed, view=new_view)
        return callback

    async def _close_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.delete_original_response()

def _build_dangerous_embed() -> discord.Embed:
    overrides = get_dangerous_overrides()
    embed = discord.Embed(
        title="🔒  Phân Quyền Lệnh Nguy Hiểm",
        description=(
            "Tất cả lệnh nguy hiểm đều cho phép **Admin** (`ADMIN_IDS`) sử dụng.\n"
            "🟢 **Cả Admin** — tất cả admin trong `ADMIN_IDS` dùng được"
        ),
        color=0xED4245,
        timestamp=datetime.now(timezone.utc)
    )
    for cmd, label in DANGEROUS_CMDS.items():
        level = overrides.get(cmd, "admin")
        val = "🟢 Admin"
        embed.add_field(name=label, value=val, inline=True)
    embed.set_footer(text="TuyTam Store  •  Admin có toàn quyền")
    return embed

@bot.command(name="settings", aliases=["st"])
async def settings(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return

    panel_channel_id = get_panel_channel_id()
    if panel_channel_id:
        ch = ctx.guild.get_channel(panel_channel_id)
        panel_value = ch.mention if ch else f"⚠️ Kênh đã bị xoá (ID: `{panel_channel_id}`)"
    else:
        panel_value = "Chưa cài — dùng `.setpanel #kênh`"

    cat_id      = get_cfg_category()
    role_id     = get_cfg_support_role()
    seller_id   = get_cfg_seller_role()
    counter_id  = get_cfg_counter_channel()
    balance_id  = get_cfg_balance_channel()
    legit_id    = get_cfg_legit_channel()
    proof_id    = get_cfg_proof_channel()
    ai_ch_id    = get_cfg_ai_channel()
    qr_path     = get_qr_path()
    buy_roles   = get_buy_roles()

    cat_val     = f"<#{cat_id}>" if cat_id else "❌ Chưa cài"
    role_val    = f"<@&{role_id}>" if role_id else "❌ Chưa cài"
    seller_val  = f"<@&{seller_id}>" if seller_id else "❌ Chưa cài — nhấn **🏷️ Seller Role**"
    counter_val = f"<#{counter_id}>" if counter_id else "❌ Chưa cài"
    balance_val = f"<#{balance_id}>" if balance_id else "❌ Chưa cài — nhấn **💰 Balance Channel**"
    legit_val   = f"<#{legit_id}>" if legit_id else "❌ Chưa cài — nhấn **✅ Legit Channel**"
    proof_val   = f"<#{proof_id}>" if proof_id else "❌ Chưa cài — nhấn **🔖 Proof Channel**"
    ai_ch_val   = f"<#{ai_ch_id}>" if ai_ch_id else "❌ Chưa cài — nhấn **🤖 AI Channel**"
    qr_val      = "✅ Đã có" if qr_path and os.path.exists(qr_path) else "❌ Chưa có"
    if buy_roles:
        buy_role_val = "\n".join(
            f"› **{r.get('label','?')}** — {fmt_amount(r.get('min_amount',0))} → {fmt_amount(r['max_amount']) if r.get('max_amount') else '∞'}"
            for r in buy_roles
        )
    else:
        buy_role_val = "❌ Chưa cài — nhấn **🏆 Role Mua Hàng**"

    embed = discord.Embed(
        title="⚙️  Cấu Hình Hiện Tại",
        description="Nhấn các nút bên dưới để chỉnh sửa từng mục.",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📌  Panel Channel",   value=panel_value,  inline=False)
    embed.add_field(name="📂  Ticket Category",  value=cat_val,      inline=True)
    embed.add_field(name="🛡️  Support Role",     value=role_val,     inline=True)
    embed.add_field(name="🏷️  Seller Role",      value=seller_val,   inline=True)
    embed.add_field(name="🔢  Counter Channel",  value=counter_val,  inline=True)
    embed.add_field(name="💰  Balance Channel",  value=balance_val,  inline=True)
    embed.add_field(name="✅  Legit Channel",    value=legit_val,    inline=True)
    embed.add_field(name="🔖  Proof Channel",    value=proof_val,    inline=True)
    embed.add_field(name="🤖  AI Chat Channel",  value=ai_ch_val,    inline=True)
    embed.add_field(name="📱  Mã QR",            value=qr_val,       inline=True)
    embed.add_field(name="🏆  Role Mua Hàng",    value=buy_role_val, inline=False)
    embed.set_footer(text="TuyTam Store  •  Dùng .st hoặc .settings")
    await ctx.reply(embed=embed, view=SettingsView())

@bot.command()
async def close(ctx):
    if not is_staff(ctx.author):
        return await ctx.reply("❌ Bạn không có quyền.")
    if not (ctx.channel.topic and "|" in ctx.channel.topic):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    await _close_ticket(ctx.channel, bot, closer=ctx.author)

