"""
cogs/giveaway.py — Hệ thống giveaway: tạo, kết thúc, reroll, list, resume.
Slash: /giveaway, /gend, /greroll, /gwlist
"""

import random
import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput

from core.data import (
    ADMIN_IDS, load_giveaways_data, save_giveaways_data,
    _uname, _uname_plain, get_or_fetch_channel,
)

# ── State in-memory ──
active_giveaways: dict = {}   # message_id (int) → giveaway dict
_gw_counter: int = 0          # ID giveaway tự tăng từ 1

def _next_gw_id() -> int:
    global _gw_counter
    _gw_counter += 1
    return _gw_counter


def _get_net_invites_from_cog(user_id: int) -> tuple:
    """Lazy import để tránh circular — lấy invite stats từ cog invite."""
    try:
        from cogs.invite import _get_net_invites
        return _get_net_invites(user_id)
    except Exception:
        return 0, 0, 0, 0


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════
async def end_giveaway(message_id, channel, winners_count, prize, host_id):
    gw = active_giveaways.get(message_id) or active_giveaways.get(str(message_id))
    if gw:
        gw["ended"] = True
    save_giveaways_data(active_giveaways)

    try:
        msg = await channel.fetch_message(message_id)
    except Exception:
        return

    entries = list(gw.get("entries", set())) if gw else []

    if not entries:
        # Giữ embed gốc, chỉ thêm thông báo không có người tham gia
        orig = msg.embeds[0] if msg.embeds else None
        if orig:
            embed = orig.copy()
            embed.color = 0x99AAB5
            embed.add_field(name="❌ Kết quả", value="Không có ai tham gia giveaway này.", inline=False)
        else:
            embed = discord.Embed(title="🎉  Giveaway Kết Thúc", description="❌ Không có ai tham gia giveaway này.", color=0x99AAB5, timestamp=datetime.now(timezone.utc))
        await msg.edit(embed=embed, view=None)
        await channel.send("❌ Giveaway kết thúc nhưng không có người tham gia!")
        return

    count        = min(winners_count, len(entries))
    winner_ids   = random.sample(entries, count)
    winner_mentions = ", ".join(f"<@{uid}>" for uid in winner_ids)

    # Giữ nguyên embed gốc, chỉ thêm field winner
    orig = msg.embeds[0] if msg.embeds else None
    if orig:
        embed = orig.copy()
        embed.add_field(name="🏆 Winner", value=winner_mentions, inline=False)
    else:
        host  = channel.guild.get_member(host_id)
        embed = discord.Embed(title="🎉  GIVEAWAY", description=f"**Phần thưởng:** {prize}", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏆 Winner", value=winner_mentions, inline=False)
        embed.set_footer(text=f"Host: {_uname_plain(host) if host else host_id}")
    await msg.edit(embed=embed, view=None)
    await channel.send(f"🎊 Chúc mừng {winner_mentions}! Bạn đã thắng **{prize}**!")

    if gw:
        gw["winner_ids"] = winner_ids
        save_giveaways_data(active_giveaways)
        if gw.get("send_invite", False):
            await _check_winner_invites(channel, winner_ids, prize)


async def giveaway_timer(channel_id: int, message_id: int, winners_count: int, seconds: int):
    await asyncio.sleep(seconds)
    gw = active_giveaways.get(message_id)
    if not gw or gw.get("ended"):
        return
    channel = discord.utils.get(__import__("discord").utils.find(lambda g: g.get_channel(channel_id), []), id=channel_id) if False else None
    # Lấy channel qua bot instance được truyền vào qua Cog
    # Sẽ được gọi từ GiveawayCog._giveaway_timer thay thế


async def _check_winner_invites(channel, winner_ids, prize):
    lines  = []
    medals = ["🥇", "🥈", "🥉"]
    for i, uid in enumerate(winner_ids):
        icon   = medals[i] if i < len(medals) else f"`{i+1}.`"
        member = channel.guild.get_member(uid)
        name   = _uname(member) if member else f"<@{uid}>"
        total, fake, left, net = _get_net_invites_from_cog(uid)
        lines.append(f"{icon} **{name}**\n  ✅ Net: **{net}**  •  📊 Tổng: `{total}`  •  ⚠️ Fake: `{fake}`  •  🚪 Rời: `{left}`")
    embed = discord.Embed(title="📨  Thống Kê Invite — Winner Giveaway", description="\n".join(lines) if lines else "*(không có winner nào)*", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="🏆 Phần thưởng", value=prize, inline=False)
    embed.set_footer(text="Net = Tổng − Fake − Đã rời  •  TuyTam Store")
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[GIVEAWAY] ⚠️ Không gửi được check invite winner: {e}")


# ══════════════════════════════════════════
# VIEWS / MODALS
# ══════════════════════════════════════════
class GiveawayView(View):
    def __init__(self, message_id: int = None):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="🎉 Tham gia", style=discord.ButtonStyle.primary, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: Button):
        mid = interaction.message.id
        gw  = active_giveaways.get(mid) or active_giveaways.get(str(mid))
        if not gw:
            return await interaction.response.send_message("❌ Giveaway này không còn hoạt động.")
        if gw.get("ended"):
            return await interaction.response.send_message("❌ Giveaway đã kết thúc rồi!")

        uid     = interaction.user.id
        entries = gw.setdefault("entries", set())
        if not isinstance(entries, set):
            gw["entries"] = set(entries)
            entries = gw["entries"]

        if uid in entries:
            entries.discard(uid)
            msg_reply = "↩️ Bạn đã **rút khỏi** giveaway."
        else:
            entries.add(uid)
            msg_reply = "✅ Bạn đã **tham gia** giveaway!"

        save_giveaways_data(active_giveaways)

        try:
            msg   = await interaction.channel.fetch_message(mid)
            embed = msg.embeds[0]
            for i, field in enumerate(embed.fields):
                if "Người tham gia" in field.name:
                    embed.set_field_at(i, name=field.name, value=f"**{len(entries)}** người", inline=field.inline)
                    await msg.edit(embed=embed)
                    break
        except Exception as e:
            print(f"[GIVEAWAY] ⚠️ Không cập nhật được embed: {e}")

        await interaction.response.send_message(msg_reply)


