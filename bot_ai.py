"""
bot_ai.py — Entry point RIÊNG cho AI Bot (Phase 2, pilot tách bot).

Chạy CÙNG repo, CÙNG cogs/core/shared với bot.py (KHÔNG copy file) — chỉ khác:
  - Token riêng (biến env TOKEN_AI, KHÁC với TOKEN của bot chính)
  - Chỉ load 2 cog: cogs.ai_chat, cogs.message_search (không load ticket/mod/seller...)
  - KHÔNG chạy verify_server (webhook SePay) — vẫn là việc riêng của bot.py chính

Vì sao gọn vậy: core/ai_tools.py vẫn cần đọc cogs.seller/cogs.ticket/cogs.invite (câu hỏi
kiểu "tôi có đang là seller không") — các cog đó KHÔNG bị copy riêng cho bot_ai, mà đọc
thẳng từ cùng thư mục cogs/ dùng chung với bot.py. Nghĩa là bot_ai VẪN phụ thuộc vào code
(không phải RAM/process) của các cog khác — đây là lý do file này chạy từ GỐC repo (không
tách thư mục con riêng), không phải bot_ai đã độc lập hoàn toàn 100%. Ticket status dùng
has_open_ticket_db() (đọc qua Mongo) thay vì has_ticket() (cache RAM riêng của bot chính)
— 2 process đọc chung Mongo vẫn ra kết quả đúng dù chạy tách biệt.

Deploy: process/service riêng (VPS: 1 service systemd riêng, chạy từ gốc repo như bot.py), Start Command =
`python bot_ai.py`, biến env TOKEN_AI + toàn bộ biến MONGO_URI/ADMIN_*/GROQ_API_KEY/... y
hệt bot.py (dùng CHUNG 1 MongoDB).
"""

import os
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

BOT_AI_VERSION = "1.0.0"

TOKEN_AI = os.getenv("TOKEN_AI")
if not TOKEN_AI:
    raise RuntimeError("❌ Thiếu biến môi trường TOKEN_AI! (token RIÊNG cho AI bot, "
                        "KHÁC với TOKEN của bot chính — tạo Discord Application mới)")

intents = discord.Intents.all()

_background_tasks: set = set()

def spawn_background(coro) -> asyncio.Task:
    t = asyncio.create_task(coro)
    _background_tasks.add(t)
    t.add_done_callback(_background_tasks.discard)
    return t


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
    print(f"[BOT_AI] ✅ Đã tham gia guild mới: {guild.name} ({guild.id})")
    await notify_admins_unauthorized_guild(bot, guild)


COGS_AI = [
    "cogs.ai_chat",
    "cogs.message_search",
]

async def load_cogs():
    for cog in COGS_AI:
        try:
            await bot.load_extension(cog)
            print(f"[COG] ✅ Loaded: {cog}")
        except Exception as e:
            print(f"[COG] ❌ Failed {cog}: {e}")


_on_ready_first_boot_done = False

@bot.event
async def on_ready():
    """Bản RÚT GỌN của on_ready() bên bot.py chính — chỉ giữ phần thật sự cần cho AI bot
    (init cache, sync slash, check AI provider). Bỏ: resume ticket/giveaway/sold views,
    backfill legit, embed changelog — đều là domain của bot chính, không phải AI bot."""
    global _on_ready_first_boot_done
    from shared.data import init_data_cache

    await init_data_cache(bot)

    first_boot = not _on_ready_first_boot_done
    _on_ready_first_boot_done = True

    if first_boot:
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands (bot_ai)")
        except Exception as e:
            print(f"❌ Slash sync error: {e}")

        async def _print_ai_connection_status():
            from cogs.ai_chat import check_ai_connections
            print("🔌 Đang kiểm tra kết nối AI provider...")
            try:
                results = await check_ai_connections()
            except Exception as e:
                print(f"❌ Lỗi khi kiểm tra kết nối AI: {e}")
                return
            print("🔌 Trạng thái kết nối AI provider:")
            for label, (ok, detail) in results.items():
                icon = "✅" if ok else "❌"
                print(f"   {icon} {label:<8}: {detail}")
        spawn_background(_print_ai_connection_status())

    print(f"✅ Bot AI online: {bot.user} | {len(bot.guilds)} server(s)" + ("" if first_boot else " (reconnect)"))


async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN_AI)

if __name__ == "__main__":
    asyncio.run(main())
