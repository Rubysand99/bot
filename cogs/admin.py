"""
cogs/admin.py — AdminCog: commands, slash commands, event handlers.
UI Views/Modals nằm trong cogs/admin_views.py.
v4.0.0 — 2026-05-30
"""

import re as _re
import asyncio
import json
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, TextInput

from cogs.logger import send_log
from core.data import (
    ADMIN_IDS, ADMIN_TUYTAM_ID, ADMIN_RUBY_ID,
    get_cfg_stock_category, get_cfg_sold_category,
    get_cfg_font, _uname_plain, is_staff_member,
    load_data, get_price_sections,
    can_use_dangerous_cmd, parse_amount, fmt_amount,
    get_or_fetch_channel, set_current_guild,
    add_seller_sale, add_user_spent,
    add_pending_sold_price, get_pending_sold_price, get_all_pending_sold_price,
    remove_pending_sold_price, set_pending_sold_dm, mark_pending_sold_escalated,
    mark_pending_sold_resolved, get_resolved_sold_price,
    add_pending_sold_buyer, get_pending_sold_buyer, get_all_pending_sold_buyer,
    remove_pending_sold_buyer, set_pending_sold_buyer_dm, mark_pending_sold_buyer_escalated,
    get_cfg_shop_orders_enabled, set_cfg_shop_orders_enabled,
    get_embed_template, get_embed_templates, save_embed_template, delete_embed_template,
    GuildContextView as View, GuildContextModal as Modal,
)
from cogs.seller import is_active_seller
from cogs.ticket import get_panel_buttons_cfg, PANEL_BUTTON_DEFS

from cogs.admin_views import (
    SettingsView, SetupMainView, PriceManagerView,
    build_sv_embed, FONT_LABELS,
    _detect_channel_parts, _rebuild_name,
    _DEFAULT_PRICE_SECTIONS,
    MkChannelView,
    EmbedAnnounceView, EmbedAnnounceModal, EmbedPreviewView, EmbedUsePreviewButtonView, build_embed_from_payload,
)

BOT_VERSION = "4.13.1"
BOT_UPDATED = "2026-07-20"

try:
    import bot as _bot_module
    BOT_VERSION = getattr(_bot_module, "BOT_VERSION", BOT_VERSION)
    BOT_UPDATED = getattr(_bot_module, "BOT_UPDATED", BOT_UPDATED)
except Exception:
    pass