class GiveawayConfirmView(View):
    def __init__(self, host, channel, prize, w_count, seconds, end_time, description):
        super().__init__(timeout=120)
        self.host        = host
        self.channel     = channel
        self.prize       = prize
        self.w_count     = w_count
        self.seconds     = seconds
        self.end_time    = end_time
        self.description = description
        self.send_invite = False
        self._update_button_label()

    def _update_button_label(self):
        for item in self.children:
            if getattr(item, "custom_id", None) == "gw_toggle_invite":
                item.label = "📨 Check Invite Winner: BẬT" if self.send_invite else "📨 Check Invite Winner: TẮT"
                item.style = discord.ButtonStyle.success if self.send_invite else discord.ButtonStyle.secondary
                break

    def build_preview_embed(self) -> discord.Embed:
        invite_status = "✅ **BẬT** — Bot sẽ tự kiểm tra & hiển thị số invite của winner" if self.send_invite else "❌ **TẮT** — Không kiểm tra invite tự động"
        embed = discord.Embed(title="👀  Xem Trước Giveaway", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏆 Phần thưởng",           value=self.prize,                   inline=False)
        embed.add_field(name="🎊 Số người thắng",        value=f"**{self.w_count}** người",  inline=True)
        embed.add_field(name="⏰ Kết thúc",              value=f"<t:{int(self.end_time)}:R>", inline=True)
        embed.add_field(name="📨 Kiểm tra Invite Winner", value=invite_status,               inline=False)
        if self.description:
            embed.add_field(name="📝 Mô tả", value=self.description, inline=False)
        embed.set_footer(text="Nhấn Toggle để bật/tắt • Nhấn Xác Nhận để đăng")
        return embed

    @discord.ui.button(label="📨 Check Invite Winner: TẮT", style=discord.ButtonStyle.secondary, custom_id="gw_toggle_invite")
    async def toggle_invite(self, interaction: discord.Interaction, button: Button):
        self.send_invite = not self.send_invite
        self._update_button_label()
        await interaction.response.edit_message(embed=self.build_preview_embed(), view=self)

    @discord.ui.button(label="✅ Xác Nhận & Đăng", style=discord.ButtonStyle.primary, custom_id="gw_confirm")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="✅ Đang đăng giveaway...", view=self)

        gw_embed = discord.Embed(title=f"🎉  GIVEAWAY — {self.prize}", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
        gw_embed.add_field(name="🏆 Phần thưởng",   value=f"**{self.prize}**",                    inline=False)
        gw_embed.add_field(name="🎊 Số người thắng", value=f"**{self.w_count}** người",           inline=True)
        gw_embed.add_field(name="⏰ Kết thúc",       value=f"<t:{int(self.end_time)}:R>",         inline=True)
        gw_embed.add_field(name="👥 Người tham gia",  value="**0** người",                        inline=True)
        if self.description:
            gw_embed.add_field(name="📝 Mô tả", value=self.description, inline=False)
        gw_id = _next_gw_id()
        gw_embed.set_footer(text=f"Host: {_uname_plain(self.host)}  •  GW #{gw_id}  •  Nhấn nút để tham gia!")

        view    = GiveawayView()
        gw_msg  = await self.channel.send(embed=gw_embed, view=view)
        mid     = gw_msg.id

        active_giveaways[mid] = {
            "channel_id":  self.channel.id,
            "prize":       self.prize,
            "winners":     self.w_count,
            "end_time":    self.end_time,
            "host":        self.host.id,
            "entries":     set(),
            "ended":       False,
            "type":        "button",
            "send_invite": self.send_invite,
            "gw_id":       gw_id,
        }
        save_giveaways_data(active_giveaways)

        asyncio.create_task(_giveaway_timer_task(interaction.client, self.channel.id, mid, self.w_count, self.seconds))

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.danger, custom_id="gw_cancel")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.stop()
        await interaction.response.edit_message(content="🚫 Đã huỷ giveaway.", embed=None, view=None)


