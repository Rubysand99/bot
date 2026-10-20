"""
shared/auth_gate.py — AUTH_GATE dùng chung cho MỌI bot con (lớp 1 + lớp 2, xem
AI_CONTEXT_SHARED.md mục AUTH_GATE). Lớp 3 (GuildContextView/GuildContextModal) nằm ở
shared/data.py vì gắn liền với contextvar.

⚠️ File này KHÔNG tự chạy được — mỗi bot con vẫn cần TỰ tạo `discord.commands.Bot`
instance của riêng mình (mỗi bot 1 process, 1 token, không share instance được). Đây là
các BUILDING BLOCK để bot.py của từng bot con wire vào, xem mẫu wiring ở cuối file.

Dùng ở bot_xxx/bot.py:

    from shared.auth_gate import GuildContextTree, get_prefix, set_guild_context_prefix, \\
        global_guild_authorization_check, notify_admins_unauthorized_guild

    bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None,
                        tree_cls=GuildContextTree)
    bot.before_invoke(set_guild_context_prefix)
    bot.check(global_guild_authorization_check)

    @bot.event
    async def on_guild_join(guild):
        from shared.data import ensure_guild_loaded, set_current_guild
        await ensure_guild_loaded(guild.id)
        set_current_guild(guild.id)
        await notify_admins_unauthorized_guild(bot, guild)
"""

import discord
from discord import app_commands
import logging
import time

from discord.ext import commands

from shared.data import (
    set_current_guild, is_guild_authorized, ADMIN_IDS, get_extra_admins, is_admin,
    set_command_context,
)

# Lệnh LUÔN được phép chạy dù server chưa ủy quyền — CHỈ bot_core có lệnh `.as` thật,
# nhưng để tên lệnh exempt ở đây (dùng chung) phòng trường hợp 1 bot khác cũng cần 1 lệnh
# "luôn chạy được" tương tự (vd .ping kiểm tra bot còn sống) — thêm tên lệnh vào set này.
AUTH_EXEMPT_COMMANDS = {"as"}

log = logging.getLogger("auth_gate")

# Lệnh/tham số chứa dữ liệu nhạy cảm (số tài khoản, token...) — KHÔNG log phần tham số.
_SENSITIVE = ("bank", "token", "key", "pass", "stk", "secret")

def _redact(cmd_name: str, content: str) -> str:
    if any(x in (cmd_name or "").lower() for x in _SENSITIVE):
        return (content or "").split(" ", 1)[0] + " <tham số đã ẩn>"
    return (content or "")[:120]


class GuildContextTree(app_commands.CommandTree):
    """CommandTree tùy chỉnh — tự set guild context TRƯỚC khi chạy bất kỳ slash command
    nào, đồng thời chặn slash command ở server CHƯA được ủy quyền (AUTH_GATE lớp 2)."""
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cmd = interaction.command
        cname = getattr(cmd, "qualified_name", None) or getattr(cmd, "name", None) or "?"
        set_command_context(f"/{cname}")
        u = interaction.user
        opts = ""
        try:
            raw = (interaction.data or {}).get("options") or []
            if not any(x in cname.lower() for x in _SENSITIVE):
                opts = " ".join(f"{o.get('name')}={str(o.get('value', ''))[:40]}" for o in raw if isinstance(o, dict))
        except Exception:
            pass
        if interaction.guild_id:
            set_current_guild(interaction.guild_id)
            if not is_guild_authorized(interaction.guild_id):
                fixed = u.id in ADMIN_IDS
                extra = u.id in get_extra_admins()
                log.warning(f"[AUTH-GATE] ⛔ chặn /{cname} · user={u.id} ({u}) · guild={interaction.guild_id}: server CHƯA ủy quyền "
                            f"(admin cố định={fixed}, admin phụ={extra}) → dùng `.as {interaction.guild_id}` để bật")
                if fixed or extra:
                    try:
                        await interaction.response.send_message(
                            f"🔒 Server này (`{interaction.guild_id}`) chưa được ủy quyền.\n"
                            + (f"Dùng `.as {interaction.guild_id}` để bật." if fixed
                               else f"Nhờ Ruby/TuyTam dùng `.as {interaction.guild_id}` để bật."),
                            ephemeral=True,
                        )
                    except Exception:
                        pass
                return False
        log.info(f"[SLASH] /{cname} {opts} · user={u.id} ({u}) · guild={interaction.guild_id} · kênh={interaction.channel_id}")
        return True


async def get_prefix(bot_: commands.Bot, message: discord.Message):
    """Đọc prefix riêng theo từng guild — DM và guild chưa cấu hình fallback ".".
    ⚠️ import trễ (trong hàm) để tránh vòng lặp import — mỗi bot con định nghĩa
    get_guild_prefix() trong data_ext.py riêng (rất ngắn, đọc load_data()["cfg_prefix"])."""
    if message.guild:
        from core.data import get_guild_prefix
        return get_guild_prefix(message.guild.id)
    return "."


async def set_guild_context_prefix(ctx: commands.Context):
    """Đăng ký qua bot.before_invoke — set guild context cho lệnh gõ chữ (.command),
    chạy TRƯỚC mọi lệnh prefix. Đồng thời set command context (để log quyền biết lệnh nào) và
    LOG mỗi lần gọi lệnh: `[CMD] .tên · user · guild · kênh · nội dung` (lệnh nhạy cảm bị ẩn tham số)."""
    if ctx.guild:
        set_current_guild(ctx.guild.id)
    name = ctx.command.qualified_name if ctx.command else "?"
    set_command_context(f".{name}")
    try: ctx._cmd_t0 = time.monotonic()
    except Exception: pass
    log.info(f"[CMD] .{name} · user={ctx.author.id} ({ctx.author}) · guild={getattr(ctx.guild, 'id', None)} "
             f"· kênh={getattr(ctx.channel, 'id', None)} · {_redact(name, ctx.message.content)!r}")


