# cogs/giveaway.py — Giveaway system
from config import *
import re as _re
import random

async def end_giveaway(message_id: int, channel: discord.TextChannel, winners_count: int, prize: str, host_id: int, forced_winners: list = None):
    """Kết thúc giveaway. Nếu forced_winners được truyền vào thì dùng danh sách đó, ngược lại random."""
    try:
        msg = await channel.fetch_message(message_id)
    except:
        return

    if forced_winners:
        winners = forced_winners
    else:
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        entries = [u async for u in reaction.users() if not u.bot] if reaction else []
        gw = active_giveaways.get(message_id, {})
        btn_entries = [channel.guild.get_member(uid) for uid in gw.get("entries", set())]
        btn_entries = [m for m in btn_entries if m]
        entries = list({u.id: u for u in entries + btn_entries}.values())

        if not entries:
            embed = discord.Embed(
                title="🎉  Giveaway Kết Thúc",
                description="❌ Không có ai tham gia giveaway này.",
                color=0x99AAB5, timestamp=datetime.now(timezone.utc)
            )
            try:
                await msg.edit(embed=embed, view=None)
            except:
                pass
            await channel.send("❌ Giveaway kết thúc nhưng không có người tham gia!")
            if message_id in active_giveaways:
                active_giveaways[message_id]["ended"] = True
            save_giveaways_data()
            return

        count = min(winners_count, len(entries))
        winners = random.sample(entries, count)

    winner_mentions = ", ".join(w.mention for w in winners)
    host = channel.guild.get_member(host_id)
    embed = discord.Embed(
        title="🎉  Giveaway Kết Thúc!",
        description=f"**Phần thưởng:** {prize}\n**🏆 Winner:** {winner_mentions}",
        color=0xF1C40F, timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Host: {_uname_plain(host) if host else host_id}")
    try:
        await msg.edit(embed=embed, view=None)
    except:
        pass
    await channel.send(f"🎊 Chúc mừng {winner_mentions}! Bạn đã thắng **{prize}**!")
    if message_id in active_giveaways:
        active_giveaways[message_id]["ended"] = True
        active_giveaways[message_id]["winner_ids"] = [w.id for w in winners]
    save_giveaways_data()

@bot.command(name="gstart")
async def gstart_cmd(ctx, time_str: str = None, winners: str = None, *, prize: str = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not time_str or not winners or not prize:
        return await ctx.reply("❌ Dùng: `.gstart <time> <winners> <prize>`\nVí dụ: `.gstart 10m 1 100m ingame`")
    duration = parse_time(time_str)
    if duration <= 0:
        return await ctx.reply("❌ Thời gian không hợp lệ! Dùng: `30s`, `10m`, `1h`, `1d`")
    try:
        w_count = max(1, int(winners))
    except ValueError:
        return await ctx.reply("❌ Số người thắng phải là số!")
    ends_at = int(datetime.now(timezone.utc).timestamp()) + duration
    embed = discord.Embed(
        title="🎉  GIVEAWAY",
        description=(
            f"**Phần thưởng:** {prize}\n\n"
            f"React 🎉 để tham gia!\n"
            f"⏰ Kết thúc: <t:{ends_at}:R>\n"
            f"🏆 Số người thắng: **{w_count}**"
        ),
        color=0xF1C40F,
        timestamp=datetime.fromtimestamp(ends_at, tz=timezone.utc)
    )
    embed.set_footer(text=f"Host: {_uname_plain(ctx.author)}  •  Kết thúc lúc")
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")
    try:
        await ctx.message.delete()
    except:
        pass
    active_giveaways[msg.id] = {
        "type": "reaction",                 # phân biệt với slash /giveaway
        "channel_id": ctx.channel.id,
        "winners": w_count,
        "prize": prize,
        "host_id": ctx.author.id,
        "end_time": ends_at,
        "ended": False,
    }
    save_giveaways_data()

    async def _countdown():
        await asyncio.sleep(duration)
        if not active_giveaways.get(msg.id, {}).get("ended"):
            await end_giveaway(msg.id, ctx.channel, w_count, prize, ctx.author.id)
    asyncio.create_task(_countdown())

@bot.command(name="greroll")
async def greroll_cmd(ctx, message_id: int = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not message_id:
        return await ctx.reply("❌ Dùng: `.greroll <message_id>`")
    try:
        msg = await ctx.channel.fetch_message(message_id)
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        entries_reaction = [u async for u in reaction.users() if not u.bot] if reaction else []
        gw = active_giveaways.get(message_id, {})
        entries_btn = [ctx.guild.get_member(uid) for uid in gw.get("entries", set())]
        entries_btn = [m for m in entries_btn if m]
        entries = entries_reaction or entries_btn
        if not entries:
            return await ctx.reply("❌ Không có người tham gia hợp lệ!")
        winner = random.choice(entries)
        prize = gw.get("prize", "phần thưởng")
        await ctx.send(f"🎊 **Reroll!** Chúc mừng {winner.mention}! Bạn đã thắng **{prize}**!")
    except discord.NotFound:
        await ctx.reply("❌ Không tìm thấy tin nhắn!")
    except Exception as e:
        await ctx.reply(f"❌ Lỗi: `{e}`")


@bot.command(name="gpick", aliases=["gwin", "gwinner"])
async def gpick_cmd(ctx, message_id: int = None, *, targets: str = None):
    """
    Admin chỉ định winner cho giveaway thay vì random.
    Dùng: .gpick <message_id> <@mention | username | display name | ID> ...
    Nếu không dùng lệnh này, giveaway sẽ tự random khi hết giờ.
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not message_id:
        return await ctx.reply("❌ Dùng: `.gpick <message_id> <user1> <user2> ...`")
    if not targets:
        return await ctx.reply("❌ Phải chỉ định ít nhất 1 người thắng!")

    gw = active_giveaways.get(message_id)
    if not gw:
        return await ctx.reply("❌ Không tìm thấy giveaway với ID này!\n> ℹ️ Chỉ hoạt động khi bot còn giữ data của giveaway.")
    if gw.get("ended"):
        return await ctx.reply("❌ Giveaway này đã kết thúc rồi!")

    channel = bot.get_channel(gw["channel_id"])
    if not channel:
        return await ctx.reply("❌ Không tìm thấy kênh của giveaway!")

    # Parse từng token: mention, ID, username, hoặc display name
    import re as _re2
    tokens = targets.split()
    forced = []
    not_found = []
    for token in tokens:
        member = None
        # mention <@id> hoặc <@!id>
        m = _re2.match(r"<@!?(\d+)>", token)
        if m:
            member = ctx.guild.get_member(int(m.group(1)))
        # ID thuần
        elif token.isdigit():
            member = ctx.guild.get_member(int(token))
        # username hoặc display name (case-insensitive)
        else:
            token_lower = token.lower()
            member = discord.utils.find(
                lambda m: m.name.lower() == token_lower or m.display_name.lower() == token_lower,
                ctx.guild.members
            )
        if member:
            if member not in forced:
                forced.append(member)
        else:
            not_found.append(token)

    if not_found:
        return await ctx.reply(f"❌ Không tìm thấy thành viên: {', '.join(f'`{t}`' for t in not_found)}")
    if not forced:
        return await ctx.reply("❌ Không tìm thấy ai hợp lệ!")

    prize = gw.get("prize", "phần thưởng")
    await end_giveaway(message_id, channel, len(forced), prize, gw.get("host_id", ctx.author.id), forced_winners=forced)
    winner_mentions = ", ".join(m.mention for m in forced)
    await ctx.reply(f"✅ Đã chỉ định winner cho giveaway **{prize}**: {winner_mentions}")

@bot.command(name="gwlist")
async def gwlist_cmd(ctx, message_id: int = None):
    """
    Xem danh sách người tham gia giveaway.
    Dùng: .gwlist <message_id>
    """
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not message_id:
        return await ctx.reply("❌ Dùng: `.gwlist <message_id>`\nVí dụ: `.gwlist 1234567890123456789`")

    gw = active_giveaways.get(message_id)
    if not gw:
        return await ctx.reply("❌ Không tìm thấy giveaway với ID này!\n> ℹ️ Giveaway có thể đã bị xoá khỏi bộ nhớ. Chỉ hoạt động khi bot còn giữ data.")

    entries = gw.get("entries", set())
    if not isinstance(entries, set):
        entries = set(entries)

    prize    = gw.get("prize", "?")
    ended    = gw.get("ended", False)
    w_count  = gw.get("winners", 1)
    end_time = gw.get("end_time", 0)

    status_str = "✅ Đã kết thúc" if ended else f"🟢 Đang chạy — kết thúc <t:{int(end_time)}:R>"

    embed = discord.Embed(
        title="👥  Danh Sách Người Tham Gia Giveaway",
        color=0xF1C40F if not ended else 0x99AAB5,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏆 Phần thưởng", value=prize,            inline=True)
    embed.add_field(name="🎊 Số người thắng", value=f"**{w_count}**", inline=True)
    embed.add_field(name="📊 Trạng thái",   value=status_str,      inline=False)
    embed.add_field(name="👥 Tổng tham gia", value=f"**{len(entries)}** người", inline=True)

    if entries:
        mentions = []
        for uid in entries:
            member = ctx.guild.get_member(int(uid))
            mentions.append(member.mention if member else f"`{uid}`")

        # Chia thành nhiều field nếu danh sách dài (giới hạn 1024 ký tự/field)
        chunk_size = 20
        chunks = [mentions[i:i+chunk_size] for i in range(0, len(mentions), chunk_size)]
        for idx, chunk in enumerate(chunks):
            field_name = "📋 Danh sách" if idx == 0 else f"📋 (tiếp {idx+1})"
            embed.add_field(name=field_name, value=" ".join(chunk), inline=False)
    else:
        embed.add_field(name="📋 Danh sách", value="*(Chưa có ai tham gia)*", inline=False)

    if gw.get("winner_ids"):
        winner_mentions = ", ".join(
            ctx.guild.get_member(wid).mention if ctx.guild.get_member(wid) else f"`{wid}`"
            for wid in gw["winner_ids"]
        )
        embed.add_field(name="🏆 Winner", value=winner_mentions, inline=False)

    embed.set_footer(text=f"Message ID: {message_id}  •  Yêu cầu bởi {_uname_plain(ctx.author)}")
    await ctx.reply(embed=embed)

@bot.command(name="gend")
async def gend_cmd(ctx, message_id: int = None):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.reply("❌ Chỉ admin mới dùng được.")
    if not message_id:
        return await ctx.reply("❌ Dùng: `.gend <message_id>`")
    gw = active_giveaways.get(message_id)
    if not gw:
        return await ctx.reply("❌ Không tìm thấy giveaway đang hoạt động!")
    if gw.get("ended"):
        return await ctx.reply("❌ Giveaway này đã kết thúc rồi!")
    host_id = gw.get("host_id") or gw.get("host", 0)
    await end_giveaway(message_id, ctx.channel, gw["winners"], gw["prize"], host_id)
    await ctx.reply("✅ Đã kết thúc giveaway sớm!")

# ================= INFO COMMANDS =================

class GiveawayView(View):
    def __init__(self, message_id: int = None):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(label="🎉 Tham gia", style=discord.ButtonStyle.primary, custom_id="giveaway_join")
    async def join(self, interaction: discord.Interaction, button: Button):
        mid = interaction.message.id
        gw = active_giveaways.get(mid) or active_giveaways.get(str(mid))
        if not gw:
            return await interaction.response.send_message("❌ Giveaway này không còn hoạt động.", ephemeral=True)
        if gw.get("ended"):
            return await interaction.response.send_message("❌ Giveaway đã kết thúc rồi!", ephemeral=True)

        uid = interaction.user.id
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

        save_giveaways_data()

        try:
            msg = await interaction.channel.fetch_message(mid)
            embed = msg.embeds[0]
            updated = False
            for i, field in enumerate(embed.fields):
                if "Người tham gia" in field.name:
                    embed.set_field_at(i, name=field.name, value=f"**{len(entries)}** người", inline=field.inline)
                    updated = True
                    break
            if updated:
                await msg.edit(embed=embed)
        except Exception as e:
            print(f"[GIVEAWAY] ⚠️ Không cập nhật được embed: {e}")

        await interaction.response.send_message(msg_reply, ephemeral=True)

async def giveaway_timer(channel_id: int, message_id: int, winners_count: int, seconds: int):
    await asyncio.sleep(seconds)
    gw = active_giveaways.get(message_id)
    if not gw or gw.get("ended"):
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        return

    gw["ended"] = True
    entries = list(gw.get("entries", set()))

    try:
        msg = await channel.fetch_message(message_id)
    except Exception:
        return

    if not entries:
        embed = discord.Embed(
            title="🎉  Giveaway Kết Thúc",
            description="❌ Không có ai tham gia giveaway này.",
            color=0x99AAB5,
            timestamp=datetime.now(timezone.utc)
        )
        await msg.edit(embed=embed, view=None)
        await channel.send("❌ Giveaway kết thúc nhưng không có người tham gia!")
        return

    count = min(winners_count, len(entries))
    winner_ids = random.sample(entries, count)
    winner_mentions = ", ".join(f"<@{uid}>" for uid in winner_ids)

    embed = discord.Embed(
        title="🎉  Giveaway Kết Thúc!",
        description=f"**Phần thưởng:** {gw['prize']}\n**🏆 Winner:** {winner_mentions}",
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    host = channel.guild.get_member(gw["host"])
    embed.set_footer(text=f"Host: {_uname_plain(host) if host else gw['host']}")
    await msg.edit(embed=embed, view=None)
    await channel.send(f"🎊 Chúc mừng {winner_mentions}! Bạn đã thắng **{gw['prize']}**!")

    gw["winner_ids"] = winner_ids
    save_giveaways_data()

    if gw.get("send_invite", False):
        await _check_winner_invites(channel, winner_ids, gw["prize"])

class GiveawayModal(discord.ui.Modal, title="🎉 Tạo Giveaway"):
    duration = discord.ui.TextInput(
        label="Thời gian",
        placeholder="Ví dụ: 30s / 10m / 1h / 2d",
        min_length=2, max_length=10
    )
    winners_count = discord.ui.TextInput(
        label="Số người trúng thưởng",
        placeholder="Ví dụ: 1",
        min_length=1, max_length=2
    )
    prize = discord.ui.TextInput(
        label="Phần thưởng",
        placeholder="Ví dụ: 100m ingame, Elytra...",
        min_length=1, max_length=200
    )
    description = discord.ui.TextInput(
        label="Mô tả (tuỳ chọn)",
        placeholder="Điều kiện tham gia, ghi chú thêm...",
        style=discord.TextStyle.paragraph,
        required=False, max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        dur = self.duration.value.strip()
        unit = dur[-1].lower()
        try:
            val = int(dur[:-1])
        except:
            return await interaction.response.send_message("❌ Thời gian không hợp lệ! Dùng: `30s`, `10m`, `1h`, `2d`", ephemeral=True)
        seconds = {"s": val, "m": val*60, "h": val*3600, "d": val*86400}.get(unit)
        if not seconds:
            return await interaction.response.send_message("❌ Đơn vị thời gian không hợp lệ! Dùng: `s`, `m`, `h`, `d`", ephemeral=True)

        try:
            w_count = int(self.winners_count.value.strip())
            if w_count < 1: raise ValueError
        except:
            return await interaction.response.send_message("❌ Số người trúng thưởng phải là số nguyên dương!", ephemeral=True)

        end_time = datetime.now(timezone.utc).timestamp() + seconds

        confirm_view = GiveawayConfirmView(
            host=interaction.user,
            channel=interaction.channel,
            prize=self.prize.value,
            w_count=w_count,
            seconds=seconds,
            end_time=end_time,
            description=self.description.value or "",
        )
        embed_preview = confirm_view.build_preview_embed()
        await interaction.response.send_message(
            content="## ⚙️ Xác nhận trước khi đăng giveaway",
            embed=embed_preview,
            view=confirm_view,
            ephemeral=True
        )

async def _check_winner_invites(channel: discord.TextChannel, winner_ids: list, prize: str):
    """
    Kiểm tra số lượng invite của từng winner (giống lệnh .invite)
    và gửi embed tổng hợp vào kênh giveaway.
    """
    guild = channel.guild
    lines = []
    medals = ["🥇", "🥈", "🥉"]

    for i, uid in enumerate(winner_ids):
        icon   = medals[i] if i < len(medals) else f"`{i+1}.`"
        member = guild.get_member(uid)
        name   = _uname(member) if member else f"<@{uid}>"
        total, fake, left, net = _get_net_invites(uid)
        lines.append(
            f"{icon} **{name}**\n"
            f"  ✅ Net: **{net}**  •  📊 Tổng: `{total}`  •  ⚠️ Fake: `{fake}`  •  🚪 Rời: `{left}`"
        )

    embed = discord.Embed(
        title="📨  Thống Kê Invite — Winner Giveaway",
        description="\n".join(lines) if lines else "*(không có winner nào)*",
        color=0xF1C40F,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="🏆 Phần thưởng", value=prize, inline=False)
    embed.set_footer(text="Net = Tổng − Fake − Đã rời  •  TuyTam Store")
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[GIVEAWAY] ⚠️ Không gửi được check invite winner: {e}")

class GiveawayConfirmView(View):
    """
    View xác nhận giveaway — hiển thị ephemeral cho admin.
    Cho phép bật/tắt gửi invite link cho winner trước khi xác nhận đăng.
    """
    def __init__(self, host, channel, prize, w_count, seconds, end_time, description):
        super().__init__(timeout=120)
        self.host        = host
        self.channel     = channel
        self.prize       = prize
        self.w_count     = w_count
        self.seconds     = seconds
        self.end_time    = end_time
        self.description = description
        self.send_invite = False   # mặc định TẮT
        self._update_button_label()

    def _update_button_label(self):
        for item in self.children:
            if getattr(item, "custom_id", None) == "gw_toggle_invite":
                if self.send_invite:
                    item.label  = "📨 Check Invite Winner: BẬT"
                    item.style  = discord.ButtonStyle.success
                else:
                    item.label  = "📨 Check Invite Winner: TẮT"
                    item.style  = discord.ButtonStyle.secondary
                break

    def build_preview_embed(self) -> discord.Embed:
        invite_status = "✅ **BẬT** — Bot sẽ tự kiểm tra & hiển thị số invite của winner" if self.send_invite \
                   else "❌ **TẮT** — Không kiểm tra invite tự động"
        embed = discord.Embed(
            title="👀  Xem Trước Giveaway",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🏆 Phần thưởng",       value=self.prize,                   inline=False)
        embed.add_field(name="🎊 Số người thắng",    value=f"**{self.w_count}** người",   inline=True)
        embed.add_field(name="⏰ Kết thúc",           value=f"<t:{int(self.end_time)}:R>", inline=True)
        embed.add_field(name="📨 Kiểm tra Invite Winner", value=invite_status,            inline=False)
        if self.description:
            embed.add_field(name="📝 Mô tả", value=self.description, inline=False)
        embed.set_footer(text="Nhấn Toggle để bật/tắt • Nhấn Xác Nhận để đăng")
        return embed

    @discord.ui.button(label="📨 Check Invite Winner: TẮT", style=discord.ButtonStyle.secondary, custom_id="gw_toggle_invite")
    async def toggle_invite(self, interaction: discord.Interaction, button: Button):
        self.send_invite = not self.send_invite
        self._update_button_label()
        await interaction.response.edit_message(
            embed=self.build_preview_embed(),
            view=self
        )

    @discord.ui.button(label="✅ Xác Nhận & Đăng", style=discord.ButtonStyle.primary, custom_id="gw_confirm")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        self.stop()

        for item in self.children:
            item.disabled = True

        end_time = self.end_time
        embed = discord.Embed(
            title="🎉  GIVEAWAY!",
            description=self.description or "Nhấn nút **🎉 Tham gia** để tham dự!",
            color=0xF1C40F,
            timestamp=datetime.fromtimestamp(end_time, tz=timezone.utc)
        )
        embed.add_field(name="🏆  Phần thưởng",    value=self.prize,                          inline=False)
        embed.add_field(name="🎊  Số người thắng", value=f"**{self.w_count}** người",          inline=True)
        embed.add_field(name="👥  Người tham gia", value="**0** người",                        inline=True)
        embed.add_field(name="⏰  Kết thúc",       value=f"<t:{int(end_time)}:R>",             inline=True)
        embed.add_field(name="🎤  Host",           value=self.host.mention,                    inline=True)
        if self.send_invite:
            embed.add_field(name="📨  Invite Check",  value="Bot sẽ kiểm tra invite của winner", inline=False)
        embed.set_footer(text="TuyTam Store  •  Kết thúc lúc")

        await interaction.response.edit_message(
            content="✅ **Đã đăng giveaway!**",
            embed=self.build_preview_embed(),
            view=self
        )
        msg = await self.channel.send(embed=embed, view=GiveawayView())

        active_giveaways[msg.id] = {
            "type":        "button",
            "prize":       self.prize,
            "winners":     self.w_count,
            "entries":     set(),
            "channel_id":  self.channel.id,
            "end_time":    end_time,
            "host":        self.host.id,
            "ended":       False,
            "send_invite": self.send_invite,
        }
        save_giveaways_data()
        asyncio.create_task(giveaway_timer(self.channel.id, msg.id, self.w_count, self.seconds))

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.danger, custom_id="gw_cancel")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="🚫 **Đã huỷ tạo giveaway.**",
            embed=None,
            view=self
        )

@tree.command(name="giveaway", description="Tạo giveaway mới")
async def slash_giveaway(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Chỉ admin mới được tạo giveaway.", ephemeral=True)
    await interaction.response.send_modal(GiveawayModal())

@tree.command(name="gend", description="Kết thúc giveaway sớm")
@app_commands.describe(message_id="ID tin nhắn giveaway")
async def slash_gend(interaction: discord.Interaction, message_id: str):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
    try:
        mid = int(message_id)
    except:
        return await interaction.response.send_message("❌ ID không hợp lệ!", ephemeral=True)
    gw = active_giveaways.get(mid)
    if not gw:
        return await interaction.response.send_message("❌ Không tìm thấy giveaway đang chạy.", ephemeral=True)
    await interaction.response.send_message("✅ Đang kết thúc giveaway...", ephemeral=True)
    channel = bot.get_channel(gw["channel_id"])
    if channel:
        await end_giveaway(mid, channel, gw["winners"], gw.get("prize", "phần thưởng"), gw.get("host", 0))


