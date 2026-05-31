"""
bot.py — Entry point của RUDEUS BOT v3.4.0
Chỉ chứa: khởi tạo bot, load cogs, on_ready, on_message.
Mọi logic đều nằm trong cogs/ và core/.
"""

import os
import re as _re
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv
from core.data import BOT_VERSION, BOT_UPDATED, get_cfg_balance_channel
from cogs.admin import handle_sold
from cogs.ai_chat import handle_ai_message
from cogs.balance import handle_balance_message

CHANGELOG_CHANNEL_ID    = 1486967511839801414
CODE_GEN_LOG_CHANNEL_ID = 1504434579967316021  # Kênh log khi user bypass link & tạo mã

if os.path.exists(".env"):
    load_dotenv()

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Thiếu biến môi trường TOKEN!")

intents = discord.Intents.all()
bot     = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ══════════════════════════════════════════
# LOAD COGS
# ══════════════════════════════════════════
COGS = [
    "cogs.logger",
    "cogs.ticket",
    "cogs.balance",
    "cogs.ai_chat",
    "cogs.invite",
    "cogs.giveaway",
    "cogs.admin",
    "cogs.mod",

    "cogs.banking",
]

async def load_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"[COG] ✅ Loaded: {cog}")
        except Exception as e:
            print(f"[COG] ❌ Failed {cog}: {e}")

