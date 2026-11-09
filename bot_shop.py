"""
bot_shop.py — Entry point RIÊNG cho Shop Bot (Phase 2, bot con thứ 4 sau AI/Ticket/Growth).

Cùng repo, cùng cogs/core/shared với bot.py chính. Chỉ khác:
  - Token riêng (biến env TOKEN_SHOP)
  - Load 6 cog: cogs.shop_admin, cogs.listings, cogs.shop_orders, cogs.leaderboard, cogs.seller, cogs.autobuy
  - Tự chạy verify_server.py (webhook SePay) trong process của MÌNH — ĐÚNG chỗ theo
    AI_CONTEXT.md gốc ("verify_server.py PHẢI thuộc Shop"). shop_orders.py gọi
    register_payment_callback() lúc cog_load() — callback đó CHỈ hoạt động nếu
    verify_server chạy CHUNG process, xem docstring đầu verify_server.py.
  - on_message RIÊNG chỉ gọi handle_sold() (domain Shop) — KHÔNG gọi handle_ai_message/
    legit/vouch, mấy cái đó thuộc bot AI/Ticket.
  - resume_pending_sold_views() lúc on_ready (1 lần/first_boot) — domain CỦA RIÊNG
    Shop, KHÔNG resume GiveawayView/TicketPanel, mấy cái đó thuộc bot Growth/Ticket.

⚠️ admin.py (cogs.admin, Core) vẫn `from cogs.shop_admin import ShopOrdersToggleButton,
ReceiptMessageButton` để hiển thị 2 nút đó trong `.st` — bot_shop.py KHÔNG load
cogs.admin nên KHÔNG có lệnh `.st`/`.as`/... (đúng ý định, `.st` là dashboard Core).

⚠️ Test cục bộ 2 bot cùng lúc (bot.py + bot_shop.py) trên CÙNG máy Termux: cả 2 cùng
cố bind PORT mặc định 8080 cho verify_server — cái chạy SAU sẽ bind lỗi, tự in cảnh
báo rồi BỎ QUA verify_server (không crash bot, xem verify_server.py: start_verify_server
catch OSError). Muốn test webhook SePay thật ở bot_shop.py cục bộ, đặt PORT khác trong
.env trước khi chạy, hoặc tắt bot.py lúc test.

⚠️ Y HỆT lưu ý đã đưa ra lúc tách Growth: bot.py hiện VẪN load cả cogs.shop_admin/
cogs.listings/cogs.shop_orders/cogs.seller (pilot, chưa cắt) — mời bot Shop (token
khác) vào SERVER THẬT lúc này sẽ khiến `.sold`/handle_sold()/webhook SePay bị xử lý
2 LẦN (2 bot, 2 process, cùng ghi vào 1 MongoDB). Test trên server riêng trước, xem
chi tiết bước "cutover thật" ở phần tách Growth.

Deploy: process/service riêng (VPS: 1 service systemd riêng, chạy từ gốc repo như bot.py), Start Command =
`python bot_shop.py`, biến env TOKEN_SHOP + MONGO_URI/ADMIN_*/SEPAY_WEBHOOK_API_KEY/
PORT/... y hệt bot.py (dùng CHUNG 1 MongoDB).
"""

import os
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

TOKEN_SHOP = os.getenv("TOKEN_SHOP")
if not TOKEN_SHOP:
    raise RuntimeError("❌ Thiếu biến môi trường TOKEN_SHOP! (token RIÊNG cho Shop bot, "
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

# Cùng lý do với spawn_background() trong bot.py — asyncio chỉ giữ weak reference tới
# Task, task nền (verify server) không ai giữ reference có thể bị GC giữa chừng.
_background_tasks: set = set()

def spawn_background(coro) -> asyncio.Task:
    t = asyncio.create_task(coro)
    _background_tasks.add(t)
    t.add_done_callback(_background_tasks.discard)
    return t


@bot.event
async def on_guild_join(guild: discord.Guild):
    await ensure_guild_loaded(guild.id)
    set_current_guild(guild.id)
    print(f"[BOT_SHOP] ✅ Đã tham gia guild mới: {guild.name} ({guild.id})")
    await notify_admins_unauthorized_guild(bot, guild)


COGS_SHOP = [
    "cogs.shop_admin",
    "cogs.listings",
    "cogs.shop_orders",
    "cogs.leaderboard",
    "cogs.seller",
    "cogs.autobuy",
]

async def load_cogs():
    for cog in COGS_SHOP:
        try:
            await bot.load_extension(cog)
            print(f"[COG] ✅ Loaded: {cog}")
        except Exception as e:
            print(f"[COG] ❌ Failed {cog}: {e}")


_on_ready_first_boot_done = False

@bot.event
async def on_ready():
    """Bản RÚT GỌN của on_ready() bên bot.py chính — chỉ giữ phần thuộc domain Shop.
    KHÔNG resume giveaway/ticket/legit — domain của bot khác. resume_pending_sold_views()
    CHỈ chạy 1 lần (if first_boot) — cùng lý do với resume_active_giveaways() bên
    bot_growth.py: gọi lại lúc reconnect sẽ tạo thêm task escalate trùng cho đơn đang
    chờ giá/buyer, ping Ruby lặp lại. QueueOrderView (shop_orders.py) VÀ
    register_payment_callback() đã tự đăng ký trong ShopOrdersCog.cog_load() — không
    cần gọi gì thêm ở đây."""
    global _on_ready_first_boot_done
    from shared.data import init_data_cache
    from cogs.shop_admin import resume_pending_sold_views

    await init_data_cache(bot)

    first_boot = not _on_ready_first_boot_done
    _on_ready_first_boot_done = True

    if first_boot:
        await resume_pending_sold_views(bot)

        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands (bot_shop)")
        except Exception as e:
            print(f"❌ Slash sync error: {e}")

    print(f"✅ Bot Shop online: {bot.user} | {len(bot.guilds)} server(s)" + ("" if first_boot else " (reconnect)"))


@bot.event
async def on_message(message: discord.Message):
    """Bản RÚT GỌN của on_message() bên bot.py chính — chỉ giữ handle_sold() (domain
    Shop). KHÔNG gọi handle_ai_message/legit/vouch — domain của bot khác."""
    if message.author.bot:
        return

    if message.guild:
        set_current_guild(message.guild.id)

    await bot.process_commands(message)

    if not message.guild:
        return

    from core.data import is_guild_authorized
    if not is_guild_authorized(message.guild.id):
        return

    from cogs.shop_admin import handle_sold
    await handle_sold(bot, message)


async def main():
    from verify_server import start_verify_server
    port = int(os.getenv("PORT", 8080))

    async def _run_verify():
        try:
            await start_verify_server(host="0.0.0.0", port=port)
        except (OSError, SystemExit) as e:
            print(f"[VERIFY] ⚠️ Không thể bind port {port}: {e} — verify server tắt, bot vẫn chạy")
        except Exception as e:
            print(f"[VERIFY] ❌ Lỗi không mong muốn: {e}")

    async with bot:
        await load_cogs()
        spawn_background(_run_verify())
        await bot.start(TOKEN_SHOP)

if __name__ == "__main__":
    asyncio.run(main())
