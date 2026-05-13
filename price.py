# cogs/price.py — .sv .giaset
from config import *

class EditPriceModal(Modal):
    def __init__(self, section: dict, index: int):
        super().__init__(title=f"✏️ Sửa: {section['name'][:40]}")
        self.section = section
        self.index   = index

        self.name_input = TextInput(
            label="Tên mục (có thể chứa emoji)",
            default=section["name"],
            max_length=100,
        )
        self.add_item(self.name_input)

        self.content_input = TextInput(
            label="Nội dung (markdown, blockquote, emoji OK)",
            default=section["content"],
            style=discord.TextStyle.paragraph,
            max_length=1024,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        sections = get_price_sections()
        if self.index >= len(sections):
            return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)

        sections[self.index]["name"]    = self.name_input.value.strip()
        sections[self.index]["content"] = self.content_input.value.strip()
        save_price_sections(sections)

        await interaction.response.send_message(
            f"✅ Đã cập nhật mục **{sections[self.index]['name']}**!\n"
            f"Dùng `.sv` để xem bảng giá mới.",
            ephemeral=True
        )

# ── Select: Chọn mục muốn sửa ──
class EditPriceSectionSelect(Select):
    def __init__(self):
        sections = get_price_sections()
        options  = [
            discord.SelectOption(
                label=sec["name"][:100],
                value=str(i),
                description=f"Key: {sec['key']}"
            )
            for i, sec in enumerate(sections)
        ]
        super().__init__(placeholder="Chọn mục muốn sửa...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        idx      = int(self.values[0])
        sections = get_price_sections()
        if idx >= len(sections):
            return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)
        await interaction.response.send_modal(EditPriceModal(sections[idx], idx))

