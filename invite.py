# cogs/invite.py — .invite .invitetop .resetinvite
from config import *

@bot.command(name="invite", aliases=["inv", "invites"])
async def invite_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    total, fake, left, net = _get_net_invites(target.id)
    embed = discord.Embed(
        title=f"📨 Invite của {_uname(target)}",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="✅ Net (thực tế)",  value=f"**{net}** người",   inline=True)
    embed.add_field(name="📊 Tổng",           value=f"**{total}** lần",   inline=True)
    embed.add_field(name="⚠️ Fake",           value=f"**{fake}** người",  inline=True)
    embed.add_field(name="🚪 Đã rời",         value=f"**{left}** người",  inline=True)
    embed.set_footer(text=f"Net = Tổng − Fake − Đã rời  •  TuyTam Store")
    await ctx.reply(embed=embed)

@bot.command(name="invitetop", aliases=["invtop"])
async def invitetop_cmd(ctx, top: int = 10):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin.")
    top = max(1, min(top, 25))
    counts = _get_invite_counts()
    board = []
    for uid_str, c in counts.items():
        total = c.get("total", 0)
        fake  = c.get("fake",  0)
        left  = c.get("left",  0)
        net   = max(0, total - fake - left)
        board.append((int(uid_str), net, total, fake, left))
    board.sort(key=lambda x: x[1], reverse=True)
    board = board[:top]

    if not board:
        return await ctx.reply("❌ Chưa có dữ liệu invite nào.")

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, net, total, fake, left) in enumerate(board):
        icon = medals[i] if i < 3 else f"`{i+1}.`"
        member = ctx.guild.get_member(uid)
        name = _uname(member) if member else f"<@{uid}>"
        lines.append(f"{icon} **{name}** — **{net}** net (`{total}` tổng, `{fake}` fake, `{left}` rời)")

    embed = discord.Embed(
        title=f"🏆 Bảng xếp hạng Invite — Top {top}",
        description="\n".join(lines),
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="TuyTam Store  •  Net = Tổng − Fake − Đã rời")
    await ctx.reply(embed=embed)

@bot.command(name="resetinvite", aliases=["resetinv"])
async def resetinvite_cmd(ctx, member: discord.Member = None):
    """
    Reset invite của 1 user hoặc toàn bộ server. *(admin)*
    .resetinvite @user  — reset 1 người
    .resetinvite all    — reset tất cả
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin.")

    raw = ctx.message.content.split()
    is_all = len(raw) > 1 and raw[-1].lower() == "all" and not ctx.message.mentions

    if is_all:
        _save_invite_counts({})
        await ctx.reply("✅ Đã reset toàn bộ invite của server.")
    elif member:
        counts = _get_invite_counts()
        uid = str(member.id)
        if uid in counts:
            del counts[uid]
            _save_invite_counts(counts)
        await ctx.reply(f"✅ Đã reset invite của **{_uname(member)}**.")
    else:
        await ctx.reply(
            "❌ Dùng:\n"
            "`.resetinvite @user` — reset 1 người\n"
            "`.resetinvite all` — reset toàn bộ server"
        )

@bot.command(name="mkchannel", aliases=["mkch", "taokenh"])
async def mkchannel_cmd(ctx, *, args: str = None):
    """
    Tạo kênh mới với font đồng bộ server.
    Dùng: .mkchannel <loại> <tên kênh> [category]
    Ví dụ:
      .mkchannel text thông-báo
      .mkchannel voice Phòng Chờ
      .mkchannel category Mua Bán
      .mkchannel text tin-tức "Thông Báo"
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin.")

    if not args:
        embed = discord.Embed(
            title="📖 Hướng dẫn tạo kênh",
            color=0x5865F2,
            description=(
                "**`.mkchannel text <tên>`** — Tạo kênh text\n"
                "**`.mkchannel voice <tên>`** — Tạo kênh voice\n"
                "**`.mkchannel category <tên>`** — Tạo category\n\n"
                "Tên kênh sẽ tự động áp dụng font server đang dùng.\n"
                f"Font hiện tại: **{FONT_LABELS.get(get_cfg_font(), get_cfg_font())}**"
            )
        )
        return await ctx.reply(embed=embed)

    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return await ctx.reply("❌ Thiếu tên kênh. Dùng: `.mkchannel text <tên kênh>`")

    ch_type = parts[0].lower()
    raw_name = parts[1].strip().strip('"').strip("'")

    if ch_type not in ("text", "voice", "category", "t", "v", "c"):
        return await ctx.reply("❌ Loại kênh không hợp lệ. Dùng: `text`, `voice`, hoặc `category`")

    server_font = get_cfg_font()
    ch_parts = _detect_channel_parts(raw_name)
    styled_name = _rebuild_name(ch_parts, ch_parts["base_text"], server_font)

    category = ctx.channel.category  # đặt vào category của kênh hiện tại

    try:
        if ch_type in ("text", "t"):
            new_ch = await ctx.guild.create_text_channel(
                name=styled_name,
                category=category,
                reason=f"Tạo bởi {ctx.author}"
            )
            ch_icon = "📝"
        elif ch_type in ("voice", "v"):
            new_ch = await ctx.guild.create_voice_channel(
                name=styled_name,
                category=category,
                reason=f"Tạo bởi {ctx.author}"
            )
            ch_icon = "🔊"
        else:  # category
            new_ch = await ctx.guild.create_category(
                name=styled_name,
                reason=f"Tạo bởi {ctx.author}"
            )
            ch_icon = "📂"

        embed = discord.Embed(
            title=f"{ch_icon} Đã tạo kênh thành công!",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Tên gốc", value=f"`{raw_name}`", inline=True)
        embed.add_field(name="Tên đã tạo", value=new_ch.mention, inline=True)
        embed.add_field(name="Font", value=FONT_LABELS.get(server_font, server_font), inline=True)
        if category:
            embed.add_field(name="Category", value=category.name, inline=True)
        embed.set_footer(text=f"Tạo bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền tạo kênh.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: {e}")


