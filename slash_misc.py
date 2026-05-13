# cogs/slash_misc.py — slash misc commands
from config import *

@tree.command(name="giveaway", description="Tạo giveaway mới")
async def slash_giveaway(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Chỉ admin mới được tạo giveaway.", ephemeral=True)
    await interaction.response.send_modal(GiveawayModal())

@tree.command(name="gend", description="Kết thúc giveaway sớm")
@app_commands.describe(message_id="ID tin nhắn giveaway")
async def slash_gend(interaction: discord.Interaction, message_id: str):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
    try:
        mid = int(message_id)
    except:
        return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)
    gw = active_giveaways.get(mid)
    if not gw:
        return await interaction.response.send_message("❌ Không tìm thấy giveaway đang chạy.", ephemeral=True)
    await interaction.response.send_message("✅ Đang kết thúc giveaway...", ephemeral=True)
    channel = bot.get_channel(gw["channel_id"])
    if channel:
        await end_giveaway(mid, channel, gw["winners"], gw.get("prize", "phần thưởng"), gw.get("host", 0))

@tree.command(name="clear", description="Xoá tin nhắn trong kênh")
@app_commands.describe(amount="Số tin nhắn cần xoá (1-500)")
async def slash_clear(interaction: discord.Interaction, amount: int):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
    if amount < 1 or amount > 500:
        return await interaction.response.send_message("❌ Số lượng phải từ 1 đến 500.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🗑️ Đã xoá **{len(deleted)}** tin nhắn.", ephemeral=True)

@tree.command(name="addrole", description="Thêm role cho thành viên")
@app_commands.describe(member="Thành viên", role="Role cần thêm")
async def slash_addrole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
    if role >= interaction.guild.me.top_role:
        return await interaction.response.send_message("❌ Role này cao hơn role của bot.", ephemeral=True)
    await member.add_roles(role, reason=f"Bởi {interaction.user}")
    embed = discord.Embed(title="✅ Đã Thêm Role", color=0x57F287)
    embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
    embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="removerole", description="Xoá role của thành viên")
@app_commands.describe(member="Thành viên", role="Role cần xoá")
async def slash_removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
    if role >= interaction.guild.me.top_role:
        return await interaction.response.send_message("❌ Role này cao hơn role của bot.", ephemeral=True)
    await member.remove_roles(role, reason=f"Bởi {interaction.user}")
    embed = discord.Embed(title="✅ Đã Xoá Role", color=0xFEE75C)
    embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
    embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
    await interaction.response.send_message(embed=embed)

@tree.command(name="createchannel", description="Tạo kênh text mới")
@app_commands.describe(name="Tên kênh", category="Category (tuỳ chọn)")
async def slash_createchannel(interaction: discord.Interaction, name: str, category: discord.CategoryChannel = None):
    if not can_use_dangerous_cmd(interaction.user.id, "createchannel"):
        return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
    name = name.lower().replace(" ", "-")
    ch = await interaction.guild.create_text_channel(name, category=category, reason=f"Bởi {interaction.user}")
    await interaction.response.send_message(f"✅ Đã tạo kênh {ch.mention}!", ephemeral=True)

@tree.command(name="deletechannel", description="Xoá kênh")
@app_commands.describe(channel="Kênh cần xoá (để trống = kênh hiện tại)")
async def slash_deletechannel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not can_use_dangerous_cmd(interaction.user.id, "deletechannel"):
        return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
    target = channel or interaction.channel
    name = target.name
    await interaction.response.send_message(f"✅ Đang xoá kênh `#{name}`...", ephemeral=True)
    await target.delete(reason=f"Bởi {interaction.user}")

