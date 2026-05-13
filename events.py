# cogs/events.py — on_message, on_member_join, on_member_remove
from config import *

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)

    await handle_ai_message(message)

    bal_ch = get_cfg_balance_channel()
    if bal_ch and message.channel.id == bal_ch:
        await handle_balance_message(message)

    await handle_legit_message(message)

    await handle_vouch_message(message)

async def handle_legit_message(message: discord.Message):
    """
    Lắng nghe tin nhắn +1legit trong kênh legit.
    Cú pháp: +1legit(+1 legit) {seller} {loại đơn}
    Tự động +1 vào số đếm trong tên kênh.
    """
    import re as _re_legit

    IGNORED_BOT_IDS = {628400349979344919}
    if message.author.id in IGNORED_BOT_IDS:
        return

    legit_ch_id = get_cfg_legit_channel()
    if legit_ch_id:
        if message.channel.id != legit_ch_id:
            return
    else:
        if "legit" not in message.channel.name.lower():
            return

    content = message.content.strip()

    # Nhận dạng cú pháp: +1legit hoặc +1 legit (không phân biệt hoa thường)
    if not _re_legit.match(r"^\+1\s*legit\b", content, _re_legit.IGNORECASE):
        return

    channel = message.channel
    current_name = channel.name  # ví dụ: ✅•𝐋𝐞𝐠𝐢𝐭-58

    match = _re_legit.search(r"-(\d+)$", current_name)
    if not match:
        new_count = 1
        base_name = current_name
    else:
        new_count = int(match.group(1)) + 1
        base_name = current_name[:match.start()]  # phần tên trước dấu -số

    new_name = f"{base_name}-{new_count}"

    try:
        await channel.edit(name=new_name, reason=f"+1 legit bởi {message.author} → {new_count} đơn")
        await message.add_reaction("✅")
    except discord.Forbidden:
        pass  # Bot thiếu quyền Manage Channels — bỏ qua
    except Exception as e:
        print(f"[LEGIT] Lỗi cập nhật tên kênh: {e}")

async def handle_vouch_message(message: discord.Message):
    """
    Lắng nghe tin nhắn 'done {loại đơn}' trong kênh vouch.
    Tự động +1 vào số đếm ở cuối tên kênh.
    (Việc give role mua hàng do staff nhấn nút trong ticket.)
    """
    import re as _re_vouch

    IGNORED_BOT_IDS = {628400349979344919}
    if message.author.id in IGNORED_BOT_IDS:
        return

    proof_ch_id = get_cfg_proof_channel()
    if message.channel.id != proof_ch_id:
        return

    content = message.content.strip()

    if not _re_vouch.match(r"^done\b", content, _re_vouch.IGNORECASE):
        return

    channel = message.channel
    current_name = channel.name  # ví dụ: 🎉•vouch-120

    match = _re_vouch.search(r"-(\d+)$", current_name)
    if not match:
        new_count = 1
        base_name = current_name
    else:
        new_count = int(match.group(1)) + 1
        base_name = current_name[:match.start()]

    new_name = f"{base_name}-{new_count}"

    try:
        await channel.edit(name=new_name, reason=f"+1 vouch bởi {message.author} → {new_count} đơn")
        await message.add_reaction("✅")
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"[VOUCH] Lỗi cập nhật tên kênh: {e}")

# ================= ON MEMBER JOIN =================
WELCOME_GUILDS = {
    950363132679831642: 1276087208150827070,  # Star Clan → kênh welcome
}

# ================= INVITE TRACKING =================
# LƯU Ý:
# • Bot cache snapshot invites của từng guild sau mỗi lần join/leave
# • So sánh snapshot trước/sau để xác định ai đã invite member mới
# • Dữ liệu lưu trong MongoDB key "invite_counts" — không bao giờ xoá
#   trừ khi admin dùng .resetinvite
# • fake invite: member join rồi leave trong vòng 10 phút không được tính
# • Hoàn toàn tách biệt khỏi giveaway/buyer/ticket data

_invite_cache: dict[int, dict[str, int]] = {}
# guild_id → { invite_code: uses_count }

