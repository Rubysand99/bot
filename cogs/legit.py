"""
cogs/legit.py — Tính năng Legit/Vouch (+1legit / done → đổi tên kênh + thả reaction).
Tách từ bot.py (trước đây nằm thẳng trong entry point, không phải cog) — xác nhận qua
review: KHÔNG có ràng buộc chéo với ticket_history/seller/admin, chỉ đọc core/data.py
(cfg_legit_channel, cfg_proof_channel, cfg_legit_emoji, cfg_vouch_emoji) + field
"_pending_renames" ở global data — an toàn để tách sang bot riêng.

Vì sao thuộc bot Ticket (không phải Shop/Growth): về nghiệp vụ đây là bước "xác nhận
uy tín SAU giao dịch" — thường diễn ra ngay sau khi đóng ticket, cùng luồng làm việc
với người xử lý ticket. Không có ràng buộc kỹ thuật bắt buộc — nếu sau này thấy hợp lý
hơn ở bot khác, chuyển cũng không khó (đã tách gọn thành 1 cog độc lập).
"""

import re as _re
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from core.data import (
    set_current_guild, is_guild_authorized, is_admin,
    get_cfg_legit_channel, get_cfg_legit_emoji,
    get_cfg_proof_channel, get_cfg_vouch_emoji,
    load_global_data, save_global_data, get_or_fetch_channel,
)

IGNORED_USERS = {628400349979344919}
BACKFILL_LIMIT = 25


def _parse_emoji(emoji_str: str):
    """Chuyển chuỗi emoji lưu trong DB (unicode hoặc '<:name:id>') thành dạng
    add_reaction() dùng được. Custom emoji không hợp lệ → fallback về ✅."""
    try:
        return discord.PartialEmoji.from_str((emoji_str or "").strip() or "✅")
    except Exception:
        return "✅"


class LegitVouchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._pending_tasks: dict = {}   # channel_id -> asyncio.Task đang chờ retry
        self._first_boot_done = False

    # ── Hàng đợi rename khi bị Discord rate limit (tối đa 2 lần đổi tên kênh / 10 phút) ──
    # Lưu bền trong Mongo (field "_pending_renames" ở global data "main") để không mất
    # khi bot restart giữa lúc đang chờ hết rate limit.

    def _get_pending_rename(self, channel_id: int):
        g = load_global_data()
        return g.get("_pending_renames", {}).get(str(channel_id))

    def _set_pending_rename(self, channel_id: int, base: str, target_num: int):
        g = load_global_data()
        g.setdefault("_pending_renames", {})[str(channel_id)] = {"base": base, "target_num": target_num}
        save_global_data(g)

    def _clear_pending_rename(self, channel_id: int):
        g = load_global_data()
        if g.get("_pending_renames", {}).pop(str(channel_id), None) is not None:
            save_global_data(g)

    def _next_rename_target(self, channel: discord.abc.GuildChannel):
        pending = self._get_pending_rename(channel.id)
        if pending:
            return pending["base"], pending["target_num"] + 1
        match = _re.search(r"-(\d+)$", channel.name)
        if match:
            return channel.name[:match.start()], int(match.group(1)) + 1
        return None, None

    async def _apply_rename_with_retry(self, channel: discord.abc.GuildChannel, channel_id: int, label: str):
        while True:
            pending = self._get_pending_rename(channel_id)
            if not pending:
                self._pending_tasks.pop(channel_id, None)
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
                self._clear_pending_rename(channel_id)
                self._pending_tasks.pop(channel_id, None)
                return
            latest = self._get_pending_rename(channel_id)
            if not latest or latest.get("target_num") == target_num:
                self._clear_pending_rename(channel_id)
                self._pending_tasks.pop(channel_id, None)
                return

    async def _queue_or_rename(self, channel: discord.abc.GuildChannel, base: str, new_num: int, reason: str, label: str):
        try:
            await channel.edit(name=f"{base}-{new_num}", reason=reason)
            self._clear_pending_rename(channel.id)
        except discord.HTTPException as e:
            print(f"[{label.upper()}] ⚠️ Rate limit đổi tên kênh {channel.id}, xếp vào hàng đợi (target={new_num}): {e}")
            self._set_pending_rename(channel.id, base, new_num)
            if channel.id not in self._pending_tasks or self._pending_tasks[channel.id].done():
                self._pending_tasks[channel.id] = asyncio.create_task(
                    self._apply_rename_with_retry(channel, channel.id, label)
                )

    async def _resume_pending_renames(self):
        pending_map = load_global_data().get("_pending_renames", {})
        if not pending_map:
            return
        print(f"[RENAME] 🔁 Resume {len(pending_map)} hàng đợi rename dở dang từ trước khi restart")
        for cid_str in list(pending_map.keys()):
            channel_id = int(cid_str)
            channel = await get_or_fetch_channel(self.bot, channel_id)
            if channel is None:
                print(f"[RENAME] ⚠️ Không tìm thấy kênh {channel_id} (có thể đã bị xoá) — bỏ khỏi hàng đợi")
                self._clear_pending_rename(channel_id)
                continue
            if channel_id not in self._pending_tasks or self._pending_tasks[channel_id].done():
                self._pending_tasks[channel_id] = asyncio.create_task(
                    self._apply_rename_with_retry(channel, channel_id, "resume")
                )

    # ── Handlers ──

    async def _handle_legit(self, message: discord.Message):
        try:
            if message.author.id in IGNORED_USERS:
                return
            legit_ch = get_cfg_legit_channel()
            if legit_ch:
                if message.channel.id != legit_ch:
                    return
            else:
                cname = message.channel.name.lower()
                if "legit" not in cname and "vouch" not in cname:
                    return
            if not _re.match(r"^\+1\s*legit\b", message.content.strip(), _re.IGNORECASE):
                return

            ch = message.channel
            base, new_num = self._next_rename_target(ch)
            if base is not None:
                await self._queue_or_rename(ch, base, new_num, f"+1 legit bởi {message.author}", "legit")

            await message.add_reaction(_parse_emoji(get_cfg_legit_emoji()))
        except Exception as e:
            print(f"[LEGIT] ❌ Lỗi: {e}")

    async def _handle_vouch(self, message: discord.Message):
        try:
            if message.author.id in IGNORED_USERS:
                return
            proof_ch = get_cfg_proof_channel()
            if proof_ch:
                if message.channel.id != proof_ch:
                    return
            else:
                cname = message.channel.name.lower()
                if "vouch" not in cname and "proof" not in cname:
                    return
            if not _re.match(r"^done\b", message.content.strip(), _re.IGNORECASE):
                return

            ch = message.channel
            base, new_num = self._next_rename_target(ch)
            if base is not None:
                await self._queue_or_rename(ch, base, new_num, f"+1 vouch bởi {message.author}", "vouch")

            await message.add_reaction(_parse_emoji(get_cfg_vouch_emoji()))
        except Exception as e:
            print(f"[VOUCH] ❌ Lỗi: {e}")

    # ── Backfill lúc khởi động ──

    async def _backfill_legit(self):
        """Sau khi bot online, quét N tin nhắn gần nhất trong kênh legit CỦA TỪNG GUILD.
        Tin nào khớp +1legit mà chưa có reaction ✅ từ bot → thả reaction và đổi tên kênh +1."""
        await asyncio.sleep(3)
        for guild in self.bot.guilds:
            set_current_guild(guild.id)
            legit_ch_id = get_cfg_legit_channel()
            if not legit_ch_id:
                print(f"[BACKFILL] ⚠️ Guild {guild.id} chưa cài legit channel, bỏ qua.")
                continue
            emoji_str    = get_cfg_legit_emoji()
            target_emoji = _parse_emoji(emoji_str)

            channel = await get_or_fetch_channel(self.bot, legit_ch_id)
            if not channel:
                print(f"[BACKFILL] ⚠️ Guild {guild.id}: không tìm thấy channel {legit_ch_id}")
                continue

            fixed = 0
            try:
                msgs = []
                async for msg in channel.history(limit=BACKFILL_LIMIT):
                    msgs.append(msg)
                msgs.reverse()

                for msg in msgs:
                    if msg.author.bot:
                        continue
                    if msg.author.id in IGNORED_USERS:
                        continue
                    if not _re.match(r"^\+1\s*legit\b", msg.content.strip(), _re.IGNORECASE):
                        continue

                    already = any(str(r.emoji) == str(target_emoji) and r.me for r in msg.reactions)
                    if not already:
                        try:
                            await msg.add_reaction(target_emoji)
                        except Exception as e:
                            print(f"[BACKFILL] ❌ Không thả được reaction msg {msg.id}: {e}")
                        try:
                            channel = await channel.guild.fetch_channel(channel.id)
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

    # ── Lệnh .backfill (thủ công, admin tự gọi) ──
    # CHUYỂN từ cogs/admin.py (session tách bot Core — xem CHANGELOG.md). Trước đây
    # command này `from bot import _next_rename_target, _queue_or_rename` — import
    # thẳng module bot.py, vỡ nếu chạy ở process khác (đã ghi nhận là landmine lúc
    # tách Shop). Giờ dùng self._next_rename_target/self._queue_or_rename — cùng file,
    # không còn phụ thuộc bot.py nữa.
    #
    # FIX: khác với _backfill_legit() (auto lúc khởi động) dùng channel.edit() trần
    # trụi, lệnh này CỐ Ý dùng self._next_rename_target()/self._queue_or_rename() (hàng
    # đợi rate-limit) vì .backfill tồn tại để xử lý NHIỀU tin nhắn bị bỏ sót CÙNG LÚC —
    # đúng kịch bản dễ dính rate limit Discord nhất (tối đa 2 lần đổi tên kênh/10 phút).
    # Dùng channel.edit() trần trụi ở đây sẽ nuốt lỗi rate-limit im lặng → kênh bị
    # "đếm thiếu" dù mọi tin nhắn đều đã có ✅ (trông như xử lý xong hoàn chỉnh nhưng số
    # đếm trên tên kênh thực ra bị hụt).
    @commands.command(name="backfill")
    async def backfill_cmd(self, ctx, limit: int = 25):
        if not is_admin(ctx.author):
            return await ctx.reply("❌ Chỉ admin mới có quyền dùng lệnh này.")

        legit_ch_id = get_cfg_legit_channel()
        if not legit_ch_id:
            return await ctx.reply("❌ Chưa cài Legit Channel. Vào `.st` để cài trước.")

        channel = await get_or_fetch_channel(self.bot, legit_ch_id)
        if not channel:
            return await ctx.reply(f"❌ Không tìm thấy kênh legit (ID: `{legit_ch_id}`).")

        limit = max(1, min(limit, 100))
        msg_status = await ctx.reply(f"🔍 Đang quét **{limit}** tin nhắn gần nhất trong {channel.mention}...")

        missed = []
        scanned = 0
        try:
            msgs = []
            async for msg in channel.history(limit=limit):
                msgs.append(msg)
            msgs.reverse()  # cũ → mới để xử lý đúng thứ tự

            for msg in msgs:
                if msg.author.bot: continue
                if msg.author.id in IGNORED_USERS: continue
                if not _re.match(r"^\+1\s*legit\b", msg.content.strip(), _re.IGNORECASE): continue
                scanned += 1
                already = any(r.emoji == "✅" and r.me for r in msg.reactions)
                if not already:
                    missed.append(msg)
        except Exception as e:
            return await msg_status.edit(content=f"❌ Lỗi khi quét: `{e}`")

        fixed = 0
        name_before = channel.name
        for msg in missed:
            try:
                await msg.add_reaction("✅")
            except Exception:
                pass
            try:
                channel = await channel.guild.fetch_channel(channel.id)  # refresh tên mới nhất
                base, new_num = self._next_rename_target(channel)
                if base is None:
                    base, new_num = channel.name, 1
                await self._queue_or_rename(channel, base, new_num, f"Backfill +1 legit bởi {ctx.author}", "backfill")
                fixed += 1
            except Exception:
                pass

        name_after = channel.name
        embed = discord.Embed(
            title="✅ Backfill Legit Hoàn Tất",
            color=0x57F287,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🔍 Quét", value=f"**{limit}** tin nhắn", inline=True)
        embed.add_field(name="📝 Khớp +1legit", value=f"**{scanned}** tin", inline=True)
        embed.add_field(name="✅ Đã xử lý", value=f"**{fixed}** tin bị bỏ sót", inline=True)
        embed.add_field(name="📌 Kênh", value=f"`{name_before}` → `{name_after}`", inline=False)
        embed.set_footer(text="Nếu dính rate limit đổi tên kênh (Discord giới hạn 2 lần/10 phút), phần còn lại sẽ tự đổi tiếp ở nền — số trên tên kênh có thể cập nhật chậm hơn vài phút so với số ✅ đã thả.")
        await msg_status.edit(content=None, embed=embed)

    # ── Events ──

    @commands.Cog.listener()
    async def on_ready(self):
        """CHỈ resume + backfill 1 lần lúc khởi động thật — KHÔNG lặp lại mỗi lần
        Discord gateway reconnect (giữ đúng nguyên tắc first_boot của bot.py gốc)."""
        if self._first_boot_done:
            return
        self._first_boot_done = True
        await self._resume_pending_renames()
        asyncio.create_task(self._backfill_legit())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        set_current_guild(message.guild.id)
        if not is_guild_authorized(message.guild.id):
            return
        await self._handle_legit(message)
        await self._handle_vouch(message)


async def setup(bot: commands.Bot):
    await bot.add_cog(LegitVouchCog(bot))
