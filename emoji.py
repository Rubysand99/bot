# cogs/emoji.py — .emoji .delemoji
from config import *
import re as _re_emoji

@bot.command(name="emoji")
async def emoji_cmd(ctx, *, args: str = None):
    """
    .emoji         → Lắng nghe 60s, tự động thêm ảnh/GIF được gửi trong kênh làm emoji server.
    .emoji <emoji> → Thêm emoji từ server khác vào server này (có thể nhiều emoji cách nhau bởi khoảng trắng).
    Chỉ admin mới dùng được.
    """
    if not can_use_dangerous_cmd(ctx.author.id, "emoji"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")

    guild: discord.Guild = ctx.guild
    if guild is None:
        return await ctx.reply("❌ Lệnh này chỉ dùng được trong server.")

    if args:
        import aiohttp as _aiohttp

        _emoji_pattern = r"<(a?):([^:>]+):(\d+)>"
        matches = _re_emoji.findall(_emoji_pattern, args)
        if not matches:
            return await ctx.reply("❌ Không tìm thấy emoji hợp lệ.\nCú pháp: `.emoji <emoji1> <emoji2> ...`")

        prog_msg = await ctx.reply(f"⏳ Đang thêm **{len(matches)}** emoji, vui lòng chờ...")

        added, failed = [], []
        name_count: dict = {}

        n = len(matches)
        delay = 1.0 if n <= 5 else 2.0 if n <= 15 else 3.0 if n <= 30 else 5.0

        async with _aiohttp.ClientSession() as session:
            for idx, (animated, name, emoji_id) in enumerate(matches):
                ext = "gif" if animated else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?quality=lossless"

                base_name = name[:32]
                if base_name in name_count:
                    name_count[base_name] += 1
                    final_name = f"{base_name[:29]}_{name_count[base_name]}"
                else:
                    name_count[base_name] = 1
                    final_name = base_name

                try:
                    async with session.get(url, timeout=_aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            raise Exception(f"Không tải được ảnh (HTTP {resp.status})")
                        image_bytes = await resp.read()

                    new_emoji = await guild.create_custom_emoji(
                        name=final_name,
                        image=image_bytes,
                        reason=f"Thêm bởi {ctx.author} qua .emoji"
                    )
                    added.append(str(new_emoji))
                except discord.HTTPException as e:
                    failed.append(f"`{final_name}` — {e.text}")
                except Exception as e:
                    failed.append(f"`{final_name}` — {e}")

                if idx < n - 1:
                    await asyncio.sleep(delay)
                if (idx + 1) % 10 == 0:
                    await prog_msg.edit(content=f"⏳ Đang thêm emoji... **{idx+1}/{n}**")

        lines = []
        if added:
            emoji_str = " ".join(added)
            lines.append(f"✅ Đã thêm **{len(added)}** emoji:\n{emoji_str[:900]}")
        if failed:
            fail_str = "\n".join(failed[:20])
            lines.append(f"❌ Thất bại **{len(failed)}**:\n{fail_str}")

        result_text = "\n\n".join(lines) if lines else "Không có emoji nào được thêm."
        try:
            await prog_msg.edit(content=result_text)
        except Exception:
            await ctx.reply(result_text)
        return

    embed = discord.Embed(
        title="🖼️  Chế độ thêm Emoji",
        description="Gửi **ảnh hoặc GIF** vào kênh này trong **60 giây**.\n"
                    "Bot sẽ tự động thêm tất cả làm emoji của server.\n"
                    "Gõ `hủy` để dừng sớm.",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Được kích hoạt bởi {ctx.author}")
    status_msg = await ctx.reply(embed=embed)

    added, failed = [], []

    def check(m: discord.Message):
        return (
            m.channel == ctx.channel
            and not m.author.bot
            and m.author.id in ADMIN_IDS
            and (m.attachments or m.content.strip().lower() == "hủy")
        )

    deadline = asyncio.get_event_loop().time() + 60

    while asyncio.get_event_loop().time() < deadline:
        timeout_left = deadline - asyncio.get_event_loop().time()
        try:
            msg: discord.Message = await bot.wait_for("message", check=check, timeout=timeout_left)
        except asyncio.TimeoutError:
            break

        if msg.content.strip().lower() == "hủy":
            await msg.add_reaction("🛑")
            break

        for idx, attachment in enumerate(msg.attachments):
                content_type = attachment.content_type or ""
                if not (content_type.startswith("image/") or content_type.startswith("video/")):
                    failed.append(f"`{attachment.filename}` (không phải ảnh/GIF)")
                    continue

                raw_name = attachment.filename.rsplit(".", 1)[0]
                emoji_name = _re_emoji.sub(r"[^a-zA-Z0-9_]", "_", raw_name)[:32] or "emoji"
                if len(emoji_name) < 2:
                    emoji_name = emoji_name + "_"

                try:
                    image_bytes = await attachment.read()
                    new_emoji = await guild.create_custom_emoji(
                        name=emoji_name,
                        image=image_bytes,
                        reason=f"Thêm bởi {ctx.author} qua .emoji"
                    )
                    added.append(str(new_emoji))
                    await msg.add_reaction("✅")
                except discord.HTTPException as e:
                    failed.append(f"`{emoji_name}` ({e.text})")
                    await msg.add_reaction("❌")
                except Exception as e:
                    failed.append(f"`{emoji_name}` ({e})")
                    await msg.add_reaction("❌")

                if idx < len(msg.attachments) - 1:
                    await asyncio.sleep(1.5)

    result_embed = discord.Embed(
        title="✅  Kết Quả Thêm Emoji",
        color=0x57F287 if added else 0xED4245,
        timestamp=datetime.now(timezone.utc)
    )
    if added:
        result_embed.add_field(
            name=f"✅ Đã thêm ({len(added)})",
            value=" ".join(added) if added else "—",
            inline=False
        )
    if failed:
        result_embed.add_field(
            name=f"❌ Thất bại ({len(failed)})",
            value="\n".join(failed),
            inline=False
        )
    if not added and not failed:
        result_embed.description = "Không có ảnh nào được gửi trong 60 giây."

    result_embed.set_footer(text=f"Kích hoạt bởi {ctx.author}")
    await status_msg.edit(embed=result_embed)

# ================= XOÁ EMOJI COMMAND =================

@bot.command(name="delemoji", aliases=["deleteemoji", "xoaemoji", "removeemoji"])
async def delemoji_cmd(ctx, *, args: str = None):
    """
    Xoá emoji khỏi server.
    .delemoji <emoji>       → Xoá 1 hoặc nhiều emoji (cách nhau bởi khoảng trắng)
    .delemoji tên:tên2      → Xoá theo tên emoji (không cần paste emoji)
    Chỉ admin mới dùng được.
    """
    if not can_use_dangerous_cmd(ctx.author.id, "delemoji"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")

    guild: discord.Guild = ctx.guild
    if guild is None:
        return await ctx.reply("❌ Lệnh này chỉ dùng được trong server.")

    if not args:
        embed = discord.Embed(
            title="🗑️  Xoá Emoji Server",
            color=0xED4245,
            description=(
                "**Cách dùng:**\n"
                "`.delemoji <emoji1> <emoji2> ...` — paste emoji trực tiếp\n"
                "`.delemoji tên` — xoá theo tên emoji\n\n"
                "**Ví dụ:**\n"
                "`.delemoji :pepe: :catjam:` — paste nhiều emoji\n"
                "`.delemoji pepe` — xoá emoji tên \"pepe\""
            )
        )
        return await ctx.reply(embed=embed)

    _emoji_pattern = r"<(a?):([^:>]+):(\d+)>"
    matches = _re_emoji.findall(_emoji_pattern, args)

    to_delete: list[discord.Emoji] = []
    not_found: list[str] = []

    if matches:
        for _, name, emoji_id in matches:
            emoji = discord.utils.get(guild.emojis, id=int(emoji_id))
            if emoji:
                to_delete.append(emoji)
            else:
                not_found.append(f"`{name}` (ID: {emoji_id})")
    else:
        # Tìm theo tên (cho phép nhiều tên cách nhau khoảng trắng hoặc dấu phẩy)
        names = [n.strip().strip(":") for n in _re_emoji.split(r"[\s,]+", args.strip()) if n.strip()]
        for name in names:
            found = [e for e in guild.emojis if e.name.lower() == name.lower()]
            if found:
                to_delete.extend(found)
            else:
                not_found.append(f"`{name}`")

    if not to_delete and not_found:
        return await ctx.reply(
            f"❌ Không tìm thấy emoji nào trong server:\n" + "\n".join(not_found)
        )

    prog_msg = await ctx.reply(f"⏳ Đang xoá **{len(to_delete)}** emoji...")

    deleted, failed = [], []
    for emoji in to_delete:
        try:
            await emoji.delete(reason=f"Xoá bởi {ctx.author} qua .delemoji")
            deleted.append(f"`:{emoji.name}:`")
        except discord.Forbidden:
            failed.append(f"`:{emoji.name}:` (thiếu quyền)")
        except Exception as e:
            failed.append(f"`:{emoji.name}:` ({e})")

    embed = discord.Embed(
        title="🗑️  Kết Quả Xoá Emoji",
        color=0x57F287 if deleted else 0xED4245,
        timestamp=datetime.now(timezone.utc)
    )
    if deleted:
        embed.add_field(
            name=f"✅ Đã xoá ({len(deleted)})",
            value=" ".join(deleted)[:1024],
            inline=False
        )
    if failed:
        embed.add_field(
            name=f"❌ Thất bại ({len(failed)})",
            value="\n".join(failed)[:1024],
            inline=False
        )
    if not_found:
        embed.add_field(
            name=f"🔍 Không tìm thấy ({len(not_found)})",
            value="\n".join(not_found)[:512],
            inline=False
        )
    embed.set_footer(text=f"Xoá bởi {ctx.author}")
    await prog_msg.edit(content=None, embed=embed)

# Cấu trúc mỗi mục: {"key": str, "name": str, "content": str}
# content là raw text hiển thị thẳng vào embed field (giữ markdown, emoji, blockquote)

_DEFAULT_PRICE_SECTIONS = [
    {
        "key": "steam",
        "name": "🎮  Game Steam",
        "content": (
            "**Giá stock:**\n"
            "> - **acc offline đông giá 60.000 VNĐ**"
        ),
    },
    {
        "key": "robux",
        "name": "<:robux:1456493708382830735>  Robux",
        "content": (
            "**Giá stock:**\n"
            "> - **250 <:robux:1456493708382830735> -> 47.000 VNĐ**\n"
            "> - **500 <:robux:1456493708382830735> -> 89.000 VNĐ**\n"
            "> - **750 <:robux:1456493708382830735> -> 129.000 VNĐ**\n"
            "> - **1000 <:robux:1456493708382830735> -> 165.000 VNĐ**"
        ),
    },
    {
        "key": "nitro",
        "name": "💎  Nitro",
        "content": (
            "**Giá stock:**\n"
            "> - **1 Tháng: 95.000 VNĐ**\n"
            "> - **2 Tháng: 119.000 VNĐ**\n"
            "> - **12 Tháng: 899.000 VNĐ**"
        ),
    },
    {
        "key": "decao_login_gip",
        "name": "🎵  Decao — Dạng Login & Gip",
        "content": (
            "**Dạng login**\n"
            "> - ~~66.000 VNĐ~~ -> **35.000 VNĐ**\n"
            "> - ~~79.000 VNĐ~~ -> **45.000 VNĐ**\n"
            "> - ~~92.000 VNĐ~~ -> **55.000 VNĐ**\n"
            "> - ~~105.000 VNĐ~~ -> **62.000 VNĐ**\n"
            "> - ~~111.000 VNĐ~~ -> **74.000 VNĐ**\n"
            "> - ~~118.000 VNĐ~~ -> **79.000 VNĐ**\n"
            "> - ~~131.000 VNĐ~~ -> **92.000 VNĐ**\n"
            "> - ~~136.000 VNĐ~~ -> **99.000 VNĐ**\n"
            "> - ~~141.000 VNĐ~~ -> **103.000 VNĐ**\n"
            "> - ~~146.000 VNĐ~~ -> **109.000 VNĐ**\n"
            "> - ~~189.000 VNĐ~~ -> **125.000 VNĐ**\n"
            "**Dạng gip**\n"
            "> - ~~66.000 VNĐ~~ -> **48.000 VNĐ**\n"
            "> - ~~79.000 VNĐ~~ -> **58.000 VNĐ**\n"
            "> - ~~92.000 VNĐ~~ -> **62.000 VNĐ**\n"
            "> - ~~105.000 VNĐ~~ -> **69.000 VNĐ**\n"
            "> - ~~111.000 VNĐ~~ -> **85.000 VNĐ**\n"
            "> - ~~118.000 VNĐ~~ -> **89.000 VNĐ**\n"
            "> - ~~131.000 VNĐ~~ -> **99.000 VNĐ**\n"
            "> - ~~136.000 VNĐ~~ -> **109.000 VNĐ**\n"
            "> - ~~141.000 VNĐ~~ -> **114.000 VNĐ**\n"
            "> - ~~146.000 VNĐ~~ -> **119.000 VNĐ**\n"
            "> - ~~189.000 VNĐ~~ -> **139.000 VNĐ**"
        ),
    },
    {
        "key": "decao_bundle",
        "name": "🎵  Decao — Gip Bundle",
        "content": (
            "> - **x2 dc66: 85.000 VNĐ**\n"
            "> - **x3 dc66: 120.000 VNĐ**\n"
            "> - **x3 dc79: 140.000 VNĐ**\n"
            "> - **x2 dc92: 115.000 VNĐ**\n"
            "> - **x3 dc92: 165.000 VNĐ**\n"
            "> - **x2 dc105: 115.000 VNĐ**\n"
            "> - **x2 dc118: 150.000 VNĐ**\n"
            "> - **x3 dc118: 240.000 VNĐ**\n"
            "> - **x2 dc131: 170.000 VNĐ**"
        ),
    },
    {
        "key": "chatgpt",
        "name": "🤖  Chat GPT",
        "content": (
            "**Giá stock:**\n"
            "> - **Chat GPT Plus 1 tháng: hết hàng**\n"
            "> - **Code Chat GPT Plus 1 tháng: hết hàng**"
        ),
    },
    {
        "key": "capcut",
        "name": "✂️  CapCut",
        "content": (
            "**Giá stock:**\n"
            "> - **Capcut Pro 35day: 20.000 VNĐ**\n"
            "> - **Capcut Pro 6 Tháng: 120.000 VNĐ**"
        ),
    },
    {
        "key": "canva",
        "name": "🎨  Canva",
        "content": (
            "**Giá stock:**\n"
            "> - **2 tháng pro: 15.000 VNĐ**"
        ),
    },
    {
        "key": "youtube",
        "name": "▶️  YouTube Premium",
        "content": (
            "**Giá stock:**\n"
            "> - **15.000 VNĐ/Tháng**"
        ),
    },
]

def get_price_sections() -> list:
    data = load_data()
    return data.get("price_sections", _DEFAULT_PRICE_SECTIONS)

def save_price_sections(sections: list):
    data = load_data()
    data["price_sections"] = sections
    save_data(data)

def build_sv_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏪  TuyTam Store — Bảng Giá",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc),
    )
    for sec in get_price_sections():
        embed.add_field(name=sec["name"], value=sec["content"], inline=False)
    embed.set_footer(text="TuyTam Store  •  .sv để xem lại bất cứ lúc nào")
    return embed