# ── View chính của .giaset ──
class PriceManagerView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(EditPriceSectionSelect())

    @discord.ui.button(label="➕ Thêm mục mới", style=discord.ButtonStyle.success, row=1)
    async def add_section(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_modal(AddPriceSectionModal())

    @discord.ui.button(label="🗑️ Xoá mục", style=discord.ButtonStyle.danger, row=1)
    async def del_section(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        await interaction.response.send_message(
            "Chọn mục muốn xoá:", view=DeletePriceSectionView(), ephemeral=True
        )

    @discord.ui.button(label="🔄 Reset về mặc định", style=discord.ButtonStyle.grey, row=1)
    async def reset_sections(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        save_price_sections(_DEFAULT_PRICE_SECTIONS)
        await interaction.response.send_message("✅ Đã reset bảng giá về mặc định!", ephemeral=True)

    @discord.ui.button(label="👁️ Xem trước .sv", style=discord.ButtonStyle.blurple, row=2)
    async def preview(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(embed=build_sv_embed(), ephemeral=True)

# ── Modal: Thêm mục giá mới ──
class AddPriceSectionModal(Modal, title="➕ Thêm Mục Giá Mới"):
    key_input = TextInput(
        label="Key (chữ thường, không dấu, không khoảng trắng)",
        placeholder="vd: spotify, tiktok, office",
        max_length=30,
    )
    name_input = TextInput(
        label="Tên mục (có thể chứa emoji)",
        placeholder="vd: 🎵  Spotify",
        max_length=100,
    )
    content_input = TextInput(
        label="Nội dung (markdown, blockquote, emoji OK)",
        placeholder="> - **Gói 1 tháng: 30.000 VNĐ**",
        style=discord.TextStyle.paragraph,
        max_length=1024,
    )

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip().lower().replace(" ", "_")
        sections = get_price_sections()
        for s in sections:
            if s["key"] == key:
                return await interaction.response.send_message(
                    f"❌ Key `{key}` đã tồn tại! Chọn key khác.", ephemeral=True
                )
        sections.append({
            "key":     key,
            "name":    self.name_input.value.strip(),
            "content": self.content_input.value.strip(),
        })
        save_price_sections(sections)
        await interaction.response.send_message(
            f"✅ Đã thêm mục **{self.name_input.value.strip()}** vào bảng giá!", ephemeral=True
        )

# ── View xoá mục ──
class DeletePriceSectionSelect(Select):
    def __init__(self):
        sections = get_price_sections()
        options  = [
            discord.SelectOption(label=sec["name"][:100], value=str(i), description=f"Key: {sec['key']}")
            for i, sec in enumerate(sections)
        ]
        super().__init__(placeholder="Chọn mục muốn xoá...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        idx      = int(self.values[0])
        sections = get_price_sections()
        if idx >= len(sections):
            return await interaction.response.send_message("❌ Mục không tồn tại.", ephemeral=True)
        removed = sections.pop(idx)
        save_price_sections(sections)
        await interaction.response.send_message(
            f"🗑️ Đã xoá mục **{removed['name']}** khỏi bảng giá.", ephemeral=True
        )

class DeletePriceSectionView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(DeletePriceSectionSelect())

# ── Lệnh .sv — hiển thị bảng giá ──
@bot.command(name="sv", aliases=["dichvu", "service"])
async def sv_command(ctx: commands.Context):
    await ctx.send(embed=build_sv_embed())

# ── Lệnh .giaset — admin quản lý bảng giá ──
@bot.command(name="giaset", aliases=["setgia", "pricemanager", "priceset"])
async def giaset_command(ctx: commands.Context):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")

    sections = get_price_sections()
    embed = discord.Embed(
        title="⚙️  Quản Lý Bảng Giá — .sv",
        description=(
            f"Hiện có **{len(sections)} mục** trong bảng giá.\n"
            "Chọn mục từ dropdown để **sửa**, hoặc dùng nút bên dưới để **thêm/xoá/reset**.\n\n"
            + "\n".join(f"`{i+1}.` {s['name']}" for i, s in enumerate(sections))
        ),
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="💡 Hướng dẫn nội dung",
        value=(
            "Hỗ trợ đầy đủ **Discord markdown**:\n"
            "› `**bold**`, `~~gạch~~`, `> blockquote`\n"
            "› Emoji server: `<:tên:id>`\n"
            "› Mention: `<@userID>`\n"
            "› `### Tiêu đề nhỏ`"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Timeout 2 phút")
    await ctx.reply(embed=embed, view=PriceManagerView())

# ── Resume giveaway sau khi bot restart ──
async def resume_active_giveaways():
    saved = load_giveaways_data()
    if not saved:
        return
    now = datetime.now(timezone.utc).timestamp()
    resumed = 0
    for mid, gw in saved.items():
        if gw.get("ended"):
            active_giveaways[mid] = gw   # giữ lại để greroll hoạt động
            continue
        active_giveaways[mid] = gw
        channel_id  = gw.get("channel_id")
        winners_cnt = gw.get("winners", 1)
        end_time    = gw.get("end_time", 0)
        remaining   = end_time - now
        gw_type     = gw.get("type", "reaction")

        if remaining <= 0:
            channel = bot.get_channel(channel_id)
            if channel:
                if gw_type == "button":
                    asyncio.create_task(giveaway_timer(channel_id, mid, winners_cnt, 0))
                else:
                    prize   = gw.get("prize", "phần thưởng")
                    host_id = gw.get("host_id", 0)
                    asyncio.create_task(end_giveaway(mid, channel, winners_cnt, prize, host_id))
        else:
            if gw_type == "button":
                asyncio.create_task(giveaway_timer(channel_id, mid, winners_cnt, int(remaining)))
            else:
                async def _reaction_resume(m=mid, ch=channel_id, w=winners_cnt,
                                            p=gw.get("prize",""), h=gw.get("host_id",0), r=remaining):
                    await asyncio.sleep(r)
                    if not active_giveaways.get(m, {}).get("ended"):
                        channel_obj = bot.get_channel(ch)
                        if channel_obj:
                            await end_giveaway(m, channel_obj, w, p, h)
                asyncio.create_task(_reaction_resume())
        resumed += 1
        print(f"[GIVEAWAY] ▶️  Resume mid={mid} type={gw_type} còn {max(0,int(remaining))}s")
    if resumed:
        print(f"[GIVEAWAY] ✅ Đã resume {resumed} giveaway")