# ══════════════════════════════════════════
# ON READY
# ══════════════════════════════════════════
@bot.event
async def on_ready():
    from core.data import init_data_cache
    from cogs.ticket import TicketPanel, TicketButtons, sync_ticket_counter
    from cogs.giveaway import GiveawayView, GiveawayCog

    await init_data_cache()

    # Resume giveaways
    gw_cog = bot.cogs.get("GiveawayCog")
    if gw_cog:
        await gw_cog.resume_active_giveaways()

    # Register persistent views
    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    bot.add_view(GiveawayView())

    # Sync invite cache & ticket counter
    from cogs.invite import cache_invites
    for guild in bot.guilds:
        await cache_invites(guild)
        await sync_ticket_counter(bot, guild)

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")

    print(f"✅ Bot online: {bot.user} | {len(bot.guilds)} server(s)")

    # Quét lại legit channel — thả ✅ cho tin nhắn bị bỏ sót lúc bot offline
    asyncio.create_task(_backfill_legit())

    # Gửi changelog — đọc từ CHANGELOG.md
    from core.data import get_or_fetch_channel
    ch = await get_or_fetch_channel(bot, CHANGELOG_CHANNEL_ID)
    if ch:
        embed = discord.Embed(
            title=f"🔄 Bot Khởi Động — v{BOT_VERSION}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        try:
            with open("CHANGELOG.md", "r", encoding="utf-8") as f:
                content = f.read()
            import re
            # Lấy block entry mới nhất (từ ## đầu đến ## tiếp theo)
            blocks = re.split(r"\n(?=## \[)", content)
            latest = next((b for b in blocks if b.strip().startswith("##")), "")

            if latest:
                lines = latest.strip().splitlines()
                # Dòng đầu: ## [v3.9.4] — 2026-05-23  → bỏ vào title embed
                header = lines[0].lstrip("#").strip()
                embed.title = f"🔄 Bot Khởi Động — {header}"

                # Parse từng section ### thành field
                current_section = None
                current_lines   = []

                def flush(sec, lns, emb):
                    if sec and lns:
                        val = "\n".join(lns)[:1020]
                        emb.add_field(name=sec, value=val, inline=False)

                for line in lines[1:]:
                    if line.startswith("### "):
                        flush(current_section, current_lines, embed)
                        current_section = line.lstrip("#").strip()
                        current_lines   = []
                    elif line.startswith("- ") or line.startswith("  - "):
                        # Giữ bullet, bỏ markdown backtick path nếu quá dài
                        current_lines.append(line)
                    elif line.strip() == "---":
                        break
                    elif line.strip():
                        current_lines.append(line)

                flush(current_section, current_lines, embed)

                # Nếu không có section nào (entry không có ###)
                if not any(True for f in embed.fields):
                    body = "\n".join(lines[1:]).strip()[:1500]
                    embed.description = body if body else None

        except Exception as e:
            embed.description = f"Bot đã khởi động lại — **v{BOT_VERSION}** ({BOT_UPDATED})\n`{e}`"

        embed.add_field(name="✅ Cogs đã load", value="\n".join(f"› `{c}`" for c in COGS), inline=False)
        embed.add_field(name="⚡ Latency",       value=f"{round(bot.latency*1000)}ms",        inline=True)
        embed.set_footer(text="TuyTam Store  •  Dùng .help để xem tất cả lệnh")
        try:
            await ch.send(embed=embed)
        except Exception as e:
            print(f"[CHANGELOG] ❌ {e}")

# ══════════════════════════════════════════
# ON MESSAGE
# ══════════════════════════════════════════
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    # Auto sold — stock → sold category
    await handle_sold(bot, message)

    # AI channel
    await handle_ai_message(message)

    # Balance channel
    bal_ch = get_cfg_balance_channel()
    if bal_ch and message.channel.id == bal_ch:
        await handle_balance_message(message)

    # Legit & Vouch
    await _handle_legit(message)
    await _handle_vouch(message)


# ══════════════════════════════════════════
# LEGIT / VOUCH HANDLERS
# ══════════════════════════════════════════

async def _handle_legit(message: discord.Message):
    from core.data import get_cfg_legit_channel
    IGNORED = {628400349979344919}
    if message.author.id in IGNORED: return
    legit_ch = get_cfg_legit_channel()
    if legit_ch:
        if message.channel.id != legit_ch: return
    else:
        if "legit" not in message.channel.name.lower(): return
    if not _re.match(r"^\+1\s*legit\b", message.content.strip(), _re.IGNORECASE): return
    ch      = message.channel
    name    = ch.name
    match   = _re.search(r"-(\d+)$", name)
    new_num = (int(match.group(1)) + 1) if match else 1
    base    = name[:match.start()] if match else name
    try:
        await ch.edit(name=f"{base}-{new_num}", reason=f"+1 legit bởi {message.author}")
        await message.add_reaction("✅")
    except: pass

async def _handle_vouch(message: discord.Message):
    from core.data import get_cfg_proof_channel
    IGNORED = {628400349979344919}
    if message.author.id in IGNORED: return
    proof_ch = get_cfg_proof_channel()
    if not proof_ch or message.channel.id != proof_ch: return
    if not _re.match(r"^done\b", message.content.strip(), _re.IGNORECASE): return
    ch      = message.channel
    name    = ch.name
    match   = _re.search(r"-(\d+)$", name)
    new_num = (int(match.group(1)) + 1) if match else 1
    base    = name[:match.start()] if match else name
    try:
        await ch.edit(name=f"{base}-{new_num}", reason=f"+1 vouch bởi {message.author}")
        await message.add_reaction("✅")
    except: pass



# ══════════════════════════════════════════
# BACKFILL LEGIT — Quét lại lúc khởi động
# ══════════════════════════════════════════
BACKFILL_LIMIT = 25  # Số tin nhắn gần nhất cần quét

async def _backfill_legit():
    """Sau khi bot online, quét 25 tin nhắn gần nhất trong kênh legit.
    Tin nào khớp +1legit mà chưa có reaction ✅ từ bot → thả reaction và đổi tên kênh +1.
    Fetch lại tên kênh sau mỗi lần edit để tránh số đếm bị sai."""
    await asyncio.sleep(3)  # Chờ cache sẵn sàng
    from core.data import get_cfg_legit_channel, get_or_fetch_channel
    IGNORED = {628400349979344919}

    legit_ch_id = get_cfg_legit_channel()
    if not legit_ch_id:
        print("[BACKFILL] ⚠️ Chưa cài legit channel, bỏ qua.")
        return

    channel = await get_or_fetch_channel(bot, legit_ch_id)
    if not channel:
        print(f"[BACKFILL] ⚠️ Không tìm thấy channel {legit_ch_id}")
        return

    fixed = 0
    try:
        msgs = []
        async for msg in channel.history(limit=BACKFILL_LIMIT):
            msgs.append(msg)
        msgs.reverse()  # cũ → mới

        for msg in msgs:
            if msg.author.bot: continue
            if msg.author.id in IGNORED: continue
            if not _re.match(r"^\+1\s*legit\b", msg.content.strip(), _re.IGNORECASE): continue

            already = any(r.emoji == "✅" and r.me for r in msg.reactions)
            if not already:
                try:
                    await msg.add_reaction("✅")
                except Exception as e:
                    print(f"[BACKFILL] ❌ Không thả được reaction msg {msg.id}: {e}")
                # Đổi tên kênh +1, fetch lại channel để lấy tên mới nhất
                try:
                    channel = await channel.guild.fetch_channel(channel.id)  # refresh
                    name = channel.name
                    match = _re.search(r"-(\d+)$", name)
                    new_num = (int(match.group(1)) + 1) if match else 1
                    base = name[:match.start()] if match else name
                    await channel.edit(name=f"{base}-{new_num}", reason=f"+1 legit backfill bởi {msg.author}")
                    fixed += 1
                    print(f"[BACKFILL] ✅ {msg.id} — kênh đổi thành {base}-{new_num}")
                except Exception as e:
                    print(f"[BACKFILL] ❌ Không đổi được tên kênh: {e}")
    except Exception as e:
        print(f"[BACKFILL] ❌ Lỗi khi quét legit channel: {e}")
        return

    print(f"[BACKFILL] ✅ Hoàn tất — đã xử lý {fixed} tin nhắn bị bỏ sót.")


# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
