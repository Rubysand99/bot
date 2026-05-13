# cogs/setup.py — .setup .setperm .rename .mkchannel
from config import *
import re as _re_setup
import unicodedata as _unicodedata

class SetupMainView(View):
    """Menu chính của .setup."""
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=300)
        self.guild = guild

    @discord.ui.button(label="📋 Xem danh sách kênh", style=discord.ButtonStyle.secondary, row=0)
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await _show_channel_list(interaction, self.guild)

    @discord.ui.button(label="✏️ Đổi tên kênh (hàng loạt)", style=discord.ButtonStyle.primary, row=0)
    async def btn_rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(SetupFontSampleModal(self.guild, mode="rename"))

    @discord.ui.button(label="➕ Tạo kênh mới", style=discord.ButtonStyle.success, row=0)
    async def btn_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(CreateChannelModal(self.guild))

    @discord.ui.button(label="🔒 Sửa quyền kênh", style=discord.ButtonStyle.danger, row=1)
    async def btn_perms(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_message(
            "🔒 **Sửa quyền kênh**\nDùng lệnh: `.setperm #kênh @role xem=true gửi=false`\n"
            "Hoặc chọn kênh cụ thể từ danh sách bên dưới.",
            ephemeral=True,
            view=PermSelectView(self.guild)
        )

    @discord.ui.button(label="🔤 Chọn font chữ", style=discord.ButtonStyle.secondary, row=1)
    async def btn_font(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_message(
            "🔤 **Chọn font chữ mẫu**\nBot sẽ áp dụng font này khi tạo/đổi tên kênh.",
            ephemeral=True,
            view=FontSelectView(self.guild)
        )

    @discord.ui.button(label="🏆 Cài Role Mua Hàng", style=discord.ButtonStyle.blurple, row=2)
    async def btn_buy_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await _show_buy_role_panel(interaction)

async def _show_buy_role_panel(interaction: discord.Interaction):
    buy_roles = get_buy_roles()
    embed = discord.Embed(
        title="🏆  Cấu Hình Role Buyer Tự Động",
        description=(
            "Bot give role dựa trên **tổng tiền đã mua** của buyer.\n"
            "Mỗi role tương ứng 1 khoảng tiền. VD: buyer 50-100k, buyer 100-200k...\n\n"
            "**Cách hoạt động:**\n"
            "› Staff gõ `.done 50k` trong ticket sau khi giao dịch thành công\n"
            "› Bot cộng tiền vào tổng của buyer → give đúng role khoảng tương ứng\n"
            "› Khi tổng vượt khoảng hiện tại → tự động upgrade lên role cao hơn"
        ),
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    if buy_roles:
        lines = []
        for i, r in enumerate(buy_roles):
            role_obj = interaction.guild.get_role(r.get("role_id", 0))
            role_str = role_obj.mention if role_obj else f"❌ ID:{r.get('role_id')}"
            min_a    = fmt_amount(r.get("min_amount", 0))
            max_a    = fmt_amount(r.get("max_amount")) if r.get("max_amount") else "∞"
            lines.append(f"`{i+1}.` {role_str} — **{r.get('label','?')}** — {min_a} → {max_a}")
        embed.add_field(name=f"📋 Danh sách role ({len(buy_roles)})", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="📋 Danh sách role", value="*Chưa có role nào được cấu hình.*", inline=False)

    embed.set_footer(text="TuyTam Store  •  Setup → Role Buyer")
    await interaction.response.send_message(embed=embed, view=BuyRoleManageView(), ephemeral=True)

class BuyRoleManageView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="➕ Thêm Role", style=discord.ButtonStyle.success, row=0)
    async def btn_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(AddBuyRoleModal())

    @discord.ui.button(label="🗑️ Xoá Role", style=discord.ButtonStyle.danger, row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        if not get_buy_roles():
            return await interaction.response.send_message("❌ Chưa có role nào.", ephemeral=True)
        await interaction.response.send_modal(RemoveBuyRoleModal())

    @discord.ui.button(label="🔄 Xoá tất cả", style=discord.ButtonStyle.danger, row=0)
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        save_buy_roles([])
        await interaction.response.send_message("✅ Đã xoá toàn bộ cấu hình role buyer.", ephemeral=True)

    @discord.ui.button(label="📊 Xem tổng tiền user", style=discord.ButtonStyle.secondary, row=1)
    async def btn_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(CheckUserSpentModal())

    @discord.ui.button(label="✏️ Sửa tổng tiền user", style=discord.ButtonStyle.secondary, row=1)
    async def btn_set_orders(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(SetUserSpentModal())

    @discord.ui.button(label="🔄 Sync role cũ", style=discord.ButtonStyle.blurple, row=2)
    async def btn_sync(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(SyncExistingRolesModal())

class AddBuyRoleModal(Modal, title="➕ Thêm Role Buyer"):
    role_id_input = TextInput(
        label="ID của Role",
        placeholder="Chuột phải vào role → Copy ID",
        min_length=15, max_length=20
    )
    min_amount_input = TextInput(
        label="Mốc tiền TỐI THIỂU để nhận role",
        placeholder="VD: 50k, 100k, 1tr5 (tổng tiền đã mua)",
        min_length=1, max_length=15
    )
    max_amount_input = TextInput(
        label="Mốc tiền TỐI ĐA (bỏ trống = không giới hạn)",
        placeholder="VD: 100k, 200k — để trống nếu là role cao nhất",
        required=False,
        max_length=15
    )
    label_input = TextInput(
        label="Tên hiển thị của role",
        placeholder="VD: buyer 50-100k, buyer 100-200k",
        min_length=1, max_length=40
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID role không hợp lệ!", ephemeral=True)

        min_a = parse_amount(self.min_amount_input.value)
        if min_a is None:
            return await interaction.response.send_message(
                f"❌ Mốc tiền tối thiểu `{self.min_amount_input.value}` không hợp lệ!\nVD: `50k`, `1tr`, `200000`",
                ephemeral=True
            )

        max_raw = self.max_amount_input.value.strip()
        max_a   = None
        if max_raw:
            max_a = parse_amount(max_raw)
            if max_a is None:
                return await interaction.response.send_message(
                    f"❌ Mốc tiền tối đa `{max_raw}` không hợp lệ!", ephemeral=True
                )
            if max_a <= min_a:
                return await interaction.response.send_message(
                    "❌ Mốc tối đa phải lớn hơn mốc tối thiểu!", ephemeral=True
                )

        label    = self.label_input.value.strip()
        role_obj = interaction.guild.get_role(role_id)
        if not role_obj:
            return await interaction.response.send_message(
                f"❌ Không tìm thấy role ID `{role_id}` trong server.", ephemeral=True
            )

        buy_roles = get_buy_roles()
        for r in buy_roles:
            if r["role_id"] == role_id:
                return await interaction.response.send_message(
                    f"❌ Role {role_obj.mention} đã được cấu hình rồi.", ephemeral=True
                )

        buy_roles.append({"role_id": role_id, "min_amount": min_a, "max_amount": max_a, "label": label})
        buy_roles = sorted(buy_roles, key=lambda r: r["min_amount"])
        save_buy_roles(buy_roles)

        embed = discord.Embed(title="✅ Đã Thêm Role Buyer", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏷️ Role",      value=role_obj.mention,                           inline=True)
        embed.add_field(name="📛 Tên",        value=f"`{label}`",                               inline=True)
        embed.add_field(name="💰 Khoảng tiền",
                        value=f"**{fmt_amount(min_a)}** → **{fmt_amount(max_a) if max_a else '∞'}**",
                        inline=True)
        all_lines = []
        for r in buy_roles:
            ro   = interaction.guild.get_role(r["role_id"])
            mn   = fmt_amount(r["min_amount"])
            mx   = fmt_amount(r["max_amount"]) if r.get("max_amount") else "∞"
            all_lines.append(f"› {ro.mention if ro else r['role_id']} — **{r['label']}** ({mn}→{mx})")
        embed.add_field(name="📋 Danh sách hiện tại", value="\n".join(all_lines) or "—", inline=False)
        embed.set_footer(text=f"Thêm bởi {interaction.user}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class RemoveBuyRoleModal(Modal, title="🗑️ Xoá Role Buyer"):
    role_id_input = TextInput(
        label="ID của Role muốn xoá",
        placeholder="Chuột phải vào role → Copy ID",
        min_length=15, max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

        buy_roles = get_buy_roles()
        new_roles = [r for r in buy_roles if r["role_id"] != role_id]
        if len(new_roles) == len(buy_roles):
            return await interaction.response.send_message(
                f"❌ Không tìm thấy role ID `{role_id}` trong danh sách.", ephemeral=True
            )

        save_buy_roles(new_roles)
        role_obj = interaction.guild.get_role(role_id)
        await interaction.response.send_message(
            f"✅ Đã xoá role **{role_obj.name if role_obj else role_id}** khỏi danh sách buyer.",
            ephemeral=True
        )

class CheckUserSpentModal(Modal, title="📊 Xem Tổng Tiền Của User"):
    user_id_input = TextInput(
        label="ID của User",
        placeholder="Chuột phải vào user → Copy ID",
        min_length=15, max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

        member    = interaction.guild.get_member(uid)
        total     = get_user_total_spent(uid)
        buy_roles = get_buy_roles()

        embed = discord.Embed(title="📊 Thống Kê Buyer", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 User",        value=member.mention if member else f"ID: {uid}", inline=True)
        embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(total)}**",                inline=True)

        cur_cfg = None
        for r in reversed(buy_roles):
            min_a = r.get("min_amount", 0)
            max_a = r.get("max_amount")
            if total >= min_a and (max_a is None or total < max_a):
                cur_cfg = r
                break
        if cur_cfg:
            ro = interaction.guild.get_role(cur_cfg["role_id"])
            embed.add_field(name="🏆 Role hiện tại", value=ro.mention if ro else cur_cfg["label"], inline=True)
        else:
            embed.add_field(name="🏆 Role hiện tại", value="Chưa đủ điều kiện", inline=True)

        next_roles = [r for r in buy_roles if total < r.get("min_amount", 0)]
        if next_roles:
            nxt  = next_roles[0]
            need = nxt["min_amount"] - total
            ro2  = interaction.guild.get_role(nxt["role_id"])
            embed.add_field(
                name="⬆️ Role tiếp theo",
                value=f"{ro2.mention if ro2 else nxt['label']} — cần thêm **{fmt_amount(need)}**",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

class SetUserSpentModal(Modal, title="✏️ Sửa Tổng Tiền Của User"):
    user_id_input = TextInput(
        label="ID của User",
        placeholder="Chuột phải vào user → Copy ID",
        min_length=15, max_length=20
    )
    amount_input = TextInput(
        label="Tổng tiền mới",
        placeholder="VD: 50k, 1tr5, 200000",
        min_length=1, max_length=15
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)

        new_total = parse_amount(self.amount_input.value)
        if new_total is None or new_total < 0:
            return await interaction.response.send_message(
                f"❌ Số tiền `{self.amount_input.value}` không hợp lệ!", ephemeral=True
            )

        data = load_data()
        if "user_total_spent" not in data:
            data["user_total_spent"] = {}
        old_total = data["user_total_spent"].get(str(uid), 0)
        data["user_total_spent"][str(uid)] = new_total
        save_data(data)

        member = interaction.guild.get_member(uid)
        if member:
            await auto_give_buy_roles(interaction.guild, member, new_total)

        embed = discord.Embed(title="✅ Đã Sửa Tổng Tiền", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 User",         value=member.mention if member else f"ID:{uid}",   inline=True)
        embed.add_field(name="💰 Tổng tiền cũ", value=f"**{fmt_amount(old_total)}**",              inline=True)
        embed.add_field(name="💰 Tổng tiền mới", value=f"**{fmt_amount(new_total)}**",             inline=True)
        embed.set_footer(text=f"Sửa bởi {interaction.user}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SyncExistingRolesModal(Modal, title="🔄 Sync Role Cũ → Tổng Tiền"):
    default_amount_input = TextInput(
        label="Tổng tiền mặc định theo từng bậc role",
        placeholder="VD: 50k,100k,200k — từ thấp→cao (bỏ trống = dùng min_amount)",
        required=False,
        max_length=100
    )
    overwrite_input = TextInput(
        label="Ghi đè người đã có data? (yes/no)",
        placeholder="no = chỉ set cho người chưa có dữ liệu (mặc định)",
        default="no",
        max_length=5,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        buy_roles = get_buy_roles()
        if not buy_roles:
            return await interaction.followup.send("❌ Chưa cấu hình role nào.", ephemeral=True)

        overwrite = self.overwrite_input.value.strip().lower() in ("yes", "y", "có", "co")

        raw = self.default_amount_input.value.strip()
        if raw:
            parts = [x.strip() for x in raw.split(",")]
            default_amounts = []
            for p in parts:
                a = parse_amount(p)
                if a is None:
                    return await interaction.followup.send(f"❌ Số tiền `{p}` không hợp lệ!", ephemeral=True)
                default_amounts.append(a)
        else:
            default_amounts = [r["min_amount"] for r in buy_roles]

        while len(default_amounts) < len(buy_roles):
            default_amounts.append(default_amounts[-1] if default_amounts else 0)

        guild = interaction.guild
        data  = load_data()
        if "user_total_spent" not in data:
            data["user_total_spent"] = {}

        synced = 0; skipped = 0; lines = []

        for member in guild.members:
            if member.bot:
                continue
            uid_str = str(member.id)
            already = uid_str in data["user_total_spent"]

            highest_idx = -1
            for i, r_cfg in enumerate(buy_roles):
                role = guild.get_role(r_cfg["role_id"])
                if role and role in member.roles:
                    highest_idx = i

            if highest_idx == -1:
                continue
            if already and not overwrite:
                skipped += 1
                continue

            target = default_amounts[highest_idx]
            old    = data["user_total_spent"].get(uid_str, 0)
            data["user_total_spent"][uid_str] = target
            synced += 1
            label  = buy_roles[highest_idx].get("label", "?")
            lines.append(f"› {_uname(member)} — **{label}** → **{fmt_amount(target)}** (cũ: {fmt_amount(old)})")

        save_data(data)

        embed = discord.Embed(title="🔄 Sync Hoàn Tất", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="✅ Đã sync", value=f"**{synced}** thành viên",     inline=True)
        embed.add_field(name="⏭️ Bỏ qua", value=f"**{skipped}** (đã có data)", inline=True)
        embed.add_field(name="🔁 Ghi đè", value="Có" if overwrite else "Không", inline=True)
        if lines:
            preview = "\n".join(lines[:20])
            if len(lines) > 20:
                preview += f"\n... (+{len(lines)-20} người nữa)"
            embed.add_field(name="📋 Chi tiết", value=preview[:1024], inline=False)
        embed.set_footer(text=f"Sync bởi {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def _show_channel_list(interaction: discord.Interaction, guild: discord.Guild):
    lines = []
    no_cat = [ch for ch in guild.channels if ch.category is None and isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]
    if no_cat:
        lines.append("**— Không có category —**")
        for ch in sorted(no_cat, key=lambda c: c.position):
            icon = "💬" if isinstance(ch, discord.TextChannel) else "🔊"
            lines.append(f"  {icon} `#{ch.name}` (ID: {ch.id})")

    for cat in sorted(guild.categories, key=lambda c: c.position):
        lines.append(f"\n**📁 {cat.name}**")
        for ch in sorted(cat.channels, key=lambda c: c.position):
            icon = "💬" if isinstance(ch, discord.TextChannel) else ("🔊" if isinstance(ch, discord.VoiceChannel) else "📢")
            lines.append(f"  {icon} `{ch.name}` (ID: {ch.id})")

    text = "\n".join(lines) if lines else "Server không có kênh nào."
    chunks = []
    cur = ""
    for line in lines:
        if len(cur) + len(line) + 1 > 1800:
            chunks.append(cur)
            cur = line
        else:
            cur += "\n" + line
    if cur:
        chunks.append(cur)

    await interaction.response.send_message(
        f"📋 **Danh sách kênh — {guild.name}** ({len(guild.channels)} kênh)\n{chunks[0] if chunks else '(trống)'}",
        ephemeral=True
    )
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)

# ── Modal: Tạo kênh mới ──
class CreateChannelModal(Modal, title="➕ Tạo Kênh Mới"):
    ch_name = TextInput(label="Tên kênh", placeholder="vd: 💰•money hoặc ✅•legit-0", max_length=100)
    ch_type = TextInput(label="Loại (text/voice/category)", placeholder="text", default="text", max_length=10)
    font    = TextInput(label="Font (normal/bold/sans_bold/serif/script/double)", placeholder="normal", default="normal", max_length=20, required=False)

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        raw_name = self.ch_name.value.strip()
        ch_type  = self.ch_type.value.strip().lower()
        font     = self.font.value.strip().lower() or "normal"

        parts = _detect_channel_parts(raw_name)
        final_name = _rebuild_name(parts, parts["base_text"], font)
        # Discord yêu cầu tên kênh không có ký tự đặc biệt trong phần slug (chỉ với text channel)

        try:
            if ch_type in ("voice", "vc"):
                ch = await self.guild.create_voice_channel(final_name, reason=f"Setup bởi {interaction.user}")
                icon = "🔊"
            elif ch_type in ("category", "cat"):
                ch = await self.guild.create_category(final_name, reason=f"Setup bởi {interaction.user}")
                icon = "📁"
            else:
                ch = await self.guild.create_text_channel(final_name, reason=f"Setup bởi {interaction.user}")
                icon = "💬"

            embed = discord.Embed(title="✅ Tạo Kênh Thành Công", color=0x57F287,
                                  timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Tên", value=f"`{final_name}`", inline=True)
            embed.add_field(name="Loại", value=f"{icon} {ch_type}", inline=True)
            embed.add_field(name="Font", value=FONT_LABELS.get(font, font), inline=True)
            if isinstance(ch, discord.TextChannel):
                embed.add_field(name="Kênh", value=ch.mention, inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot thiếu quyền tạo kênh!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Lỗi: {e}", ephemeral=True)

# ── Modal: Nhập font mẫu để đổi tên hàng loạt ──
class SetupFontSampleModal(Modal, title="✏️ Đổi Tên Kênh Hàng Loạt"):
    sample = TextInput(
        label="Font mẫu (paste ký tự hoặc gõ tên font)",
        placeholder="Paste: 𝐐𝐮𝐢𝐞𝐭 𝐒𝐜𝐡𝐞𝐦𝐚𝐭𝐢𝐜𝐬  hoặc gõ: bold",
        max_length=50,
        required=False
    )
    font_name = TextInput(
        label="Font: bold/sans_bold/serif/script/double",
        placeholder="bold | sans_bold | serif | script | double | normal",
        default="bold",
        max_length=20,
        required=False
    )
    scope = TextInput(
        label="Áp dụng cho? (all/text/voice/category)",
        placeholder="all",
        default="all",
        max_length=20,
        required=False
    )

    def __init__(self, guild: discord.Guild, mode: str = "rename"):
        super().__init__()
        self.guild = guild
        self.mode  = mode

    async def on_submit(self, interaction: discord.Interaction):
        font     = self.font_name.value.strip().lower() or "sans_bold"
        scope    = self.scope.value.strip().lower() or "all"

        sample_text = self.sample.value.strip()
        if sample_text:
            font = _detect_font_from_sample(sample_text) or font

        await interaction.response.send_message(
            f"⏳ Đang xem trước... Font: **{FONT_LABELS.get(font, font)}** | Scope: **{scope}**",
            ephemeral=True,
            view=RenamePreviewView(self.guild, font, scope)
        )

def _detect_font_from_sample(sample: str) -> str:
    """Nhận diện font từ ký tự Unicode mẫu người dùng paste vào, hoặc từ alias tên."""
    if not sample:
        return "normal"

    # Kiểm tra alias trước (user gõ tên như "bold", "quiet", "sb", "serif"...)
    low = sample.strip().lower()
    if low in FONT_ALIASES:
        return FONT_ALIASES[low]
    if low in FONT_LABELS:
        return low

    c = sample[0]
    cp = ord(c)
    if 0x1D400 <= cp <= 0x1D433:
        return "bold"
    if 0x1D7CE <= cp <= 0x1D7D7:
        return "bold"
    if 0x1D468 <= cp <= 0x1D49B:
        return "bold_italic"
    if 0x1D5D4 <= cp <= 0x1D607:
        return "sans_bold"
    if 0x1D7EC <= cp <= 0x1D7F5:
        return "sans_bold"
    if 0x1D4D0 <= cp <= 0x1D503 or c in "ℬℰℱℋℐℒℳℛℯℊℴ":
        return "script"
    if 0x1D538 <= cp <= 0x1D56B or c in "ℂℍℕℙℚℝℤ":
        return "double"
    return "normal"

# ── View: Preview đổi tên hàng loạt ──
class RenamePreviewView(View):
    def __init__(self, guild: discord.Guild, font: str, scope: str):
        super().__init__(timeout=180)
        self.guild = guild
        self.font  = font
        self.scope = scope

    def _get_channels(self):
        import re as _re_tc
        scope = self.scope
        channels = []
        for ch in self.guild.channels:
            if scope == "text"     and not isinstance(ch, discord.TextChannel):     continue
            if scope == "voice"    and not isinstance(ch, discord.VoiceChannel):    continue
            if scope == "category" and not isinstance(ch, discord.CategoryChannel): continue
            # Bỏ qua kênh có tên bắt đầu bằng ticket- (ticket-001, ticket-002, ...)
            if _re_tc.match(r'^ticket-', ch.name, _re_tc.IGNORECASE):
                continue
            channels.append(ch)
        return sorted(channels, key=lambda c: c.position)

    def _build_preview(self):
        channels = self._get_channels()
        lines = []
        for ch in channels[:30]:   # preview tối đa 30
            parts  = _detect_channel_parts(ch.name)
            new_name = _rebuild_name(parts, parts["base_text"], self.font)
            if new_name != ch.name:
                lines.append(f"`{ch.name}` → `{new_name}`")
        return lines, len(channels)

    @discord.ui.button(label="👁️ Xem trước 30 kênh đầu", style=discord.ButtonStyle.secondary)
    async def btn_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        import re as _re_tc3
        ticket_skipped = sum(
            1 for ch in self.guild.channels
            if _re_tc3.match(r'^ticket-', ch.name, _re_tc3.IGNORECASE)
        )
        lines, total = self._build_preview()
        if not lines:
            return await interaction.response.send_message(
                f"✅ Không có kênh nào cần đổi tên với font này.\n"
                f"⏭️ Đã bỏ qua **{ticket_skipped}** kênh ticket-.",
                ephemeral=True
            )
        text = "\n".join(lines[:25])
        await interaction.response.send_message(
            f"👁️ **Preview** ({total} kênh — font: {FONT_LABELS.get(self.font, self.font)})\n"
            f"⏭️ Bỏ qua **{ticket_skipped}** kênh ticket-\n```\n{text}\n```",
            ephemeral=True
        )

    @discord.ui.button(label="✅ Xác nhận đổi tên", style=discord.ButtonStyle.success)
    async def btn_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        import re as _re_tc2
        ticket_skipped = [
            ch for ch in self.guild.channels
            if _re_tc2.match(r'^ticket-', ch.name, _re_tc2.IGNORECASE)
        ]
        channels = self._get_channels()
        await interaction.response.send_message(
            f"⏳ Đang đổi tên **{len(channels)}** kênh... "
            f"(bỏ qua **{len(ticket_skipped)}** kênh ticket-)",
            ephemeral=True
        )
        done, errors = 0, []
        skipped_already = []   # đã đúng font
        skipped_empty   = []   # base_text rỗng (divider, ký tự đặc biệt)

        for ch in channels:
            parts    = _detect_channel_parts(ch.name)
            new_name = _rebuild_name(parts, parts["base_text"], self.font)

            if new_name == ch.name:
                if not parts["base_text"].strip():
                    skipped_empty.append(f"`{ch.name}`")
                else:
                    skipped_already.append(f"`{ch.name}`")
                continue

            try:
                await ch.edit(name=new_name, reason=f"Setup font bởi {interaction.user}")
                done += 1
                await asyncio.sleep(0.7)
            except discord.Forbidden:
                errors.append(f"`{ch.name}` — thiếu quyền")
            except Exception as e:
                errors.append(f"`{ch.name}` — {e}")

        result = f"✅ Đổi tên thành công: **{done}** kênh"

        if done > 0:
            set_cfg_font(self.font)
            result += f"\n💾 Đã lưu font server: **{FONT_LABELS.get(self.font, self.font)}**"

        if skipped_already:
            result += f"\n\n⏭️ **Đã đúng font ({len(skipped_already)})** — bỏ qua:\n"
            result += " ".join(skipped_already[:20])
            if len(skipped_already) > 20:
                result += f" ... (+{len(skipped_already)-20})"

        if skipped_empty:
            result += f"\n\n🚫 **Không xử lý được ({len(skipped_empty)})** — divider/ký tự đặc biệt:\n"
            result += " ".join(skipped_empty[:20])

        if errors:
            result += f"\n\n❌ Lỗi ({len(errors)}):\n" + "\n".join(errors[:10])

        await interaction.followup.send(result, ephemeral=True)

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.danger)
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🚫 Đã huỷ thao tác.", ephemeral=True)
        self.stop()

# ── View: Chọn font ──
class FontSelectView(View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        self.guild = guild
        options = [
            discord.SelectOption(label=label, value=key, description=f"Font: {key}")
            for key, label in FONT_LABELS.items()
        ]
        self.add_item(FontSelectMenu(guild, options))

class FontSelectMenu(Select):
    def __init__(self, guild: discord.Guild, options):
        super().__init__(placeholder="Chọn font chữ...", options=options, min_values=1, max_values=1)
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        font = self.values[0]
        _setup_sessions[self.guild.id] = _setup_sessions.get(self.guild.id, {})
        _setup_sessions[self.guild.id]["font"] = font
        sample = _apply_font("Legit Money Store", font)
        await interaction.response.send_message(
            f"✅ Đã chọn font: **{FONT_LABELS.get(font, font)}**\nMẫu: `{sample}`\n\n"
            f"Dùng nút **✏️ Đổi tên kênh** để áp dụng.",
            ephemeral=True
        )

# ── View: Chọn kênh để sửa quyền ──
class PermSelectView(View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        options = [
            discord.SelectOption(label=f"#{ch.name}"[:100], value=str(ch.id))
            for ch in sorted(guild.text_channels, key=lambda c: c.position)[:25]
        ]
        if options:
            self.add_item(PermChannelSelect(guild, options))

    @discord.ui.button(label="🔒 Khoá @everyone đọc kênh này", style=discord.ButtonStyle.danger, row=1)
    async def btn_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        ch = interaction.channel
        try:
            await ch.set_permissions(interaction.guild.default_role,
                                     read_messages=False,
                                     reason=f"Lock bởi {interaction.user}")
            await interaction.response.send_message(f"🔒 Đã khoá `#{ch.name}` với @everyone.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)

    @discord.ui.button(label="🔓 Mở khoá @everyone", style=discord.ButtonStyle.success, row=1)
    async def btn_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        ch = interaction.channel
        try:
            await ch.set_permissions(interaction.guild.default_role,
                                     read_messages=True,
                                     reason=f"Unlock bởi {interaction.user}")
            await interaction.response.send_message(f"🔓 Đã mở khoá `#{ch.name}` với @everyone.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)

class PermChannelSelect(Select):
    def __init__(self, guild: discord.Guild, options):
        super().__init__(placeholder="Chọn kênh để xem/sửa quyền...", options=options)
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        ch_id = int(self.values[0])
        ch = self.guild.get_channel(ch_id)
        if not ch:
            return await interaction.response.send_message("❌ Không tìm thấy kênh.", ephemeral=True)

        overwrites = ch.overwrites
        lines = []
        for target, ow in overwrites.items():
            name = target.name if hasattr(target, "name") else str(target)
            pairs = []
            if ow.read_messages is not None:
                pairs.append(f"xem={'✅' if ow.read_messages else '❌'}")
            if ow.send_messages is not None:
                pairs.append(f"gửi={'✅' if ow.send_messages else '❌'}")
            if ow.manage_messages is not None:
                pairs.append(f"quản lý={'✅' if ow.manage_messages else '❌'}")
            lines.append(f"**{name}**: {', '.join(pairs) or 'mặc định'}")

        perm_text = "\n".join(lines) if lines else "Không có quyền tuỳ chỉnh"
        await interaction.response.send_message(
            f"🔒 **Quyền kênh `#{ch.name}`**\n{perm_text}\n\n"
            f"Dùng `.setperm #{ch.name} @role xem=true gửi=false` để sửa.",
            ephemeral=True
        )

@bot.command(name="setup")
async def setup_cmd(ctx):
    if not can_use_dangerous_cmd(ctx.author.id, "setup"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    guild = ctx.guild
    if not guild:
        return await ctx.reply("❌ Lệnh này chỉ dùng trong server.")

    text_ch  = len(guild.text_channels)
    voice_ch = len(guild.voice_channels)
    cats     = len(guild.categories)
    members  = guild.member_count

    embed = discord.Embed(
        title=f"⚙️  Setup Server — {guild.name}",
        description=(
            f"👥 **{members}** thành viên  |  "
            f"💬 **{text_ch}** text  |  "
            f"🔊 **{voice_ch}** voice  |  "
            f"📁 **{cats}** category\n\n"
            "Chọn thao tác bên dưới:"
        ),
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(
        name="📝 Các chức năng",
        value=(
            "› **📋 Xem danh sách kênh** — liệt kê toàn bộ kênh theo category\n"
            "› **✏️ Đổi tên hàng loạt** — áp dụng font chữ mới cho tên kênh\n"
            "› **➕ Tạo kênh mới** — tạo kênh text/voice/category với font\n"
            "› **🔒 Sửa quyền kênh** — xem & chỉnh quyền @everyone / role\n"
            "› **🔤 Chọn font chữ** — xem trước các kiểu font Unicode\n"
            "› **🏆 Cài Role Mua Hàng** — cấu hình role tự động theo số đơn (buy+, buy++, ...)"
        ),
        inline=False
    )
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Hết hạn sau 5 phút")
    await ctx.reply(embed=embed, view=SetupMainView(guild))

@bot.command(name="setperm")
async def setperm_cmd(ctx, channel: discord.TextChannel = None, role: discord.Role = None, *, flags: str = ""):
    """
    Sửa quyền kênh nhanh.
    Cú pháp: .setperm #kênh @role xem=true gửi=false
    """
    if not can_use_dangerous_cmd(ctx.author.id, "setperm"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    if not channel or not role:
        return await ctx.reply("❌ Dùng: `.setperm #kênh @role xem=true gửi=false`")

    overwrite = channel.overwrites_for(role)
    flag_map = {
        "xem": "read_messages", "gửi": "send_messages",
        "đọc": "read_messages", "view": "read_messages",
        "send": "send_messages", "manage": "manage_messages",
        "ql": "manage_messages", "reaction": "add_reactions",
        "embed": "embed_links", "file": "attach_files",
    }
    changes = []
    for part in flags.split():
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.lower().strip()
        v = v.lower().strip()
        attr = flag_map.get(k)
        if not attr:
            continue
        val = True if v in ("true", "1", "yes", "✅", "on") else (False if v in ("false", "0", "no", "❌", "off") else None)
        if val is None:
            setattr(overwrite, attr, None)
        else:
            setattr(overwrite, attr, val)
        changes.append(f"{k}={'✅' if val else ('❌' if val is False else '↩️ default')}")

    if not changes:
        return await ctx.reply("❌ Không có flag hợp lệ.\nVí dụ: `xem=true gửi=false`")

    try:
        await channel.set_permissions(role, overwrite=overwrite, reason=f"setperm bởi {ctx.author}")
        await ctx.reply(f"✅ Đã sửa quyền `#{channel.name}` cho {role.mention}:\n" + "\n".join(f"  › {c}" for c in changes))
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền Manage Channels.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: {e}")

@bot.command(name="rename")
async def rename_cmd(ctx, channel: discord.abc.GuildChannel = None, *, new_name: str = None):
    """
    Đổi tên 1 kênh cụ thể, giữ icon & số đếm.
    Cú pháp: .rename #kênh tên-mới
    """
    if not can_use_dangerous_cmd(ctx.author.id, "rename"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    if not channel or not new_name:
        return await ctx.reply("❌ Dùng: `.rename #kênh tên-mới`")

    old_name = channel.name
    parts    = _detect_channel_parts(old_name)

    font = _setup_sessions.get(ctx.guild.id, {}).get("font", "normal")
    final_name = _rebuild_name(parts, new_name, font)

    try:
        await channel.edit(name=final_name, reason=f"Rename bởi {ctx.author}")
        await ctx.reply(f"✅ `{old_name}` → `{final_name}`")
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền.")
    except Exception as e:
        await ctx.reply(f"❌ {e}")

# ================= EMOJI COMMAND =================