# Nạp cog 1 lần duy nhất lúc bot khởi động (không reload theo từng lệnh) nên
# dùng làm mốc tính uptime cho .botinfo là đủ chính xác.
_BOT_START_TS = datetime.now(timezone.utc)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── .settings ──
    @commands.command(name="settings", aliases=["setting", "caidat", "st"])
    async def settings_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return
        data = load_data()
        embed = discord.Embed(title="⚙️  Bot Settings — TuyTam Store", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        def ch(k, d): c = data.get(k, d); return f"<#{c}>" if c else "Chưa cài"
        def ro(k, d): r = data.get(k, d); return f"<@&{r}>" if r else "Chưa cài"
        embed.add_field(name="📋 Log Channel (Rudy)", value=ch("cfg_log_rudy", 0),                                    inline=True)
        embed.add_field(name="🎫 Ticket Category",    value=ch("cfg_ticket_category", 0),                              inline=True)
        embed.add_field(name="🛡️ Support Role",      value=ro("cfg_support_role",    1474572393908404305), inline=True)
        embed.add_field(name="🏪 Seller Role",       value=ro("cfg_seller_role",     0),                   inline=True)
        embed.add_field(name="✅ Legit Channel",     value=ch("cfg_legit_channel",   0),                   inline=True)
        embed.add_field(name="📸 Proof Channel",    value=ch("cfg_proof_channel",   1469647159560241318), inline=True)
        embed.add_field(name="🤖 AI Channel",        value=ch("cfg_ai_channel",      0),                   inline=True)
        embed.add_field(name="📦 Stock Category",    value=ch("cfg_stock_category",  0),                   inline=True)
        embed.add_field(name="✅ Sold Category",     value=ch("cfg_sold_category",   0),                   inline=True)
        embed.add_field(name="🔤 Font server",       value=FONT_LABELS.get(data.get("cfg_font","normal"),"normal"), inline=True)
        shop_status = "🟢 Bật" if get_cfg_shop_orders_enabled() else "🔴 Tắt"
        embed.add_field(name="🧪 Shop Orders (thử nghiệm)", value=shop_status, inline=True)
        relay_status = "🟢 Bật" if data.get("cfg_ticket_relay", True) else "🔴 Tắt"
        embed.add_field(name="🪄 Relay Tin Admin (Ticket)", value=relay_status, inline=True)
        panel_cfg = get_panel_buttons_cfg()
        panel_on  = sum(1 for v in panel_cfg.values() if v)
        embed.add_field(name="🔘 Panel Buttons", value=f"{panel_on}/{len(PANEL_BUTTON_DEFS)} bật — `.panelbtn` để chỉnh", inline=True)
        embed.set_footer(text=f"Nhấn nút bên dưới để thay đổi  •  Yêu cầu bởi {ctx.author}")

        view = SettingsView(ctx.guild)
        view.add_item(ShopOrdersToggleButton())
        await ctx.reply(embed=embed, view=view)

    # ── .sv / .giaset ──
    @commands.command(name="sv", aliases=["dichvu", "service"])
    async def sv_cmd(self, ctx):
        await ctx.send(embed=build_sv_embed())

    @commands.command(name="giaset", aliases=["setgia", "pricemanager", "priceset"])
    async def giaset_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        sections = get_price_sections() or _DEFAULT_PRICE_SECTIONS
        embed = discord.Embed(title="⚙️  Quản Lý Bảng Giá — .sv", description=f"Hiện có **{len(sections)} mục** trong bảng giá.\nChọn mục từ dropdown để **sửa**, hoặc dùng nút bên dưới.\n\n" + "\n".join(f"`{i+1}.` {s['name']}" for i, s in enumerate(sections)), color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="💡 Hướng dẫn", value="Hỗ trợ đầy đủ **Discord markdown**:\n› `**bold**`, `~~gạch~~`, `> blockquote`\n› Emoji server: `<:tên:id>`\n› `### Tiêu đề nhỏ`", inline=False)
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Timeout 2 phút")
        await ctx.reply(embed=embed, view=PriceManagerView())

    # ── .addrole / .removerole ──
    @commands.command(name="addrole", aliases=["giverole"])
    async def addrole_cmd(self, ctx, member: discord.Member = None, role: discord.Role = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Bạn không có quyền.")
        if not member or not role: return await ctx.reply("❌ Dùng: `.addrole @user @role`")
        if role >= ctx.guild.me.top_role: return await ctx.reply("❌ Role này cao hơn role của bot.")
        await member.add_roles(role, reason=f"Bởi {ctx.author}")
        embed = discord.Embed(title="✅ Đã Thêm Role", color=0x57F287)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
        await ctx.reply(embed=embed)

    @commands.command(name="removerole", aliases=["takerole"])
    async def removerole_cmd(self, ctx, member: discord.Member = None, role: discord.Role = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Bạn không có quyền.")
        if not member or not role: return await ctx.reply("❌ Dùng: `.removerole @user @role`")
        await member.remove_roles(role, reason=f"Bởi {ctx.author}")
        embed = discord.Embed(title="✅ Đã Xoá Role", color=0xFEE75C)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
        await ctx.reply(embed=embed)

    # ── .emoji / .delemoji ──
    @commands.command(name="emoji")
    async def emoji_cmd(self, ctx, *, args: str = None):
        if not can_use_dangerous_cmd(ctx.author.id, "emoji"): return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not args:
            return await ctx.reply("❌ Dùng: `.emoji <emoji1> <emoji2>...` để copy emoji từ server khác.\nHoặc `.emoji` để vào chế độ chờ ảnh upload.")
        import aiohttp
        matches = _re.findall(r"<(a?):([^:>]+):(\d+)>", args)
        if not matches: return await ctx.reply("❌ Không tìm thấy emoji hợp lệ.")
        prog = await ctx.reply(f"⏳ Đang thêm **{len(matches)}** emoji...")
        added, failed = [], []
        async with aiohttp.ClientSession() as session:
            for animated, name, emoji_id in matches:
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}?quality=lossless"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status != 200: raise Exception(f"HTTP {r.status}")
                        data = await r.read()
                    em = await ctx.guild.create_custom_emoji(name=name[:32], image=data, reason=f"Bởi {ctx.author}")
                    added.append(str(em))
                except Exception as e:
                    failed.append(f"`{name}` — {e}")
                await asyncio.sleep(1.5)
        lines = []
        if added:   lines.append(f"✅ Đã thêm **{len(added)}**:\n{' '.join(added)[:900]}")
        if failed:  lines.append(f"❌ Thất bại **{len(failed)}**:\n" + "\n".join(failed[:10]))
        await prog.edit(content="\n\n".join(lines) if lines else "Không có emoji nào được thêm.")

    @commands.command(name="delemoji")
    async def delemoji_cmd(self, ctx, *, args: str = None):
        if ctx.author.id not in ADMIN_IDS: return await ctx.reply("❌ Chỉ admin.")
        if not args: return await ctx.reply("❌ Dùng: `.delemoji <emoji1> <emoji2>...`")
        matches = _re.findall(r"<a?:[^:>]+:(\d+)>", args)
        if not matches: return await ctx.reply("❌ Không tìm thấy emoji hợp lệ.")
        deleted, failed = [], []
        for eid_str in matches:
            eid = int(eid_str)
            em  = discord.utils.get(ctx.guild.emojis, id=eid)
            if not em: failed.append(f"`{eid}`"); continue
            try: await em.delete(reason=f"Bởi {ctx.author}"); deleted.append(f"`:{em.name}:`")
            except Exception as e: failed.append(f"`:{em.name}:` — {e}")
        lines = []
        if deleted: lines.append(f"✅ Đã xoá **{len(deleted)}** emoji:\n{' '.join(deleted)}")
        if failed:  lines.append(f"❌ Thất bại **{len(failed)}**:\n{' '.join(failed[:10])}")
        await ctx.reply("\n\n".join(lines) if lines else "Không có emoji nào được xoá.")

    # ── .rename / .setperm / .mkchannel / .setup ──
    @commands.command(name="rename")
    async def rename_cmd(self, ctx, channel: discord.abc.GuildChannel = None, *, new_name: str = None):
        if not can_use_dangerous_cmd(ctx.author.id, "rename"): return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not channel or not new_name: return await ctx.reply("❌ Dùng: `.rename #kênh tên-mới`")
        parts = _detect_channel_parts(channel.name)
        font  = get_cfg_font()
        final = _rebuild_name(parts, new_name, font)
        try: await channel.edit(name=final, reason=f"Rename bởi {ctx.author}"); await ctx.reply(f"✅ `{channel.name}` → `{final}`")
        except discord.Forbidden: await ctx.reply("❌ Bot thiếu quyền.")
        except Exception as e: await ctx.reply(f"❌ {e}")

    @commands.command(name="setperm")
    async def setperm_cmd(self, ctx, channel: discord.TextChannel = None, role: discord.Role = None, *, flags: str = ""):
        if not can_use_dangerous_cmd(ctx.author.id, "setperm"): return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not channel or not role: return await ctx.reply("❌ Dùng: `.setperm #kênh @role xem=true gửi=false`")
        overwrite = channel.overwrites_for(role)
        flag_map  = {"xem":"read_messages","gửi":"send_messages","đọc":"read_messages","view":"read_messages","send":"send_messages","manage":"manage_messages","ql":"manage_messages","reaction":"add_reactions","embed":"embed_links","file":"attach_files"}
        changes   = []
        for part in flags.split():
            if "=" not in part: continue
            k, v = part.split("=", 1)
            attr = flag_map.get(k.lower().strip())
            if not attr: continue
            val  = True if v.lower() in ("true","1","yes","on") else (False if v.lower() in ("false","0","no","off") else None)
            setattr(overwrite, attr, val)
            changes.append(f"{k}={'✅' if val else ('❌' if val is False else '↩️ default')}")
        if not changes: return await ctx.reply("❌ Không có flag hợp lệ. VD: `xem=true gửi=false`")
        try: await channel.set_permissions(role, overwrite=overwrite, reason=f"setperm bởi {ctx.author}"); await ctx.reply(f"✅ Đã sửa quyền `#{channel.name}` cho {role.mention}:\n" + "\n".join(f"  › {c}" for c in changes))
        except discord.Forbidden: await ctx.reply("❌ Bot thiếu quyền Manage Channels.")
        except Exception as e: await ctx.reply(f"❌ {e}")

    @commands.command(name="mkchannel", aliases=["mkch", "taokenh"])
    async def mkchannel_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")
        cats = sorted(ctx.guild.categories, key=lambda c: c.position)
        cat_opts = [discord.SelectOption(label=c.name[:100], value=str(c.id)) for c in cats[:24]]
        cat_opts.insert(0, discord.SelectOption(label="(Không có danh mục)", value="0", emoji="🚫"))
        embed = discord.Embed(
            title="➕  Tạo Kênh Mới",
            description=(
                "**①** Chọn **loại kênh**\n"
                "**②** Chọn **danh mục** chứa kênh\n"
                "**③** Chọn **quyền truy cập** (Public / Private)\n"
                "**④** Chọn **khoá gửi tin** (Mở / Khoá read-only)\n"
                "**⑤** Nhấn **Tiếp tục →** → nhập tên và số lượng\n\n"
                f"Font đang dùng: **{FONT_LABELS.get(get_cfg_font(), get_cfg_font())}**"
            ),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Timeout 2 phút")
        await ctx.reply(embed=embed, view=MkChannelView(ctx, cat_opts))

    # ── .setup ──
    @commands.command(name="setup", aliases=["sv_setup", "serversetup"])
    async def setup_cmd(self, ctx):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền dùng lệnh này.")
        embed = discord.Embed(
            title="🔧  Setup Server — TuyTam Bot",
            description=(
                "Chọn nhóm chức năng bạn muốn thiết lập.\n"
                "Dùng các nút bên dưới để điều hướng."
            ),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="📋 Quản lý kênh",    value="Tạo / Xoá / Đổi tên / Font / Clone kênh", inline=True)
        embed.add_field(name="🗂️ Quản lý danh mục", value="Tạo / Xoá / Đổi tên / Di chuyển kênh",    inline=True)
        embed.add_field(name="🏷️ Quản lý role",    value="Tạo / Xoá / Gán role cho member",           inline=True)
        embed.add_field(name="⚙️ Setup server",     value="Welcome / Log / Auto-role / Prefix",        inline=True)
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author}  •  Timeout 3 phút")
        await ctx.reply(embed=embed, view=SetupMainView(ctx))

    # ── .botinfo ──
    @commands.command(name="botinfo")
    async def botinfo_cmd(self, ctx):
        import platform

        # Uptime
        delta = datetime.now(timezone.utc) - _BOT_START_TS
        days, rem = divmod(int(delta.total_seconds()), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        uptime_str = (f"{days}n " if days else "") + f"{hours}g {minutes}p"

        # MongoDB health-check (ping nhẹ, không tính là lỗi nếu chậm — chỉ báo mất kết nối)
        mongo_status = "🟢 OK"
        try:
            from core.data import _get_mongo
            col, _ = _get_mongo()
            await asyncio.wait_for(col.database.command("ping"), timeout=3)
        except Exception:
            mongo_status = "🔴 Mất kết nối"

        # RAM (bỏ qua êm nếu chưa cài psutil — không chặn lệnh)
        ram_str = "N/A"
        try:
            import psutil
            proc = psutil.Process()
            ram_mb = proc.memory_info().rss / (1024 * 1024)
            ram_str = f"{ram_mb:.0f} MB"
        except Exception:
            pass

        lat = round(self.bot.latency * 1000)
        lat_icon = "🟢" if lat < 100 else ("🟡" if lat < 200 else "🔴")

        embed = discord.Embed(title=f"🤖  {self.bot.user.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="📋 Version",    value=f"`v{BOT_VERSION}` ({BOT_UPDATED})",     inline=True)
        embed.add_field(name="⏱️ Uptime",     value=uptime_str,                              inline=True)
        embed.add_field(name="🏓 Latency",    value=f"{lat_icon} **{lat}ms**",                inline=True)
        embed.add_field(name="🗄️ MongoDB",    value=mongo_status,                             inline=True)
        embed.add_field(name="💾 RAM",        value=ram_str,                                  inline=True)
        embed.add_field(name="🌐 Servers",    value=f"**{len(self.bot.guilds)}**",            inline=True)
        embed.add_field(name="⚙️ Cogs",       value=f"**{len(self.bot.cogs)}**",              inline=True)
        embed.add_field(name="📜 Lệnh",       value=f"**{len(self.bot.commands)}** prefix",   inline=True)
        embed.add_field(name="🐍 Python",     value=f"`{platform.python_version()}`",         inline=True)
        embed.add_field(name="📦 discord.py", value=f"`{discord.__version__}`",               inline=True)
        if self.bot.user.avatar: embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text="TuyTam Store  •  Ticket System")
        await ctx.reply(embed=embed)

    # ── .help ──
    @commands.command(name="help", aliases=["h"])
    async def help_cmd(self, ctx, *, topic: str = None):
        TOPICS = {
            "ticket": {
                "emoji": "🎫", "title": "Ticket",
                "fields": [
                    ("📋 Lệnh cơ bản",
                     "`.panel` — Đăng panel mua/bán\n"
                     "`.panelbuttons` (alias `.panelbtn`) — Bật/tắt từng nút của panel (riêng theo server)\n"
                     "`.setpanel #kênh` — Cài kênh đăng panel tự động\n"
                     "`.close` — Đóng ticket hiện tại\n"
                     "`.done <tiền>` — Hoàn thành đơn (chỉ admin)\n"
                     "`.addnote <ghi chú>` — Thêm ghi chú vào ticket\n"
                     "`.orderbase` — Tạo ticket Order Base (admin)", False),
                    ("🏷️ Loại ticket → Role",
                     "`.setrole <ticket_key> <seller|builder|xoá>` — Gán loại ticket vào nhóm role\n"
                     "`.listroles` — Xem toàn bộ cấu hình loại ticket → role", False),
                    ("💎 Ruby Shop",
                     "Panel có thêm nút 💎 Ruby Shop — trước khi tạo ticket, bot hỏi user cần hỗ trợ "
                     "dịch vụ gì (chọn trong danh sách admin tự thêm)\n"
                     "`.rubyoption add <tên>` (alias `.rbopt`) — Thêm 1 dịch vụ vào danh sách lựa chọn\n"
                     "`.rubyoption remove <tên>` — Xoá 1 dịch vụ\n"
                     "`.rubyoption edit <tên cũ> -> <tên mới>` — Đổi tên 1 dịch vụ\n"
                     "`.rubyoption list` — Xem danh sách hiện tại\n"
                     "-# Gộp nhiều thao tác cùng lúc, cách nhau bằng dấu phẩy: `.rbopt add A, add B, remove C, edit D -> E`\n"
                     "`.setrole rubyshop @role` — Gán role xử lý ticket Ruby Shop", False),
                    ("📦 Stock Limit",
                     "`.setsl <item_key> <số lượng>` — Cài giới hạn tồn kho\n"
                     "`.removesl <item_key>` — Xoá giới hạn tồn kho\n"
                     "`.listsl` — Xem danh sách stock limit hiện tại", False),
                    ("📊 Thống kê",
                     "`.ticketinfo [@user]` — Xem lịch sử ticket của user\n"
                     "`.thongke [MM/YYYY]` — Thống kê doanh thu theo tháng", False),
                    ("🔷 Slash commands",
                     "`/close` `/done` `/addnote`", False),
                ]
            },
            "invite": {
                "emoji": "📨", "title": "Invite & Verify",
                "fields": [
                    ("📋 Thống kê invite",
                     "`.invite [@user]` — Xem invite tháng này + all-time của bản thân / người khác\n"
                     "`.invitetop [n] [MM/YYYY] [alltime]` — Leaderboard invite\n"
                     "  • Mặc định: top 10 tháng hiện tại\n"
                     "  • `.invitetop 20` — top 20 tháng này\n"
                     "  • `.invitetop 06/2026` — top 10 tháng 6/2026\n"
                     "  • `.invitetop alltime` — top 10 all-time", False),
                    ("✅ Verify thủ công (admin)",
                     "`.verify [user_id]` — Verify tay 1 thành viên (đổi trạng thái unverify → verify),\n"
                     "dùng khi verify server (chống VPN) bị lỗi/timeout", False),
                    ("🔄 Reset invite (admin)",
                     "`.resetinvite [@user|all]` — Reset invite **tháng hiện tại** (all-time giữ nguyên)\n"
                     "`.resetinvites [@user]` — Reset invite **all-time** *(hỏi lại trước khi xóa)*", False),
                    ("🔐 Kiểm tra IP (admin)",
                     "`.checkip @user` — Xem tất cả tài khoản chung IP với user đó\n"
                     "`.ipstats` — Danh sách IP có từ 2 tài khoản trở lên\n"
                     "`.backfillip [số]` — Đọc lại lịch sử kênh log, backfill IP records vào DB (mặc định 2000 message)\n"
                     "`.testip` — Test kết nối verify server (chống VPN/multi-acc)", False),
                    ("🌐 Quản lý server bot (admin)",
                     "`.serverlist` (alias `.servers`/`.guildlist`) — Danh sách server bot đang ở kèm ID\n"
                     "`.leaveguild <guild_id>` — Cho bot rời khỏi 1 server cụ thể", False),
                    ("🔷 Slash commands",
                     "`/invite` `/invitetop` `/resetinvite`", False),
                ]
            },
            "dichvu": {
                "emoji": "🏪", "title": "Dịch Vụ",
                "fields": [
                    ("📋 Lệnh",
                     "`.sv` — Xem bảng giá dịch vụ\n"
                     "`.giaset` — Admin chỉnh sửa bảng giá\n"
                     "`/sv` `/giaset`", False),
                ]
            },
            "giveaway": {
                "emoji": "🎉", "title": "Giveaway",
                "fields": [
                    ("📋 Slash commands",
                     "`/giveaway` — Tạo giveaway mới\n"
                     "`/gend <message_id>` — Kết thúc giveaway sớm\n"
                     "`/greroll <message_id>` — Quay số lại\n"
                     "`/gwlist <message_id>` — Xem danh sách người tham gia", False),
                    ("🔧 Prefix commands (admin)",
                     "`.gwstatus` — Xem toàn bộ giveaway đang chạy & đã kết thúc\n"
                     "`.gwpick <gw_id> <@user>` — Chọn tay winner cho giveaway\n"
                     "`.gwreset <gw_id>` — Reset giveaway (xoá danh sách người tham gia)", False),
                ]
            },
            "mod": {
                "emoji": "🔨", "title": "Mod",
                "fields": [
                    ("⚖️ Xử lý thành viên",
                     "`.ban @user [lý do]` — Ban vĩnh viễn\n"
                     "`.unban <user_id>` — Unban\n"
                     "`.kick @user [lý do]` — Kick khỏi server\n"
                     "`.timeout @user <thời gian> [lý do]` — Timeout Discord native (alias: `.mute`)\n"
                     "`.untimeout @user` — Gỡ timeout (alias: `.unmute`)\n"
                     "`.tempban @user <thời gian> [lý do]` — Ban tạm thời, tự unban (vd: 2d, 1h)", False),
                    ("⚠️ Cảnh cáo",
                     "`.warn @user [lý do]` — Cảnh cáo user (có cooldown 60s)\n"
                     "`.warns [@user]` — Xem danh sách cảnh cáo\n"
                     "`.clearwarn @user [số]` — Xóa 1 warn hoặc toàn bộ\n"
                     "`.modlog @user` — Xem lịch sử ban/kick/timeout/warn", False),
                    ("🗑️ Tin nhắn",
                     "`.xoa <số> [@user]` — Xóa hàng loạt tin nhắn (tối đa 100)\n"
                     "`.slowmode <giây>` — Cài chế độ chậm (0 = tắt)\n"
                     "`.lock [#kênh]` — Khóa kênh\n"
                     "`.unlock [#kênh]` — Mở khóa kênh", False),
                    ("🛡️ AutoMod",
                     "`.automod on/off` — Bật/tắt automod\n"
                     "`.automod links/invites/spam on/off` — Lọc link, invite, spam\n"
                     "`.automod imagespam on/off` — Chống spam ảnh/sticker (4+ ảnh/10s → timeout 5p)\n"
                     "`.automod caps on/off [%] [min_len]` — Xóa tin nhắn ALL CAPS\n"
                     "`.automod addword/delword/words` — Quản lý từ cấm\n"
                     "`.automod addrole/delrole` — Role bypass automod\n"
                     "`.automod adduser/deluser` — User bypass automod\n"
                     "`.automod whitelist` — Xem danh sách bypass", False),
                    ("🔷 Slash commands",
                     "`/ban` `/unban` `/kick` `/timeout` `/untimeout`\n"
                     "`/tempban` `/warn` `/warns` `/clearwarn` `/modlog`\n"
                     "`/xoa` `/slowmode` `/lock` `/unlock`", False),
                ]
            },
            "log": {
                "emoji": "📋", "title": "Log",
                "fields": [
                    ("📋 Lệnh",
                     "`.setlog <nhóm> #kênh` — Cài kênh log cho từng nhóm\n"
                     "`.setuplog [category_id]` — Tự động tạo toàn bộ kênh log\n"
                     "`.loginfo` — Xem kênh log đang được cài\n"
                     "`.testlog [nhóm]` — Gửi log test để kiểm tra hoạt động\n"
                     "`.baocao` — Báo cáo tổng hợp 24h (ticket, giveaway)", False),
                    ("🗂️ Nhóm log",
                     "`ticket` `mod` `giveaway`\n"
                     "`member` `role` `ai` `admin` `invite` `general`", False),
                    ("⚠️ Lưu ý",
                     "`.setuplog` tự nhận kênh đã đổi font chữ (Unicode) — không cần đặt lại tên kênh", False),
                ]
            },
            "ai": {
                "emoji": "🤖", "title": "AI Chat",
                "fields": [
                    ("🛠️ Điều khiển bot bằng AI (admin)",
                     "`.ai <yêu cầu>` — Ra lệnh cho bot bằng ngôn ngữ tự nhiên (tự nhận diện qua router: "
                     "điều hành server / báo cáo / tra cứu tài khoản)\n"
                     "Vd: `.ai tạo kênh test riêng tư`, `.ai ban @user spam`, `.ai đóng ticket này`\n"
                     "Hành động nguy hiểm (ban/kick/mute/xoá kênh/xoá role/purge) sẽ hỏi xác nhận trước khi chạy", False),
                    ("📋 Lệnh",
                     "`.aireset` (alias `.airst`) — Xoá lịch sử chat AI trong kênh\n"
                     "`.mychat` — Xem lịch sử hội thoại AI của bạn", False),
                    ("ℹ️ Cách dùng (chat khách hàng)",
                     "Nhắn tin trong kênh AI được cài → bot tự trả lời\n"
                     "Có thể hỏi AI tự tra cứu ticket/gói seller/invite/lịch sử mua hàng của CHÍNH bạn\n"
                     "Cài kênh AI qua `.st` → AI Channel", False),
                    ("🔍 Tìm tin nhắn cũ (admin)",
                     "`.aisearchch add/remove/list [#kênh]` — Bật/tắt tự động index 1 kênh\n"
                     "`.aiindex [limit]` — Quét & index lịch sử kênh hiện tại (mặc định 1000, tối đa 3000)\n"
                     "`.aisearch <câu hỏi>` — Tìm tin nhắn cũ theo NGHĨA, không theo từ khoá", False),
                ]
            },
            "seller": {
                "emoji": "🏪", "title": "Seller Subscription",
                "fields": [
                    ("📋 Lệnh admin",
                     "`.seller add @user [days]` — Thêm mới hoặc gia hạn seller (mặc định 30 ngày)\n"
                     "`.seller remove @user` — Xoá seller\n"
                     "`.seller list` — Danh sách tất cả seller + trạng thái hết hạn\n"
                     "`.seller info @user` — Xem thông tin gói của 1 seller\n"
                     "`.seller panel [@user]` — Gửi embed thông tin seller (mẫu chào mừng)", False),
                    ("👤 Lệnh seller (tự dùng)",
                     "`.myseller` — Xem thông tin gói đăng ký của bản thân", False),
                    ("🎨 Trạng thái",
                     "🟢 Xanh — Còn hạn\n"
                     "🟡 Vàng — Sắp hết hạn (≤ 3 ngày)\n"
                     "🔴 Đỏ — Đã hết hạn\n\n"
                     "Bot tự động log kênh ticket khi seller sắp hết/đã hết hạn (mỗi giờ kiểm tra 1 lần)", False),
                ]
            },
            "shoporders": {
                "emoji": "🧾", "title": "Shop Orders (VietQR) & Bảng xếp hạng",
                "fields": [
                    ("ℹ️ Giới thiệu",
                     "Tính năng thử nghiệm — bật/tắt qua `.st`. Khi bật, `.done <tiền>` (mục Ticket)\n"
                     "sẽ tự tạo mã QR VietQR động theo số tiền thay vì chỉ báo hoàn thành.", False),
                    ("⚙️ Cấu hình (admin, bắt buộc trước khi dùng)",
                     "`.shopbank <thông tin>` — Cài thông tin ngân hàng (tên NH, số TK, chủ TK...) để tạo QR\n"
                     "`.setqueue #kênh` — Cài kênh hàng đợi đơn hàng cho seller (nút ✅ xác nhận đã xử lý)\n"
                     "`.shoporderno [số]` — Xem/đổi số hóa đơn kế tiếp (admin)\n"
                     "Kênh Proof (nơi hóa đơn công khai được gửi) — cài trong `.st` → Proof Channel", False),
                    ("🧾 Hóa đơn công khai",
                     "Staff bấm ✅ trên đơn hàng ở kênh hàng đợi → nhập tên/mã sản phẩm →\n"
                     "bot tự gửi hóa đơn (số hóa đơn tăng dần, nội dung CK tự sinh) vào kênh Proof", False),
                    ("🏆 Bảng xếp hạng",
                     "`.bxh` (alias `.leaderboard`/`.top`) — Top 10 chi tiêu nhiều nhất trong server\n"
                     "(cộng dồn tự động mỗi khi `.done`)", False),
                ]
            },
            "admin": {
                "emoji": "⚙️", "title": "Admin",
                "fields": [
                    ("🛠️ Quản lý server",
                     "`.st` — Cài đặt bot\n"
                     "`.setup` — Setup server (kênh / category / role / server)\n"
                     "`.botinfo` — Thông tin bot\n"
                     "`.ping` — Kiểm tra độ trễ\n"
                     "`.clear <n>` — Xóa n tin nhắn\n"
                     "`.addrole @user @role` — Thêm role\n"
                     "`.removerole @user @role` — Xóa role\n"
                     "`.userinfo [@user]` — Thông tin thành viên\n"
                     "`.serverinfo` — Thông tin server\n"
                     "`.backfill [số]` — Quét lại kênh legit, thả ✅ cho tin bị bỏ sót (mặc định 25)", False),
                    ("🎨 Emoji & Kênh",
                     "`.emoji <url/file> <tên>` — Thêm emoji\n"
                     "`.delemoji <tên>` — Xóa emoji\n"
                     "`.rename #kênh <tên mới>` — Đổi tên kênh\n"
                     "`.setperm #kênh @role <quyền>` — Cài quyền kênh\n"
                     "`.mkchannel` — Tạo kênh (chọn loại / danh mục / public-private / khoá)", False),
                    ("📢 Thông báo",
                     "`.embed [#kênh] [everyone|here]` (alias `.thongbao`/`.announce`) — Nhấn nút để "
                     "soạn embed (tiêu đề/nội dung/màu/ảnh lớn/thumbnail/footer). Sau khi soạn xong sẽ "
                     "hiện **bản xem trước** (chỉ mình bạn thấy) kèm 3 nút: 📤 Gửi thật vào kênh / "
                     "✏️ Sửa lại (mở lại form, giữ nguyên nội dung cũ) / ❌ Huỷ. Staff dùng được; ping "
                     "@everyone/@here chỉ dành cho admin\n"
                     "`.embeduse <tên> [#kênh] [everyone|here]` — Gửi lại 1 mẫu đã lưu, cũng qua bước "
                     "xem trước (nhấn 👁️ rồi mới 📤 Gửi; có thể ✏️ Sửa tạm trước khi gửi mà không ảnh "
                     "hưởng mẫu gốc). Lưu mẫu qua nút 💾 sau khi gửi thành công\n"
                     "`.embedlist` (alias `.dsmautb`) — Xem danh sách mẫu đã lưu\n"
                     "`.embeddel <tên>` — Xoá 1 mẫu\n"
                     "`.embedimport` (alias `.nhapmautb`) — Đính kèm file `.json` để nhập nhiều mẫu cùng lúc, "
                     "bot lưu thẳng vào MongoDB ngay, không cần restart\n"
                     "`/embed` `/embeduse` `/embedlist` `/embedimport` — Tương tự bản slash, `/embed` mở form soạn ngay lập tức", False),
                    ("🔷 Slash commands",
                     "`/clear` `/addrole` `/removerole` `/ping`\n"
                     "`/userinfo` `/serverinfo` `/botinfo`", False),
                ]
            },
            "listings": {
                "emoji": "🛒", "title": "Sản phẩm (Forum Listing)",
                "fields": [
                    ("ℹ️ Giới thiệu",
                     "Đăng sản phẩm dạng bài (thread) trong 1 kênh Forum, kèm nút Mua cho khách bấm.", False),
                    ("📋 Lệnh (staff/seller)",
                     '`.addlisting #forum "<IGN>" "<Giá>" "<Cape>" ["<Thông tin thêm>"]`\n'
                     "Đính kèm ảnh preview vào cùng tin nhắn nếu muốn (không bắt buộc)\n"
                     "Ví dụ: `.addlisting #stock \"test\" \"999K\" \"common, pan, copper\" \"Unban All\"`", False),
                    ("🔘 Nút trên bài đăng",
                     "🟢 Chưa bán / 🔴 Đã bán — staff/seller bấm để đổi trạng thái (tự khoá nút Mua khi Đã bán)\n"
                     "🛒 Mua — khách bấm → bot tự tạo ticket kèm sẵn thông tin sản phẩm (IGN/giá)", False),
                    ("🏷️ Role ping riêng (tuỳ chọn)",
                     "Cấu hình role nhận ping khi có ticket Mua sản phẩm qua `.st` → Vai trò ticket\n"
                     "→ chọn mục `🛒 Mua Sản Phẩm (Listing)`", False),
                ]
            },
        }

        # Normalize topic aliases
        ALIASES = {
            "ticket": "ticket", "vé": "ticket",

            "invite": "invite", "inv": "invite",
            "dichvu": "dichvu", "dịch vụ": "dichvu", "dv": "dichvu", "sv": "dichvu",
            "giveaway": "giveaway", "gw": "giveaway",
            "mod": "mod",
            "ai": "ai", "aichat": "ai", "chatai": "ai",
            "log": "log", "logger": "log",
            "admin": "admin", "adm": "admin",
            "seller": "seller",
            "shoporders": "shoporders", "shop": "shoporders", "qr": "shoporders",
            "vietqr": "shoporders", "donhang": "shoporders", "order": "shoporders", "bxh": "shoporders",
            "listings": "listings", "listing": "listings", "sanpham": "listings", "forum": "listings",
        }

        if topic:
            key = ALIASES.get(topic.lower().strip())
            if not key:
                topics_list = " | ".join(f"`{k}`" for k in ["ticket", "invite", "dichvu", "giveaway", "mod", "ai", "log", "admin", "seller", "shoporders", "listings"])
                return await ctx.reply(f"❌ Không tìm thấy mục `{topic}`.\nCác mục hợp lệ: {topics_list}")
            t = TOPICS[key]
            embed = discord.Embed(
                title=f"{t['emoji']}  Help — {t['title']}",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc)
            )
            for name, value, inline in t["fields"]:
                embed.add_field(name=name, value=value, inline=inline)
            embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  .help để về trang chính")
            return await ctx.reply(embed=embed)

        # Embed tổng quan
        embed = discord.Embed(
            title="📖  Danh Sách Lệnh — TuyTam Bot",
            description="Dùng `.help <mục>` để xem chi tiết từng phần.\nVí dụ: `.help mod` | `.help ticket` | `.help admin` | `.help listings`",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🎫 Ticket",    value="`.panel` `.panelbuttons` `.close` `.done` `.addnote`\n`.ticketinfo` `.thongke` `.setsl` `.setrole`", inline=True)
        embed.add_field(name="📨 Invite",    value="`.invite` `.invitetop` `.resetinvite` `.verify`\n`/invite` `/invitetop`", inline=True)
        embed.add_field(name="🏪 Dịch vụ",  value="`.sv` `.giaset`\n`/sv` `/giaset`", inline=True)
        embed.add_field(name="🎉 Giveaway",  value="`/giveaway` `/gend`\n`/greroll` `/gwlist`\n`.gwstatus` `.gwpick` `.gwreset`", inline=True)
        embed.add_field(name="🔨 Mod",       value="`.ban` `.kick` `.timeout` `.tempban`\n`.warn` `.modlog` `.xoa` `.automod`", inline=True)
        embed.add_field(name="🤖 AI Chat",   value="`.aireset` `.mychat` `.aisearch`", inline=True)
        embed.add_field(name="📋 Log",       value="`.setlog` `.setuplog` `.loginfo` `.baocao`", inline=True)
        embed.add_field(name="⚙️ Admin",     value="`.st` `.setup` `.clear` `.addrole` `.emoji`\n`.rename` `.mkchannel`", inline=True)
        embed.add_field(name="🏪 Seller",    value="`.seller add/remove/list/panel`\n`.myseller`", inline=True)
        embed.add_field(name="🧾 Shop Orders", value="`.shopbank` `.setqueue` `.shoporderno`\n`.bxh` — bảng xếp hạng\n*(dùng chung `.done` ở Ticket)*", inline=True)
        embed.add_field(name="🛒 Sản phẩm",    value="`.addlisting #forum \"IGN\" \"Giá\" \"Cape\"`\n*(xem `.help listings`)*", inline=True)
        embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  .help <mục> để xem chi tiết")
        await ctx.reply(embed=embed)

    # ── .backfill ──
    @commands.command(name="backfill")
    async def backfill_cmd(self, ctx, limit: int = 25):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới có quyền dùng lệnh này.")
        from core.data import get_cfg_legit_channel
        import re as _re
        IGNORED = {628400349979344919}

        legit_ch_id = get_cfg_legit_channel()
        if not legit_ch_id:
            return await ctx.reply("❌ Chưa cài Legit Channel. Vào `.st` để cài trước.")

        channel = await get_or_fetch_channel(self.bot, legit_ch_id)
        if not channel:
            return await ctx.reply(f"❌ Không tìm thấy kênh legit (ID: `{legit_ch_id}`).")

        limit = max(1, min(limit, 100))
        msg_status = await ctx.reply(f"🔍 Đang quét **{limit}** tin nhắn gần nhất trong {channel.mention}...")

        # Thu thập các tin nhắn bị bỏ sót (chưa có ✅), sắp xếp từ cũ → mới
        missed = []
        scanned = 0
        try:
            msgs = []
            async for msg in channel.history(limit=limit):
                msgs.append(msg)
            msgs.reverse()  # cũ → mới để xử lý đúng thứ tự

            for msg in msgs:
                if msg.author.bot: continue
                if msg.author.id in IGNORED: continue
                if not _re.match(r"^\+1\s*legit\b", msg.content.strip(), _re.IGNORECASE): continue
                scanned += 1
                already = any(r.emoji == "✅" and r.me for r in msg.reactions)
                if not already:
                    missed.append(msg)
        except Exception as e:
            return await msg_status.edit(content=f"❌ Lỗi khi quét: `{e}`")

        # Xử lý từng tin bị bỏ sót: thả reaction + đổi tên kênh +1
        fixed = 0
        name_before = channel.name
        for msg in missed:
            try:
                await msg.add_reaction("✅")
            except Exception:
                pass
            # Đổi tên kênh +1, fetch lại để tránh số đếm sai
            try:
                channel = await channel.guild.fetch_channel(channel.id)  # refresh
                name = channel.name
                match = _re.search(r"-(\d+)$", name)
                new_num = (int(match.group(1)) + 1) if match else 1
                base = name[:match.start()] if match else name
                new_name = f"{base}-{new_num}"
                await channel.edit(name=new_name, reason=f"Backfill +1 legit bởi {ctx.author}")
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
        await msg_status.edit(content=None, embed=embed)

    # ── PREFIX commands cho các slash ──
    @commands.command(name="ping")
    async def ping_cmd(self, ctx):
        lat    = round(self.bot.latency * 1000)
        color  = 0x57F287 if lat < 100 else (0xFEE75C if lat < 200 else 0xED4245)
        status = "Tốt 🟢" if lat < 100 else ("Bình thường 🟡" if lat < 200 else "Chậm 🔴")
        embed  = discord.Embed(title="🏓 Pong!", description=f"Độ trễ: **{lat}ms** — {status}", color=color)
        await ctx.reply(embed=embed)

    def _resolve_embed_ping(self, user, raw: str | None) -> tuple[str | None, str | None]:
        """'everyone'/'here' → nội dung ping thật. Chỉ ADMIN_IDS được ping
        @everyone/@here (staff thường vẫn gửi/soạn embed được, chỉ không kèm ping)."""
        if not raw:
            return None, None
        m = raw.strip().lstrip("@").lower()
        if m not in ("everyone", "here"):
            return None, None
        if user.id not in ADMIN_IDS:
            return None, "⚠️ Chỉ admin mới được ping @everyone/@here — thông báo sẽ gửi **không kèm ping**."
        return f"@{m}", None

    # ── .embed — gửi thông báo dạng embed, nội dung tự soạn lúc dùng lệnh ──
    @commands.command(name="embed", aliases=["thongbao", "announce"])
    async def embed_cmd(self, ctx, channel: discord.TextChannel = None, mention: str = None):
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        target = channel or ctx.channel
        ping, warn = self._resolve_embed_ping(ctx.author, mention)
        view = EmbedAnnounceView(target, ping)
        msg = (
            f"📝 Nhấn nút bên dưới để soạn nội dung thông báo gửi tới {target.mention}"
            + (f" (kèm `{ping}`)" if ping else "") + "."
        )
        if warn:
            msg += f"\n{warn}"
        await ctx.reply(msg, view=view)

    # ── .embeduse — gửi lại 1 mẫu embed đã lưu (qua bản xem trước) ──
    @commands.command(name="embeduse", aliases=["mautb"])
    async def embeduse_cmd(self, ctx, name: str = None, channel: discord.TextChannel = None, mention: str = None):
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not name:
            return await ctx.reply("❌ Dùng: `.embeduse <tên mẫu> [#kênh] [everyone|here]`\nXem danh sách mẫu bằng `.embedlist`.")
        payload = get_embed_template(name.strip().lower())
        if not payload:
            return await ctx.reply(f"❌ Không tìm thấy mẫu `{name}`. Dùng `.embedlist` để xem danh sách.")
        target = channel or ctx.channel
        ping, warn = self._resolve_embed_ping(ctx.author, mention)
        msg = f"🏷️ Mẫu `{name}` — nhấn nút bên dưới để xem trước rồi gửi tới {target.mention}" + (f" (kèm `{ping}`)" if ping else "") + "."
        if warn:
            msg += f"\n{warn}"
        await ctx.reply(msg, view=EmbedUsePreviewButtonView(payload, target, ping, name.strip().lower()))

    # ── .embedlist — xem danh sách mẫu đã lưu ──
    @commands.command(name="embedlist", aliases=["dsmautb"])
    async def embedlist_cmd(self, ctx):
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        templates = get_embed_templates()
        if not templates:
            return await ctx.reply("📭 Server chưa có mẫu thông báo nào. Sau khi gửi `.embed`, nhấn nút 💾 để lưu làm mẫu.")
        embed = discord.Embed(title="📋 Danh sách mẫu thông báo", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.description = "\n".join(
            f"`{name}` — {p.get('title') or '(không tiêu đề)'}" for name, p in templates.items()
        )[:4000]
        embed.set_footer(text="Dùng .embeduse <tên> [#kênh] [everyone|here] để gửi lại")
        await ctx.reply(embed=embed)

    # ── .embeddel — xoá 1 mẫu đã lưu ──
    @commands.command(name="embeddel", aliases=["xoamautb"])
    async def embeddel_cmd(self, ctx, name: str = None):
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not name:
            return await ctx.reply("❌ Dùng: `.embeddel <tên mẫu>`")
        if delete_embed_template(name.strip().lower()):
            await ctx.reply(f"🗑️ Đã xoá mẫu `{name}`.")
        else:
            await ctx.reply(f"❌ Không tìm thấy mẫu `{name}`.")

    @staticmethod
    def _color_from_raw(raw) -> int:
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            s = raw.strip().lstrip("#")
            try:
                return int(s, 16)
            except ValueError:
                pass
        return 0x5865F2

    def _clean_template_payload(self, raw: dict) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("phải là object JSON")
        title = str(raw.get("title", "")).strip()
        desc  = str(raw.get("description", "")).strip()
        if not title or not desc:
            raise ValueError("thiếu 'title' hoặc 'description'")
        return {
            "title": title,
            "description": desc,
            "color": self._color_from_raw(raw.get("color", 0x5865F2)),
            "image": (raw.get("image") or None),
            "thumbnail": (raw.get("thumbnail") or None),
            "footer": (raw.get("footer") or None),
        }

    async def _import_templates_from_json(self, raw_text: str) -> tuple[list[str], list[str]]:
        """Parse JSON dạng {"tên_mẫu": {title/description/color/image/thumbnail/footer}, ...}
        và lưu thẳng vào MongoDB qua save_embed_template() (bot đang chạy sẵn, có kết nối
        DB rồi nên lưu ngay lập tức, không cần restart). Trả về (đã lưu, lỗi)."""
        data = json.loads(raw_text)
        if not isinstance(data, dict) or not data:
            raise ValueError("File JSON phải là 1 object dạng {\"tên_mẫu\": {...}, ...}")
        saved, failed = [], []
        for name, payload in data.items():
            try:
                clean = self._clean_template_payload(payload)
                save_embed_template(str(name).strip().lower(), clean)
                saved.append(str(name).strip().lower())
            except Exception as e:
                failed.append(f"`{name}` ({e})")
        return saved, failed

    # ── .embedimport — nhập nhiều mẫu cùng lúc từ file .json đính kèm ──
    @commands.command(name="embedimport", aliases=["nhapmautb"])
    async def embedimport_cmd(self, ctx):
        if not is_staff_member(ctx.author):
            return await ctx.reply("❌ Bạn không có quyền dùng lệnh này.")
        if not ctx.message.attachments:
            return await ctx.reply(
                "❌ Đính kèm 1 file `.json` khi gõ lệnh này. Định dạng:\n"
                "```json\n"
                '{"ten-mau": {"title": "...", "description": "...", "color": "#5865F2", '
                '"image": null, "thumbnail": null, "footer": null}}\n'
                "```"
            )
        att = ctx.message.attachments[0]
        if not att.filename.lower().endswith(".json"):
            return await ctx.reply("❌ File phải có đuôi `.json`.")
        try:
            raw_text = (await att.read()).decode("utf-8")
        except Exception as e:
            return await ctx.reply(f"❌ Không đọc được file: {e}")
        try:
            saved, failed = await self._import_templates_from_json(raw_text)
        except Exception as e:
            return await ctx.reply(f"❌ File JSON không hợp lệ: {e}")

        msg = (f"✅ Đã lưu {len(saved)} mẫu vào MongoDB: " + ", ".join(f"`{n}`" for n in saved)) if saved \
              else "❌ Không lưu được mẫu nào."
        if failed:
            msg += "\n⚠️ Lỗi: " + "; ".join(failed)
        if saved:
            msg += "\nDùng ngay `.embeduse <tên>` — không cần restart bot."
        await ctx.reply(msg)

    @commands.command(name="userinfo", aliases=["ui", "whois"])
    async def userinfo_cmd(self, ctx, member: discord.Member = None):
        m     = member or ctx.author
        roles = [r.mention for r in m.roles if r.name != "@everyone"]
        account_age_days = (datetime.now(timezone.utc) - m.created_at).days

        badges = []
        if m.id in ADMIN_IDS:
            badges.append("👑 Admin")
        if is_staff_member(m):
            badges.append("🛡️ Staff")
        if m.id == ctx.guild.owner_id:
            badges.append("🏠 Owner")

        embed = discord.Embed(title=f"👤  {m}", color=m.color if m.color.value else 0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",         value=f"`{m.id}`",                                                         inline=True)
        embed.add_field(name="🤖 Bot",        value="✅" if m.bot else "❌",                                               inline=True)
        embed.add_field(name="📅 Tạo acc",    value=f"<t:{int(m.created_at.timestamp())}:D>",                             inline=True)
        embed.add_field(name="📥 Vào server", value=f"<t:{int(m.joined_at.timestamp())}:D>" if m.joined_at else "N/A",   inline=True)
        embed.add_field(name="🎖️ Role cao nhất", value=m.top_role.mention if m.top_role.name != "@everyone" else "Không có", inline=True)
        embed.add_field(name="🚀 Boost server", value=f"<t:{int(m.premium_since.timestamp())}:R>" if m.premium_since else "Không", inline=True)
        if m.is_timed_out():
            embed.add_field(name="🔇 Timeout", value=f"Đến <t:{int(m.timed_out_until.timestamp())}:R>", inline=True)
        if badges:
            embed.add_field(name="🏷️ Danh hiệu", value="  ".join(badges), inline=True)
        if account_age_days < 7:
            embed.add_field(
                name="⚠️ Cảnh báo",
                value=f"Tài khoản mới tạo **{account_age_days} ngày trước** — cẩn thận invite ảo/spam.",
                inline=False,
            )
        embed.add_field(name="🏷️ Roles",      value=" ".join(roles[-10:]) if roles else "Không có",                      inline=False)
        embed.set_thumbnail(url=m.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.command(name="serverinfo", aliases=["si", "server"])
    async def serverinfo_cmd(self, ctx):
        g    = ctx.guild
        bots = sum(1 for m in g.members if m.bot)
        boost_bar = "🚀" * g.premium_tier if g.premium_tier else "—"
        verif_labels = {
            discord.VerificationLevel.none:   "Không",
            discord.VerificationLevel.low:    "Thấp",
            discord.VerificationLevel.medium: "Trung bình",
            discord.VerificationLevel.high:   "Cao",
            discord.VerificationLevel.highest: "Rất cao",
        }
        threads = sum(1 for t in g.threads) if hasattr(g, "threads") else 0

        embed = discord.Embed(title=f"🏠  {g.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",         value=f"`{g.id}`",                                              inline=True)
        embed.add_field(name="👑 Owner",      value=g.owner.mention if g.owner else "N/A",                    inline=True)
        embed.add_field(name="📅 Tạo lúc",   value=f"<t:{int(g.created_at.timestamp())}:D>",                 inline=True)
        embed.add_field(name="👥 Thành viên", value=f"👤 {g.member_count - bots}  🤖 {bots}",                 inline=True)
        embed.add_field(
            name="💬 Kênh",
            value=f"📝 {len(g.text_channels)}  🔊 {len(g.voice_channels)}  🗂️ {len(g.forums)}  🧵 {threads}",
            inline=True,
        )
        embed.add_field(name="📁 Category",   value=f"**{len(g.categories)}**",                               inline=True)
        embed.add_field(name="🏷️ Roles",      value=f"**{len(g.roles) - 1}**",                                inline=True)
        embed.add_field(name="😀 Emoji",      value=f"**{len(g.emojis)}** / {g.emoji_limit}",                 inline=True)
        embed.add_field(name="🚀 Boost",      value=f"{boost_bar}  Level {g.premium_tier} ({g.premium_subscription_count} boost)", inline=True)
        embed.add_field(name="🛡️ Xác minh",   value=verif_labels.get(g.verification_level, "?"),              inline=True)
        if g.icon: embed.set_thumbnail(url=g.icon.url)
        if g.banner: embed.set_image(url=g.banner.url)
        await ctx.reply(embed=embed)

    @commands.command(name="giaset2", aliases=["priceset2"])
    async def giaset2_prefix(self, ctx):
        """Alias prefix cho /giaset — giống .giaset"""
        await self.giaset_cmd(ctx)

    # ── Slash mod commands ──
    @app_commands.command(name="clear", description="Xoá tin nhắn trong kênh")
    @app_commands.describe(amount="Số tin nhắn cần xoá (1-500)")
    async def slash_clear(self, interaction: discord.Interaction, amount: int):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if amount < 1 or amount > 500: return await interaction.response.send_message("❌ Số lượng phải từ 1 đến 500.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Đã xoá **{len(deleted)}** tin nhắn.")

    @app_commands.command(name="addrole", description="Thêm role cho thành viên")
    @app_commands.describe(member="Thành viên", role="Role cần thêm")
    async def slash_addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if role >= interaction.guild.me.top_role: return await interaction.response.send_message("❌ Role này cao hơn role của bot.", ephemeral=True)
        await member.add_roles(role, reason=f"Bởi {interaction.user}")
        embed = discord.Embed(title="✅ Đã Thêm Role", color=0x57F287)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="removerole", description="Xoá role của thành viên")
    @app_commands.describe(member="Thành viên", role="Role cần xoá")
    async def slash_removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if interaction.user.id not in ADMIN_IDS and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        await member.remove_roles(role, reason=f"Bởi {interaction.user}")
        embed = discord.Embed(title="✅ Đã Xoá Role", color=0xFEE75C)
        embed.add_field(name="👤 Thành viên", value=member.mention, inline=True)
        embed.add_field(name="🏷️ Role",       value=role.mention,   inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Kiểm tra độ trễ bot")
    async def slash_ping(self, interaction: discord.Interaction):
        lat   = round(self.bot.latency * 1000)
        color = 0x57F287 if lat < 100 else (0xFEE75C if lat < 200 else 0xED4245)
        status = "Tốt 🟢" if lat < 100 else ("Bình thường 🟡" if lat < 200 else "Chậm 🔴")
        embed = discord.Embed(title="🏓 Pong!", description=f"Độ trễ: **{lat}ms** — {status}", color=color)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="embed", description="Soạn và gửi thông báo dạng embed")
    @app_commands.describe(
        channel="Kênh gửi thông báo (để trống = kênh hiện tại)",
        mention="Ping kèm theo thông báo (tuỳ chọn, chỉ admin dùng được)",
    )
    @app_commands.choices(mention=[
        app_commands.Choice(name="Không ping", value="none"),
        app_commands.Choice(name="@everyone", value="everyone"),
        app_commands.Choice(name="@here", value="here"),
    ])
    async def slash_embed(
        self, interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        mention: app_commands.Choice[str] = None,
    ):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
        target = channel or interaction.channel
        raw = mention.value if mention else None
        ping, warn = self._resolve_embed_ping(interaction.user, raw)
        if warn:
            # send_modal phải là response ĐẦU TIÊN cho slash command — gửi cảnh báo
            # qua followup ephemeral SAU khi modal đã mở, không gộp chung được.
            await interaction.response.send_modal(EmbedAnnounceModal(target, ping))
            await interaction.followup.send(warn, ephemeral=True)
        else:
            await interaction.response.send_modal(EmbedAnnounceModal(target, ping))

    @app_commands.command(name="embeduse", description="Gửi lại 1 mẫu thông báo đã lưu")
    @app_commands.describe(
        name="Tên mẫu (xem qua .embedlist / /embedlist)",
        channel="Kênh gửi thông báo (để trống = kênh hiện tại)",
        mention="Ping kèm theo thông báo (tuỳ chọn, chỉ admin dùng được)",
    )
    @app_commands.choices(mention=[
        app_commands.Choice(name="Không ping", value="none"),
        app_commands.Choice(name="@everyone", value="everyone"),
        app_commands.Choice(name="@here", value="here"),
    ])
    async def slash_embeduse(
        self, interaction: discord.Interaction, name: str,
        channel: discord.TextChannel = None,
        mention: app_commands.Choice[str] = None,
    ):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
        payload = get_embed_template(name.strip().lower())
        if not payload:
            return await interaction.response.send_message(f"❌ Không tìm thấy mẫu `{name}`.", ephemeral=True)
        target = channel or interaction.channel
        raw = mention.value if mention else None
        ping, warn = self._resolve_embed_ping(interaction.user, raw)
        embed = build_embed_from_payload(payload, requester=interaction.user)
        note = (
            f"👁️ **Xem trước mẫu `{name}`** — chỉ mình bạn thấy tin nhắn này. Gửi tới {target.mention}"
            + (f" (kèm `{ping}`)" if ping else "") + "."
        )
        if warn:
            note += f"\n{warn}"
        view = EmbedPreviewView(dict(payload), target, ping, interaction.user.id, template_name=name.strip().lower())
        await interaction.response.send_message(content=note, embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="embedlist", description="Xem danh sách mẫu thông báo đã lưu")
    async def slash_embedlist(self, interaction: discord.Interaction):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
        templates = get_embed_templates()
        if not templates:
            return await interaction.response.send_message(
                "📭 Server chưa có mẫu thông báo nào. Sau khi gửi `.embed`, nhấn nút 💾 để lưu làm mẫu.", ephemeral=True
            )
        embed = discord.Embed(title="📋 Danh sách mẫu thông báo", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.description = "\n".join(
            f"`{name}` — {p.get('title') or '(không tiêu đề)'}" for name, p in templates.items()
        )[:4000]
        embed.set_footer(text="Dùng /embeduse <tên> để gửi lại")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="embeddel", description="Xoá 1 mẫu thông báo đã lưu")
    @app_commands.describe(name="Tên mẫu cần xoá")
    async def slash_embeddel(self, interaction: discord.Interaction, name: str):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
        if delete_embed_template(name.strip().lower()):
            await interaction.response.send_message(f"🗑️ Đã xoá mẫu `{name}`.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Không tìm thấy mẫu `{name}`.", ephemeral=True)

    @app_commands.command(name="embedimport", description="Nhập nhiều mẫu thông báo cùng lúc từ file .json")
    @app_commands.describe(file="File .json dạng {\"tên_mẫu\": {title, description, color, image, thumbnail, footer}}")
    async def slash_embedimport(self, interaction: discord.Interaction, file: discord.Attachment):
        if not is_staff_member(interaction.user):
            return await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.", ephemeral=True)
        if not file.filename.lower().endswith(".json"):
            return await interaction.response.send_message("❌ File phải có đuôi `.json`.", ephemeral=True)
        try:
            raw_text = (await file.read()).decode("utf-8")
        except Exception as e:
            return await interaction.response.send_message(f"❌ Không đọc được file: {e}", ephemeral=True)
        try:
            saved, failed = await self._import_templates_from_json(raw_text)
        except Exception as e:
            return await interaction.response.send_message(f"❌ File JSON không hợp lệ: {e}", ephemeral=True)

        msg = (f"✅ Đã lưu {len(saved)} mẫu vào MongoDB: " + ", ".join(f"`{n}`" for n in saved)) if saved \
              else "❌ Không lưu được mẫu nào."
        if failed:
            msg += "\n⚠️ Lỗi: " + "; ".join(failed)
        if saved:
            msg += "\nDùng ngay `/embeduse` — không cần restart bot."
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="userinfo", description="Xem thông tin thành viên")
    @app_commands.describe(member="Thành viên (để trống = bản thân)")
    async def slash_userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        m     = member or interaction.user
        roles = [r.mention for r in m.roles if r.name != "@everyone"]
        embed = discord.Embed(title=f"👤  {m}", color=m.color if m.color.value else 0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",        value=f"`{m.id}`",                                                inline=True)
        embed.add_field(name="🤖 Bot",       value="✅" if m.bot else "❌",                                    inline=True)
        embed.add_field(name="📅 Tạo acc",   value=f"<t:{int(m.created_at.timestamp())}:D>",                  inline=True)
        embed.add_field(name="📥 Vào server",value=f"<t:{int(m.joined_at.timestamp())}:D>" if m.joined_at else "N/A", inline=True)
        embed.add_field(name="🏷️ Roles",     value=" ".join(roles[-10:]) if roles else "Không có",            inline=False)
        embed.set_thumbnail(url=m.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Xem thông tin server")
    async def slash_serverinfo(self, interaction: discord.Interaction):
        g     = interaction.guild
        bots  = sum(1 for m in g.members if m.bot)
        embed = discord.Embed(title=f"🏠  {g.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🆔 ID",        value=f"`{g.id}`",                                              inline=True)
        embed.add_field(name="👑 Owner",     value=g.owner.mention if g.owner else "N/A",                    inline=True)
        embed.add_field(name="📅 Tạo lúc",  value=f"<t:{int(g.created_at.timestamp())}:D>",                 inline=True)
        embed.add_field(name="👥 Thành viên",value=f"👤 {g.member_count - bots}  🤖 {bots}",                 inline=True)
        embed.add_field(name="💬 Kênh",     value=f"📝 {len(g.text_channels)}  🔊 {len(g.voice_channels)}", inline=True)
        if g.icon: embed.set_thumbnail(url=g.icon.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="botinfo", description="Xem thông tin bot")
    async def slash_botinfo(self, interaction: discord.Interaction):
        import platform
        embed = discord.Embed(title=f"🤖  {self.bot.user.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🏓 Latency",  value=f"**{round(self.bot.latency*1000)}ms**", inline=True)
        embed.add_field(name="🌐 Servers",  value=f"**{len(self.bot.guilds)}**",            inline=True)
        embed.add_field(name="📋 Version",  value=f"`v{BOT_VERSION}`",                     inline=True)
        embed.add_field(name="🐍 Python",   value=f"`{platform.python_version()}`",        inline=True)
        if self.bot.user.avatar: embed.set_thumbnail(url=self.bot.user.avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Error handler ──
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound): pass
        elif isinstance(error, commands.MissingPermissions): await ctx.reply("❌ Bạn không có quyền thực hiện lệnh này.")


STOCK_CATEGORY_ID = 1506520186063163423
SOLD_CATEGORY_ID  = 1506652491779932240
SOLD_ESCALATE_AFTER_SECONDS = 24 * 3600  # 24h không ai xử lý → escalate sang Ruby
# Role "Đã Mua Hàng" — tặng cho buyer khi đơn được cộng tiền, dùng chung bởi
# .done (cogs/ticket.py) và luồng sold-stock (_SoldBuyerModal bên dưới).
DONE_ROLE_ID = 1515393691206811901

# ══════════════════════════════════════════
# SOLD-STOCK — parse giá từ tên kênh
# ══════════════════════════════════════════
def _parse_price_from_channel_name(name: str) -> int | None:
    """
    Bóc giá ở đầu tên kênh stock, vd: ✅𝟏𝟑𝟎𝐤-𝐧𝐨𝐧-𝟏𝐜𝐚𝐩𝐞 → 130000.
    Bỏ font Unicode + ký tự không phải chữ/số ở đầu trước khi parse.
    """
    from cogs.admin_views import _strip_unicode_font
    clean = _strip_unicode_font(name)
    # Bỏ mọi ký tự đầu không phải chữ/số (✅, •, -, khoảng trắng...)
    clean = _re.sub(r"^[^a-zA-Z0-9]+", "", clean)
    # Lấy token đầu tiên trước dấu '-' hoặc '_'
    m = _re.match(r"^([a-zA-Z0-9.]+)", clean)
    if not m:
        return None
    token = m.group(1)
    return parse_amount(token)


# ══════════════════════════════════════════
# SOLD-STOCK — Modal admin TuyTam/Ruby điền giá thủ công
# ══════════════════════════════════════════
class _SoldPriceModal(Modal, title="💰 Nhập giá đơn sold"):
    price_input = TextInput(label="Giá (vd: 130k, 1m2, 1tr5)", placeholder="130k", max_length=20)

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        amount = parse_amount(self.price_input.value)
        if amount is None or amount <= 0:
            return await interaction.response.send_message(
                f"❌ Giá `{self.price_input.value}` không hợp lệ. Dùng dạng: `130k`, `1m2`, `1tr5`.",
                ephemeral=True,
            )
        pending = get_pending_sold_price(self.channel_id)
        if not pending:
            resolved = get_resolved_sold_price(self.channel_id)
            if resolved:
                resolver = f"<@{resolved['resolved_by']}>"
                return await interaction.response.edit_message(
                    content=(
                        f"ℹ️ Đơn này đã được {resolver} xử lý — "
                        f"giá **{fmt_amount(resolved['amount'])}** (kênh cũ: `{resolved['old_name']}`)."
                    ),
                    embed=None, view=None,
                )
            return await interaction.response.send_message(
                "❌ Đơn này đã được xử lý hoặc không còn tồn tại.", ephemeral=True,
            )

        # ⚠️ Interaction này chạy trong DM admin — interaction.guild_id LUÔN None nên
        # GuildContextModal.interaction_check KHÔNG set được context. pending["guild_id"]
        # (đọc từ global data, không cần context) mới là nguồn đúng để set context ở đây,
        # TRƯỚC khi gọi add_seller_sale/add_pending_sold_buyer (data theo-guild).
        guild_id = pending.get("guild_id")
        if guild_id:
            set_current_guild(guild_id)

        seller_id = pending["seller_id"]
        add_seller_sale(seller_id, amount, pending["channel_name"], self.channel_id)
        mark_pending_sold_resolved(self.channel_id, amount, interaction.user.id, pending["old_name"])
        remove_pending_sold_price(self.channel_id)

        bot_ref = interaction.client
        await send_log(bot_ref, "INFO", "Sold-stock — điền giá thủ công",
            fields=[
                ("👤 Seller",  f"<@{seller_id}>",              True),
                ("💰 Giá",     fmt_amount(amount),              True),
                ("🎫 Kênh cũ", f"`{pending['old_name']}`",       True),
                ("✍️ Điền bởi", _uname_plain(interaction.user),   True),
            ],
            user=interaction.user, guild_id=guild_id)

        # Báo cho admin còn lại biết đơn đã được xử lý (nếu đã escalate sang cả 2)
        await _notify_other_admin(bot_ref, self.channel_id, interaction.user.id, amount, pending)

        # Đã có giá — giờ hỏi tiếp admin buyer là tài khoản Discord nào để cộng tiền
        # (giống lệnh .done), thay vì dừng lại ở đây như trước.
        if guild_id:
            add_pending_sold_buyer(
                self.channel_id, seller_id, amount, pending["channel_name"], pending["old_name"], guild_id,
            )
            await interaction.response.edit_message(
                content=(
                    f"✅ Đã ghi nhận **{fmt_amount(amount)}** cho <@{seller_id}> "
                    f"(kênh cũ: `{pending['old_name']}`).\n\n"
                    f"👉 Bấm nút bên dưới để cho biết **tài khoản Discord nào đã mua** — "
                    f"bot sẽ cộng tiền cho đúng người đó như lệnh `.done`."
                ),
                embed=None, view=_SoldBuyerView(self.channel_id),
            )
        else:
            await interaction.response.edit_message(
                content=(
                    f"✅ Đã ghi nhận **{fmt_amount(amount)}** cho <@{seller_id}> "
                    f"(kênh cũ: `{pending['old_name']}`).\n\n"
                    f"⚠️ Không xác định được guild của đơn này nên bot KHÔNG hỏi buyer tiếp — "
                    f"nếu cần cộng tiền cho khách, dùng lệnh `.done` trực tiếp trong ticket."
                ),
                embed=None, view=None,
            )


async def _notify_other_admin(bot, channel_id: int, resolved_by: int, amount: int, pending: dict):
    """Sau khi 1 admin điền giá, báo cho admin còn lại (nếu họ cũng có DM cho đơn này)."""
    other_id = None
    if resolved_by == ADMIN_TUYTAM_ID and ADMIN_RUBY_ID and pending.get("ruby_message_id"):
        other_id = ADMIN_RUBY_ID
    elif resolved_by == ADMIN_RUBY_ID and ADMIN_TUYTAM_ID and pending.get("tuytam_message_id"):
        other_id = ADMIN_TUYTAM_ID

    if not other_id:
        return
    try:
        other_user = bot.get_user(other_id) or await bot.fetch_user(other_id)
        if other_user:
            await other_user.send(
                f"ℹ️ Đơn sold kênh `{pending['old_name']}` đã được <@{resolved_by}> "
                f"xử lý — giá **{fmt_amount(amount)}**."
            )
    except discord.Forbidden:
        pass


class _SoldPriceView(View):
    """Nút trong DM admin TuyTam/Ruby — nhấn để mở Modal nhập giá."""
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="💰 Nhập giá", style=discord.ButtonStyle.primary, custom_id="sold_price_input")
    async def input_price(self, interaction: discord.Interaction, button: Button):
        pending = get_pending_sold_price(self.channel_id)
        if not pending:
            for item in self.children:
                item.disabled = True
            resolved = get_resolved_sold_price(self.channel_id)
            if resolved:
                content = (
                    f"ℹ️ Đơn này đã được <@{resolved['resolved_by']}> xử lý — "
                    f"giá **{fmt_amount(resolved['amount'])}**."
                )
            else:
                content = "ℹ️ Đơn này đã được xử lý rồi."
            return await interaction.response.edit_message(content=content, view=self)
        await interaction.response.send_modal(_SoldPriceModal(self.channel_id))


async def _send_sold_price_dm(bot, target_user_id: int, channel_id: int, old_name: str, seller_mention: str) -> int | None:
    """Gửi DM hỏi giá cho 1 admin, trả về message_id nếu gửi thành công."""
    target_user = bot.get_user(target_user_id) or await bot.fetch_user(target_user_id)
    if not target_user:
        return None
    embed = discord.Embed(
        title="💰 Cần nhập giá đơn sold",
        description=(
            f"Seller {seller_mention} vừa sold kênh `{old_name}` nhưng bot không đọc "
            f"được giá từ tên kênh.\n\nNhấn nút bên dưới để nhập giá thủ công."
        ),
        color=0xF0A500,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🎫 Kênh cũ", value=f"`{old_name}`", inline=True)
    embed.add_field(name="👤 Seller", value=seller_mention, inline=True)
    try:
        msg = await target_user.send(embed=embed, view=_SoldPriceView(channel_id))
        return msg.id
    except discord.Forbidden:
        return None


# ══════════════════════════════════════════
# SOLD-STOCK — hỏi admin TuyTam/Ruby "tài khoản Discord nào mua" để cộng tiền
# cho buyer (giống lệnh .done: add_user_spent + auto_give_buy_roles + role "Đã Mua Hàng")
# ══════════════════════════════════════════
class _SoldBuyerModal(Modal, title="🧑 Người mua đơn sold"):
    buyer_input = TextInput(
        label="ID hoặc @mention người mua",
        placeholder="vd: 123456789012345678 hoặc @tên",
        max_length=100,
    )

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        pending = get_pending_sold_buyer(self.channel_id)
        if not pending:
            return await interaction.response.edit_message(
                content="ℹ️ Đơn này đã được xử lý hoặc không còn tồn tại.", embed=None, view=None,
            )

        # Bóc ID từ dạng "<@123>", "<@!123>" hoặc số thuần
        raw = self.buyer_input.value.strip()
        digits = _re.sub(r"[^0-9]", "", raw)
        if not digits:
            return await interaction.response.send_message(
                f"❌ Không đọc được ID từ `{raw}`. Nhập ID số hoặc @mention người mua.",
                ephemeral=True,
            )
        buyer_id = int(digits)

        # ⚠️ Chạy trong DM admin — set_current_guild() thủ công từ guild_id đã lưu trong
        # pending (đọc từ global data, không cần context) TRƯỚC khi gọi add_user_spent/
        # auto_give_buy_roles (data + role theo-guild).
        guild_id = pending["guild_id"]
        set_current_guild(guild_id)

        bot_ref = interaction.client
        guild = bot_ref.get_guild(guild_id)
        if not guild:
            return await interaction.response.send_message(
                "❌ Bot không thấy server của đơn này (có thể đã rời server).", ephemeral=True,
            )

        try:
            buyer = guild.get_member(buyer_id) or await guild.fetch_member(buyer_id)
        except discord.NotFound:
            buyer = None
        except discord.HTTPException:
            buyer = None

        if not buyer:
            return await interaction.response.send_message(
                f"❌ Không tìm thấy thành viên `{buyer_id}` trong server. Kiểm tra lại ID/mention rồi thử lại.",
                ephemeral=True,
            )

        amount = pending["amount"]
        new_total = add_user_spent(buyer_id, amount)

        from cogs.admin_views import auto_give_buy_roles
        role_cfg = await auto_give_buy_roles(guild, buyer, new_total)

        done_role = guild.get_role(DONE_ROLE_ID)
        done_role_given = False
        if done_role:
            try:
                if done_role not in buyer.roles:
                    await buyer.add_roles(done_role, reason=f"Sold-stock — cộng tiền qua DM bởi {_uname_plain(interaction.user)}")
                done_role_given = True
            except Exception as _e:
                log_msg = f"[SOLD] Không thể give role {DONE_ROLE_ID} cho {buyer}: {_e}"
                print(log_msg)

        remove_pending_sold_buyer(self.channel_id)

        content = (
            f"✅ Đã cộng **{fmt_amount(amount)}** cho {buyer.mention} "
            f"(tổng hiện tại: **{fmt_amount(new_total)}**) — kênh cũ: `{pending['old_name']}`."
        )
        if role_cfg:
            content += f"\n🏆 Role hiện tại: **{role_cfg.get('label', '?')}**"
        if done_role:
            content += f"\n🎖️ Role tặng: {done_role.mention} {'✅' if done_role_given else '*(đã có sẵn)*'}"
        await interaction.response.edit_message(content=content, embed=None, view=None)

        await send_log(bot_ref, "INFO", "💰 Sold-stock — đã cộng tiền cho buyer qua DM",
            fields=[
                ("👤 Buyer",   buyer.mention,                    True),
                ("💰 Giá",     fmt_amount(amount),                True),
                ("🎫 Kênh cũ", f"`{pending['old_name']}`",        True),
                ("✍️ Nhập bởi", _uname_plain(interaction.user),  True),
            ],
            user=buyer, guild_id=guild_id)


class _SoldBuyerView(View):
    """Nút trong DM admin TuyTam/Ruby — nhấn để mở Modal nhập tài khoản buyer."""
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @discord.ui.button(label="🧑 Nhập người mua", style=discord.ButtonStyle.primary, custom_id="sold_buyer_input")
    async def input_buyer(self, interaction: discord.Interaction, button: Button):
        pending = get_pending_sold_buyer(self.channel_id)
        if not pending:
            for item in self.children:
                item.disabled = True
            return await interaction.response.edit_message(
                content="ℹ️ Đơn này đã được xử lý hoặc không còn tồn tại.", view=self,
            )
        await interaction.response.send_modal(_SoldBuyerModal(self.channel_id))


async def _send_sold_buyer_dm(bot, target_user_id: int, channel_id: int, old_name: str, amount: int, seller_mention: str) -> int | None:
    """Gửi DM hỏi 'tài khoản Discord nào mua' cho 1 admin, trả về message_id nếu gửi thành công."""
    target_user = bot.get_user(target_user_id) or await bot.fetch_user(target_user_id)
    if not target_user:
        return None
    embed = discord.Embed(
        title="🧑 Cần xác nhận người mua đơn sold",
        description=(
            f"Seller {seller_mention} vừa sold kênh `{old_name}` với giá **{fmt_amount(amount)}**.\n\n"
            f"Nhấn nút bên dưới và cho biết **tài khoản Discord nào đã mua** — bot sẽ cộng tiền "
            f"cho đúng người đó, y như lệnh `.done`."
        ),
        color=0xF0A500,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🎫 Kênh cũ", value=f"`{old_name}`", inline=True)
    embed.add_field(name="👤 Seller", value=seller_mention, inline=True)
    embed.add_field(name="💰 Giá", value=fmt_amount(amount), inline=True)
    try:
        msg = await target_user.send(embed=embed, view=_SoldBuyerView(channel_id))
        return msg.id
    except discord.Forbidden:
        return None


async def _escalate_pending_sold(bot, channel_id: int):
    """Sau 24h không ai xử lý → DM thêm cho Ruby, KHÔNG thu hồi nút bên TuyTam."""
    await asyncio.sleep(SOLD_ESCALATE_AFTER_SECONDS)
    pending = get_pending_sold_price(channel_id)
    if not pending or pending.get("escalated"):
        return  # Đã xử lý hoặc đã escalate rồi (resume sau restart)
    if not ADMIN_RUBY_ID:
        return

    seller_mention = f"<@{pending['seller_id']}>"
    msg_id = await _send_sold_price_dm(bot, ADMIN_RUBY_ID, channel_id, pending["old_name"], seller_mention)
    mark_pending_sold_escalated(channel_id)
    if msg_id:
        set_pending_sold_dm(channel_id, ruby_message_id=msg_id)
        bot.add_view(_SoldPriceView(channel_id), message_id=msg_id)

    await send_log(bot, "INFO", "⏰ Sold-stock — quá 24h, đã escalate sang admin Ruby",
        fields=[("👤 Seller", seller_mention, True), ("🎫 Kênh cũ", f"`{pending['old_name']}`", True)],
        guild_id=pending.get("guild_id"))


async def resume_pending_sold_views(bot):
    """Gọi từ bot.py on_ready — đăng ký lại persistent view cho mọi đơn pending còn tồn
    (giá lẫn buyer), và lên lịch escalate đúng theo thời gian còn lại (hoặc escalate ngay
    nếu đã quá 24h). [v4.18.0] Data đã chuyển sang global nên KHÔNG cần loop theo guild
    nữa — get_all_pending_sold_price()/get_all_pending_sold_buyer() đọc được ngay."""
    pending_price_all = get_all_pending_sold_price()
    for channel_id_str, pending in pending_price_all.items():
        channel_id = int(channel_id_str)

        tuytam_mid = pending.get("tuytam_message_id")
        if tuytam_mid:
            bot.add_view(_SoldPriceView(channel_id), message_id=tuytam_mid)

        ruby_mid = pending.get("ruby_message_id")
        if ruby_mid:
            bot.add_view(_SoldPriceView(channel_id), message_id=ruby_mid)

        if pending.get("escalated"):
            continue  # Đã escalate trước khi restart, không cần lên lịch lại

        try:
            created_at = datetime.fromisoformat(pending["time"])
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except Exception:
            created_at = datetime.now(timezone.utc)

        elapsed   = (datetime.now(timezone.utc) - created_at).total_seconds()
        remaining = SOLD_ESCALATE_AFTER_SECONDS - elapsed

        if remaining <= 0:
            asyncio.create_task(_escalate_pending_sold_now(bot, channel_id))
        else:
            asyncio.create_task(_escalate_pending_sold_after(bot, channel_id, remaining))

    # Đơn đang chờ xác định BUYER (không escalate — chỉ cần đăng ký lại nút bấm)
    pending_buyer_all = get_all_pending_sold_buyer()
    for channel_id_str, pending in pending_buyer_all.items():
        channel_id = int(channel_id_str)
        tuytam_mid = pending.get("tuytam_message_id")
        if tuytam_mid:
            bot.add_view(_SoldBuyerView(channel_id), message_id=tuytam_mid)
        ruby_mid = pending.get("ruby_message_id")
        if ruby_mid:
            bot.add_view(_SoldBuyerView(channel_id), message_id=ruby_mid)


async def _escalate_pending_sold_now(bot, channel_id: int):
    """Escalate ngay (dùng khi resume và đã quá 24h từ lúc tạo pending)."""
    pending = get_pending_sold_price(channel_id)
    if not pending or pending.get("escalated") or not ADMIN_RUBY_ID:
        return
    seller_mention = f"<@{pending['seller_id']}>"
    msg_id = await _send_sold_price_dm(bot, ADMIN_RUBY_ID, channel_id, pending["old_name"], seller_mention)
    mark_pending_sold_escalated(channel_id)
    if msg_id:
        set_pending_sold_dm(channel_id, ruby_message_id=msg_id)
        bot.add_view(_SoldPriceView(channel_id), message_id=msg_id)
    await send_log(bot, "INFO", "⏰ Sold-stock — quá 24h (resume sau restart), đã escalate sang admin Ruby",
        fields=[("👤 Seller", seller_mention, True), ("🎫 Kênh cũ", f"`{pending['old_name']}`", True)],
        guild_id=pending.get("guild_id"))


async def _escalate_pending_sold_after(bot, channel_id: int, delay_seconds: float):
    await asyncio.sleep(delay_seconds)
    await _escalate_pending_sold_now(bot, channel_id)


async def handle_sold(bot, message: discord.Message):
    """Gọi từ bot.py on_message để xử lý auto-sold."""
    if message.author.bot or not message.guild:
        return

    channel = message.channel
    if not isinstance(channel, discord.TextChannel):
        return

    stock_cat_id = get_cfg_stock_category()
    sold_cat_id  = get_cfg_sold_category()

    if not channel.category_id or channel.category_id != stock_cat_id:
        return

    content = message.content.strip().lower()
    if not (content.startswith("sold") or content.startswith("## sold")):
        return

    sold_category = message.guild.get_channel(sold_cat_id)
    if not sold_category or not isinstance(sold_category, discord.CategoryChannel):
        await message.add_reaction("⚠️")
        return

    old_name = channel.name
    if "•" in old_name:
        new_name = "❌•" + old_name.split("•", 1)[-1]
    else:
        new_name = "❌•" + old_name

    try:
        await channel.edit(
            name=new_name,
            category=sold_category,
            reason=f"Sold bởi {message.author} — auto-move",
        )
        await message.add_reaction("✅")
        await send_log(bot, "INFO", f"Kênh sold: `{old_name}` → `{new_name}`",
            fields=[("Seller", _uname_plain(message.author), True), ("Kênh mới", f"<#{channel.id}>", True), ("Category", sold_category.name, True)],
            guild_id=message.guild.id)
    except discord.Forbidden:
        await message.add_reaction("⚠️")
        return
    except Exception as e:
        await message.add_reaction("❌")
        await channel.send(f"⚠️ Lỗi khi chuyển kênh: `{e}`", delete_after=10)
        return

    # ── Thống kê doanh số seller (chỉ tính nếu seller hợp lệ — .seller add còn hạn) ──
    seller_id = message.author.id
    if not is_active_seller(message.guild.id, seller_id):
        return  # Không phải seller hợp lệ → vẫn chuyển kênh nhưng không tính thống kê

    amount = _parse_price_from_channel_name(old_name)

    if amount is not None and amount > 0:
        add_seller_sale(seller_id, amount, old_name, channel.id)
        await send_log(bot, "INFO", "💰 Sold-stock — đã ghi nhận thống kê",
            fields=[
                ("👤 Seller",  _uname_plain(message.author),  True),
                ("💰 Giá",     fmt_amount(amount),       True),
                ("🎫 Kênh cũ", f"`{old_name}`",          True),
            ],
            user=message.author, guild_id=message.guild.id)

        # ── Giá đã có ngay — hỏi admin TuyTam tài khoản Discord nào mua để cộng
        # tiền cho đúng người (giống lệnh .done), KHÔNG chặn phần trên (kênh đã
        # chuyển, thống kê seller đã ghi xong dù DM này có gửi được hay không).
        add_pending_sold_buyer(channel.id, seller_id, amount, new_name, old_name, message.guild.id)
        if not ADMIN_TUYTAM_ID:
            print(f"[SOLD] ⚠️ Không hỏi được người mua cho kênh `{old_name}` — chưa cài ADMIN_TUYTAM_ID.")
            await send_log(bot, "INFO", "⚠️ Sold-stock — chưa cài ADMIN_TUYTAM_ID, không hỏi được người mua",
                fields=[("👤 Seller", _uname_plain(message.author), True), ("🎫 Kênh cũ", f"`{old_name}`", True)],
                user=message.author, guild_id=message.guild.id)
            return
        msg_id = await _send_sold_buyer_dm(bot, ADMIN_TUYTAM_ID, channel.id, old_name, amount, message.author.mention)
        if msg_id:
            set_pending_sold_buyer_dm(channel.id, tuytam_message_id=msg_id)
            bot.add_view(_SoldBuyerView(channel.id), message_id=msg_id)
        else:
            print(f"[SOLD] ⚠️ Không gửi được DM hỏi người mua cho admin TuyTam — kênh `{old_name}` (DM tắt?).")
            await send_log(bot, "INFO", "⚠️ Không gửi được DM hỏi người mua cho admin TuyTam (DM tắt)",
                fields=[("👤 Seller", _uname_plain(message.author), True), ("🎫 Kênh cũ", f"`{old_name}`", True)],
                user=message.author, guild_id=message.guild.id)
        return

    # ── Không parse được giá → lưu pending + DM admin TuyTam nhập tay ──
    # (sau khi admin nhập giá xong, _SoldPriceModal.on_submit sẽ TỰ hỏi tiếp người mua)
    add_pending_sold_price(channel.id, seller_id, new_name, old_name, message.guild.id)

    if not ADMIN_TUYTAM_ID:
        print(f"[SOLD] ⚠️ Không đọc được giá từ tên kênh `{old_name}` & chưa cài ADMIN_TUYTAM_ID — bỏ qua hỏi giá.")
        await send_log(bot, "INFO", "⚠️ Sold-stock — không parse được giá & chưa cài ADMIN_TUYTAM_ID",
            fields=[("👤 Seller", _uname_plain(message.author), True), ("🎫 Kênh cũ", f"`{old_name}`", True)],
            user=message.author, guild_id=message.guild.id)
        return

    msg_id = await _send_sold_price_dm(bot, ADMIN_TUYTAM_ID, channel.id, old_name, message.author.mention)
    if msg_id:
        set_pending_sold_dm(channel.id, tuytam_message_id=msg_id)
        bot.add_view(_SoldPriceView(channel.id), message_id=msg_id)
    else:
        await send_log(bot, "INFO", "⚠️ Không gửi được DM hỏi giá cho admin TuyTam (DM tắt)",
            fields=[("👤 Seller", _uname_plain(message.author), True), ("🎫 Kênh cũ", f"`{old_name}`", True)],
            user=message.author, guild_id=message.guild.id)

    # Sau 24h nếu chưa xử lý → escalate sang Ruby
    asyncio.create_task(_escalate_pending_sold(bot, channel.id))


# ══════════════════════════════════════════
# SHOP ORDERS — nút bật/tắt trong .st (tính năng đang thử nghiệm)
# ══════════════════════════════════════════
class ShopOrdersToggleButton(discord.ui.Button):
    def __init__(self):
        enabled = get_cfg_shop_orders_enabled()
        super().__init__(
            label="Tắt Shop Orders" if enabled else "Bật Shop Orders",
            emoji="🧪",
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Bạn không có quyền dùng nút này.", ephemeral=True)

        new_state = not get_cfg_shop_orders_enabled()
        set_cfg_shop_orders_enabled(new_state)

        embed = interaction.message.embeds[0]
        status_text = "🟢 Bật" if new_state else "🔴 Tắt"
        for i, field in enumerate(embed.fields):
            if field.name == "🧪 Shop Orders (thử nghiệm)":
                embed.set_field_at(i, name=field.name, value=status_text, inline=True)
                break

        self.label = "Tắt Shop Orders" if new_state else "Bật Shop Orders"
        self.style = discord.ButtonStyle.danger if new_state else discord.ButtonStyle.success

        await interaction.response.edit_message(embed=embed, view=self.view)
        await send_log(
            interaction.client, "SETTINGS", f"Shop Orders (thử nghiệm) → {status_text}",
            fields=[("👤 Admin", f"{interaction.user}", True)],
            user=interaction.user,
            guild_id=interaction.guild_id,
        )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
