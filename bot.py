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
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

BOT_VERSION = "4.11.4"
BOT_UPDATED = "2026-07-12"
CHANGELOG_CHANNEL_ID = 1486967511839801414

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Thiếu biến môi trường TOKEN!")

intents = discord.Intents.all()


class GuildContextTree(app_commands.CommandTree):
    """CommandTree tùy chỉnh — tự set guild context (contextvar ở core/data.py) TRƯỚC khi
    chạy bất kỳ slash command nào, để load_data()/save_data() thao tác đúng document
    của guild đang gõ lệnh (thay vì lẫn giữa 2 server)."""
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        from core.data import set_current_guild
        if interaction.guild_id:
            set_current_guild(interaction.guild_id)
        return True


bot = commands.Bot(command_prefix=".", intents=intents, help_command=None, tree_cls=GuildContextTree)

@bot.before_invoke
async def _set_guild_context_prefix(ctx: commands.Context):
    """Tương tự GuildContextTree nhưng cho lệnh gõ chữ (.command) — chạy TRƯỚC mọi lệnh prefix."""
    from core.data import set_current_guild
    if ctx.guild:
        set_current_guild(ctx.guild.id)

@bot.event
async def on_guild_join(guild: discord.Guild):
    """Bot vừa được mời vào 1 server mới — load cache riêng cho guild đó ngay,
    không cần đợi bot restart mới hoạt động đúng."""
    from core.data import ensure_guild_loaded, set_current_guild
    await ensure_guild_loaded(guild.id)
    set_current_guild(guild.id)
    print(f"[BOT] ✅ Đã tham gia guild mới: {guild.name} ({guild.id})")

# ══════════════════════════════════════════
# LOAD COGS
# ══════════════════════════════════════════
COGS = [
    "cogs.logger",
    "cogs.ticket",
    "cogs.ai_chat",
    "cogs.invite",
    "cogs.giveaway",
    "cogs.admin",
    "cogs.mod",
    "cogs.seller",
    "cogs.shop_orders",
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
    from core.data import init_data_cache, set_current_guild
    from cogs.ticket import TicketPanel, TicketButtons, sync_ticket_counter
    from cogs.giveaway import GiveawayView
    from cogs.admin import resume_pending_sold_views

    await init_data_cache(bot)

    # Resume hàng đợi rename legit/vouch bị rate limit dở dang từ trước khi bot restart
    await _resume_pending_renames(bot)

    # Resume giveaways (không cần guild context — giveaway tách theo message_id, xem core/data.py)
    gw_cog = bot.cogs.get("GiveawayCog")
    if gw_cog:
        await gw_cog.resume_active_giveaways()

    # Register persistent views
    bot.add_view(TicketPanel())
    bot.add_view(TicketButtons())
    bot.add_view(GiveawayView())

    # Resume nút DM "Nhập giá" sold-stock (đơn pending chưa được admin xử lý)
    # Hàm này tự loop qua từng guild bên trong (vì pending_sold_price giờ tách theo guild).
    await resume_pending_sold_views(bot)

    # Sync invite cache & ticket counter — set context TRƯỚC mỗi guild vì cache_invites()/
    # sync_ticket_counter() đều gọi load_data()/save_data() bên trong.
    from cogs.invite import cache_invites
    for guild in bot.guilds:
        set_current_guild(guild.id)
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

    # Auto sold — stock → sold category
    from cogs.admin import handle_sold
    await handle_sold(bot, message)

    # AI channel
    from cogs.ai_chat import handle_ai_message
    await handle_ai_message(message)


    # Legit & Vouch
    await _handle_legit(message)
    await _handle_vouch(message)


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
        asyncio.create_task(_run_verify())
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