_pending_joins: dict[int, dict] = {}
# member_id → { "inviter_id": int, "guild_id": int, "joined_at": float }
# dùng để phát hiện fake invite (leave trong 10 phút)

async def _cache_invites(guild: discord.Guild):
    try:
        invites = await guild.invites()
        _invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
    except (discord.Forbidden, discord.HTTPException):
        pass

def _get_invite_counts() -> dict:
    data = load_data()
    return data.get("invite_counts", {})

def _save_invite_counts(counts: dict):
    data = load_data()
    data["invite_counts"] = counts
    save_data(data)

def _add_invite(inviter_id: int, field: str, amount: int = 1):
    counts = _get_invite_counts()
    uid = str(inviter_id)
    if uid not in counts:
        counts[uid] = {"total": 0, "fake": 0, "left": 0}
    counts[uid][field] = counts[uid].get(field, 0) + amount
    _save_invite_counts(counts)

def _get_net_invites(inviter_id: int) -> tuple[int, int, int, int]:
    counts = _get_invite_counts()
    uid = str(inviter_id)
    c = counts.get(uid, {"total": 0, "fake": 0, "left": 0})
    total = c.get("total", 0)
    fake  = c.get("fake",  0)
    left  = c.get("left",  0)
    net   = max(0, total - fake - left)
    return total, fake, left, net

@bot.event
async def on_member_join(member: discord.Member):
    ch_id = WELCOME_GUILDS.get(member.guild.id)
    if ch_id:
        channel = member.guild.get_channel(ch_id)
        if channel:
            try:
                msg = await channel.send(member.mention)
                await asyncio.sleep(10)
                await msg.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

    try:
        old_cache = _invite_cache.get(member.guild.id, {})
        new_invites = await member.guild.invites()
        new_cache = {inv.code: inv.uses for inv in new_invites}

        inviter_id = None
        for inv in new_invites:
            old_uses = old_cache.get(inv.code, 0)
            if inv.uses > old_uses:
                if inv.inviter:
                    inviter_id = inv.inviter.id
                break

        _invite_cache[member.guild.id] = new_cache

        if inviter_id and inviter_id != member.id:
            import time as _time
            _pending_joins[member.id] = {
                "inviter_id": inviter_id,
                "guild_id":   member.guild.id,
                "joined_at":  _time.time(),
            }
            _add_invite(inviter_id, "total", 1)

            async def _check_fake():
                await asyncio.sleep(600)  # 10 phút
                still_here = member.guild.get_member(member.id)
                if not still_here:
                    _add_invite(inviter_id, "fake", 1)
                    print(f"[INVITE] ⚠️ Fake invite: {member} invited by {inviter_id}")
                _pending_joins.pop(member.id, None)

            asyncio.create_task(_check_fake())

    except (discord.Forbidden, discord.HTTPException):
        pass

@bot.event
async def on_member_remove(member: discord.Member):
    await _cache_invites(member.guild)

    pend = _pending_joins.pop(member.id, None)
    if pend is None:
        pass
    await _cache_invites(member.guild)

# ================= ERROR HANDLER =================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ Bạn không có quyền thực hiện lệnh này.")

# ================= SETUP SERVER =================
import re as _re_setup
import unicodedata as _unicodedata

# ── Bảng font chữ Unicode đặc biệt (Bold, Bold Italic, Circled, v.v.) ──
_FONT_MAPS = {
    "bold": {
        **{chr(ord('A')+i): chr(0x1D400+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D41A+i) for i in range(26)},
        **{str(i): chr(0x1D7CE+i) for i in range(10)},
    },
    "bold_italic": {
        **{chr(ord('A')+i): chr(0x1D468+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D482+i) for i in range(26)},
    },
    "sans_bold": {
        **{chr(ord('A')+i): chr(0x1D5D4+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D5EE+i) for i in range(26)},
        **{str(i): chr(0x1D7EC+i) for i in range(10)},
    },
    "script": {
        **{chr(ord('A')+i): chr(0x1D4D0+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D4EA+i) for i in range(26)},
    },
    "double": {
        **{chr(ord('A')+i): chr(0x1D538+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D552+i) for i in range(26)},
    },
    "math_bold_serif": {
        **{chr(ord('A')+i): chr(0x1D400+i) for i in range(26)},
        **{chr(ord('a')+i): chr(0x1D41A+i) for i in range(26)},
        **{str(i): chr(0x1D7CE+i) for i in range(10)},
    },
    "normal": {},  # giữ nguyên
}