async def global_guild_authorization_check(ctx: commands.Context) -> bool:
    """Đăng ký qua bot.check — AUTH_GATE lớp 1, chặn MỌI lệnh prefix (.command) ở server
    CHƯA được ủy quyền, trừ lệnh nằm trong AUTH_EXEMPT_COMMANDS. DM luôn được phép.
    Server chưa ủy quyền: admin cố định VÀ admin phụ được báo lý do; người khác im lặng. Luôn có log."""
    if not ctx.guild:
        return True
    if ctx.command and ctx.command.qualified_name in AUTH_EXEMPT_COMMANDS:
        return True
    if is_guild_authorized(ctx.guild.id):
        return True
    set_current_guild(ctx.guild.id)  # để tra được admin phụ của đúng guild này
    fixed = ctx.author.id in ADMIN_IDS
    extra = (not fixed) and is_admin(ctx.author, quiet=True)
    log.warning(f"[AUTH-GATE] ⛔ chặn .{ctx.command.qualified_name if ctx.command else '?'} · user={ctx.author.id} ({ctx.author}) "
                f"· guild={ctx.guild.id}: server CHƯA ủy quyền (admin cố định={fixed}, admin phụ={extra}) "
                f"→ dùng `.as {ctx.guild.id}` để bật")
    if fixed or extra:
        try:
            await ctx.reply(
                f"🔒 Server này (`{ctx.guild.id}`) chưa được ủy quyền.\n"
                + (f"Dùng `.as {ctx.guild.id}` (gõ ở server đã ủy quyền, hoặc DM bot_core) để bật." if fixed
                   else f"Nhờ Ruby/TuyTam dùng `.as {ctx.guild.id}` để bật."),
                mention_author=False,
            )
        except Exception:
            pass
    return False


# ── LOG KẾT QUẢ LỆNH — đăng ký ở bot.py bằng bot.add_listener(...) ──
# Vì sao cần: AdminCog có on_command_error riêng → discord.py TẮT in traceback mặc định, nên mọi lệnh
# crash đều im lặng hoàn toàn trên Railway. Các hàm dưới đây khôi phục log (kèm traceback đầy đủ).
async def log_command_completion(ctx: commands.Context):
    t0 = getattr(ctx, "_cmd_t0", None)
    ms = f" · {int((time.monotonic() - t0) * 1000)}ms" if t0 else ""
    log.info(f"[CMD] ✅ .{ctx.command.qualified_name if ctx.command else '?'} chạy xong · user={ctx.author.id} · guild={getattr(ctx.guild, 'id', None)}{ms}")


async def log_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandNotFound):
        return  # gõ nhầm lệnh — quá nhiều, không log
    name = ctx.command.qualified_name if ctx.command else "?"
    who = f"user={ctx.author.id} ({ctx.author}) · guild={getattr(ctx.guild, 'id', None)}"
    if isinstance(error, commands.CheckFailure):
        log.warning(f"[CMD] ⛔ .{name} bị CHẶN bởi check ({type(error).__name__}: {error or 'check trả False — thường là AUTH_GATE server chưa ủy quyền'}) · {who}")
    elif isinstance(error, (commands.UserInputError, commands.CommandOnCooldown)):
        log.info(f"[CMD] ⚠️ .{name} sai tham số / cooldown: {type(error).__name__}: {error} · {who}")
    else:
        orig = getattr(error, "original", error)
        log.error(f"[CMD] ❌ .{name} LỖI: {type(orig).__name__}: {orig} · {who}", exc_info=orig)


async def log_app_command_completion(interaction: discord.Interaction, command):
    log.info(f"[SLASH] ✅ /{getattr(command, 'qualified_name', '?')} chạy xong · user={interaction.user.id} · guild={interaction.guild_id}")


async def notify_admins_unauthorized_guild(bot: discord.Client, guild: discord.Guild) -> None:
    """DM cho ADMIN_IDS khi bot được mời vào 1 server mới CHƯA ủy quyền. Gọi từ
    on_guild_join của TỪNG bot con — mỗi bot tự báo, vì admin cần biết BOT NÀO vừa được
    mời (tên bot lấy từ chính client `bot` truyền vào)."""
    from datetime import datetime, timezone
    if is_guild_authorized(guild.id):
        return
    embed = discord.Embed(
        title=f"🔒 {bot.user} vừa được mời vào server mới — CHƯA được ủy quyền",
        description=(
            f"**Server:** {guild.name}\n"
            f"**ID:** `{guild.id}`\n"
            f"**Thành viên:** {guild.member_count}\n\n"
            f"Bot sẽ KHÔNG hoạt động ở server này cho đến khi được ủy quyền.\n\n"
            f"Chạy lệnh sau ở bot_core để bật (DM bot_core hoặc gõ ở 1 server đã ủy quyền sẵn):\n"
            f"`.as {guild.id}`"
        ),
        color=0xFEE75C,
        timestamp=datetime.now(timezone.utc),
    )
    for admin_id in ADMIN_IDS:
        try:
            user = await bot.fetch_user(admin_id)
            await user.send(embed=embed)
        except Exception as e:
            print(f"[BOT] ⚠️ Không gửi được DM ủy quyền cho admin {admin_id}: {e}")
