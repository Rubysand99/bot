"""
cogs/balance.py — Hệ thống số dư: nạp/chi trong kênh balance, .balance, .balset, .balreset
"""

from datetime import datetime, timezone
import discord
from discord.ext import commands
from discord.ui import View, Button

from core.data import (
    ADMIN_IDS, get_cfg_balance_channel, get_balance_data, save_balance_data,
    load_data, save_data, can_use_dangerous_cmd, _uname, _uname_plain, fmt_amount,
)
from cogs.logger import send_log


def fmt_vnd(amount: int) -> str:
    if amount < 0:
        return f"-{abs(amount):,}đ".replace(",", ".")
    return f"{amount:,}đ".replace(",", ".")


async def handle_balance_message(message: discord.Message):
    content = message.content.strip()
    if not (content.startswith("+") or content.startswith("-")):
        return
    op      = content[0]
    raw_str = content[1:].strip().replace(".", "").replace(",", "").replace(" ", "")
    if not raw_str.isdigit():
        return
    raw = int(raw_str)
    if raw <= 0:
        return

    bal     = get_balance_data()
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    if op == "+":
        fee = round(raw * 0.05)
        net = raw - fee
        bal["current"]   += net
        bal["total_in"]  += net
        bal["total_fee"] += fee
        bal["tx_count"]  += 1
        bal["history"].append({"type": "+", "raw": raw, "fee": fee, "net": net, "user": str(message.author), "time": now_str})
        bal["history"] = bal["history"][-100:]
        save_balance_data(bal)
        embed = discord.Embed(title="💰  Nạp Tiền", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="💵  Số tiền nhận",   value=f"**{fmt_vnd(raw)}**",            inline=True)
        embed.add_field(name="📉  Phí 5%",         value=f"- {fmt_vnd(fee)}",              inline=True)
        embed.add_field(name="✅  Thực nhận",       value=f"**{fmt_vnd(net)}**",            inline=True)
        embed.add_field(name="🏦  Số dư hiện tại", value=f"**{fmt_vnd(bal['current'])}**", inline=False)
        embed.set_footer(text=f"Bởi {_uname_plain(message.author)}  •  {now_str}")
    else:
        bal["current"]   -= raw
        bal["total_out"] += raw
        bal["tx_count"]  += 1
        bal["history"].append({"type": "-", "raw": raw, "fee": 0, "net": raw, "user": str(message.author), "time": now_str})
        bal["history"] = bal["history"][-100:]
        save_balance_data(bal)
        color = 0xED4245 if bal["current"] >= 0 else 0x9B59B6
        embed = discord.Embed(title="💸  Chi Tiền", color=color, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="💵  Số tiền chi",   value=f"**{fmt_vnd(raw)}**",                                                                          inline=True)
        embed.add_field(name="🏦  Số dư còn lại", value=f"**{fmt_vnd(bal['current'])}**" + (" ⚠️" if bal["current"] < 0 else ""), inline=True)
        embed.set_footer(text=f"Bởi {_uname_plain(message.author)}  •  {now_str}")

    try:
        await message.delete()
    except:
        pass
    await message.channel.send(embed=embed)

    # LOG
    event_type = "BALANCE_IN" if op == "+" else "BALANCE_OUT"
    bot_client = message._state._get_client()
    await send_log(
        bot_client,
        event_type,
        f"{'Nạp' if op == '+' else 'Chi'} Tiền — Balance",
        fields=[
            ("💵 Số tiền",       fmt_vnd(raw),           True),
            ("🏦 Số dư còn lại", fmt_vnd(bal["current"]), True),
            ("👤 Bởi",           str(message.author),     True),
        ],
        user=message.author,
    )