# Vài override đặc biệt (script/double có ký tự ngoại lệ)
_FONT_MAPS["script"].update({"B": "ℬ","E": "ℰ","F": "ℱ","H": "ℋ","I": "ℐ","L": "ℒ","M": "ℳ","R": "ℛ","e":"ℯ","g":"ℊ","o":"ℴ"})
_FONT_MAPS["double"].update({"C": "ℂ","H": "ℍ","N": "ℕ","P": "ℙ","Q": "ℚ","R": "ℝ","Z": "ℤ"})

def _apply_font(text: str, font: str) -> str:
    if font == "normal" or font not in _FONT_MAPS:
        return text
    mapping = _FONT_MAPS[font]
    return "".join(mapping.get(c, c) for c in text)

def _strip_unicode_font(text: str) -> str:
    ranges = [
        (0x1D400, 0x1D419, ord('A')),   # Bold A-Z
        (0x1D41A, 0x1D433, ord('a')),   # Bold a-z
        (0x1D434, 0x1D44D, ord('A')),   # Italic A-Z
        (0x1D44E, 0x1D467, ord('a')),   # Italic a-z
        (0x1D468, 0x1D481, ord('A')),   # Bold Italic A-Z
        (0x1D482, 0x1D49B, ord('a')),   # Bold Italic a-z
        (0x1D49C, 0x1D4B5, ord('A')),   # Script A-Z (thường)
        (0x1D4B6, 0x1D4CF, ord('a')),   # Script a-z (thường)
        (0x1D4D0, 0x1D4E9, ord('A')),   # Script Bold A-Z
        (0x1D4EA, 0x1D503, ord('a')),   # Script Bold a-z
        (0x1D538, 0x1D551, ord('A')),   # Double A-Z
        (0x1D552, 0x1D56B, ord('a')),   # Double a-z
        (0x1D5D4, 0x1D5ED, ord('A')),   # Sans Bold A-Z
        (0x1D5EE, 0x1D607, ord('a')),   # Sans Bold a-z
        (0x1D7CE, 0x1D7D7, ord('0')),   # Bold digits 0-9
        (0x1D7EC, 0x1D7F5, ord('0')),   # Sans Bold digits 0-9
    ]
    special = {
        'ℬ':'B','ℰ':'E','ℱ':'F','ℋ':'H','ℐ':'I','ℒ':'L','ℳ':'M','ℛ':'R',
        'ℯ':'e','ℊ':'g','ℴ':'o',
        'ℂ':'C','ℍ':'H','ℕ':'N','ℙ':'P','ℚ':'Q','ℝ':'R','ℤ':'Z',
        'ℬ':'B',  # đã trên
        # Script thường — lowercase ngoại lệ: e=ℯ(0x212F), g=ℊ(0x210A), o=ℴ(0x2134)
        '\u212F':'e',  # ℯ
        '\u210A':'g',  # ℊ
        '\u2134':'o',  # ℴ
        '\u212C':'B',  # ℬ
        '\u2130':'E',  # ℰ
        '\u2131':'F',  # ℱ
        '\u210B':'H',  # ℋ
        '\u2110':'I',  # ℐ
        '\u2112':'L',  # ℒ
        '\u2133':'M',  # ℳ
        '\u211B':'R',  # ℛ
    }
    result = []
    for c in text:
        if c in special:
            result.append(special[c])
            continue
        cp = ord(c)
        converted = False
        for start, end, base in ranges:
            if start <= cp <= end:
                result.append(chr(base + (cp - start)))
                converted = True
                break
        if not converted:
            result.append(c)
    return ''.join(result)

