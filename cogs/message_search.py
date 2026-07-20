"""
cogs/message_search.py — Semantic search lịch sử tin nhắn server (mục 14).

Lệnh (admin-only):
  .aiindex [limit]              — chạy TRONG kênh cần index, backfill lịch sử cũ
  .aisearchch add|remove|list   — quản lý danh sách kênh tự động index liên tục
  .aisearch <câu hỏi>           — tìm tin nhắn cũ theo NGHĨA, không theo từ khoá

Nhớ thêm "cogs.message_search" vào danh sách COGS trong bot.py.
"""

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core.data import ADMIN_IDS, load_data, save_cfg, set_current_guild
from core.message_search import is_indexable, save_message, save_messages_batch, search_messages

log = logging.getLogger("message_search")

BACKFILL_BATCH_SIZE    = 50     # số tin/lần gọi Voyage batch
BACKFILL_DEFAULT_LIMIT = 1000
BACKFILL_MAX_LIMIT     = 3000


def _is_command_text(content: str) -> bool:
    return bool(content) and content[0] in ('.', '/', '!')


class MessageSearchCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ─────────────────────────────────────
    # BACKFILL — index lịch sử kênh hiện tại
    # ─────────────────────────────────────
    @commands.command(name="aiindex")
    async def aiindex(self, ctx: commands.Context, limit: int = BACKFILL_DEFAULT_LIMIT):
        if ctx.author.id not in ADMIN_IDS:
            return
        limit = max(1, min(limit, BACKFILL_MAX_LIMIT))

        progress = await ctx.send(f"⏳ Đang quét lịch sử **#{ctx.channel.name}** (tối đa {limit} tin)…")

        batch: list[dict] = []
        total_indexed = 0
        total_skipped = 0

        async for msg in ctx.channel.history(limit=limit):
            if not is_indexable(msg.content, msg.author.bot, _is_command_text(msg.content)):
                total_skipped += 1
                continue

            batch.append({
                "guild_id": ctx.guild.id,
                "channel_id": ctx.channel.id,
                "message_id": msg.id,
                "author_id": msg.author.id,
                "content": msg.content,
                "created_at": msg.created_at,
            })

            if len(batch) >= BACKFILL_BATCH_SIZE:
                total_indexed += await save_messages_batch(batch)
                batch = []

        if batch:
            total_indexed += await save_messages_batch(batch)

        await progress.edit(content=(
            f"✅ Xong! Đã index **{total_indexed}** tin nhắn mới từ **#{ctx.channel.name}** "
            f"(bỏ qua {total_skipped} tin không đáng embed — quá ngắn/lệnh/bot; "
            f"tin đã index từ trước cũng tự bỏ qua)."
        ))

    # ─────────────────────────────────────
    # QUẢN LÝ KÊNH TỰ ĐỘNG INDEX LIÊN TỤC
    # ─────────────────────────────────────
    @commands.command(name="aisearchch")
    async def aisearchch(self, ctx: commands.Context, action: str = "list",
                          channel: discord.TextChannel = None):
        if ctx.author.id not in ADMIN_IDS:
            return
        data = load_data()
        channels = data.get("cfg_ai_search_channels", [])

        if action == "list":
            if not channels:
                return await ctx.send("📋 Chưa có kênh nào được tự động index.")
            mentions = "\n".join(f"• <#{cid}>" for cid in channels)
            return await ctx.send(f"📋 Các kênh đang tự động index:\n{mentions}")

        target = channel or ctx.channel
        if action == "add":
            if target.id not in channels:
                channels.append(target.id)
                save_cfg("cfg_ai_search_channels", channels)
            return await ctx.send(
                f"✅ Đã bật tự động index cho {target.mention}. "
                f"Chạy `.aiindex` TRONG kênh đó để quét lịch sử cũ."
            )
        elif action == "remove":
            if target.id in channels:
                channels.remove(target.id)
                save_cfg("cfg_ai_search_channels", channels)
            return await ctx.send(f"✅ Đã tắt tự động index cho {target.mention}.")
        else:
            return await ctx.send("❌ Dùng: `.aisearchch add/remove/list [#kênh]`")

    # ─────────────────────────────────────
    # INDEX LIÊN TỤC — chỉ kênh trong danh sách
    # ─────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # QUAN TRỌNG: on_message ở Cog này chạy trên Task RIÊNG so với on_message
        # chính trong bot.py — KHÔNG thừa hưởng guild context, phải tự set.
        set_current_guild(message.guild.id)

        data = load_data()
        search_channels = data.get("cfg_ai_search_channels", [])
        if message.channel.id not in search_channels:
            return
        if not is_indexable(message.content, message.author.bot, _is_command_text(message.content)):
            return

        await save_message(
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            message_id=message.id,
            author_id=message.author.id,
            content=message.content,
            created_at=message.created_at,
        )

    # ─────────────────────────────────────
    # TÌM KIẾM
    # ─────────────────────────────────────
    @commands.command(name="aisearch")
    async def aisearch(self, ctx: commands.Context, *, query: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return
        if not query:
            return await ctx.send("❌ Dùng: `.aisearch <nội dung cần tìm>`")

        async with ctx.typing():
            results = await search_messages(ctx.guild.id, query, top_k=5)

        if not results:
            return await ctx.send(
                "🔍 Không tìm thấy tin nhắn nào liên quan "
                "(hoặc chưa có kênh nào được index — dùng `.aisearchch add`)."
            )

        embed = discord.Embed(
            title=f"🔍 Kết quả tìm kiếm: {query[:100]}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        for r in results:
            jump = f"https://discord.com/channels/{ctx.guild.id}/{r['channel_id']}/{r['_id']}"
            when = r["created_at"].strftime("%d/%m/%Y") if r.get("created_at") else "?"
            snippet = r["content"][:200]
            embed.add_field(
                name=f"📅 {when} • <#{r['channel_id']}> • độ khớp {r['score']:.2f}",
                value=f"{snippet}\n[Xem tin nhắn]({jump})",
                inline=False,
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MessageSearchCog(bot))