class BuyerSpendingView(View):
    def __init__(self, entries: list, requester: discord.Member):
        super().__init__(timeout=120)
        self.entries   = entries
        self.requester = requester
        self.page      = 0
        self.per_page  = 15

    def _build_embed(self) -> discord.Embed:
        total_pages = max(1, -(-len(self.entries) // self.per_page))
        start = self.page * self.per_page
        chunk = self.entries[start: start + self.per_page]
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (member, uid, spent) in enumerate(chunk):
            rank = start + i
            icon = medals[rank] if rank < 3 else f"`{rank+1}.`"
            name = _uname(member) if member else f"<@{uid}>"
            lines.append(f"{icon} **{name}** — {fmt_vnd(spent)}")
        grand_total = sum(s for _, _, s in self.entries)
        embed = discord.Embed(title="👥 Danh Sách Buyer — Tổng Chi Tiêu", description="\n".join(lines) or "Chưa có dữ liệu.", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="💰 Tổng doanh thu", value=f"**{fmt_vnd(grand_total)}**",      inline=True)
        embed.add_field(name="👤 Số buyer",       value=f"**{len(self.entries)}** người",   inline=True)
        embed.set_footer(text=f"Trang {self.page+1}/{total_pages}  •  Yêu cầu bởi {_uname_plain(self.requester)}")
        return embed

    def _update_buttons(self):
        total_pages = max(1, -(-len(self.entries) // self.per_page))
        self.btn_prev.disabled = self.page <= 0
        self.btn_next.disabled = self.page >= total_pages - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.grey)
    async def btn_prev(self, interaction: discord.Interaction, button: Button):
        self.page -= 1; self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.grey)
    async def btn_next(self, interaction: discord.Interaction, button: Button):
        self.page += 1; self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


class BalanceView(View):
    def __init__(self, guild: discord.Guild, requester: discord.Member):
        super().__init__(timeout=120)
        self.guild     = guild
        self.requester = requester

    @discord.ui.button(label="👥 Xem Buyer", style=discord.ButtonStyle.blurple)
    async def show_buyers(self, interaction: discord.Interaction, button: Button):
        data = load_data()
        raw  = data.get("user_total_spent", {})
        if not raw:
            return await interaction.response.send_message("❌ Chưa có dữ liệu buyer nào.", ephemeral=True)
        entries = []
        for uid_str, spent in raw.items():
            if spent <= 0: continue
            uid    = int(uid_str)
            member = self.guild.get_member(uid)
            entries.append((member, uid, spent))
        entries.sort(key=lambda x: x[2], reverse=True)
        if not entries:
            return await interaction.response.send_message("❌ Chưa có dữ liệu buyer nào.", ephemeral=True)
        view = BuyerSpendingView(entries, self.requester)
        view._update_buttons()
        await interaction.response.send_message(embed=view._build_embed(), view=view)


class BalanceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="balance", aliases=["bal", "b"])
    async def balance_cmd(self, ctx):
        bal        = get_balance_data()
        ch_id      = get_cfg_balance_channel()
        ch_mention = f"<#{ch_id}>" if ch_id else "Chưa cài"
        embed = discord.Embed(title="📊  Thống Kê Số Dư", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏦  Số dư hiện tại", value=f"**{fmt_vnd(bal['current'])}**", inline=False)
        embed.add_field(name="📥  Tổng nạp",       value=fmt_vnd(bal['total_in']),         inline=True)
        embed.add_field(name="📤  Tổng chi",       value=fmt_vnd(bal['total_out']),        inline=True)
        embed.add_field(name="📉  Tổng phí 5%",    value=fmt_vnd(bal['total_fee']),        inline=True)
        embed.add_field(name="🔢  Tổng giao dịch", value=f"**{bal['tx_count']}** lần",    inline=True)
        embed.add_field(name="📌  Kênh balance",   value=ch_mention,                       inline=True)
        history = bal.get("history", [])
        if history:
            last5 = history[-5:][::-1]
            lines = [f"{'📥' if tx['type']=='+' else '📤'} **{fmt_vnd(tx['net'])}** — {tx['user']} — {tx['time']}" for tx in last5]
            embed.add_field(name="🕐  5 giao dịch gần nhất", value="\n".join(lines), inline=False)
        embed.set_footer(text="TuyTam Store  •  Nhấn nút bên dưới để xem danh sách buyer")
        await ctx.reply(embed=embed, view=BalanceView(ctx.guild, ctx.author))

    @commands.command(name="balreset")
    async def balreset_cmd(self, ctx):
        if not can_use_dangerous_cmd(ctx.author.id, "balreset"):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        data = load_data()
        data["balance"] = {"current":0,"total_in":0,"total_fee":0,"total_out":0,"tx_count":0,"history":[]}
        save_data(data)
        await ctx.reply("✅ Đã reset toàn bộ số dư về 0.")
        await send_log(self.bot, "BALANCE_RESET", "Reset Số Dư",
            fields=[("👤 Bởi", ctx.author.mention, True)], user=ctx.author)

    @commands.command(name="balset")
    async def balset_cmd(self, ctx, *, amount: str = None):
        if not can_use_dangerous_cmd(ctx.author.id, "balset"):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if amount is None:
            return await ctx.reply("❌ Dùng: `.balset <số tiền>`")
        raw_str  = amount.strip().replace(".", "").replace(",", "").replace(" ", "")
        negative = raw_str.startswith("-")
        raw_str  = raw_str.lstrip("-+")
        if not raw_str.isdigit():
            return await ctx.reply("❌ Số tiền không hợp lệ!")
        new_balance = int(raw_str) * (-1 if negative else 1)
        bal = get_balance_data()
        old = bal["current"]
        bal["current"] = new_balance
        now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        bal["history"].append({"type": "set", "raw": new_balance, "fee": 0, "net": new_balance, "user": str(ctx.author), "time": now_str})
        bal["history"] = bal["history"][-100:]
        save_balance_data(bal)
        embed = discord.Embed(title="⚙️  Đã Đặt Số Dư", color=0x57F287 if new_balance >= 0 else 0x9B59B6, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="📊  Số dư cũ",  value=fmt_vnd(old),                  inline=True)
        embed.add_field(name="✅  Số dư mới", value=f"**{fmt_vnd(new_balance)}**",  inline=True)
        embed.set_footer(text=f"Đặt bởi {ctx.author}")
        await ctx.reply(embed=embed)
        await send_log(self.bot, "BALANCE_SET", "Đặt Số Dư Thủ Công",
            fields=[
                ("📊 Số dư cũ",  fmt_vnd(old),         True),
                ("✅ Số dư mới", fmt_vnd(new_balance),  True),
                ("👤 Bởi",       ctx.author.mention,    True),
            ], user=ctx.author)

    # ── SLASH COMMANDS ──
    @discord.app_commands.command(name="balance", description="Xem thống kê số dư quỹ")
    async def slash_balance(self, interaction: discord.Interaction):
        bal        = get_balance_data()
        ch_id      = get_cfg_balance_channel()
        ch_mention = f"<#{ch_id}>" if ch_id else "Chưa cài"
        embed = discord.Embed(title="📊  Thống Kê Số Dư", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏦  Số dư hiện tại", value=f"**{fmt_vnd(bal['current'])}**", inline=False)
        embed.add_field(name="📥  Tổng nạp",       value=fmt_vnd(bal['total_in']),         inline=True)
        embed.add_field(name="📤  Tổng chi",       value=fmt_vnd(bal['total_out']),        inline=True)
        embed.add_field(name="📉  Tổng phí 5%",    value=fmt_vnd(bal['total_fee']),        inline=True)
        embed.add_field(name="🔢  Tổng giao dịch", value=f"**{bal['tx_count']}** lần",    inline=True)
        embed.add_field(name="📌  Kênh balance",   value=ch_mention,                       inline=True)
        history = bal.get("history", [])
        if history:
            last5 = history[-5:][::-1]
            lines = [f"{'📥' if tx['type']=='+' else '📤'} **{fmt_vnd(tx['net'])}** — {tx['user']} — {tx['time']}" for tx in last5]
            embed.add_field(name="🕐  5 giao dịch gần nhất", value="\n".join(lines), inline=False)
        embed.set_footer(text="TuyTam Store  •  Nhấn nút bên dưới để xem buyer")
        await interaction.response.send_message(embed=embed, view=BalanceView(interaction.guild, interaction.user))

    @discord.app_commands.command(name="balset", description="Đặt số dư quỹ thủ công (admin)")
    @discord.app_commands.describe(amount="Số tiền mới, vd: 5000000 hoặc -100000")
    async def slash_balset(self, interaction: discord.Interaction, amount: str):
        if not can_use_dangerous_cmd(interaction.user.id, "balset"):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        raw_str  = amount.strip().replace(".", "").replace(",", "").replace(" ", "")
        negative = raw_str.startswith("-")
        raw_str  = raw_str.lstrip("-+")
        if not raw_str.isdigit():
            return await interaction.response.send_message("❌ Số tiền không hợp lệ!", ephemeral=True)
        new_balance = int(raw_str) * (-1 if negative else 1)
        bal = get_balance_data()
        old = bal["current"]
        bal["current"] = new_balance
        now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        bal["history"].append({"type": "set", "raw": new_balance, "fee": 0, "net": new_balance, "user": str(interaction.user), "time": now_str})
        bal["history"] = bal["history"][-100:]
        save_balance_data(bal)
        embed = discord.Embed(title="⚙️  Đã Đặt Số Dư", color=0x57F287 if new_balance >= 0 else 0x9B59B6)
        embed.add_field(name="📊 Cũ",  value=fmt_vnd(old),         inline=True)
        embed.add_field(name="✅ Mới", value=fmt_vnd(new_balance),  inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await send_log(self.bot, "BALANCE_SET", "Đặt Số Dư Thủ Công",
            fields=[("📊 Cũ", fmt_vnd(old), True), ("✅ Mới", fmt_vnd(new_balance), True), ("👤 Bởi", interaction.user.mention, True)],
            user=interaction.user)

    @discord.app_commands.command(name="balreset", description="Reset toàn bộ số dư về 0 (admin)")
    async def slash_balreset(self, interaction: discord.Interaction):
        if not can_use_dangerous_cmd(interaction.user.id, "balreset"):
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        data = load_data()
        data["balance"] = {"current":0,"total_in":0,"total_fee":0,"total_out":0,"tx_count":0,"history":[]}
        save_data(data)
        await interaction.response.send_message("✅ Đã reset toàn bộ số dư về 0.", ephemeral=True)
        await send_log(self.bot, "BALANCE_RESET", "Reset Số Dư",
            fields=[("👤 Bởi", interaction.user.mention, True)], user=interaction.user)


async def setup(bot):
    await bot.add_cog(BalanceCog(bot))
