# cogs/info.py — .botinfo .serverinfo .userinfo
from config import *

@bot.command(name="botinfo", aliases=["bi"])
async def botinfo_cmd(ctx):
    import platform, sys, time
    latency = round(bot.latency * 1000)
    lat_status = "🟢 Tốt" if latency < 100 else ("🟡 Bình thường" if latency < 200 else "🔴 Chậm")

    total_users  = sum(g.member_count or 0 for g in bot.guilds)
    total_ch     = sum(len(g.channels) for g in bot.guilds)
    total_roles  = sum(len(g.roles) for g in bot.guilds)
    cmds_count   = len(bot.commands)

    embed = discord.Embed(
        title=f"🤖  {bot.user.name}",
        description=f"Bot ticket & quản lý giao dịch của **TuyTam Store**",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(name="👤  Tag",          value=f"`{bot.user}`",                               inline=True)
    embed.add_field(name="🆔  ID",           value=f"`{bot.user.id}`",                            inline=True)
    embed.add_field(name="🏷️  Version",      value=f"`v{BOT_VERSION}` ({BOT_UPDATED})",           inline=True)

    embed.add_field(name="🏓  Latency",      value=f"**{latency}ms** {lat_status}",          inline=True)
    embed.add_field(name="🐍  Python",       value=f"`{platform.python_version()}`",         inline=True)
    embed.add_field(name="📚  discord.py",   value=f"`{discord.__version__}`",               inline=True)

    embed.add_field(name="🌐  Servers",      value=f"**{len(bot.guilds)}** server",           inline=True)
    embed.add_field(name="👥  Tổng users",   value=f"**{total_users:,}** người",             inline=True)
    embed.add_field(name="💬  Tổng kênh",    value=f"**{total_ch}** kênh",                   inline=True)

    embed.add_field(name="🎭  Tổng roles",   value=f"**{total_roles}** roles",               inline=True)
    embed.add_field(name="⌨️  Lệnh",         value=f"**{cmds_count}** prefix + slash",       inline=True)
    embed.add_field(name="🖥️  OS",           value=f"`{platform.system()} {platform.release()}`", inline=True)

    embed.set_footer(
        text=f"TuyTam Store  •  Prefix: .  |  Được yêu cầu bởi {_uname_plain(ctx.author)}",
        icon_url=ctx.author.display_avatar.url
    )
    await ctx.reply(embed=embed)

@bot.command(name="serverinfo", aliases=["si"])
async def serverinfo_cmd(ctx):
    g = ctx.guild

    bots    = sum(1 for m in g.members if m.bot)
    humans  = (g.member_count or 0) - bots
    online  = sum(1 for m in g.members if m.status != discord.Status.offline)

    cats    = len(g.categories)
    text_ch = len(g.text_channels)
    voice_ch= len(g.voice_channels)
    stage_ch= len(g.stage_channels)
    forum_ch= len([c for c in g.channels if isinstance(c, discord.ForumChannel)])

    verify_map = {
        discord.VerificationLevel.none:    "Không",
        discord.VerificationLevel.low:     "Thấp",
        discord.VerificationLevel.medium:  "Trung bình",
        discord.VerificationLevel.high:    "Cao",
        discord.VerificationLevel.highest: "Rất cao",
    }
    verify = verify_map.get(g.verification_level, str(g.verification_level))

    data   = load_data()
    tickets_total = data.get("ticket", 0)

    embed = discord.Embed(
        title=f"🌐  {g.name}",
        description=g.description or "",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    if g.banner:
        embed.set_image(url=g.banner.url)

    embed.add_field(name="🆔  ID",              value=f"`{g.id}`",                                                       inline=True)
    embed.add_field(name="👑  Owner",            value=g.owner.mention if g.owner else "N/A",                            inline=True)
    embed.add_field(name="📅  Ngày tạo",         value=f"<t:{int(g.created_at.timestamp())}:F>",                         inline=True)

    embed.add_field(
        name="👥  Members",
        value=f"**{g.member_count:,}** tổng\n🟢 Online: **{online}** | 👤 Người: **{humans}** | 🤖 Bot: **{bots}**",
        inline=False
    )

    embed.add_field(
        name="💬  Kênh",
        value=f"📁 Categories: **{cats}** | 💬 Text: **{text_ch}** | 🔊 Voice: **{voice_ch}**"
              + (f" | 🎭 Stage: **{stage_ch}**" if stage_ch else "")
              + (f" | 📋 Forum: **{forum_ch}**" if forum_ch else ""),
        inline=False
    )

    embed.add_field(name="🎭  Roles",            value=f"**{len(g.roles)}** roles",                                      inline=True)
    embed.add_field(name="😀  Emojis",           value=f"**{len(g.emojis)}** / {g.emoji_limit}",                        inline=True)
    embed.add_field(name="🔒  Xác minh",         value=verify,                                                           inline=True)

    boost_bar = "⭐" * g.premium_tier if g.premium_tier else "—"
    embed.add_field(
        name="🚀  Nitro Boost",
        value=f"Level **{g.premium_tier}** {boost_bar}\n💎 **{g.premium_subscription_count}** boosts",
        inline=True
    )

    embed.add_field(name="🎫  Tổng ticket",      value=f"**{tickets_total}** đơn đã tạo",                               inline=True)
    embed.add_field(name="🖼️  Features",          value=f"**{len(g.features)}** tính năng",                             inline=True)

    embed.set_footer(
        text=f"TuyTam Store  •  Được yêu cầu bởi {_uname_plain(ctx.author)}",
        icon_url=ctx.author.display_avatar.url
    )
    await ctx.reply(embed=embed)

@bot.command(name="userinfo", aliases=["ui"])
async def userinfo_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author

    roles = [r for r in reversed(member.roles) if r != ctx.guild.default_role]
    roles_str = " ".join(r.mention for r in roles[:15]) + (f"\n*...và {len(roles)-15} roles nữa*" if len(roles) > 15 else "")
    roles_str = roles_str or "Không có"

    key_perms = []
    if member.guild_permissions.administrator:        key_perms.append("👑 Administrator")
    if member.guild_permissions.manage_guild:         key_perms.append("⚙️ Manage Server")
    if member.guild_permissions.manage_channels:      key_perms.append("📁 Manage Channels")
    if member.guild_permissions.manage_roles:         key_perms.append("🎭 Manage Roles")
    if member.guild_permissions.manage_messages:      key_perms.append("🗑️ Manage Messages")
    if member.guild_permissions.kick_members:         key_perms.append("👢 Kick")
    if member.guild_permissions.ban_members:          key_perms.append("🔨 Ban")
    if member.guild_permissions.moderate_members:     key_perms.append("🔇 Timeout")
    perm_str = " | ".join(key_perms) if key_perms else "Không có quyền đặc biệt"

    data = load_data()
    user_tickets = sum(
        1 for t in data.get("ticket_notes", {}).values()
        for note in t if note.get("author", "").startswith(str(member))
    )

    status_map = {
        discord.Status.online:    "🟢 Online",
        discord.Status.idle:      "🟡 Idle",
        discord.Status.dnd:       "🔴 Do Not Disturb",
        discord.Status.offline:   "⚫ Offline",
    }
    status_str = status_map.get(member.status, str(member.status))

    activity_str = "Không có"
    if member.activities:
        for act in member.activities:
            if isinstance(act, discord.Game):
                activity_str = f"🎮 Đang chơi **{act.name}**"
                break
            elif isinstance(act, discord.Streaming):
                activity_str = f"📡 Stream: **{act.name}**"
                break
            elif isinstance(act, discord.CustomActivity) and act.name:
                activity_str = f"💬 {act.name}"
                break
            elif isinstance(act, discord.Activity):
                activity_str = f"▶️ {act.name}"
                break

    joined_str = f"<t:{int(member.joined_at.timestamp())}:F>" if member.joined_at else "N/A"

    sorted_members = sorted(
        [m for m in ctx.guild.members if m.joined_at],
        key=lambda m: m.joined_at
    )
    join_pos = next((i+1 for i, m in enumerate(sorted_members) if m.id == member.id), "?")

    embed = discord.Embed(
        title=f"👤  {_uname(member)}",
        description=f"{'🤖 Bot' if member.bot else '👤 Người dùng'} | {status_str}",
        color=member.color if member.color.value else 0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(name="🏷️  Tag",          value=f"`{member.name}`",                                             inline=True)
    embed.add_field(name="🆔  ID",            value=f"`{member.id}`",                                          inline=True)
    embed.add_field(name="🤖  Bot",           value="✅ Có" if member.bot else "❌ Không",                      inline=True)

    embed.add_field(name="📅  Tạo tài khoản", value=f"<t:{int(member.created_at.timestamp())}:F>",             inline=True)
    embed.add_field(name="📥  Vào server",    value=f"{joined_str}\n*(thứ **#{join_pos}** vào server)*",        inline=True)
    embed.add_field(name="🎨  Màu role",      value=str(member.color) if member.color.value else "#mặc định",  inline=True)

    embed.add_field(name="🎮  Hoạt động",     value=activity_str,                                               inline=False)

    embed.add_field(name="🔑  Quyền nổi bật", value=perm_str,                                                   inline=False)

    embed.add_field(name=f"🎭  Roles ({len(roles)})", value=roles_str,                                          inline=False)

    embed.set_footer(
        text=f"TuyTam Store  •  Được yêu cầu bởi {_uname_plain(ctx.author)}",
        icon_url=ctx.author.display_avatar.url
    )
    await ctx.reply(embed=embed)

@bot.command()
async def panel(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    await ctx.send(embed=build_panel_embed(ctx.guild), view=TicketPanel())
    await ctx.message.delete()

@bot.command()
async def setpanel(ctx, channel: discord.TextChannel = None):
    if ctx.author.id not in ADMIN_IDS:
        return
    if channel is None:
        return await ctx.reply("❌ Thiếu kênh! Ví dụ: `.setpanel #shop`")
    save_panel_channel_id(channel.id)
    embed = discord.Embed(
        title="⚙️  Đã Cài Đặt Panel Channel",
        description=f"Bot sẽ gửi panel ticket vào {channel.mention}.",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Cài bởi {ctx.author}")
    await ctx.reply(embed=embed)

# ================= SETTINGS MODALS =================

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


