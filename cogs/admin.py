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
    get_guild_prefix,
    get_cfg_font, _uname_plain, is_staff_member,
    load_data,
    is_guild_authorized, set_guild_authorized, is_data_cache_ready,
    add_extra_admin, get_extra_admins, remove_extra_admin, is_admin,
    ensure_guild_loaded,
    can_use_dangerous_cmd,
    set_current_guild,
    get_cfg_shop_orders_enabled,
    get_cfg_receipt_thankyou,
    get_embed_template, get_embed_templates, save_embed_template, delete_embed_template,
    GuildContextView as View, GuildContextModal as Modal,
)
from cogs.ticket import get_panel_buttons_cfg, PANEL_BUTTON_DEFS
from cogs.shop_admin import ShopOrdersToggleButton, ReceiptMessageButton

from cogs.admin_views import (
    SettingsView, SetupMainView,
    FONT_LABELS,
    _detect_channel_parts, _rebuild_name,
    MkChannelView,
    EmbedAnnounceView, EmbedAnnounceModal, EmbedPreviewView, EmbedUsePreviewButtonView, build_embed_from_payload,
    RoleAssignSelectView,
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

    # ── .as — Ủy quyền / thu hồi quyền dùng bot cho 1 server (AUTH_GATE, xem bot.py) ──
    @commands.command(name="as", aliases=["authorize", "uyquyen"])
    async def authorize_server_cmd(self, ctx, guild_id: int = None):
        if ctx.author.id not in ADMIN_IDS: return

        if guild_id is None:
            if ctx.guild:
                guild_id = ctx.guild.id
            else:
                await ctx.reply("❌ Dùng: `.as <id_server>` (hoặc DM/gõ trong server cần bật).", mention_author=False)
                return

        guild_obj  = self.bot.get_guild(guild_id)
        guild_name = guild_obj.name if guild_obj else "*(bot chưa/không còn ở server này)*"

        # FIX (v4.59.1): .as được miễn AUTH_GATE nên có thể chạy khi cache global CHƯA nạp — ghi lúc
        # đó sẽ đè danh sách ủy quyền thật. Chặn + báo lỗi rõ ràng thay vì ghi bừa.
        if not is_data_cache_ready():
            await ctx.reply("⏳ Bot đang khởi động / chưa nạp xong dữ liệu — thử lại sau vài giây.", mention_author=False)
            return
        try:
            if is_guild_authorized(guild_id):
                await set_guild_authorized(guild_id, False)
                embed = discord.Embed(
                    title="🔒 Đã THU HỒI ủy quyền",
                    description=f"**Server:** {guild_name}\n**ID:** `{guild_id}`\n\nBot sẽ ngừng hoạt động ở server này ngay lập tức.",
                    color=0xED4245,
                )
            else:
                # Đảm bảo guild đó đã có cache/document riêng ngay, không cần đợi bot restart.
                if not await ensure_guild_loaded(guild_id):
                    raise RuntimeError("không nạp được dữ liệu guild từ MongoDB")
                await set_guild_authorized(guild_id, True)  # await xong (đã ghi Mongo) mới báo thành công
                embed = discord.Embed(
                    title="🔓 Đã ỦY QUYỀN",
                    description=(
                        f"**Server:** {guild_name}\n**ID:** `{guild_id}`\n\n"
                        f"Bot đã có thể hoạt động ở server này. Data hoàn toàn riêng — "
                        f"không dùng chung với bất kỳ server nào khác."
                    ),
                    color=0x57F287,
                )
        except RuntimeError as e:
            await ctx.reply(f"❌ Không thực hiện được: {e}", mention_author=False)
            return
        await ctx.reply(embed=embed, mention_author=False)

    # ── .ad — Thêm admin PHỤ. FIX (đổi kiến trúc): trước đây admin thêm qua .ad có
    # TOÀN QUYỀN Ở MỌI SERVER bot đang hoạt động. Giờ admin phụ CHỈ có quyền ở ĐÚNG
    # server đang gõ lệnh — dùng `.ad` ở server nào thì chỉ server đó nhận quyền (xem
    # is_admin()/get_extra_admins() ở core/data.py, lưu theo guild). Vẫn CHỈ Ruby dùng
    # được — Ruby là người quyết định cấp quyền cho từng server.
    @commands.command(name="ad", aliases=["addadmin", "themadmin"])
    async def add_admin_cmd(self, ctx, user_id: str = None):
        if ctx.author.id != ADMIN_RUBY_ID:
            return await ctx.reply("❌ Chỉ Ruby được dùng lệnh này.", mention_author=False)
        if not ctx.guild:
            return await ctx.reply(
                "❌ Dùng lệnh này **trong server** cần cấp quyền (không dùng qua DM) — "
                "quyền admin phụ giờ chỉ áp dụng cho đúng server đang gõ lệnh.",
                mention_author=False)

        if not user_id or not user_id.strip("<@!>").isdigit():
            return await ctx.reply("❌ Dùng: `.ad <id>` (gõ ngay trong server muốn cấp quyền).", mention_author=False)
        uid = int(user_id.strip("<@!>"))

        try:
            user = await self.bot.fetch_user(uid)
        except discord.NotFound:
            return await ctx.reply(f"❌ Không tìm thấy user Discord với ID `{uid}`.", mention_author=False)
        except discord.HTTPException as e:
            return await ctx.reply(f"❌ Lỗi khi tra ID `{uid}`: {e}", mention_author=False)

        added = await add_extra_admin(uid)
        if not added:
            return await ctx.reply(
                f"ℹ️ {user.mention} (`{uid}`) đã là admin (cố định hoặc đã là admin phụ của server này) từ trước rồi.",
                mention_author=False)

        embed = discord.Embed(
            title="✅ Đã thêm Admin server này",
            description=(
                f"**User:** {user.mention} ({user})\n**ID:** `{uid}`\n"
                f"**Server:** {ctx.guild.name} (`{ctx.guild.id}`)\n\n"
                f"Có toàn quyền admin **CHỈ ở server này**, có hiệu lực ngay lập tức — "
                f"không cần restart bot. Dùng `.rmad {uid}` để thu hồi."
            ),
            color=0x57F287,
        )
        embed.set_footer(text=f"Thêm bởi {ctx.author}")
        await ctx.reply(embed=embed, mention_author=False)

        await send_log(self.bot, "SETTINGS", "Thêm admin server (qua .ad)",
            fields=[("👤 User", f"{user} ({uid})", True), ("👑 Bởi", str(ctx.author), True)],
            user=ctx.author, guild_id=ctx.guild.id)

    # ── .rmad — Thu hồi quyền admin PHỤ khỏi server đang gõ lệnh. KHÔNG đụng được 2
    # admin cố định (ADMIN_RUBY_ID/ADMIN_TUYTAM_ID, đọc từ env). CHỈ Ruby dùng được. ──
    @commands.command(name="rmad", aliases=["removeadmin", "xoaadmin"])
    async def remove_admin_cmd(self, ctx, user_id: str = None):
        if ctx.author.id != ADMIN_RUBY_ID:
            return await ctx.reply("❌ Chỉ Ruby được dùng lệnh này.", mention_author=False)
        if not ctx.guild:
            return await ctx.reply("❌ Dùng lệnh này **trong server** cần thu hồi quyền (không dùng qua DM).", mention_author=False)

        if not user_id or not user_id.strip("<@!>").isdigit():
            return await ctx.reply("❌ Dùng: `.rmad <id>`", mention_author=False)
        uid = int(user_id.strip("<@!>"))

        if uid in ADMIN_IDS:
            return await ctx.reply(
                "❌ Không thể xoá admin cố định (Ruby/TuyTam) qua lệnh này — phải đổi biến "
                "môi trường `ADMIN_RUBY_ID`/`ADMIN_TUYTAM_ID` trên Railway.",
                mention_author=False)

        removed = await remove_extra_admin(uid)
        if not removed:
            return await ctx.reply(f"ℹ️ `{uid}` không phải admin phụ của server này.", mention_author=False)

        await ctx.reply(f"🗑️ Đã thu hồi quyền admin của <@{uid}> ở server **{ctx.guild.name}**.", mention_author=False)
        await send_log(self.bot, "SETTINGS", "Xoá admin server (qua .rmad)",
            fields=[("👤 User", f"`{uid}`", True), ("👑 Bởi", str(ctx.author), True)],
            user=ctx.author, guild_id=ctx.guild.id)

    # ── .admin — Xem danh sách TẤT CẢ admin bot: 2 admin cố định (mọi server) + admin
    # phụ CỦA SERVER ĐANG GÕ LỆNH (thêm qua .ad — không phải mọi server). Ai đang có
    # quyền admin (cố định hoặc phụ của server này) đều xem được, không riêng Ruby. ──
    @commands.command(name="admin", aliases=["adminlist", "dsadmin"])
    async def admin_list_cmd(self, ctx):
        if not is_admin(ctx.author):
            return

        embed = discord.Embed(title="👑 Danh sách Admin", color=0x5865F2, timestamp=datetime.now(timezone.utc))

        fixed_lines = []
        for uid in ADMIN_IDS:
            tag = " *(Ruby)*" if uid == ADMIN_RUBY_ID else (" *(TuyTam)*" if uid == ADMIN_TUYTAM_ID else "")
            fixed_lines.append(f"<@{uid}>{tag} — `{uid}`")
        embed.add_field(
            name="🌍 Admin cố định (mọi server)",
            value="\n".join(fixed_lines) if fixed_lines else "*(chưa cài env)*",
            inline=False,
        )

        if ctx.guild:
            extra = get_extra_admins()
            embed.add_field(
                name=f"🏠 Admin phụ — chỉ server này ({ctx.guild.name})",
                value=("\n".join(f"<@{uid}> — `{uid}`" for uid in extra) if extra
                       else "*(chưa có — thêm qua `.ad <id>`)*"),
                inline=False,
            )
        else:
            embed.add_field(
                name="🏠 Admin phụ theo server",
                value="*(dùng lệnh trong 1 server để xem admin phụ của server đó)*",
                inline=False,
            )

        embed.set_footer(text=f"Yêu cầu bởi {ctx.author}")
        await ctx.reply(embed=embed, mention_author=False)

    # ── .settings ──
    @commands.command(name="settings", aliases=["setting", "caidat", "st"])
    async def settings_cmd(self, ctx):
        if not is_admin(ctx.author): return
        data = load_data()
        # FIX: title trước đây hardcode "TuyTam Store" — hiện sai tên cho mọi guild khác.
        embed = discord.Embed(title=f"⚙️  Bot Settings — {ctx.guild.name}", color=0x5865F2, timestamp=datetime.now(timezone.utc))
        def ch(k): c = data.get(k, 0); return f"<#{c}>" if c else "Chưa cài"
        def ro(k): r = data.get(k, 0); return f"<@&{r}>" if r else "Chưa cài"
        embed.add_field(name="📋 Log Channel (Rudy)", value=ch("cfg_log_rudy"),        inline=True)
        embed.add_field(name="🎫 Ticket Category",    value=ch("cfg_ticket_category"), inline=True)
        embed.add_field(name="🛡️ Support Role",      value=ro("cfg_support_role"),    inline=True)
        embed.add_field(name="👋 Welcome Channel",   value=ch("cfg_welcome_channel"), inline=True)
        embed.add_field(name="🏪 Seller Role",       value=ro("cfg_seller_role"),     inline=True)
        embed.add_field(name="🔨 Builder Role",      value=ro("cfg_builder_role"),    inline=True)
        embed.add_field(name="🎖️ Done Role",         value=ro("cfg_done_role"),       inline=True)
        embed.add_field(name="✅ Legit Channel",     value=ch("cfg_legit_channel"),   inline=True)
        embed.add_field(name="📸 Proof Channel",    value=ch("cfg_proof_channel"),   inline=True)
        embed.add_field(name="📄 Transcript Channel", value=ch("cfg_transcript_channel"), inline=True)
        embed.add_field(name="🤖 AI Channel",        value=ch("cfg_ai_channel"),      inline=True)
        embed.add_field(name="📦 Stock Category",    value=ch("cfg_stock_category"),  inline=True)
        embed.add_field(name="✅ Sold Category",     value=ch("cfg_sold_category"),   inline=True)
        embed.add_field(name="🔤 Font server",       value=FONT_LABELS.get(data.get("cfg_font","normal"),"normal"), inline=True)
        shop_status = "🟢 Bật" if get_cfg_shop_orders_enabled() else "🔴 Tắt"
        embed.add_field(name="🧪 Shop Orders (thử nghiệm)", value=shop_status, inline=True)
        relay_status = "🟢 Bật" if data.get("cfg_ticket_relay", True) else "🔴 Tắt"
        embed.add_field(name="🪄 Relay Tin Admin (Ticket)", value=relay_status, inline=True)
        thankyou_preview = get_cfg_receipt_thankyou().split("\n")[0]
        embed.add_field(name="🧾 Lời Cảm Ơn Hoá Đơn", value=thankyou_preview[:100], inline=False)
        panel_cfg = get_panel_buttons_cfg()
        panel_on  = sum(1 for v in panel_cfg.values() if v)
        embed.add_field(name="🔘 Panel Buttons", value=f"{panel_on}/{len(PANEL_BUTTON_DEFS)} bật — `.panelbtn` để chỉnh", inline=True)
        embed.set_footer(text=f"Nhấn nút bên dưới để thay đổi  •  Yêu cầu bởi {ctx.author}")

        view = SettingsView(ctx.guild)
        view.add_item(ShopOrdersToggleButton())
        view.add_item(ReceiptMessageButton())
        await ctx.reply(embed=embed, view=view)

    # ── .sv / .giaset ──
    # ── .addrole / .removerole ──
    # FIX: trước đây `.addrole @user @role` bắt buộc gõ role dạng @mention để
    # discord.Role converter parse được → Discord tự ping TOÀN BỘ member đang có
    # role đó ngay khi tin nhắn được gửi đi (không phải do bot, không thể chặn
    # sau khi đã gửi). Giờ chỉ gõ `.addrole @user`, chọn role qua dropdown
    # (RoleAssignSelectView ở admin_views.py — dùng discord.ui.RoleSelect, không
    # gõ chữ nên không tạo ra mention thật). Nhân tiện: `.removerole` trước đây
    # THIẾU check "role cao hơn role bot" (chỉ `.addrole` có) — giờ dùng chung 1
    # đường xử lý nên cả 2 đều được check như nhau.
    @commands.command(name="addrole", aliases=["giverole"])
    async def addrole_cmd(self, ctx, member: discord.Member = None):
        if not is_admin(ctx.author): return await ctx.reply("❌ Bạn không có quyền.")
        if not member: return await ctx.reply("❌ Dùng: `.addrole @user`, sau đó chọn role trong danh sách hiện ra.")
        view = RoleAssignSelectView(member=member, invoker_id=ctx.author.id, action="add")
        await ctx.reply(f"Chọn role muốn **thêm cho** {member.mention}:", view=view)

    @commands.command(name="removerole", aliases=["takerole"])
    async def removerole_cmd(self, ctx, member: discord.Member = None):
        if not is_admin(ctx.author): return await ctx.reply("❌ Bạn không có quyền.")
        if not member: return await ctx.reply("❌ Dùng: `.removerole @user`, sau đó chọn role trong danh sách hiện ra.")
        view = RoleAssignSelectView(member=member, invoker_id=ctx.author.id, action="remove")
        await ctx.reply(f"Chọn role muốn **xoá khỏi** {member.mention}:", view=view)

    # (Lệnh `.donerole` đã gộp vào `.st` — nút "🎖️ Done Role", xem cogs/admin_views.py: SettingsView)

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
        if not is_admin(ctx.author): return await ctx.reply("❌ Chỉ admin.")
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
        if not is_admin(ctx.author):
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
        if not is_admin(ctx.author):
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
                     "`.panel` — Đăng panel mua/bán NGAY vào kênh hiện tại\n"
                     "`.mmpanel` — Đăng panel Giao Dịch Trung Gian (AutoMM)\n"
                     "`.panelbuttons` (alias `.panelbtn`) — Bật/tắt từng nút của panel (riêng theo server)\n"
                     "`.setpanelchannel #kênh` (alias `.setpanel`) — CHỈ lưu kênh để bot tự gửi panel về sau, không gửi ngay (khác `.panel`)\n"
                     "`.close` — Đóng ticket hiện tại\n"
                     "`.done <tiền>` — Hoàn thành đơn, tạo QR (chỉ admin)\n"
                     "`.donecash <tiền>` (alias `.done+`) — Hoàn thành đơn KHÔNG cần QR, đã thu tiền mặt/chuyển khoản tay\n"
                     "`.undone <tiền>` (alias `.donesub`/`.trutien`) — Trừ tiền đã tiêu khi lỡ `.done` nhầm, tự mở lại ticket để `.done` lại đúng\n"
                     "`.orderbase` — Tạo ticket Order Base (admin)", False),
                    ("🏷️ Loại ticket → Role",
                     "`.setrole <ticket_key> <seller|builder|xoá>` — Gán loại ticket vào nhóm role\n"
                     "`.listroles` — Xem toàn bộ cấu hình loại ticket → role", False),
                    ("🛒 Ticket Mua Hàng",
                     "Panel có thêm nút 🛒 Ticket Mua Hàng — trước khi tạo ticket, bot hỏi user cần hỗ trợ "
                     "dịch vụ gì (chọn trong danh sách admin tự thêm)\n"
                     "`.ticketoptions add <tên>` (alias `.rubyoption`/`.rbopt`) — Thêm 1 dịch vụ vào danh sách lựa chọn\n"
                     "`.ticketoptions remove <tên>` — Xoá 1 dịch vụ\n"
                     "`.ticketoptions edit <tên cũ> -> <tên mới>` — Đổi tên 1 dịch vụ\n"
                     "`.ticketoptions list` — Xem danh sách hiện tại\n"
                     "-# Gộp nhiều thao tác cùng lúc, cách nhau bằng dấu phẩy: `.ticketoptions add A, add B, remove C, edit D -> E`\n"
                     "`.setrole rubyshop @role` — Gán role xử lý Ticket Mua Hàng", False),
                    ("🤝 Giao Dịch Trung Gian",
                     "`.mmpanel` — Đăng panel Giao Dịch Trung Gian (AutoMM)\n"
                     "User bấm **Tạo giao dịch** → bot hỏi ID tài khoản muốn giao dịch → tạo ticket riêng, "
                     "luôn ping admin TuyTam để trực tiếp làm trung gian\n"
                     "`.setrole middleman @role` — Gán thêm role hỗ trợ (ngoài admin TuyTam mặc định)", False),
                    ("📁 Category riêng theo Seller",
                     "`.setsellercat @seller #category` (alias `.setsl`) — Gán category riêng cho 1 seller\n"
                     "`.removesellercat @seller` (alias `.removesl`) — Xoá category riêng của 1 seller\n"
                     "`.sellercats` (alias `.listsl`) — Xem danh sách seller → category\n"
                     "-# Khác với mục dưới: đây là **kênh** riêng của seller, không phải **role**.", False),
                    ("🎭 Role được tính là Seller",
                     "`.addsellerrole @role` — Thêm 1 role vào danh sách được tính là seller\n"
                     "`.rmsellerrole @role` — Bỏ 1 role khỏi danh sách\n"
                     "`.sellerroles` — Xem danh sách role hiện tại\n"
                     "-# Khác `.seller add/remove/list` (xem `.help admin`): đó là danh sách seller cụ thể "
                     "(có hạn ngày), còn đây là ROLE nào thì tự động được coi là seller.", False),
                    ("📊 Thống kê",
                     "`.ticketinfo [@user]` — Xem lịch sử ticket của user\n"
                     "`.thongke [MM/YYYY]` — Thống kê doanh thu theo tháng", False),
                    ("🔷 Slash commands",
                     "`/close` `/done`", False),
                ]
            },
            "invite": {
                "emoji": "📨", "title": "Invite",
                "fields": [
                    ("📋 Thống kê invite",
                     "`.invite [@user]` — Xem invite tháng này + all-time của bản thân / người khác\n"
                     "`.invitetop [n] [MM/YYYY] [alltime]` — Leaderboard invite\n"
                     "  • Mặc định: top 10 tháng hiện tại\n"
                     "  • `.invitetop 20` — top 20 tháng này\n"
                     "  • `.invitetop 06/2026` — top 10 tháng 6/2026\n"
                     "  • `.invitetop alltime` — top 10 all-time", False),
                    ("🔄 Reset invite (admin)",
                     "`.resetinvitemonth [@user|all]` (alias `.resetinvite`) — Reset invite **tháng hiện tại** (all-time giữ nguyên)\n"
                     "`.resetinviteall [@user]` (alias `.resetinvites`) — Reset invite **all-time** *(hỏi lại trước khi xóa — khác hẳn lệnh trên, đừng nhầm)*", False),
                    ("🌐 Quản lý server bot (admin)",
                     "`.serverlist` (alias `.servers`/`.guildlist`) — Danh sách server bot đang ở, kèm ID + trạng thái ủy quyền\n"
                     "`.as <guild_id>` (alias `.authorize`/`.uyquyen`) — Bật/tắt (toggle) ủy quyền cho 1 server. "
                     "Server CHƯA ủy quyền → bot không chạy bất kỳ lệnh/tính năng nào ở đó. "
                     "Không truyền `guild_id` → áp dụng cho server đang gõ lệnh. Dùng được cả qua DM bot.\n"
                     "`.leaveguild <guild_id>` — Cho bot rời khỏi 1 server cụ thể", False),
                    ("👑 Quản lý Admin bot (chỉ Ruby)",
                     "`.ad <id>` (alias `.addadmin`/`.themadmin`) — Thêm 1 user làm admin bot, "
                     "toàn quyền như Ruby/TuyTam ở **mọi** server. Có hiệu lực ngay, không cần "
                     "restart bot. Chỉ Ruby dùng được lệnh này.", False),
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
                     "`.del <n>` (alias `.xoa`/`.purge`) — Xóa n tin nhắn\n"
                     "`.addrole @user` — Thêm role (chọn qua danh sách)\n"
                     "`.removerole @user` — Xóa role (chọn qua danh sách)\n"
                     "`.userinfo [@user]` — Thông tin thành viên\n"
                     "`.serverinfo` — Thông tin server\n"
                     "`.backfill [số]` — Quét lại kênh legit, thả ✅ cho tin bị bỏ sót (mặc định 25)", False),
                    ("⚠️ Xoá category (cẩn thận — không thể hoàn tác)",
                     "`.clearcategory <category>` (alias `.clearcat`/`.dondanhmuc`) — Xoá **TOÀN BỘ kênh** "
                     "trong 1 category, có bước xác nhận trước khi xoá. Khác hẳn `.del` (chỉ xoá tin nhắn) — "
                     "đừng nhầm 2 lệnh này.", False),
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
        embed.add_field(name="🎫 Ticket",    value="`.panel` `.mmpanel` `.panelbuttons` `.close` `.done` `.donecash` `.undone`\n`.ticketinfo` `.thongke` `.setrole`", inline=True)
        embed.add_field(name="📨 Invite",    value="`.invite` `.invitetop` `.resetinvitemonth`\n`/invite` `/invitetop`", inline=True)
        embed.add_field(name="🏪 Dịch vụ",  value="`.sv` `.giaset`\n`/sv` `/giaset`", inline=True)
        embed.add_field(name="🎉 Giveaway",  value="`/giveaway` `/gend`\n`/greroll` `/gwlist`\n`.gwstatus` `.gwpick` `.gwreset`", inline=True)
        embed.add_field(name="🔨 Mod",       value="`.ban` `.kick` `.timeout` `.tempban`\n`.warn` `.clearwarn` `.modlog` `.xoa` `.automod`", inline=True)
        embed.add_field(name="🤖 AI Chat",   value="`.aireset` `.mychat` `.aisearch`", inline=True)
        embed.add_field(name="📋 Log",       value="`.setlog` `.setuplog` `.loginfo` `.baocao`", inline=True)
        embed.add_field(name="⚙️ Admin",     value="`.st` `.setup` `.clearcategory` `.addrole` `.emoji`\n`.rename` `.mkchannel`", inline=True)
        embed.add_field(name="🏪 Seller",    value="`.seller add/remove/list/panel` `.myseller`\n`.setsellercat` `.addsellerrole` *(xem `.help ticket`)*", inline=True)
        embed.add_field(name="🧾 Shop Orders", value="`.shopbank` `.setqueue` `.shoporderno`\n`.bxh` — bảng xếp hạng\n*(dùng chung `.done` ở Ticket)*", inline=True)
        embed.add_field(name="🛒 Sản phẩm",    value="`.addlisting #forum \"IGN\" \"Giá\" \"Cape\"`\n*(xem `.help listings`)*", inline=True)
        embed.set_footer(text=f"TuyTam Store  •  v{BOT_VERSION}  •  .help <mục> để xem chi tiết")
        await ctx.reply(embed=embed)

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
        if not is_admin(user):
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
        if is_admin(m):
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

    # ── Slash mod commands ──
    @app_commands.command(name="clear", description="Xoá tin nhắn trong kênh")
    @app_commands.describe(amount="Số tin nhắn cần xoá (1-500)")
    async def slash_clear(self, interaction: discord.Interaction, amount: int):
        if not is_admin(interaction.user) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bạn không có quyền.", ephemeral=True)
        if amount < 1 or amount > 500: return await interaction.response.send_message("❌ Số lượng phải từ 1 đến 500.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Đã xoá **{len(deleted)}** tin nhắn.")

    @app_commands.command(name="addrole", description="Thêm role cho thành viên")
    @app_commands.describe(member="Thành viên", role="Role cần thêm")
    async def slash_addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if not is_admin(interaction.user) and not interaction.user.guild_permissions.administrator:
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
        if not is_admin(interaction.user) and not interaction.user.guild_permissions.administrator:
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


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
