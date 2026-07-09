"""
cogs/giveaway.py — Hệ thống giveaway: tạo, kết thúc, reroll, list, resume.
Slash: /giveaway, /gend, /greroll, /gwlist
"""

import random
import asyncio
from datetime import datetime, timezone

import discord
from cogs.logger import send_log
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Select

from core.data import (
    ADMIN_IDS, load_giveaways_data, save_giveaways_data,
    _uname, _uname_plain, get_or_fetch_channel,
    GuildContextView as View,
)

# ── State in-memory ──
active_giveaways: dict = {}   # message_id (int) → giveaway dict
_gw_tasks: dict = {}          # message_id (int) → asyncio.Task
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

    # Nếu admin đã chọn winner trước thì dùng luôn
    if gw and gw.get("picked_winner"):
        picked = gw["picked_winner"]
        winner_ids = [picked]
    else:
        count      = min(winners_count, len(entries))
        winner_ids = random.sample(entries, count)
    winner_mentions = ", ".join(f"<@{uid}>" for uid in winner_ids)
    try:
        from cogs.logger import send_log as _sl
        bot_ref = channel.guild._state._get_client()
        import asyncio as _asyncio
        _asyncio.create_task(_sl(bot_ref, "GIVEAWAY_END", f"Kết thúc GW — {prize}",
            fields=[("Winner", winner_mentions, True), ("Host", f"<@{host_id}>", True), ("Kênh", channel.mention, True)]))
    except Exception:
        pass

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
            return await interaction.response.send_message("❌ Giveaway này không còn hoạt động.", ephemeral=True)
        if gw.get("ended"):
            return await interaction.response.send_message("❌ Giveaway đã kết thúc rồi!", ephemeral=True)

        uid = interaction.user.id

        # Kiểm tra role Verify
        try:
            from cogs.invite import _get_verify_role_id
            member = interaction.guild.get_member(uid) if interaction.guild else None
            if member:
                verify_role_id = _get_verify_role_id(interaction.guild.id)
                if not any(r.id == verify_role_id for r in member.roles):
                    return await interaction.response.send_message(
                        "❌ Bạn cần **xác minh tài khoản** trước khi tham gia giveaway.\n"
                        "Gõ `.verify` để nhận link xác minh.",
                        ephemeral=True,
                    )
        except Exception:
            pass

        # Kiểm tra IP — mỗi IP chỉ 1 tài khoản được tham gia giveaway
        try:
            from cogs.invite import _ip_records
            entries_so_far = gw.get("entries", set())
            user_ips = [ip for ip, users in _ip_records.items() if uid in users]
            for ip in user_ips:
                shared_users = _ip_records.get(ip, [])
                conflict = [u for u in shared_users if u != uid and u in entries_so_far]
                if conflict:
                    return await interaction.response.send_message(
                        "⚠️ **Bạn không thể tham gia giveaway này.**\n\n"
                        "Địa chỉ IP của bạn đang được chia sẻ với một tài khoản khác đã tham gia giveaway này. "
                        "Theo chính sách của server, **mỗi địa chỉ IP chỉ được 1 tài khoản tham gia giveaway**.\n\n"
                        "Nếu bạn nghĩ đây là nhầm lẫn (ví dụ: dùng chung mạng gia đình), "
                        "hãy liên hệ admin để được xem xét.",
                        ephemeral=True,
                    )
        except Exception:
            pass  # Nếu import lỗi thì bỏ qua, không chặn

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

        await interaction.response.send_message(msg_reply, ephemeral=True)
        await send_log(interaction.client, "GIVEAWAY_JOIN", f"Tham gia GW #{gw.get('gw_id','?')} — {gw['prize']}",
            fields=[("User", interaction.user.mention, True), ("Tổng tham gia", str(len(entries)), True)])


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

        _gw_tasks[mid] = asyncio.create_task(_giveaway_timer_task(interaction.client, self.channel.id, mid, self.w_count, self.seconds))
        await send_log(interaction.client, "GIVEAWAY_START", f"Tạo GW #{gw_id} — {self.prize}",
            fields=[("Host", self.host.mention, True), ("Thời gian", f"{self.seconds}s", True), ("Số winner", str(self.w_count), True), ("Kênh", self.channel.mention, True)])

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
        except: return await interaction.response.send_message("❌ Thời gian không hợp lệ! Dùng: `30s`, `10m`, `1h`, `2d`", ephemeral=True)
        seconds = {"s": val, "m": val*60, "h": val*3600, "d": val*86400}.get(unit)
        if not seconds:
            return await interaction.response.send_message("❌ Đơn vị thời gian không hợp lệ!", ephemeral=True)
        try:
            w_count = int(self.winners_count.value.strip())
            if w_count < 1: raise ValueError
        except:
            return await interaction.response.send_message("❌ Số người trúng thưởng phải là số nguyên dương!", ephemeral=True)

        end_time     = datetime.now(timezone.utc).timestamp() + seconds
        confirm_view = GiveawayConfirmView(host=interaction.user, channel=interaction.channel, prize=self.prize.value, w_count=w_count, seconds=seconds, end_time=end_time, description=self.description.value or "")
        await interaction.response.send_message(content="## ⚙️ Xác nhận trước khi đăng giveaway", embed=confirm_view.build_preview_embed(), view=confirm_view, ephemeral=True)


