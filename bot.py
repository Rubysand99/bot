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

if os.path.exists(".env"):
    load_dotenv()

BOT_VERSION = "4.54.1"
BOT_UPDATED = "2026-08-31"
CHANGELOG_CHANNEL_ID = 1486967511839801414

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Thiếu biến môi trường TOKEN!")

intents = discord.Intents.all()

# asyncio chỉ giữ WEAK reference tới Task — task nền tạo bằng create_task() mà không
# ai giữ reference nào khác có thể bị GC giữa chừng, im lặng không log gì (hiếm nhưng
# có thật, xem docs asyncio.create_task). Dùng spawn_background() thay create_task()
# trực tiếp cho MỌI task nền sống lâu (verify server, backfill...) — set module-level
# này giữ reference tới khi task xong rồi tự bỏ qua done_callback.
_background_tasks: set = set()

def spawn_background(coro) -> asyncio.Task:
    t = asyncio.create_task(coro)
    _background_tasks.add(t)
    t.add_done_callback(_background_tasks.discard)
    return t


# AUTH_GATE (lớp 1 + lớp 2) giờ dùng chung từ shared/auth_gate.py — xem docstring đầu
# file đó để biết cách wiring. GuildContextTree/get_prefix/set_guild_context_prefix/
# global_guild_authorization_check/notify_admins_unauthorized_guild ĐÃ chuyển sang đó,
# KHÔNG còn định nghĩa riêng ở bot.py nữa.
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
    """Bot vừa được mời vào 1 server mới — load cache riêng cho guild đó ngay,
    không cần đợi bot restart mới hoạt động đúng. Server MẶC ĐỊNH CHƯA được ủy quyền
    (xem AUTH_GATE) — báo ngay cho admin qua DM để họ chạy `.as <id_server>`."""
    await ensure_guild_loaded(guild.id)
    set_current_guild(guild.id)
    print(f"[BOT] ✅ Đã tham gia guild mới: {guild.name} ({guild.id})")
    await notify_admins_unauthorized_guild(bot, guild)

