# cogs/ticket_cmds.py — .done .addnote .ratings .orderbase .qr + SetQRModal
from config import *

@bot.command(name="done")
async def done_cmd(ctx, amount_str: str = None):
    """
    Đánh dấu hoàn thành đơn: .done 50k / .done 1tr5 / .done 200000
    Cộng số tiền vào tổng của buyer → give role phù hợp.
    """
    if not is_staff(ctx.author):
        return await ctx.reply("❌ Bạn không có quyền.")
    if not (ctx.channel.topic and "|" in ctx.channel.topic):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    if not amount_str:
        return await ctx.reply("❌ Thiếu số tiền! Ví dụ: `.done 50k`, `.done 1tr5`, `.done 200000`")

    amount = parse_amount(amount_str)
    if amount is None or amount <= 0:
        return await ctx.reply(
            f"❌ Số tiền `{amount_str}` không hợp lệ!\n"
            f"Ví dụ đúng: `50k` `1tr` `1tr5` `200000`"
        )

    parts = ctx.channel.topic.split("|")
    try:
        user_id = int(parts[0]) if parts[0].isdigit() else None
    except Exception:
        user_id = None

    if not user_id:
        return await ctx.reply("❌ Không đọc được thông tin buyer từ ticket.")

    trade_type = parts[2] if len(parts) > 2 else None
    if trade_type not in ("sell", "buy"):
        return await ctx.reply("ℹ️ Ticket dịch vụ / hỗ trợ không tính vào đơn mua hàng.")

    buyer = ctx.guild.get_member(user_id)
    if not buyer:
        return await ctx.reply(f"❌ Không tìm thấy buyer (ID: `{user_id}`) — họ có thể đã rời server.")

    data = load_data()
    completed_key = f"completed_{ctx.channel.id}"
    if data.get(completed_key):
        total = get_user_total_spent(user_id)
        return await ctx.reply(
            f"⚠️ Đơn này đã được đánh dấu hoàn thành rồi!\n"
            f"Buyer: {buyer.mention} — tổng đã mua: **{fmt_amount(total)}**"
        )

    data[completed_key] = True
    save_data(data)

    new_total = add_user_spent(user_id, amount)
    role_cfg  = await auto_give_buy_roles(ctx.guild, buyer, new_total)

    buy_roles = get_buy_roles()
    embed = discord.Embed(
        title="✅ Hoàn Thành Đơn",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="👤 Buyer",       value=buyer.mention,           inline=True)
    embed.add_field(name="💵 Đơn này",     value=f"**{fmt_amount(amount)}**", inline=True)
    embed.add_field(name="💰 Tổng đã mua", value=f"**{fmt_amount(new_total)}**", inline=True)

    if role_cfg:
        role_obj = ctx.guild.get_role(role_cfg.get("role_id", 0))
        embed.add_field(
            name="🏆 Role hiện tại",
            value=role_obj.mention if role_obj else f"**{role_cfg.get('label','?')}**",
            inline=False
        )
    elif buy_roles:
        next_r = buy_roles[0]
        need   = next_r.get("min_amount", 0) - new_total
        embed.add_field(
            name="⏳ Role tiếp theo",
            value=f"**{next_r.get('label','?')}** — cần thêm **{fmt_amount(need)}**",
            inline=False
        )
    else:
        embed.add_field(
            name="⚙️ Chưa cấu hình role",
            value="Dùng `.setup` → 🏆 Cài Role Mua Hàng",
            inline=False
        )

    embed.set_footer(text=f"Xác nhận bởi {_uname_plain(ctx.author)}")
    await ctx.reply(embed=embed)