async def _giveaway_timer_task(bot, channel_id: int, message_id: int, winners_count: int, seconds: int):
    await asyncio.sleep(seconds)
    gw = active_giveaways.get(message_id)
    if not gw or gw.get("ended"):
        return
    channel = await get_or_fetch_channel(bot, channel_id)
    if not channel:
        return
    # FIX: Task này được tạo bằng asyncio.create_task() (ở resume_active_giveaways lúc
    # bot khởi động, TRƯỚC khi context được set cho guild nào) rồi await asyncio.sleep()
    # rất lâu (đến hàng giờ/ngày) — context lúc tạo task được "đóng băng" cho suốt vòng đời
    # task nên mãi mãi là None. Set lại NGAY TẠI ĐÂY (đã biết chắc channel.guild) để
    # end_giveaway() → send_log()/load_data() bên dưới nhận đúng guild, không rơi vào
    # nhánh "không có guild context" (xem CHANGELOG — cùng nhóm bug với v4.10.3).
    if channel.guild:
        from core.data import set_current_guild
        set_current_guild(channel.guild.id)
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
            try:
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
                        _gw_tasks[mid] = asyncio.create_task(_giveaway_timer_task(self.bot, channel_id, mid, winners_cnt, 0))
                else:
                    _gw_tasks[mid] = asyncio.create_task(_giveaway_timer_task(self.bot, channel_id, mid, winners_cnt, int(remaining)))
                resumed += 1
                print(f"[GIVEAWAY] ▶️  Resume mid={mid} còn {max(0,int(remaining))}s")
            except Exception as e:
                print(f"[GIVEAWAY] ⚠️ Bỏ qua mid={mid} khi resume: {e}")
        if resumed:
            print(f"[GIVEAWAY] ✅ Đã resume {resumed} giveaway")

    # ── Slash commands ──
    @app_commands.command(name="giveaway", description="Tạo giveaway mới")
    async def slash_giveaway(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Chỉ admin mới được tạo giveaway.", ephemeral=True)
        await interaction.response.send_modal(GiveawayModal())

    @app_commands.command(name="gend", description="Kết thúc giveaway sớm")
    @app_commands.describe(gw_id="ID giveaway (GW #?)")
    async def slash_gend(self, interaction: discord.Interaction, gw_id: str):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        try:
            ref = int(gw_id)
        except:
            return await interaction.response.send_message("❌ GW ID không hợp lệ!", ephemeral=True)

        found_mid, gw = None, None
        for mid, g in active_giveaways.items():
            if g.get("gw_id") == ref:
                found_mid, gw = mid, g
                break

        if not gw:
            return await interaction.response.send_message(f"❌ Không tìm thấy GW #{ref}.", ephemeral=True)
        if gw.get("ended"):
            return await interaction.response.send_message("❌ Giveaway đã kết thúc rồi.", ephemeral=True)

        await interaction.response.send_message(f"✅ Đang kết thúc GW #{ref}...", ephemeral=True)
        await send_log(interaction.client, "GIVEAWAY_END", f"Kết thúc sớm GW #{ref} — {gw.get('prize','')}",
            fields=[("Admin", interaction.user.mention, True)])
        channel = await get_or_fetch_channel(self.bot, gw["channel_id"])
        if channel:
            task = _gw_tasks.pop(found_mid, None)
            if task and not task.done():
                task.cancel()
            gw["ended"] = True
            await end_giveaway(found_mid, channel, gw["winners"], gw.get("prize", "phần thưởng"), gw.get("host", 0))

    @app_commands.command(name="greroll", description="Quay số lại giveaway")
    @app_commands.describe(gw_id="ID giveaway (GW #?)")
    async def slash_greroll(self, interaction: discord.Interaction, gw_id: str):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        try:
            ref = int(gw_id)
        except:
            return await interaction.response.send_message("❌ GW ID không hợp lệ!", ephemeral=True)

        gw = None
        for g in active_giveaways.values():
            if g.get("gw_id") == ref:
                gw = g
                break

        if not gw:
            return await interaction.response.send_message(f"❌ Không tìm thấy GW #{ref}.", ephemeral=True)
        entries = list(gw.get("entries", set()))
        if not entries:
            return await interaction.response.send_message("❌ Không có ai tham gia để reroll.", ephemeral=True)
        count      = min(gw.get("winners", 1), len(entries))
        winner_ids = random.sample(entries, count)
        mentions   = ", ".join(f"<@{uid}>" for uid in winner_ids)
        await interaction.response.send_message(f"🔄 Reroll GW #{ref}! Winner mới: {mentions} 🎉", ephemeral=True)
        await send_log(interaction.client, "GIVEAWAY_REROLL", f"Reroll GW #{ref}",
            fields=[("Admin", interaction.user.mention, True), ("Winner mới", mentions, True)])

    @app_commands.command(name="gwlist", description="Xem danh sách người tham gia giveaway")
    @app_commands.describe(gw_id="ID giveaway (GW #?)")
    async def slash_gwlist(self, interaction: discord.Interaction, gw_id: str):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        try:
            ref = int(gw_id)
        except:
            return await interaction.response.send_message("❌ GW ID không hợp lệ!", ephemeral=True)

        gw = None
        for g in active_giveaways.values():
            if g.get("gw_id") == ref:
                gw = g
                break

        if not gw:
            return await interaction.response.send_message(f"❌ Không tìm thấy GW #{ref}.", ephemeral=True)
        entries = list(gw.get("entries", set()))
        if not entries:
            return await interaction.response.send_message("❌ Chưa có ai tham gia.", ephemeral=True)
        mentions = " ".join(f"<@{uid}>" for uid in entries)
        await interaction.response.send_message(
            f"**GW #{ref} — {len(entries)} người tham gia:**\n{mentions[:1900]}", ephemeral=True
        )


    @commands.command(name="gwstatus")
    async def gwstatus(self, ctx):
        """Xem toàn bộ giveaway đang chạy và đã kết thúc trong data."""
        if ctx.author.id not in ADMIN_IDS:
            return
        if not active_giveaways:
            return await ctx.reply("📭 Không có giveaway nào trong data.")
        view  = GwStatusView(bot=self.bot, guild=ctx.guild, page=0)
        await ctx.reply(embed=view._build_embed(0), view=view)

    @commands.command(name="gwpick")
    async def gwpick(self, ctx, gw_id: str = None, user_id: str = None):
        """Chọn winner trước, bot công bố khi hết giờ. Dùng: .gwpick <gw_id> <user_id>"""
        if ctx.author.id not in ADMIN_IDS:
            return
        if not gw_id or not user_id:
            return await ctx.reply("❌ Dùng: `.gwpick <gw_id> <user_id>`")
        try:
            ref = int(gw_id)
        except ValueError:
            return await ctx.reply("❌ GW ID không hợp lệ!")
        try:
            uid = int(user_id)
        except ValueError:
            return await ctx.reply("❌ User ID không hợp lệ!")

        found_gw = None
        for gw in active_giveaways.values():
            if gw.get("gw_id") == ref:
                found_gw = gw
                break

        if not found_gw:
            return await ctx.reply(f"❌ Không tìm thấy giveaway **#{ref}**.")
        if found_gw.get("ended"):
            return await ctx.reply("❌ Giveaway này đã kết thúc rồi.")

        entries = set(found_gw.get("entries", set()))
        if uid not in entries:
            return await ctx.reply(f"❌ Không tìm thấy <@{uid}> trong danh sách người tham gia giveaway **#{ref}**.")

        found_gw["picked_winner"] = uid
        save_giveaways_data(active_giveaways)

        await ctx.reply(f"✅ Đã chọn <@{uid}> làm winner **GW #{ref}**. Bot sẽ công bố khi hết giờ.")
        await send_log(ctx.bot, "GIVEAWAY_END", f"Pick GW #{ref} — {found_gw.get('prize','')}",
            fields=[("Admin", ctx.author.mention, True), ("Winner (chờ công bố)", f"<@{uid}>", True)])

    @commands.command(name="gwreset")
    async def gwreset(self, ctx, gw_id: str = None):
        """Khôi phục giveaway bị kết thúc nhầm. Dùng: .gwreset <gw_id>"""
        if ctx.author.id not in ADMIN_IDS:
            return
        if not gw_id:
            return await ctx.reply("❌ Dùng: `.gwreset <gw_id>`")
        try:
            ref = int(gw_id)
        except ValueError:
            return await ctx.reply("❌ GW ID không hợp lệ!")

        found_mid, found_gw = None, None
        for mid, gw in active_giveaways.items():
            if gw.get("gw_id") == ref:
                found_mid, found_gw = mid, gw
                break

        if not found_gw:
            return await ctx.reply(f"❌ Không tìm thấy giveaway **#{ref}**.")

        end_time  = found_gw.get("end_time", 0)
        now       = datetime.now(timezone.utc).timestamp()
        remaining = int(end_time - now)

        if remaining <= 0:
            return await ctx.reply("❌ Giveaway này đã hết giờ rồi, không thể khôi phục.")

        # Reset trạng thái
        found_gw["ended"]         = False
        found_gw["picked_winner"] = None
        save_giveaways_data(active_giveaways)

        # Khởi động lại timer
        task = _gw_tasks.pop(found_mid, None)
        if task and not task.done():
            task.cancel()
        _gw_tasks[found_mid] = asyncio.create_task(
            _giveaway_timer_task(self.bot, found_gw["channel_id"], found_mid, found_gw["winners"], remaining)
        )

        # Edit embed: xoá field Winner nếu có
        try:
            channel = await get_or_fetch_channel(self.bot, found_gw["channel_id"])
            if channel:
                msg = await channel.fetch_message(found_mid)
                if msg.embeds:
                    embed = msg.embeds[0].copy()
                    new_fields = [f for f in embed.fields if "winner" not in f.name.lower() and "kết quả" not in f.name.lower()]
                    embed.clear_fields()
                    for f in new_fields:
                        embed.add_field(name=f.name, value=f.value, inline=f.inline)
                    # Cập nhật lại field Kết thúc theo end_time gốc
                    for i, f in enumerate(embed.fields):
                        if "kết thúc" in f.name.lower():
                            embed.set_field_at(i, name=f.name, value=f"<t:{int(end_time)}:R>", inline=f.inline)
                            break
                    embed.color = 0xF1C40F
                    view = GiveawayView(found_mid)
                    await msg.edit(embed=embed, view=view)
        except Exception as e:
            await ctx.reply(f"⚠️ Reset data OK nhưng không edit được embed: `{e}`")
            return

        h, r = divmod(remaining, 3600)
        m, s = divmod(r, 60)
        await ctx.reply(f"✅ Đã khôi phục **GW #{ref}**! Còn **{h}h {m}m {s}s** đến khi kết thúc.")


class GwStatusView(View):
    """View phân trang cho .gwstatus — 5 giveaway/trang, nút ◀ ▶, select kết thúc/xoá."""

    PAGE_SIZE = 5

    def __init__(self, bot, guild, page: int = 0):
        super().__init__(timeout=180)
        self.bot   = bot
        self.guild = guild
        self.page  = page
        self._rebuild(page)

    # ── Helpers ──────────────────────────────

    @staticmethod
    def _build_pages(guild) -> tuple[list, list, list]:
        """Trả về (running_lines, ended_items, all_items_flat)."""
        now = datetime.now(timezone.utc).timestamp()
        running, ended = [], []

        for mid, gw in active_giveaways.items():
            gw_id   = gw.get("gw_id", "?")
            prize   = gw.get("prize", "?")
            ch_id   = gw.get("channel_id", 0)
            ch_mention = f"<#{ch_id}>" if ch_id else "?"
            entries = len(gw.get("entries", []))

            if gw.get("ended"):
                winner_ids = gw.get("winner_ids", [])
                def _res(uid, g=guild):
                    m = g.get_member(uid) if g else None
                    return _uname_plain(m) if m else str(uid)
                wstr = ", ".join(_res(u) for u in winner_ids) if winner_ids else "Không có"
                lbl  = f"GW #{gw_id}" if gw_id != "?" else f"GW ? (msg:{str(mid)[-6:]})"
                ended.append({
                    "mid": mid, "gw_id": gw_id, "prize": prize,
                    "line": (
                        f"**{lbl}** — {prize}\n"
                        f"  🏆 Winner: {wstr}  •  👥 {entries} người  •  {ch_mention}\n"
                        f"  🆔 msg: `{mid}`"
                    ),
                })
            else:
                remaining = gw.get("end_time", 0) - now
                h, r = divmod(max(0, int(remaining)), 3600)
                m2, s = divmod(r, 60)
                tstr = f"{h}h {m2}m {s}s còn lại" if remaining > 0 else "⏰ Sắp kết thúc"
                picked = gw.get("picked_winner")
                pick_str = ""
                if picked:
                    pm = guild.get_member(picked) if guild else None
                    pick_str = f"\n  👑 Đã pick: **{_uname_plain(pm) if pm else picked}**"
                running.append({
                    "mid": mid, "gw_id": gw_id, "prize": prize,
                    "line": (
                        f"**GW #{gw_id}** — {prize}\n"
                        f"  ⏰ {tstr}  •  🎊 {gw.get('winners',1)} winner  •  👥 {entries} người  •  {ch_mention}{pick_str}\n"
                        f"  🆔 msg: `{mid}`"
                    ),
                })

        all_flat = running + ended
        return running, ended, all_flat

    def _build_embed(self, page: int) -> discord.Embed:
        running, ended, all_flat = self._build_pages(self.guild)
        total_pages = max(1, -(-len(all_flat) // self.PAGE_SIZE))  # ceil div
        page = max(0, min(page, total_pages - 1))
        self.page = page

        slice_  = all_flat[page * self.PAGE_SIZE: (page + 1) * self.PAGE_SIZE]
        n_run   = len(running)
        n_end   = len(ended)

        embed = discord.Embed(
            title     = "📋  Trạng Thái Giveaway",
            color     = 0xF1C40F,
            timestamp = datetime.now(timezone.utc),
        )

        # Header counts
        embed.add_field(
            name  = "📊 Tổng quan",
            value = f"🟢 Đang chạy: **{n_run}**  •  🔴 Đã kết thúc: **{n_end}**",
            inline= False,
        )

        if not slice_:
            embed.add_field(name="*(Không có giveaway nào)*", value="\u200b", inline=False)
        else:
            for item in slice_:
                status = "🟢" if not active_giveaways.get(item["mid"], {}).get("ended") else "🔴"
                embed.add_field(
                    name  = f"{status} GW #{item['gw_id']} — {item['prize'][:40]}",
                    value = item["line"],
                    inline= False,
                )

        embed.set_footer(
            text=f"Trang {page + 1}/{total_pages}  •  Tổng {len(all_flat)} GW  •  TuyTam Store"
        )
        return embed

    def _rebuild(self, page: int):
        self.clear_items()
        running, ended, all_flat = self._build_pages(self.guild)
        total_pages = max(1, -(-len(all_flat) // self.PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))
        self.page = page

        # Items trên trang hiện tại
        slice_ = all_flat[page * self.PAGE_SIZE: (page + 1) * self.PAGE_SIZE]

        # Nút ◀ ▶
        prev_btn = Button(emoji="◀", style=discord.ButtonStyle.secondary,
                          custom_id="gw_prev", disabled=(page == 0), row=0)
        next_btn = Button(emoji="▶", style=discord.ButtonStyle.secondary,
                          custom_id="gw_next", disabled=(page >= total_pages - 1), row=0)
        prev_btn.callback = self._prev
        next_btn.callback = self._next
        self.add_item(prev_btn)
        self.add_item(next_btn)

        # Select kết thúc sớm — chỉ GW đang chạy trên trang này
        running_opts = [
            discord.SelectOption(
                label=f"GW #{gw['gw_id']} — {gw['prize'][:40]}"[:100],
                value=str(gw["mid"]),
                description="Đang chạy",
            )
            for gw in slice_
            if not active_giveaways.get(gw["mid"], {}).get("ended")
        ]
        if running_opts:
            end_sel = Select(
                placeholder="⚡ Kết thúc sớm giveaway...",
                options=running_opts,
                custom_id="gw_end_select",
                row=1,
            )
            end_sel.callback = self._end_early_callback
            self.add_item(end_sel)

        # Select xoá — tất cả GW trên trang này
        all_opts = [
            discord.SelectOption(
                label=f"GW #{gw['gw_id']} — {gw['prize'][:40]}"[:100],
                value=str(gw["mid"]),
                description="Đã kết thúc" if active_giveaways.get(gw["mid"], {}).get("ended") else "Đang chạy",
            )
            for gw in slice_
        ]
        if all_opts:
            del_sel = Select(
                placeholder="🗑️ Xoá giveaway khỏi data...",
                options=all_opts,
                custom_id="gw_del_select",
                row=2,
            )
            del_sel.callback = self._delete_callback
            self.add_item(del_sel)

    # ── Callbacks ─────────────────────────────

    async def _prev(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        self._rebuild(self.page - 1)
        await interaction.response.edit_message(embed=self._build_embed(self.page), view=self)

    async def _next(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        self._rebuild(self.page + 1)
        await interaction.response.edit_message(embed=self._build_embed(self.page), view=self)

    async def _end_early_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        try:
            mid = int(interaction.data["values"][0])
        except:
            return await interaction.response.send_message("❌ ID không hợp lệ.", ephemeral=True)

        gw = active_giveaways.get(mid)
        if not gw:
            return await interaction.response.send_message("❌ Không tìm thấy giveaway.", ephemeral=True)
        if gw.get("ended"):
            return await interaction.response.send_message("⚠️ Giveaway đã kết thúc rồi.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        channel = await get_or_fetch_channel(self.bot, gw["channel_id"])
        if not channel:
            return await interaction.followup.send("❌ Không tìm thấy kênh.", ephemeral=True)

        task = _gw_tasks.pop(mid, None)
        if task and not task.done():
            task.cancel()
        gw["ended"] = True
        await end_giveaway(mid, channel, gw["winners"], gw.get("prize", "phần thưởng"), gw.get("host", 0))
        await send_log(self.bot, "GIVEAWAY_END",
            f"Kết thúc sớm GW #{gw.get('gw_id','?')} — {gw.get('prize','')}",
            fields=[("Admin", interaction.user.mention, True)])
        self._rebuild(self.page)
        await interaction.followup.send(
            f"✅ Đã kết thúc **GW #{gw.get('gw_id','?')}** — {gw.get('prize','')}",
            ephemeral=True,
        )

    async def _delete_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        try:
            mid = int(interaction.data["values"][0])
        except:
            return await interaction.response.send_message("❌ ID không hợp lệ.", ephemeral=True)

        gw = active_giveaways.pop(mid, None)
        if gw is None:
            return await interaction.response.send_message("❌ Không tìm thấy giveaway.", ephemeral=True)

        task = _gw_tasks.pop(mid, None)
        if task and not task.done():
            task.cancel()
        save_giveaways_data(active_giveaways)
        await send_log(self.bot, "GIVEAWAY_END",
            f"Xoá GW #{gw.get('gw_id','?')} — {gw.get('prize','')}",
            fields=[("Admin", interaction.user.mention, True)])
        self._rebuild(self.page)
        await interaction.response.send_message(
            f"🗑️ Đã xoá **GW #{gw.get('gw_id','?')}** — {gw.get('prize','')} khỏi data.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))
