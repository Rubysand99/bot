"""
bot_ticket.py — Entry point RIÊNG cho Ticket Bot (Phase 2, bot con thứ 2 sau AI).

Cùng repo, cùng cogs/core/shared với bot.py chính (xem docstring bot_ai.py để biết vì
sao không tách thư mục riêng). Chỉ khác:
  - Token riêng (biến env TOKEN_TICKET)
  - Load 2 cog: cogs.ticket, cogs.legit (Legit/Vouch — tách từ bot.py, xem cogs/legit.py)
  - Resume TicketPanel/TicketButtons/MiddlemanPanelView + sync_ticket_counter lúc on_ready
    (đây là domain CỦA RIÊNG Ticket — KHÔNG resume GiveawayView/resume_pending_sold_views,
    2 cái đó thuộc bot Growth/Shop, sẽ tự resume trong entry point của chính chúng)

Deploy: process/service riêng (VPS: 1 service systemd riêng, chạy từ gốc repo như bot.py/bot_ai.py),
Start Command = `python bot_ticket.py`, biến env TOKEN_TICKET + MONGO_URI/ADMIN_*/... y
hệt bot.py (dùng CHUNG 1 MongoDB).
"""

import os
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

TOKEN_TICKET = os.getenv("TOKEN_TICKET")
if not TOKEN_TICKET:
    raise RuntimeError("❌ Thiếu biến môi trường TOKEN_TICKET! (token RIÊNG cho Ticket bot, "
                        "KHÁC với TOKEN của bot chính — tạo Discord Application mới)")

intents = discord.Intents.all()

from shared.auth_gate import (
    GuildContextTree, get_prefix, set_guild_context_prefix,
    global_guild_authorization_check, notify_admins_unauthorized_guild,
)
from shared.data import ensure_guild_loaded, set_current_guild

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None, tree_cls=GuildContextTree)
bot.before_invoke(set_guild_context_prefix)
bot.check(global_guild_authorization_check)


@bot.event
async def on_guild_join(guild: discord.Guild):
    await ensure_guild_loaded(guild.id)
    set_current_guild(guild.id)
    print(f"[BOT_TICKET] ✅ Đã tham gia guild mới: {guild.name} ({guild.id})")
    await notify_admins_unauthorized_guild(bot, guild)


COGS_TICKET = [
    "cogs.ticket",
    "cogs.legit",
]

async def load_cogs():
    for cog in COGS_TICKET:
        try:
            await bot.load_extension(cog)
            print(f"[COG] ✅ Loaded: {cog}")
        except Exception as e:
            print(f"[COG] ❌ Failed {cog}: {e}")


_on_ready_first_boot_done = False

@bot.event
async def on_ready():
    """Bản RÚT GỌN của on_ready() bên bot.py chính — chỉ giữ phần thuộc domain Ticket.
    Resume legit/vouch rename queue đã tự chạy trong cogs/legit.py's on_ready riêng,
    KHÔNG lặp lại ở đây."""
    global _on_ready_first_boot_done
    from shared.data import init_data_cache
    from cogs.ticket import TicketPanel, TicketButtons, MiddlemanPanelView, sync_ticket_counter

    await init_data_cache(bot)

    first_boot = not _on_ready_first_boot_done
    _on_ready_first_boot_done = True

    if first_boot:
        bot.add_view(TicketPanel())
        bot.add_view(TicketButtons())
        bot.add_view(MiddlemanPanelView())

    # CỐ Ý chạy mỗi lần refire (không chỉ first_boot) — ticket counter chỉ tăng chứ
    # không giảm nên gọi lại vô hại, giống lý do ở bot.py gốc.
    for guild in bot.guilds:
        set_current_guild(guild.id)
        await sync_ticket_counter(bot, guild)

    if first_boot:
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands (bot_ticket)")
        except Exception as e:
            print(f"❌ Slash sync error: {e}")

    print(f"✅ Bot Ticket online: {bot.user} | {len(bot.guilds)} server(s)" + ("" if first_boot else " (reconnect)"))


async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN_TICKET)

if __name__ == "__main__":
    asyncio.run(main())
