# cogs/balance.py — .balance .balreset .balset
from config import *

class BuyerSpendingView(View):
    """View hiển thị danh sách buyer + số tiền đã tiêu, phân trang."""
    def __init__(self, entries: list, requester: discord.Member):
        super().__init__(timeout=120)
        self.entries   = entries   # list of (member_or_none, user_id, total_spent)
        self.requester = requester
        self.page      = 0
        self.per_page  = 15

    def _build_embed(self) -> discord.Embed:
        total_pages = max(1, -(-len(self.entries) // self.per_page))
        start = self.page * self.per_page
        chunk = self.entries[start : start + self.per_page]

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (member, uid, spent) in enumerate(chunk):
            rank   = start + i
            icon   = medals[rank] if rank < 3 else f"`{rank+1}.`"
            name   = _uname(member) if member else f"<@{uid}>"
            lines.append(f"{icon} **{name}** — {fmt_vnd(spent)}")

        grand_total = sum(s for _, _, s in self.entries)
        embed = discord.Embed(
            title=f"👥 Danh Sách Buyer — Tổng Chi Tiêu",
            description="\n".join(lines) or "Chưa có dữ liệu.",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="💰 Tổng doanh thu",  value=f"**{fmt_vnd(grand_total)}**", inline=True)
        embed.add_field(name="👤 Số buyer",        value=f"**{len(self.entries)}** người", inline=True)
        embed.set_footer(
            text=f"Trang {self.page+1}/{total_pages}  •  Yêu cầu bởi {_uname_plain(self.requester)}"
        )
        return embed

    def _update_buttons(self):
        total_pages = max(1, -(-len(self.entries) // self.per_page))
        self.btn_prev.disabled = self.page <= 0
        self.btn_next.disabled = self.page >= total_pages - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.grey)
    async def btn_prev(self, interaction: discord.Interaction, button: Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.grey)
    async def btn_next(self, interaction: discord.Interaction, button: Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

class BalanceView(View):
    """View đính kèm embed .balance — nút xem danh sách buyer."""
    def __init__(self, guild: discord.Guild, requester: discord.Member):
        super().__init__(timeout=120)
        self.guild     = guild
        self.requester = requester

    @discord.ui.button(label="👥 Xem Buyer", style=discord.ButtonStyle.blurple)
    async def show_buyers(self, interaction: discord.Interaction, button: Button):
        data = load_data()
        raw = data.get("user_total_spent", {})
        if not raw:
            return await interaction.response.send_message("❌ Chưa có dữ liệu buyer nào.", ephemeral=True)

        entries = []
        for uid_str, spent in raw.items():
            if spent <= 0:
                continue
            uid    = int(uid_str)
            member = self.guild.get_member(uid)
            entries.append((member, uid, spent))
        entries.sort(key=lambda x: x[2], reverse=True)

        if not entries:
            return await interaction.response.send_message("❌ Chưa có dữ liệu buyer nào.", ephemeral=True)

        view = BuyerSpendingView(entries, self.requester)
        view._update_buttons()
        await interaction.response.send_message(embed=view._build_embed(), view=view, ephemeral=True)

@bot.command(name="balance", aliases=["bal"])
async def balance_cmd(ctx):
    bal = get_balance_data()
    ch_id = get_cfg_balance_channel()
    ch_mention = f"<#{ch_id}>" if ch_id else "Chưa cài"

    embed = discord.Embed(
        title="📊  Thống Kê Số Dư",
        color=0x5865F2,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏦  Số dư hiện tại",  value=f"**{fmt_vnd(bal['current'])}**",   inline=False)
    embed.add_field(name="📥  Tổng nạp",        value=fmt_vnd(bal['total_in']),            inline=True)
    embed.add_field(name="📤  Tổng chi",        value=fmt_vnd(bal['total_out']),           inline=True)
    embed.add_field(name="📉  Tổng phí 5%",     value=fmt_vnd(bal['total_fee']),           inline=True)
    embed.add_field(name="🔢  Tổng giao dịch",  value=f"**{bal['tx_count']}** lần",       inline=True)
    embed.add_field(name="📌  Kênh balance",     value=ch_mention,                          inline=True)

    history = bal.get("history", [])
    if history:
        last5 = history[-5:][::-1]
        lines = []
        for tx in last5:
            icon = "📥" if tx["type"] == "+" else "📤"
            lines.append(f"{icon} **{fmt_vnd(tx['net'])}** — {tx['user']} — {tx['time']}")
        embed.add_field(name="🕐  5 giao dịch gần nhất", value="\n".join(lines), inline=False)

    embed.set_footer(text="TuyTam Store  •  Nhấn nút bên dưới để xem danh sách buyer")
    await ctx.reply(embed=embed, view=BalanceView(ctx.guild, ctx.author))

@bot.command(name="balreset")
async def balreset_cmd(ctx):
    if not can_use_dangerous_cmd(ctx.author.id, "balreset"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    data = load_data()
    data["balance"] = {
        "current": 0, "total_in": 0, "total_fee": 0,
        "total_out": 0, "tx_count": 0, "history": []
    }
    save_data(data)
    await ctx.reply("✅ Đã reset toàn bộ số dư về 0.")

@bot.command(name="balset")
async def balset_cmd(ctx, *, amount: str = None):
    if not can_use_dangerous_cmd(ctx.author.id, "balset"):
        return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
    if amount is None:
        return await ctx.reply("❌ Dùng: `.balset <số tiền>`\nVí dụ: `.balset 1500000` hoặc `.balset -200000`")

    raw_str = amount.strip().replace(".", "").replace(",", "").replace(" ", "")
    negative = raw_str.startswith("-")
    raw_str = raw_str.lstrip("-+")
    if not raw_str.isdigit():
        return await ctx.reply("❌ Số tiền không hợp lệ!")

    new_balance = int(raw_str) * (-1 if negative else 1)
    bal = get_balance_data()
    old_balance = bal["current"]
    bal["current"] = new_balance
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    bal["history"].append({
        "type": "set", "raw": new_balance, "fee": 0, "net": new_balance,
        "user": str(ctx.author), "time": now_str
    })
    bal["history"] = bal["history"][-100:]
    save_balance_data(bal)

    color = 0x57F287 if new_balance >= 0 else 0x9B59B6
    embed = discord.Embed(
        title="⚙️  Đã Đặt Số Dư",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="📊  Số dư cũ",    value=fmt_vnd(old_balance),  inline=True)
    embed.add_field(name="✅  Số dư mới",   value=f"**{fmt_vnd(new_balance)}**", inline=True)
    embed.set_footer(text=f"Đặt bởi {ctx.author}")
    await ctx.reply(embed=embed)

# ================= AI CHAT (Groq) =================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Model theo thứ tự ưu tiên — tự động fallback khi hết quota
# llama-3.1-8b-instant: 500k TPD (nhẹ, nhanh, đủ dùng cho chat bot)
# llama-3.3-70b-versatile: 100k TPD (mạnh hơn, dùng khi cần)
# gemma2-9b-it: 500k TPD (backup)
GROQ_MODELS = [
    "llama-3.1-8b-instant",      # primary — 500k token/ngày
    "llama-3.3-70b-versatile",   # fallback 1 — 100k token/ngày
    "gemma2-9b-it",              # fallback 2 — 500k token/ngày
]
GROQ_SYSTEM  = (
    "Bạn là trợ lý AI của TuyTam Store — một cửa hàng game. "
    "Hãy trả lời ngắn gọn, thân thiện, bằng tiếng Việt. "
    "Nếu không biết thông tin cụ thể về cửa hàng, hãy hướng dẫn user mở ticket để được hỗ trợ."
)

async def _call_groq(user_id: int, user_message: str) -> str:
    if not GROQ_API_KEY:
        return "❌ Chưa cài `GROQ_API_KEY` trong biến môi trường."

    history = _ai_chat_history.setdefault(user_id, [])
    history.append({"role": "user", "content": user_message})
    if len(history) > AI_HISTORY_LIMIT * 2:
        _ai_chat_history[user_id] = history[-(AI_HISTORY_LIMIT * 2):]
        history = _ai_chat_history[user_id]

    messages = [{"role": "system", "content": GROQ_SYSTEM}] + history

    import aiohttp as _aiohttp_ai
    last_err = "Unknown error"

    for model in GROQ_MODELS:
        try:
            async with _aiohttp_ai.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 1024,
                        "temperature": 0.7,
                    },
                    timeout=_aiohttp_ai.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        print(f"[AI] ⚠️ Model {model} hết quota, thử model tiếp...")
                        last_err = f"Model `{model}` hết quota"
                        continue
                    if resp.status != 200:
                        err = await resp.text()
                        print(f"[AI] ❌ Groq lỗi {resp.status} ({model}): {err[:150]}")
                        last_err = f"Lỗi {resp.status}"
                        continue
                    data = await resp.json()
                    reply = data["choices"][0]["message"]["content"]

            _ai_chat_history[user_id].append({"role": "assistant", "content": reply})
            return reply

        except Exception as e:
            print(f"[AI] ❌ Exception ({model}): {e}")
            last_err = str(e)
            continue

    return f"⚠️ AI tạm thời không khả dụng ({last_err}). Vui lòng thử lại sau ít phút."

async def handle_ai_message(message: discord.Message):
    ai_ch_id = get_cfg_ai_channel()
    if not ai_ch_id or message.channel.id != ai_ch_id:
        return

    async with message.channel.typing():
        reply = await _call_groq(message.author.id, message.content)

    if len(reply) <= 2000:
        await message.reply(reply, mention_author=False)
    else:
        chunks = [reply[i:i+1990] for i in range(0, len(reply), 1990)]
        for chunk in chunks:
            await message.channel.send(chunk)


