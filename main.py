# main.py — Khởi động bot, load tất cả cogs
from config import bot, tree, TOKEN, ADMIN_IDS, CHANGELOG_CHANNEL_ID, BOT_VERSION, BOT_UPDATED
from config import init_data_cache, discord, datetime, timezone
import asyncio

# Import các persistent views cần đăng ký trong on_ready
from cogs.ticket import TicketPanel, TicketButtons
from cogs.giveaway import GiveawayView, resume_active_giveaways

# Import để đăng ký tất cả commands/events với bot
import cogs.ticket
import cogs.ticket_cmds
import cogs.help_cmd
import cogs.mod
import cogs.giveaway
import cogs.info
import cogs.settings
import cogs.balance
import cogs.ai_chat
import cogs.invite
import cogs.events
import cogs.setup
import cogs.emoji
import cogs.price
import cogs.slash_misc


@bot.event
async def on_ready():
    await init_data_cache()
    await resume_active_giveaways()

    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    bot.add_view(GiveawayView())

    from cogs.invite import _cache_invites
    from cogs.ticket import sync_ticket_counter
    for guild in bot.guilds:
        await _cache_invites(guild)
        await sync_ticket_counter(guild)

    try:
        synced = await tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Slash sync error: {e}")

    print(f"✅ Bot online: {bot.user} | {len(bot.guilds)} server(s)")

    changelog_ch = bot.get_channel(CHANGELOG_CHANNEL_ID)
    if changelog_ch:
        embed = discord.Embed(
            title=f"📋 Changelog — v{BOT_VERSION}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
            description=(
                f"Bot đã khởi động lại và cập nhật lên **v{BOT_VERSION}** ({BOT_UPDATED})\n"
            )
        )
        embed.add_field(
            name="🆕 v3.3.5 — Phân Quyền Admin & Seller Role Ticket",
            value=(
                "• Chỉ **ADMIN_IDS** mới dùng được các lệnh: `.clear`, `.close`, `.done`, `.addnote`\n"
                "• **Seller Role** được tự động thêm vào **mọi ticket** khi tạo\n"
                "  *(view, send, history, manage messages, attach files, embed links)*\n"
                "• Các nút trong ticket (Mua/Add Staff/Ghi chú/Đóng/Hoàn thành/Gửi QR) vẫn cho phép staff dùng"
            ),
            inline=False
        )
        embed.set_footer(text="TuyTam Store  •  Dùng .help để xem tất cả lệnh")
        try:
            await changelog_ch.send(embed=embed)
        except Exception as e:
            print(f"[CHANGELOG] ❌ Không gửi được: {e}")


bot.run(TOKEN)