@tree.command(name="userinfo", description="Xem thông tin thành viên")
@app_commands.describe(member="Thành viên (để trống = bản thân)")
async def slash_userinfo(interaction: discord.Interaction, member: discord.Member = None):
    m = member or interaction.user
    roles = [r.mention for r in m.roles if r.name != "@everyone"]
    roles_str = " ".join(roles[-10:]) if roles else "Không có"
    embed = discord.Embed(title=f"👤  {m}", color=m.color if m.color.value else 0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="🆔 ID",         value=f"`{m.id}`",                                      inline=True)
    embed.add_field(name="🤖 Bot",        value="✅" if m.bot else "❌",                            inline=True)
    embed.add_field(name="📅 Tạo acc",    value=f"<t:{int(m.created_at.timestamp())}:D>",         inline=True)
    embed.add_field(name="📥 Vào server", value=f"<t:{int(m.joined_at.timestamp())}:D>" if m.joined_at else "N/A", inline=True)
    embed.add_field(name="🏷️ Roles",      value=roles_str,                                         inline=False)
    embed.set_thumbnail(url=m.display_avatar.url)
    embed.set_footer(text=f"TuyTam Store  •  Yêu cầu bởi {interaction.user}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="serverinfo", description="Xem thông tin server")
async def slash_serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    bots   = sum(1 for m in g.members if m.bot)
    humans = g.member_count - bots
    embed = discord.Embed(title=f"🏠  {g.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="🆔 ID",        value=f"`{g.id}`",                                  inline=True)
    embed.add_field(name="👑 Owner",      value=g.owner.mention if g.owner else "N/A",        inline=True)
    embed.add_field(name="📅 Tạo lúc",   value=f"<t:{int(g.created_at.timestamp())}:D>",     inline=True)
    embed.add_field(name="👥 Thành viên", value=f"👤 {humans}  🤖 {bots}",                    inline=True)
    embed.add_field(name="💬 Kênh",       value=f"📝 {len(g.text_channels)}  🔊 {len(g.voice_channels)}", inline=True)
    embed.add_field(name="💎 Boost",      value=f"Lv **{g.premium_tier}** — **{g.premium_subscription_count}** boost", inline=True)
    if g.icon: embed.set_thumbnail(url=g.icon.url)
    embed.set_footer(text=f"TuyTam Store  •  {interaction.user}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="botinfo", description="Xem thông tin bot")
async def slash_botinfo(interaction: discord.Interaction):
    import platform
    embed = discord.Embed(title=f"🤖  {bot.user.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="🆔 ID",       value=f"`{bot.user.id}`",                                          inline=True)
    embed.add_field(name="🌐 Servers",  value=f"**{len(bot.guilds)}**",                                    inline=True)
    embed.add_field(name="🏓 Latency",  value=f"**{round(bot.latency*1000)}ms**",                          inline=True)
    embed.add_field(name="🐍 Python",   value=f"`{platform.python_version()}`",                            inline=True)
    embed.add_field(name="📦 discord.py", value=f"`{discord.__version__}`",                                inline=True)
    embed.add_field(name="📅 Tạo lúc",  value=f"<t:{int(bot.user.created_at.timestamp())}:D>",            inline=True)
    if bot.user.avatar: embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(text="TuyTam Store  •  Ticket System")
    await interaction.response.send_message(embed=embed)

@tree.command(name="ping", description="Kiểm tra độ trễ bot")
async def slash_ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = 0x57F287 if latency < 100 else (0xFEE75C if latency < 200 else 0xED4245)
    status = "Tốt 🟢" if latency < 100 else ("Bình thường 🟡" if latency < 200 else "Chậm 🔴")
    embed = discord.Embed(title="🏓 Pong!", description=f"Độ trễ: **{latency}ms** — {status}", color=color)
    await interaction.response.send_message(embed=embed)

@tree.command(name="qr", description="Gửi mã QR thanh toán")
async def slash_qr(interaction: discord.Interaction):
    qr_path = get_qr_path()
    if not qr_path or not os.path.exists(qr_path):
        return await interaction.response.send_message("❌ Chưa có QR! Admin cài qua `.settings`.", ephemeral=True)
    file = discord.File(qr_path, filename="qr.png")
    embed = discord.Embed(title="📱  Mã QR Thanh Toán", color=0x57F287, timestamp=datetime.now(timezone.utc))
    embed.description = "> 🏦 **MB Bank** — `0702557706` — HOVANBUT\n> 📱 **Thẻ Viettel** bị trừ thêm **18% thuế**\n> ⚠️ Ghi rõ: `[tên MC] mua [item]`"
    embed.set_image(url="attachment://qr.png")
    await interaction.response.send_message(embed=embed, file=file)

# ================= BALANCE SYSTEM =================

def fmt_vnd(amount: int) -> str:
    if amount < 0:
        return f"-{abs(amount):,}đ".replace(",", ".")
    return f"{amount:,}đ".replace(",", ".")

async def handle_balance_message(message: discord.Message):
    content = message.content.strip()

    if not (content.startswith("+") or content.startswith("-")):
        return
    op = content[0]
    raw_str = content[1:].strip().replace(".", "").replace(",", "").replace(" ", "")
    if not raw_str.isdigit():
        return

    raw = int(raw_str)
    if raw <= 0:
        return

    bal = get_balance_data()
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    if op == "+":
        fee    = round(raw * 0.05)
        net    = raw - fee
        bal["current"]   += net
        bal["total_in"]  += net
        bal["total_fee"] += fee
        bal["tx_count"]  += 1
        bal["history"].append({
            "type": "+", "raw": raw, "fee": fee, "net": net,
            "user": str(message.author), "time": now_str
        })
        bal["history"] = bal["history"][-100:]
        save_balance_data(bal)

        embed = discord.Embed(
            title="💰  Nạp Tiền",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="💵  Số tiền nhận",   value=f"**{fmt_vnd(raw)}**",  inline=True)
        embed.add_field(name="📉  Phí 5%",         value=f"- {fmt_vnd(fee)}",    inline=True)
        embed.add_field(name="✅  Thực nhận",       value=f"**{fmt_vnd(net)}**",  inline=True)
        embed.add_field(name="🏦  Số dư hiện tại", value=f"**{fmt_vnd(bal['current'])}**", inline=False)
        embed.set_footer(text=f"Bởi {_uname_plain(message.author)}  •  {now_str}")

    else:  # op == "-"
        bal["current"]    -= raw
        bal["total_out"]  += raw
        bal["tx_count"]   += 1
        bal["history"].append({
            "type": "-", "raw": raw, "fee": 0, "net": raw,
            "user": str(message.author), "time": now_str
        })
        bal["history"] = bal["history"][-100:]
        save_balance_data(bal)

        color = 0xED4245 if bal["current"] >= 0 else 0x9B59B6
        embed = discord.Embed(
            title="💸  Chi Tiền",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="💵  Số tiền chi",    value=f"**{fmt_vnd(raw)}**",           inline=True)
        embed.add_field(name="🏦  Số dư còn lại",  value=f"**{fmt_vnd(bal['current'])}**" + (" ⚠️" if bal["current"] < 0 else ""), inline=True)
        embed.set_footer(text=f"Bởi {_uname_plain(message.author)}  •  {now_str}")

    try:
        await message.delete()
    except:
        pass
    await message.channel.send(embed=embed)


