"""
cogs/invite.py — Invite tracking: đếm invite, fake detect, leaderboard.
Lệnh: .invite, .invitetop, .resetinvite
"""

import asyncio
import time as _time
from datetime import datetime, timezone

import discord
from cogs.logger import send_log
from discord.ext import commands

from core.data import ADMIN_IDS, load_data, save_data, _uname, _uname_plain


_invite_cache: dict[int, dict[str, int]] = {}
_pending_joins: dict[int, dict] = {}


def _get_invite_counts() -> dict:
    return load_data().get("invite_counts", {})

def _save_invite_counts(counts: dict):
    data = load_data()
    data["invite_counts"] = counts
    save_data(data)

def _add_invite(inviter_id: int, field: str, amount: int = 1):
    counts = _get_invite_counts()
    uid    = str(inviter_id)
    if uid not in counts:
        counts[uid] = {"total": 0, "fake": 0, "left": 0}
    counts[uid][field] = counts[uid].get(field, 0) + amount
    _save_invite_counts(counts)

def _get_net_invites(inviter_id: int) -> tuple[int, int, int, int]:
    counts = _get_invite_counts()
    uid    = str(inviter_id)
    c      = counts.get(uid, {"total": 0, "fake": 0, "left": 0})
    total  = c.get("total", 0)
    fake   = c.get("fake",  0)
    left   = c.get("left",  0)
    net    = max(0, total - fake - left)
    return total, fake, left, net

async def cache_invites(guild: discord.Guild):
    try:
        invites = await guild.invites()
        _invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
    except (discord.Forbidden, discord.HTTPException):
        pass


class InviteCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="invite", aliases=["inv", "invites", "i"])
    async def invite_cmd(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        total, fake, left, net = _get_net_invites(target.id)
        embed = discord.Embed(title=f"📨 Invite của {_uname(target)}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="✅ Net (thực tế)", value=f"**{net}** người",  inline=True)
        embed.add_field(name="📊 Tổng",          value=f"**{total}** lần",  inline=True)
        embed.add_field(name="⚠️ Fake",          value=f"**{fake}** người", inline=True)
        embed.add_field(name="🚪 Đã rời",        value=f"**{left}** người", inline=True)
        embed.set_footer(text="Net = Tổng − Fake − Đã rời  •  TuyTam Store")
        await ctx.reply(embed=embed)

    @commands.command(name="invitetop", aliases=["invtop"])
    async def invitetop_cmd(self, ctx, top: int = 10):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")
        top    = max(1, min(top, 25))
        counts = _get_invite_counts()
        board  = []
        for uid_str, c in counts.items():
            total = c.get("total", 0)
            fake  = c.get("fake",  0)
            left  = c.get("left",  0)
            net   = max(0, total - fake - left)
            board.append((int(uid_str), net, total, fake, left))
        board.sort(key=lambda x: x[1], reverse=True)
        board = board[:top]
        if not board: return await ctx.reply("❌ Chưa có dữ liệu invite nào.")
        medals = ["🥇", "🥈", "🥉"]
        lines  = []
        for i, (uid, net, total, fake, left) in enumerate(board):
            icon   = medals[i] if i < 3 else f"`{i+1}.`"
            member = ctx.guild.get_member(uid)
            name   = _uname(member) if member else f"<@{uid}>"
            lines.append(f"{icon} **{name}** — **{net}** net (`{total}` tổng, `{fake}` fake, `{left}` rời)")
        embed = discord.Embed(title=f"🏆 Bảng xếp hạng Invite — Top {top}", description="\n".join(lines), color=0xF1C40F, timestamp=datetime.now(timezone.utc))
        embed.set_footer(text="TuyTam Store  •  Net = Tổng − Fake − Đã rời")
        await ctx.reply(embed=embed)

    @commands.command(name="resetinvite", aliases=["resetinv"])
    async def resetinvite_cmd(self, ctx, member: discord.Member = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")
        raw    = ctx.message.content.split()
        is_all = len(raw) > 1 and raw[-1].lower() == "all" and not ctx.message.mentions
        if is_all:
            _save_invite_counts({})
            await ctx.reply("✅ Đã reset toàn bộ invite của server.")
        elif member:
            counts = _get_invite_counts()
            uid    = str(member.id)
            if uid in counts:
                del counts[uid]
                _save_invite_counts(counts)
            await ctx.reply(f"✅ Đã reset invite của **{_uname(member)}**.")
            await send_log(self.bot, "INVITE", f"Reset invite — {member}",
                fields=[("Admin", ctx.author.mention, True), ("Target", member.mention, True)])
        else:
            await ctx.reply("❌ Dùng:\n`.resetinvite @user` — reset 1 người\n`.resetinvite all` — reset toàn bộ")

    # ── Events ──
    WELCOME_GUILDS = {
        950363132679831642: 1276087208150827070,
    }

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        ch_id = self.WELCOME_GUILDS.get(member.guild.id)
        if ch_id:
            channel = member.guild.get_channel(ch_id)
            if channel:
                try:
                    msg = await channel.send(member.mention)
                    await asyncio.sleep(10)
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    pass

        try:
            old_cache  = _invite_cache.get(member.guild.id, {})
            new_invites = await member.guild.invites()
            new_cache   = {inv.code: inv.uses for inv in new_invites}
            inviter_id  = None
            for inv in new_invites:
                if inv.uses > old_cache.get(inv.code, 0):
                    if inv.inviter:
                        inviter_id = inv.inviter.id
                    break
            _invite_cache[member.guild.id] = new_cache

            if inviter_id and inviter_id != member.id:
                _pending_joins[member.id] = {"inviter_id": inviter_id, "guild_id": member.guild.id, "joined_at": _time.time()}
                _add_invite(inviter_id, "total", 1)

                async def _check_fake():
                    await asyncio.sleep(600)
                    still_here = member.guild.get_member(member.id)
                    if not still_here:
                        _add_invite(inviter_id, "fake", 1)
                        print(f"[INVITE] ⚠️ Fake invite: {member} invited by {inviter_id}")
                    _pending_joins.pop(member.id, None)
                asyncio.create_task(_check_fake())

        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await cache_invites(member.guild)
        _pending_joins.pop(member.id, None)

    # ── SLASH COMMANDS ──
    @discord.app_commands.command(name="invite", description="Xem thống kê invite của thành viên")
    @discord.app_commands.describe(member="Thành viên (để trống = bản thân)")
    async def slash_invite(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        total, fake, left, net = _get_net_invites(target.id)
        embed = discord.Embed(title=f"📨 Invite của {_uname(target)}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="✅ Net", value=f"**{net}**", inline=True)
        embed.add_field(name="📊 Tổng", value=f"**{total}**", inline=True)
        embed.add_field(name="⚠️ Fake", value=f"**{fake}**", inline=True)
        embed.add_field(name="🚪 Đã rời", value=f"**{left}**", inline=True)
        embed.set_footer(text="Net = Tổng − Fake − Đã rời")
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="invitetop", description="Bảng xếp hạng invite (admin)")
    @discord.app_commands.describe(top="Số người top (mặc định 10)")
    async def slash_invitetop(self, interaction: discord.Interaction, top: int = 10):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        top    = max(1, min(top, 25))
        counts = _get_invite_counts()
        board  = []
        for uid_str, c in counts.items():
            net = max(0, c.get("total",0) - c.get("fake",0) - c.get("left",0))
            board.append((int(uid_str), net, c.get("total",0), c.get("fake",0), c.get("left",0)))
        board.sort(key=lambda x: x[1], reverse=True)
        board = board[:top]
        if not board:
            return await interaction.response.send_message("❌ Chưa có dữ liệu invite.", ephemeral=True)
        medals = ["🥇","🥈","🥉"]
        lines  = [f"{medals[i] if i<3 else f'`{i+1}.`'} **{_uname(interaction.guild.get_member(uid)) if interaction.guild.get_member(uid) else f'<@{uid}>'}** — **{net}** net" for i,(uid,net,*_) in enumerate(board)]
        embed  = discord.Embed(title=f"🏆 Top {top} Invite", description="\n".join(lines), color=0xF1C40F)
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="resetinvite", description="Reset invite của thành viên (admin)")
    @discord.app_commands.describe(member="Thành viên cần reset (để trống = reset tất cả)")
    async def slash_resetinvite(self, interaction: discord.Interaction, member: discord.Member = None):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        if member:
            counts = _get_invite_counts()
            counts.pop(str(member.id), None)
            _save_invite_counts(counts)
            await interaction.response.send_message(f"✅ Đã reset invite của {member.mention}.", ephemeral=True)
        else:
            _save_invite_counts({})
            await interaction.response.send_message("✅ Đã reset toàn bộ invite server.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(InviteCog(bot))