# ══════════════════════════════════════════
# LOAD COGS
# ══════════════════════════════════════════
COGS = [
    "cogs.logger",
    "cogs.ticket",
    "cogs.ai_chat",
    "cogs.message_search",
    "cogs.invite",
    "cogs.giveaway",
    "cogs.admin",
    "cogs.mod",
    "cogs.seller",
    "cogs.shop_orders",
    "cogs.listings",
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
_on_ready_first_boot_done = False   # FIX: xem giải thích trong on_ready() bên dưới

@bot.event
async def on_ready():
    """⚠️ on_ready() KHÔNG chỉ chạy 1 lần lúc khởi động — Discord gateway reconnect
    (rớt mạng, Railway restart container, session bị Discord invalidate...) khiến nó
    REFIRE bất cứ lúc nào trong suốt vòng đời bot. Nhiều bước "resume 1 lần" bên dưới
    trước đây chạy lại MỖI LẦN refire, gây bug thật đã xác nhận:
      • gw_cog.resume_active_giveaways() tạo THÊM 1 task đếm giờ cho MỖI giveaway đang
        chạy mà KHÔNG huỷ task cũ (không giống _resume_pending_renames() — hàm đó đã tự
        check `.done()` trước khi tạo task mới) → khi hết giờ, CẢ 2 task cùng gọi
        end_giveaway(), giveaway bị công bố kết thúc + random winner 2 LẦN (có thể ra
        2 winner khác nhau, đã sửa thêm 1 lớp phòng thủ ở chính end_giveaway() —
        xem cogs/giveaway.py).
      • resume_pending_sold_views() cùng lỗi — tạo thêm task escalate cho đơn đang chờ
        giá/buyer, ping Ruby trùng lặp.
      • Embed "Bot Khởi Động" gửi lại vào kênh changelog mỗi lần reconnect → spam.
    Fix: mọi bước CHỈ AN TOÀN CHẠY 1 LẦN được gom vào khối `if first_boot:` — chỉ chạy
    ở lần on_ready đầu tiên sau khi PROCESS khởi động (không phải lần đầu sau mỗi
    reconnect). init_data_cache() KHÔNG cần gom vào đây vì đã tự guard bên trong
    (xem CHANGELOG v4.25.4) — gọi lại mỗi lần refire vẫn an toàn.
    cache_invites()/sync_ticket_counter() CỐ Ý vẫn chạy mỗi lần refire: invite cache có
    thể lệch thật sau khi mất kết nối (cần refresh), còn ticket counter chỉ tăng chứ
    không giảm nên gọi lại vô hại."""
    global _on_ready_first_boot_done
    from core.data import init_data_cache, set_current_guild
    from cogs.ticket import TicketPanel, TicketButtons, MiddlemanPanelView, sync_ticket_counter
    from cogs.giveaway import GiveawayView
    from cogs.admin import resume_pending_sold_views

    await init_data_cache(bot)

    first_boot = not _on_ready_first_boot_done
    _on_ready_first_boot_done = True

    if first_boot:
        # Resume hàng đợi rename legit/vouch bị rate limit dở dang từ trước khi bot restart
        await _resume_pending_renames(bot)

        # Resume giveaways (không cần guild context — giveaway tách theo message_id, xem core/data.py)
        gw_cog = bot.cogs.get("GiveawayCog")
        if gw_cog:
            await gw_cog.resume_active_giveaways()

        # Register persistent views
        bot.add_view(TicketPanel())
        bot.add_view(TicketButtons())
        bot.add_view(MiddlemanPanelView())
        bot.add_view(GiveawayView())

        # Resume nút DM "Nhập giá" sold-stock (đơn pending chưa được admin xử lý)
        # Hàm này tự loop qua từng guild bên trong (vì pending_sold_price giờ tách theo guild).
        await resume_pending_sold_views(bot)

    # Sync invite cache & ticket counter — set context TRƯỚC mỗi guild vì cache_invites()/
    # sync_ticket_counter() đều gọi load_data()/save_data() bên trong. CỐ Ý chạy mỗi lần
    # refire, xem docstring ở trên.
    from cogs.invite import cache_invites
    for guild in bot.guilds:
        set_current_guild(guild.id)
        await cache_invites(guild)
        await sync_ticket_counter(bot, guild)

    if first_boot:
        # Sync slash commands — Discord rate-limit sync toàn cục, không cần (và không nên)
        # gọi lại mỗi lần reconnect vì slash command không đổi giữa các lần reconnect.
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands")
        except Exception as e:
            print(f"❌ Slash sync error: {e}")

        # Test kết nối AI provider (Groq/Gemini) + in console — CHỈ 1 lần lúc khởi
        # động thật, KHÔNG lặp lại mỗi lần reconnect (tốn quota gọi API vô ích).
        # Chạy nền (spawn_background) để không delay phần còn lại của on_ready().
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

    print(f"✅ Bot online: {bot.user} | {len(bot.guilds)} server(s)" + ("" if first_boot else " (reconnect)"))

    if not first_boot:
        return  # Phần dưới (backfill legit + embed changelog) CHỈ chạy lúc khởi động thật

    # Quét lại legit channel — thả ✅ cho tin nhắn bị bỏ sót lúc bot offline
    spawn_background(_backfill_legit())

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
            # Lấy block entry mới nhất (từ ## đầu đến ## tiếp theo)
            blocks = _re.split(r"\n(?=## \[)", content)
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

    # Set guild context NGAY ĐẦU — mọi hàm gọi bên dưới (process_commands, handle_sold,
    # handle_ai_message, legit/vouch) đều nằm trong cùng 1 task nên sẽ tự động thấy đúng guild.
    if message.guild:
        from core.data import set_current_guild
        set_current_guild(message.guild.id)

    await bot.process_commands(message)

    # Các tính năng dưới đây (auto-sold, AI channel, legit/vouch) chỉ có ý nghĩa
    # trong server — bỏ qua DM để tránh crash (DMChannel không có .name) và
    # tránh load_data() bị gọi mà thiếu guild context.
    if not message.guild:
        return

    # AUTH_GATE — server chưa được ủy quyền → bỏ qua mọi tính năng tự động
    # (auto-sold, AI channel, legit/vouch). Lệnh .command đã bị chặn riêng ở
    # global_guild_authorization_check() (shared/auth_gate.py, bot.check), không cần lặp lại ở đây.
    from core.data import is_guild_authorized
    if not is_guild_authorized(message.guild.id):
        return

    # Auto sold — stock → sold category
    from cogs.admin import handle_sold
    await handle_sold(bot, message)

    # AI channel
    from cogs.ai_chat import handle_ai_message
    await handle_ai_message(message)


    # Legit & Vouch
    await _handle_legit(message)
    await _handle_vouch(message)

    # Site feed — đẩy tin nhắn kênh thông báo/legit lên website real-time (core/site_feed.py)
    from core.site_feed import handle_site_feed
    await handle_site_feed(message)


@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    """Đồng bộ xoá vào site_feed (core/site_feed.py) — dùng RAW event để bắt được cả
    tin nhắn không còn trong cache của discord.py. Không liên quan AUTH_GATE/guild
    context vì handle_site_feed_delete() tự lọc theo WATCHED_CHANNELS (2 kênh cố định
    của TuyTam, không theo guild) — không đụng tới is_guild_authorized()."""
    from core.site_feed import handle_site_feed_delete
    await handle_site_feed_delete(payload)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """Đồng bộ sửa vào site_feed — cùng lý do trên."""
    if after.author.bot:
        return
    from core.site_feed import handle_site_feed_edit
    await handle_site_feed_edit(after)


# ══════════════════════════════════════════
# LEGIT / VOUCH HANDLERS
# ══════════════════════════════════════════

def _parse_emoji(emoji_str: str):
    """Chuyển chuỗi emoji lưu trong DB (unicode hoặc '<:name:id>') thành dạng
    add_reaction() dùng được. Custom emoji không hợp lệ (bot không cùng server,
    id sai...) → fallback về ✅ để không làm crash handler."""
    try:
        return discord.PartialEmoji.from_str((emoji_str or "").strip() or "✅")
    except Exception:
        return "✅"

# ── Hàng đợi rename khi bị Discord rate limit (tối đa 2 lần đổi tên kênh / 10 phút) ──
# Lưu bền trong Mongo (field "_pending_renames" ở global data "main") để không mất khi bot
# restart giữa lúc đang chờ hết rate limit. asyncio.Task thì KHÔNG lưu được — chỉ giữ ở RAM
# và được tạo lại lúc khởi động qua _resume_pending_renames() (gọi từ on_ready).
_pending_tasks: dict = {}   # channel_id -> asyncio.Task đang chờ retry cho channel đó

def _get_pending_rename(channel_id: int):
    from core.data import load_global_data
    g = load_global_data()
    return g.get("_pending_renames", {}).get(str(channel_id))

def _set_pending_rename(channel_id: int, base: str, target_num: int):
    from core.data import load_global_data, save_global_data
    g = load_global_data()
    g.setdefault("_pending_renames", {})[str(channel_id)] = {"base": base, "target_num": target_num}
    save_global_data(g)

def _clear_pending_rename(channel_id: int):
    from core.data import load_global_data, save_global_data
    g = load_global_data()
    if g.get("_pending_renames", {}).pop(str(channel_id), None) is not None:
        save_global_data(g)

def _next_rename_target(channel: discord.abc.GuildChannel):
    """Tính (base, new_num) tiếp theo. Nếu đang có hàng đợi cho kênh này (do lần
    trước bị rate limit, lưu trong Mongo), tính tiếp từ target đang chờ chứ KHÔNG
    đọc tên kênh hiện tại (vì tên kênh thật chưa được cập nhật lúc đó). Trả (None, None)
    nếu tên kênh không có số cuối và cũng không có hàng đợi."""
    pending = _get_pending_rename(channel.id)
    if pending:
        return pending["base"], pending["target_num"] + 1
    match = _re.search(r"-(\d+)$", channel.name)
    if match:
        return channel.name[:match.start()], int(match.group(1)) + 1
    return None, None

async def _apply_rename_with_retry(channel: discord.abc.GuildChannel, channel_id: int, label: str):
    """Chạy nền: liên tục thử đổi tên kênh về target_num MỚI NHẤT trong hàng đợi (Mongo)
    cho tới khi thành công. Nếu trong lúc chờ có +1 mới nữa (target_num tăng thêm),
    lần retry tiếp theo sẽ tự áp dụng số mới nhất, không cần chạy lại từng bước."""
    while True:
        pending = _get_pending_rename(channel_id)
        if not pending:
            _pending_tasks.pop(channel_id, None)
            return
        base, target_num = pending["base"], pending["target_num"]
        try:
            await channel.edit(name=f"{base}-{target_num}", reason=f"+1 {label} (resume sau rate limit)")
        except discord.HTTPException as e:
            retry_after = getattr(e, "retry_after", None) or 60
            print(f"[{label.upper()}] ⏳ Kênh {channel_id} vẫn đang rate limit, thử lại sau {retry_after:.0f}s")
            await asyncio.sleep(retry_after + 1)
            continue
        except Exception as e:
            print(f"[{label.upper()}] ❌ Lỗi khi resume rename: {e}")
            _clear_pending_rename(channel_id)
            _pending_tasks.pop(channel_id, None)
            return
        # Đổi tên thành công — nếu không có target mới hơn được set thêm trong lúc edit thì xong
        latest = _get_pending_rename(channel_id)
        if not latest or latest.get("target_num") == target_num:
            _clear_pending_rename(channel_id)
            _pending_tasks.pop(channel_id, None)
            return
        # Có target mới hơn (thêm +1 trong lúc đang retry) → lặp lại vòng while để áp số mới nhất

async def _queue_or_rename(channel: discord.abc.GuildChannel, base: str, new_num: int, reason: str, label: str):
    """Thử đổi tên ngay; nếu bị Discord rate limit thì lưu vào hàng đợi (Mongo) và chạy
    task nền tự retry, KHÔNG làm crash/return sớm khỏi handler gọi hàm này."""
    try:
        await channel.edit(name=f"{base}-{new_num}", reason=reason)
        _clear_pending_rename(channel.id)
    except discord.HTTPException as e:
        print(f"[{label.upper()}] ⚠️ Rate limit đổi tên kênh {channel.id}, xếp vào hàng đợi (target={new_num}): {e}")
        _set_pending_rename(channel.id, base, new_num)
        if channel.id not in _pending_tasks or _pending_tasks[channel.id].done():
            _pending_tasks[channel.id] = asyncio.create_task(
                _apply_rename_with_retry(channel, channel.id, label)
            )

async def _resume_pending_renames(bot: commands.Bot):
    """Gọi 1 lần ở on_ready — nếu bot restart giữa lúc đang có hàng đợi rename dở dang
    (rate limit Discord chưa hết hạn lúc bot tắt), tạo lại task retry cho từng kênh
    thay vì bỏ dở vĩnh viễn. Kênh không còn tồn tại (đã bị xoá) → xoá khỏi hàng đợi luôn."""
    from core.data import load_global_data, get_or_fetch_channel
    pending_map = load_global_data().get("_pending_renames", {})
    if not pending_map:
        return
    print(f"[RENAME] 🔁 Resume {len(pending_map)} hàng đợi rename dở dang từ trước khi restart")
    for cid_str in list(pending_map.keys()):
        channel_id = int(cid_str)
        channel = await get_or_fetch_channel(bot, channel_id)
        if channel is None:
            print(f"[RENAME] ⚠️ Không tìm thấy kênh {channel_id} (có thể đã bị xoá) — bỏ khỏi hàng đợi")
            _clear_pending_rename(channel_id)
            continue
        if channel_id not in _pending_tasks or _pending_tasks[channel_id].done():
            _pending_tasks[channel_id] = asyncio.create_task(
                _apply_rename_with_retry(channel, channel_id, "resume")
            )

async def _handle_legit(message: discord.Message):
    try:
        from core.data import get_cfg_legit_channel, get_cfg_legit_emoji
        IGNORED = {628400349979344919}
        if message.author.id in IGNORED: return
        legit_ch = get_cfg_legit_channel()
        if legit_ch:
            if message.channel.id != legit_ch: return
        else:
            cname = message.channel.name.lower()
            if "legit" not in cname and "vouch" not in cname: return
        if not _re.match(r"^\+1\s*legit\b", message.content.strip(), _re.IGNORECASE): return

        ch = message.channel
        base, new_num = _next_rename_target(ch)
        if base is not None:
            await _queue_or_rename(ch, base, new_num, f"+1 legit bởi {message.author}", "legit")
        # Không có số ở cuối tên kênh (và không có hàng đợi) → chỉ thả emoji, không đổi tên

        await message.add_reaction(_parse_emoji(get_cfg_legit_emoji()))
    except Exception as e:
        print(f"[LEGIT] ❌ Lỗi: {e}")

async def _handle_vouch(message: discord.Message):
    try:
        from core.data import get_cfg_proof_channel, get_cfg_vouch_emoji
        IGNORED = {628400349979344919}
        if message.author.id in IGNORED: return
        proof_ch = get_cfg_proof_channel()
        if proof_ch:
            if message.channel.id != proof_ch: return
        else:
            cname = message.channel.name.lower()
            if "vouch" not in cname and "proof" not in cname: return
        if not _re.match(r"^done\b", message.content.strip(), _re.IGNORECASE): return

        ch = message.channel
        base, new_num = _next_rename_target(ch)
        if base is not None:
            await _queue_or_rename(ch, base, new_num, f"+1 vouch bởi {message.author}", "vouch")
        # Không có số ở cuối tên kênh (và không có hàng đợi) → chỉ thả emoji, không đổi tên

        await message.add_reaction(_parse_emoji(get_cfg_vouch_emoji()))
    except Exception as e:
        print(f"[VOUCH] ❌ Lỗi: {e}")



# ══════════════════════════════════════════
# BACKFILL LEGIT — Quét lại lúc khởi động
# ══════════════════════════════════════════
BACKFILL_LIMIT = 25  # Số tin nhắn gần nhất cần quét

async def _backfill_legit():
    """Sau khi bot online, quét 25 tin nhắn gần nhất trong kênh legit CỦA TỪNG GUILD.
    Tin nào khớp +1legit mà chưa có reaction ✅ từ bot → thả reaction và đổi tên kênh +1.
    Fetch lại tên kênh sau mỗi lần edit để tránh số đếm bị sai."""
    await asyncio.sleep(3)  # Chờ cache sẵn sàng
    from core.data import get_cfg_legit_channel, get_cfg_legit_emoji, get_or_fetch_channel, set_current_guild
    IGNORED = {628400349979344919}

    for guild in bot.guilds:
        set_current_guild(guild.id)
        legit_ch_id = get_cfg_legit_channel()
        if not legit_ch_id:
            print(f"[BACKFILL] ⚠️ Guild {guild.id} chưa cài legit channel, bỏ qua.")
            continue
        emoji_str    = get_cfg_legit_emoji()
        target_emoji = _parse_emoji(emoji_str)

        channel = await get_or_fetch_channel(bot, legit_ch_id)
        if not channel:
            print(f"[BACKFILL] ⚠️ Guild {guild.id}: không tìm thấy channel {legit_ch_id}")
            continue

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

                already = any(str(r.emoji) == str(target_emoji) and r.me for r in msg.reactions)
                if not already:
                    try:
                        await msg.add_reaction(target_emoji)
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
            print(f"[BACKFILL] ❌ Guild {guild.id}: lỗi khi quét legit channel: {e}")
            continue

        print(f"[BACKFILL] ✅ Guild {guild.id} hoàn tất — đã xử lý {fixed} tin nhắn bị bỏ sót.")


# ══════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════
async def main():
    from verify_server import start_verify_server
    import os
    port = int(os.getenv("PORT", 8080))

    # Chạy verify server như background task, không block bot nếu port lỗi
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
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