@bot.command(name="addnote")
async def addnote_cmd(ctx, *, note: str = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Bạn không có quyền.")
    if not (ctx.channel.topic and "|" in ctx.channel.topic):
        return await ctx.reply("❌ Đây không phải kênh ticket.")
    if not note:
        return await ctx.reply("❌ Thiếu nội dung! Ví dụ: `.addnote khách đã chuyển tiền`")

    add_ticket_note(ctx.channel.id, str(ctx.author), note)
    embed = discord.Embed(
        title="📝 Ghi Chú Nội Bộ",
        description=note,
        color=0xFEE75C,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Bởi {ctx.author} • Chỉ staff thấy")
    await ctx.reply(embed=embed)
    try:
        await ctx.message.delete()
    except:
        pass

@bot.command(name="ratings")
async def ratings_cmd(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    data = load_data()
    ratings = data.get("ratings", [])
    if not ratings:
        return await ctx.reply("Chưa có đánh giá nào.")

    total = len(ratings)
    avg = sum(r["stars"] for r in ratings) / total
    dist = {i: sum(1 for r in ratings if r["stars"] == i) for i in range(1, 6)}

    bar = ""
    for s in range(5, 0, -1):
        count = dist[s]
        filled = int((count / total) * 10) if total > 0 else 0
        bar += f"{'⭐'*s}: {'█'*filled}{'░'*(10-filled)} {count}\n"

    embed = discord.Embed(
        title="⭐ Thống Kê Đánh Giá",
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Tổng đánh giá", value=str(total), inline=True)
    embed.add_field(name="Trung bình", value=f"{avg:.1f} ⭐", inline=True)
    embed.add_field(name="Phân bố", value=f"```{bar}```", inline=False)
    await ctx.reply(embed=embed)

@bot.command(name="orderbase")
async def orderbase_cmd(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="# Nhận Làm Base Village Trong <:emoji_17:1483684359415267449>",
        description=(
            "**Giá Chỉ Từ 20-35m Tùy Theo Base Mà Ae Chọn**\n\n"
            "**Cam Kết:**\n"
            "<:emoji_17:1483684359415267449> •Tự Tìm Chỗ Xây Base Lun Nhé Ae\n"
            "<:emoji_17:1483684359415267449> •Base Có Chỗ Nhân Giống Village\n"
            "<:emoji_17:1483684359415267449> •Base Sẽ Có Ít Nhất 3 Con Dân Làng Bán Tu Sửa\n"
            "<:emoji_17:1483684359415267449> •Còn Lại Sẽ Là Ngẫu Nhiên Và Có Thể Có Thêm Dòng Xịn Như Protection, Blast Protection, Fortune,...\n"
            "<:emoji_17:1483684359415267449> •Bảo Hành 8h Kể Từ Khi Mua\n"
            "<:emoji_17:1483684359415267449> •Nếu Bị Raid Trong Giờ Bảo Hành Sẽ Đc Hoàn Tiền\n"
            "<:emoji_17:1483684359415267449> •Và Sẽ Đảm Bảo Đc Với Anh Em Là Quay Video Xoá Home Base\n"
            "<:emoji_17:1483684359415267449> •Base 20m Sẽ Có 3 Con Roll Sẵn Tu Sửa Còn Lại Ae Tự Roll Và 35m Thì Sẽ Roll Hết Tất Cả Nhé Và Sẽ Đẹp Và Rộng Hơn Nên Ae K Lỗ Đâu\n\n"
            "**Nên Ae Yên Tâm Mà Thuê** ✅\n\n"
            "**Ai Muốn Có 1 Base Village Tuyệt Vời Như Vậy Mà Còn Rẻ Thì Hãy Tạo <#1464415587378659564> Để Có 1 Base Xịn Nhé**"
        ),
        color=0xE67E22,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="💰 DoанBaoNgoc-Stock  •  TuyTam Store")

    await ctx.send("<@&1464411190808805540> sorry ping", embed=embed)

@bot.command(name="qr")
async def qr_cmd(ctx):
    qr_path = get_qr_path()
    if not qr_path or not os.path.exists(qr_path):
        embed = discord.Embed(
            title="❌  Chưa Có Mã QR",
            description="Admin chưa cài mã QR.\nDùng `.settings` để thêm QR thanh toán.",
            color=0xED4245
        )
        return await ctx.reply(embed=embed)

    embed = discord.Embed(
        title="📱  Mã QR Thanh Toán",
        description=(
            "Quét mã bên dưới để thanh toán.\n"
            "> 🏦 **MB Bank** — HOVANBUT\n"
            "> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n"
            "> ⚠️ Ghi rõ nội dung: `[tên MC] mua [item]`"
        ),
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="TuyTam Store  •  Quét QR để thanh toán")
    file = discord.File(qr_path, filename="qr.png")
    embed.set_image(url="attachment://qr.png")
    await ctx.reply(embed=embed, file=file)

class SetQRModal(Modal):
    def __init__(self):
        super().__init__(title="🖼️ Cập Nhật Ảnh QR")

    url_input = TextInput(
        label="URL ảnh QR (để trống nếu đính kèm file)",
        placeholder="https://i.imgur.com/abc123.png",
        required=False,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value.strip()
        if url:
            import urllib.request
            try:
                qr_path = QR_FILE
                urllib.request.urlretrieve(url, qr_path)
                save_qr_path(qr_path)
                embed = discord.Embed(
                    title="✅  Đã Cập Nhật QR",
                    description="Mã QR mới đã được lưu từ URL.",
                    color=0x57F287,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_image(url=url)
                embed.set_footer(text=f"Cập nhật bởi {interaction.user}")
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                return await interaction.response.send_message(
                    f"❌ Không tải được ảnh từ URL: `{e}`", ephemeral=True
                )

        await interaction.response.send_message(
            "📎 Hãy **đính kèm ảnh QR** vào tin nhắn tiếp theo trong vòng **60 giây**.",
            ephemeral=True
        )

        def check(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel.id
                and len(m.attachments) > 0
            )

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            attachment = msg.attachments[0]
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                return await interaction.followup.send("❌ File không phải ảnh!", ephemeral=True)

            qr_path = QR_FILE
            await attachment.save(qr_path)
            save_qr_path(qr_path)

            try:
                await msg.delete()
            except:
                pass

            embed = discord.Embed(
                title="✅  Đã Cập Nhật QR",
                description="Mã QR mới đã được lưu thành công!\nDùng `.qr` để kiểm tra.",
                color=0x57F287,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Cập nhật bởi {interaction.user}")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Hết thời gian! Không nhận được ảnh.", ephemeral=True)

# ================= SLASH COMMANDS =================

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.id in ADMIN_IDS or interaction.user.guild_permissions.administrator

def is_staff_or_admin(interaction: discord.Interaction) -> bool:
    role = interaction.guild.get_role(get_cfg_support_role())
    has_role = role in interaction.user.roles if role else False
    return interaction.user.id in ADMIN_IDS or has_role

# ── Giveaway Modal ──
# ── Button tham gia giveaway (slash /giveaway) ──