def _detect_channel_parts(name: str):
    """
    Phân tích tên kênh thành các phần:
    - icon (emoji đầu nếu có)
    - separator (• hoặc ký tự phân cách)
    - base_text (phần chữ chính, đã strip font cũ về ASCII)
    - trailing_num (số cuối nếu có, vd: -58)
    Trả về dict.
    """
    icon_match = _re_setup.match(
        r'^((?:[\U00010000-\U0010FFFF]|[\u2600-\u26FF]|[\u2700-\u27BF]|[\U0001F300-\U0001F9FF])+)',
        name
    )
    icon = icon_match.group(1) if icon_match else ""
    rest = name[len(icon):].lstrip()

    sep = ""
    sep_match = _re_setup.match(r'^([•·\-–—|])\s*', rest)
    if sep_match:
        sep = sep_match.group(1)
        rest = rest[sep_match.end():]

    rest_plain = _strip_unicode_font(rest)

    num_match = _re_setup.search(r'[\-–](\d+)$', rest_plain)
    trailing_num = ""
    base_text = rest_plain
    if num_match:
        trailing_num = num_match.group(0)   # vd: "-58"
        base_text = rest_plain[:num_match.start()]

    return {
        "icon": icon,
        "sep": sep,
        "base_text": base_text,
        "trailing_num": trailing_num,
        "original": name,
    }

def _rebuild_name(parts: dict, new_base: str, font: str = "normal") -> str:
    styled_base = _apply_font(new_base, font)
    result = parts["icon"]
    if parts["icon"] and parts["sep"]:
        result += parts["sep"]
    elif parts["icon"]:
        result += ""
    result += styled_base + parts["trailing_num"]
    return result.strip()

# ── State cho phiên .setup ──
_setup_sessions: dict = {}   # guild_id → session dict

FONT_LABELS = {
    "normal":           "Thường (giữ nguyên)",
    "bold":             "𝐁𝐨𝐥𝐝  —  𝐐𝐮𝐢𝐞𝐭 𝐒𝐜𝐡𝐞𝐦𝐚𝐭𝐢𝐜𝐬",
    "bold_italic":      "𝑩𝒐𝒍𝒅 𝑰𝒕𝒂𝒍𝒊𝒄  —  𝑸𝒖𝒊𝒆𝒕 𝑺𝒄𝒉𝒆𝒎𝒂𝒕𝒊𝒄𝒔",
    "sans_bold":        "𝗦𝗮𝗻𝘀 𝗕𝗼𝗹𝗱  —  𝗤𝘂𝗶𝗲𝘁 𝗦𝗰𝗵𝗲𝗺𝗮𝘁𝗶𝗰𝘀",
    "script":           "𝒮𝒸𝓇𝒾𝓅𝓉  —  𝒬𝓊𝒾ℯ𝓉 𝒮𝒸𝒽ℯ𝓂𝒶𝓉𝒾𝒸𝓈",
    "double":           "𝔻𝕠𝕦𝕓𝕝𝕖  —  ℚ𝕦𝕚𝕖𝕥 𝕊𝕔𝕙𝕖𝕞𝕒𝕥𝕚𝕔𝕤",
    "math_bold_serif":  "𝐌𝐚𝐭𝐡 𝐁𝐨𝐥𝐝 𝐒𝐞𝐫𝐢𝐟  —  𝐐𝐮𝐢𝐞𝐭 𝐒𝐜𝐡𝐞𝐦𝐚𝐭𝐢𝐜𝐬",
}

# Alias để user gõ tên font dễ hơn
FONT_ALIASES = {
    "quiet": "bold",
    "schematics": "bold",
    "math bold": "bold",
    "mathbold": "bold",
    "bi": "bold_italic",
    "italic": "bold_italic",
    "sb": "sans_bold",
    "sansbold": "sans_bold",
    "sc": "script",
    "db": "double",
    "bb": "double",
    "math_bold_serif": "math_bold_serif",
    "mathboldserif": "math_bold_serif",
    "mbs": "math_bold_serif",
    "serif": "math_bold_serif",
    "bold serif": "math_bold_serif",
    "boldserif": "math_bold_serif",
}

class SetupMainView(View):
    """Menu chính của .setup."""