class GiveawayModal(discord.ui.Modal, title="🎉 Tạo Giveaway"):
    duration = discord.ui.TextInput(label="Thời gian", placeholder="Ví dụ: 30s / 10m / 1h / 2d", min_length=2, max_length=10)
    winners_count = discord.ui.TextInput(label="Số người trúng thưởng", placeholder="Ví dụ: 1", min_length=1, max_length=2)
    prize = discord.ui.TextInput(label="Phần thưởng", placeholder="Ví dụ: 100m ingame, Elytra...", min_length=1, max_length=200)
    description = discord.ui.TextInput(label="Mô tả (tuỳ chọn)", placeholder="Điều kiện tham gia, ghi chú thêm...", style=discord.TextStyle.paragraph, required=False, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        dur  = self.duration.value.strip()
        unit = dur[-1].lower()
        try: val = int(dur[:-1])
        except: return await interaction.response.send_message("❌ Thời gian không hợp lệ! Dùng: `30s`, `10m`, `1h`, `2d`")
        seconds = {"s": val, "m": val*60, "h": val*3600, "d": val*86400}.get(unit)
        if not seconds:
            return await interaction.response.send_message("❌ Đơn vị thời gian không hợp lệ!")
        try:
            w_count = int(self.winners_count.value.strip())
            if w_count < 1: raise ValueError
        except:
            return await interaction.response.send_message("❌ Số người trúng thưởng phải là số nguyên dương!")

        end_time     = datetime.now(timezone.utc).timestamp() + seconds
        confirm_view = GiveawayConfirmView(host=interaction.user, channel=interaction.channel, prize=self.prize.value, w_count=w_count, seconds=seconds, end_time=end_time, description=self.description.value or "")
        await interaction.response.send_message(content="## ⚙️ Xác nhận trước khi đăng giveaway", embed=confirm_view.build_preview_embed(), view=confirm_view)


async def _giveaway_timer_task(bot, channel_id: int, message_id: int, winners_count: int, seconds: int):
    await asyncio.sleep(seconds)
    gw = active_giveaways.get(message_id)
    if not gw or gw.get("ended"):
        return
    channel = await get_or_fetch_channel(bot, channel_id)
    if not channel:
        return
    gw["ended"] = True
    await end_giveaway(message_id, channel, winners_count, gw.get("prize", "phần thưởng"), gw.get("host", 0))


# ══════════════════════════════════════════
# COG
# ══════════════════════════════════════════
class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def resume_active_giveaways(self):
        global _gw_counter
        saved = load_giveaways_data()
        if not saved: return
        # Sync counter theo gw_id cao nhất đã lưu
        max_id = max((gw.get("gw_id", 0) for gw in saved.values()), default=0)
        if max_id > _gw_counter:
            _gw_counter = max_id
        now     = datetime.now(timezone.utc).timestamp()
        resumed = 0
        for mid, gw in saved.items():
            active_giveaways[mid] = gw
            if gw.get("ended"):
                continue
            channel_id  = gw.get("channel_id")
            winners_cnt = gw.get("winners", 1)
            end_time    = gw.get("end_time", 0)
            remaining   = end_time - now

            if remaining <= 0:
                channel = await get_or_fetch_channel(self.bot, channel_id)
                if channel:
                    asyncio.create_task(_giveaway_timer_task(self.bot, channel_id, mid, winners_cnt, 0))
            else:
                asyncio.create_task(_giveaway_timer_task(self.bot, channel_id, mid, winners_cnt, int(remaining)))
            resumed += 1
            print(f"[GIVEAWAY] ▶️  Resume mid={mid} còn {max(0,int(remaining))}s")
        if resumed:
            print(f"[GIVEAWAY] ✅ Đã resume {resumed} giveaway")

    # ── Slash commands ──
    @app_commands.command(name="giveaway", description="Tạo giveaway mới")
    async def slash_giveaway(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Chỉ admin mới được tạo giveaway.")
        await interaction.response.send_modal(GiveawayModal())

    @app_commands.command(name="gend", description="Kết thúc giveaway sớm")
    @app_commands.describe(message_id="ID tin nhắn giveaway")
    async def slash_gend(self, interaction: discord.Interaction, message_id: str):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Chỉ admin.")
        try: mid = int(message_id)
        except: return await interaction.response.send_message("❌ ID không hợp lệ!")
        gw = active_giveaways.get(mid)
        if not gw: return await interaction.response.send_message("❌ Không tìm thấy giveaway đang chạy.")
        await interaction.response.send_message("✅ Đang kết thúc giveaway...")
        channel = await get_or_fetch_channel(self.bot, gw["channel_id"])
        if channel:
            await end_giveaway(mid, channel, gw["winners"], gw.get("prize", "phần thưởng"), gw.get("host", 0))

    @app_commands.command(name="greroll", description="Quay số lại giveaway")
    @app_commands.describe(message_id="ID tin nhắn giveaway")
    async def slash_greroll(self, interaction: discord.Interaction, message_id: str):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Chỉ admin.")
        try: mid = int(message_id)
        except: return await interaction.response.send_message("❌ ID không hợp lệ!")
        gw = active_giveaways.get(mid)
        if not gw: return await interaction.response.send_message("❌ Không tìm thấy giveaway này.")
        entries = list(gw.get("entries", set()))
        if not entries: return await interaction.response.send_message("❌ Không có ai tham gia để reroll.")
        count       = min(gw.get("winners", 1), len(entries))
        winner_ids  = random.sample(entries, count)
        mentions    = ", ".join(f"<@{uid}>" for uid in winner_ids)
        await interaction.response.send_message(f"🔄 Reroll! Winner mới: {mentions} 🎉")

    @app_commands.command(name="gwlist", description="Xem danh sách người tham gia giveaway")
    @app_commands.describe(message_id="ID tin nhắn giveaway")
    async def slash_gwlist(self, interaction: discord.Interaction, message_id: str):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Chỉ admin.")
        try: mid = int(message_id)
        except: return await interaction.response.send_message("❌ ID không hợp lệ!")
        gw = active_giveaways.get(mid)
        if not gw: return await interaction.response.send_message("❌ Không tìm thấy giveaway này.")
        entries = list(gw.get("entries", set()))
        if not entries: return await interaction.response.send_message("❌ Chưa có ai tham gia.")
        mentions = " ".join(f"<@{uid}>" for uid in entries)
        await interaction.response.send_message(f"**{len(entries)} người tham gia:**\n{mentions[:1900]}")


    @commands.command(name="gpick", hidden=True)
    async def gpick(self, ctx, gw_ref: str, *, target: str):
        """[HIDDEN] Admin chọn tay winner cho giveaway. Dùng: .gpick <gw_id hoặc message_id> <@mention/username/user_id>"""
        if ctx.author.id not in ADMIN_IDS:
            return

        # Tìm giveaway theo gw_id (số) hoặc message_id
        found_mid = None
        found_gw  = None

        if gw_ref.isdigit():
            ref_int = int(gw_ref)
            # Thử khớp gw_id trước
            for mid, gw in active_giveaways.items():
                if gw.get("gw_id") == ref_int:
                    found_mid, found_gw = mid, gw
                    break
            # Nếu không khớp gw_id, thử message_id
            if not found_gw and ref_int in active_giveaways:
                found_mid = ref_int
                found_gw  = active_giveaways[ref_int]

        if not found_gw:
            return await ctx.reply(f"❌ Không tìm thấy giveaway `#{gw_ref}`.")

        if found_gw.get("ended"):
            return await ctx.reply("❌ Giveaway này đã kết thúc rồi.")

        # Resolve target → member
        target = target.strip()
        member = None

        # Thử mention <@id>
        if target.startswith("<@") and target.endswith(">"):
            uid_str = target[2:-1].lstrip("!")
            if uid_str.isdigit():
                member = ctx.guild.get_member(int(uid_str)) or await ctx.guild.fetch_member(int(uid_str)).catch(None)
        # Thử user ID thuần
        if not member and target.isdigit():
            try:
                member = ctx.guild.get_member(int(target)) or await ctx.guild.fetch_member(int(target))
            except Exception:
                pass
        # Thử username / display name
        if not member:
            t_lower = target.lower()
            member = discord.utils.find(
                lambda m: m.name.lower() == t_lower or m.display_name.lower() == t_lower,
                ctx.guild.members
            )

        if not member:
            return await ctx.reply(f"❌ Không tìm thấy user `{target}`.")

        # Force winner
        winner_ids      = [member.id]
        winner_mentions = member.mention
        gw_id_label     = f"#{found_gw.get('gw_id', '?')}"

        # Cập nhật embed giveaway
        try:
            channel = await get_or_fetch_channel(self.bot, found_gw["channel_id"])
            msg     = await channel.fetch_message(found_mid)
            orig    = msg.embeds[0] if msg.embeds else None
            if orig:
                embed = orig.copy()
                embed.add_field(name="🏆 Winner", value=winner_mentions, inline=False)
            else:
                embed = discord.Embed(title="🎉  GIVEAWAY", color=0xF1C40F)
                embed.add_field(name="🏆 Winner", value=winner_mentions, inline=False)
            await msg.edit(embed=embed, view=None)
        except Exception as e:
            await ctx.reply(f"⚠️ Không cập nhật được embed: {e}")

        # Đánh dấu kết thúc & lưu
        found_gw["ended"]      = True
        found_gw["winner_ids"] = winner_ids
        save_giveaways_data(active_giveaways)

        await ctx.reply(f"✅ Đã chọn {winner_mentions} làm winner giveaway {gw_id_label}!")
        if channel:
            await channel.send(f"🎊 Chúc mừng {winner_mentions}! Bạn đã trúng **{found_gw.get('prize', '')}**!")


async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))
