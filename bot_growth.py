"""
bot_growth.py — Entry point RIÊNG cho Growth Bot (Phase 2, bot con thứ 3 sau AI/Ticket).

Cùng repo, cùng cogs/core/shared với bot.py chính (xem docstring bot_ai.py để biết vì
sao không tách thư mục riêng). Chỉ khác:
  - Token riêng (biến env TOKEN_GROWTH)
  - CHỈ load 1 cog: cogs.giveaway — CHƯA load cogs.invite (xem lý do bên dưới)
  - Resume GiveawayView + gw_cog.resume_active_giveaways() lúc on_ready (đây là domain
    CỦA RIÊNG Growth — KHÔNG resume TicketPanel/MiddlemanPanelView/resume_pending_sold_views,
    mấy cái đó thuộc bot Ticket/Shop, tự resume trong entry point của chính chúng)

⚠️ cogs.invite CHƯA được load ở đây, khác với roadmap gốc "Growth = giveaway.py +
invite.py": code invite.py trong repo hiện tại vẫn import verify_server (create_token/
VERIFY_CALLBACKS) cho lệnh `.verify` — dict VERIFY_CALLBACKS chỉ tồn tại thật trong
process đang chạy start_verify_server() (hiện là bot.py). Nếu load cogs.invite ở process
KHÁC (bot_growth.py) mà verify_server vẫn chỉ chạy trong bot.py, `.verify` sẽ LUÔN báo
"Link không hợp lệ" — cùng loại lỗi mà PAYMENT_CALLBACK/shop_orders.py đã né bằng cách
bắt buộc chạy chung process với verify_server.py. Xem tin nhắn chat đi kèm bản này để
biết các phương án xử lý trước khi thêm cogs.invite vào COGS_GROWTH bên dưới.

Deploy: Railway service riêng, Root Directory = gốc repo (giống bot.py/bot_ai.py/
bot_ticket.py), Start Command = `python bot_growth.py`, biến env TOKEN_GROWTH +
MONGO_URI/ADMIN_*/... y hệt bot.py (dùng CHUNG 1 MongoDB).
"""

import os
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

TOKEN_GROWTH = os.getenv("TOKEN_GROWTH")
if not TOKEN_GROWTH:
    raise RuntimeError("❌ Thiếu biến môi trường TOKEN_GROWTH! (token RIÊNG cho Growth bot, "
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
    print(f"[BOT_GROWTH] ✅ Đã tham gia guild mới: {guild.name} ({guild.id})")
    await notify_admins_unauthorized_guild(bot, guild)


COGS_GROWTH = [
    "cogs.giveaway",
]

async def load_cogs():
    for cog in COGS_GROWTH:
        try:
            await bot.load_extension(cog)
            print(f"[COG] ✅ Loaded: {cog}")
        except Exception as e:
            print(f"[COG] ❌ Failed {cog}: {e}")


_on_ready_first_boot_done = False

@bot.event
async def on_ready():
    """Bản RÚT GỌN của on_ready() bên bot.py chính — chỉ giữ phần thuộc domain Growth
    (giveaway). KHÔNG resume ticket/sold-views/legit — domain của bot khác. Giữ nguyên
    lý do CHỈ resume 1 lần (if first_boot) từ bot.py: resume_active_giveaways() tạo
    THÊM task đếm giờ mỗi lần gọi, gọi lại lúc reconnect sẽ ra 2 task cho cùng 1
    giveaway → end_giveaway() có thể chạy 2 lần."""
    global _on_ready_first_boot_done
    from shared.data import init_data_cache
    from cogs.giveaway import GiveawayView

    await init_data_cache(bot)

    first_boot = not _on_ready_first_boot_done
    _on_ready_first_boot_done = True

    if first_boot:
        # Resume giveaways — không cần guild context, giveaway tách theo message_id
        # (collection riêng, xem core/data.py), KHÔNG thuộc guild nào trong cache.
        gw_cog = bot.cogs.get("GiveawayCog")
        if gw_cog:
            await gw_cog.resume_active_giveaways()

        bot.add_view(GiveawayView())

        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands (bot_growth)")
        except Exception as e:
            print(f"❌ Slash sync error: {e}")

    print(f"✅ Bot Growth online: {bot.user} | {len(bot.guilds)} server(s)" + ("" if first_boot else " (reconnect)"))


async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN_GROWTH)

if __name__ == "__main__":
    asyncio.run(main())
