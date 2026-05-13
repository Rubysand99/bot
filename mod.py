# cogs/mod.py — .clear .addrole .removerole .createchannel .deletechannel
from config import *

@bot.command(name="clear", aliases=["purge"])
async def clear_cmd(ctx, amount: int = 10):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Bạn không có quyền.", delete_after=3)
    if not 1 <= amount <= 100:
        return await ctx.reply("❌ Số tin cần xoá phải từ 1–100.", delete_after=3)
    try:
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.send(f"🗑️ Đã xoá **{len(deleted)}** tin nhắn.")
        await asyncio.sleep(3)
        await msg.delete()
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Messages`.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")

@bot.command(name="addrole")
async def addrole_cmd(ctx, member: discord.Member = None, role: discord.Role = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not member or not role:
        return await ctx.reply("❌ Dùng: `.addrole @user @role`")
    try:
        await member.add_roles(role)
        embed = discord.Embed(
            title="✅  Đã Thêm Role",
            description=f"Đã thêm {role.mention} cho {member.mention}",
            color=0x57F287, timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Bởi {ctx.author}")
        await ctx.reply(embed=embed)
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Roles` hoặc role cao hơn bot.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")

@bot.command(name="removerole")
async def removerole_cmd(ctx, member: discord.Member = None, role: discord.Role = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not member or not role:
        return await ctx.reply("❌ Dùng: `.removerole @user @role`")
    try:
        await member.remove_roles(role)
        embed = discord.Embed(
            title="✅  Đã Gỡ Role",
            description=f"Đã gỡ {role.mention} khỏi {member.mention}",
            color=0xED4245, timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Bởi {ctx.author}")
        await ctx.reply(embed=embed)
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Roles` hoặc role cao hơn bot.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")

@bot.command(name="createchannel", aliases=["cc"])
async def createchannel_cmd(ctx, name: str = None, ch_type: str = "text"):
    if not can_use_dangerous_cmd(ctx.author.id, "createchannel"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    if not name:
        return await ctx.reply("❌ Dùng: `.createchannel <tên> [text/voice]`")
    try:
        name = name.lower().replace(" ", "-")
        if ch_type.lower() == "voice":
            channel = await ctx.guild.create_voice_channel(name, category=ctx.channel.category)
            icon = "🔊"
        else:
            channel = await ctx.guild.create_text_channel(name, category=ctx.channel.category)
            icon = "💬"
        embed = discord.Embed(
            title="✅  Đã Tạo Kênh",
            description=f"{icon} {channel.mention} đã được tạo!",
            color=0x57F287, timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Tạo bởi {ctx.author}")
        await ctx.reply(embed=embed)
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Channels`.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")

@bot.command(name="deletechannel", aliases=["dc"])
async def deletechannel_cmd(ctx, channel: discord.TextChannel = None):
    if not can_use_dangerous_cmd(ctx.author.id, "deletechannel"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    target = channel or ctx.channel
    try:
        name = target.name
        await target.delete()
        if target != ctx.channel:
            embed = discord.Embed(
                title="✅  Đã Xoá Kênh",
                description=f"Kênh `#{name}` đã bị xoá.",
                color=0xED4245, timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Xoá bởi {ctx.author}")
            await ctx.reply(embed=embed)
    except discord.Forbidden:
        await ctx.reply("❌ Bot thiếu quyền `Manage Channels`.")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")

# ================= GIVEAWAY =================
import re as _re
import random

active_giveaways: dict[int, dict] = {}

def parse_time(time_str: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = _re.fullmatch(r"(\d+)([smhd])", time_str.lower())
    if not match:
        return 0
    return int(match.group(1)) * units[match.group(2)]

# ── Lưu/load giveaway — dùng section GIVEAWAY riêng ──
def save_giveaways_data():
    _save_giveaway_section(active_giveaways)

def load_giveaways_data() -> dict:
    raw = _load_giveaway_section()
    result = {}
    for mid_str, gw in raw.items():
        gw = dict(gw)
        gw["entries"] = set(gw.get("entries", []))
        result[int(mid_str)] = gw
    return result

