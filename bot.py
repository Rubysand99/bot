"""
bot.py — Entry point của RUDEUS BOT v3.4.0
Chỉ chứa: khởi tạo bot, load cogs, on_ready, on_message.
Mọi logic đều nằm trong cogs/ và core/.
"""

import os
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

BOT_VERSION = "3.4.1"
BOT_UPDATED = "2026-05-15"
CHANGELOG_CHANNEL_ID = 1486967511839801414
CODE_GEN_LOG_CHANNEL_ID = 1504434579967316021  # Kênh log khi user bypass link & tạo mã

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
    "cogs.point",
    "cogs.minigame",
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

    # Gửi changelog — đọc từ CHANGELOG.md
    ch = bot.get_channel(CHANGELOG_CHANNEL_ID)
    if ch:
        # Đọc entry mới nhất từ CHANGELOG.md
        changelog_text = ""
        try:
            with open("CHANGELOG.md", "r", encoding="utf-8") as f:
                content = f.read()
            # Lấy block đầu tiên (từ ## đầu đến ## tiếp theo)
            import re
            blocks = re.split(r"\n(?=## \[)", content)
            latest = next((b for b in blocks if b.strip().startswith("##")), "")
            # Lấy tối đa 1500 ký tự
            changelog_text = latest.strip()[:1500]
        except Exception:
            changelog_text = f"Bot đã khởi động lại — **v{BOT_VERSION}** ({BOT_UPDATED})"

        embed = discord.Embed(
            title=f"🔄 Bot Khởi Động — v{BOT_VERSION}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
            description=f"```md\n{changelog_text}\n```" if changelog_text else f"v{BOT_VERSION} — {BOT_UPDATED}",
        )
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

    # AI channel
    from cogs.ai_chat import handle_ai_message
    await handle_ai_message(message)

    # Balance channel
    from core.data import get_cfg_balance_channel
    from cogs.balance import handle_balance_message
    bal_ch = get_cfg_balance_channel()
    if bal_ch and message.channel.id == bal_ch:
        await handle_balance_message(message)

    # Legit & Vouch
    await _handle_legit(message)
    await _handle_vouch(message)


# ══════════════════════════════════════════
# LEGIT / VOUCH HANDLERS
# ══════════════════════════════════════════
import re as _re

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
    if message.channel.id != get_cfg_proof_channel(): return
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
# MAIN
# ══════════════════════════════════════════
async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
