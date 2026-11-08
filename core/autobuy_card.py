"""
core/autobuy_card.py — Vẽ ảnh "card" tài khoản Minecraft bằng Pillow (port từ utils/cardRenderer.js
của bot autobuy Node, vốn dùng @napi-rs/canvas).

- Nền: assets/autobuy/card_bg.png (5 file bg1..bg5 của bản Node giống hệt nhau nên chỉ giữ 1).
- Font: assets/autobuy/Minecraft.ttf nếu bạn tự bỏ vào (không đi kèm repo vì bản quyền), không thì
  assets/autobuy/font.ttf (DejaVu Sans Bold — miễn phí, kèm repo), không có nữa thì font mặc định Pillow.
- Header (logo + tên cửa hàng): nền gốc có sẵn logo/chữ "Drew Store - MFA" → vẽ đè bằng **icon + tên SERVER** của
  nơi đăng card (data["store_icon_url"], data["store_name"]); chữ cũ được xoá bằng nội suy dọc từ dải kính sạch phía trên/dưới.
- Ảnh skin/cape tải qua aiohttp (mc-heads, crafatar..., emoji Discord CDN). Lỗi mạng → bỏ phần đó, vẫn ra card.
- Phần tải ảnh chạy async, phần vẽ (CPU) chạy trong thread để không chặn event loop của bot.
"""
import asyncio
import io
import logging
import os
from functools import lru_cache
from urllib.parse import quote

from core.autobuy_logic import (
    extract_custom_emojis, format_price_abbr, format_rank, parse_price_number, parse_stats, fmt_vnd,
)

log = logging.getLogger(__name__)

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "autobuy")
W, H = 1036, 600

CAPE_SLOTS = [(296 + 94 * i, 104, 76, 114) for i in range(7)]
STATS_ROW1 = [(412, 305, 130), (630, 305, 130), (850, 305, 130)]   # LEVEL / ACHIEVEMENTS / RANK
# Bản Node đặt y=422 (đúng mép dưới khung); mẫu nền có sẵn dấu '-' placeholder ở y≈396 nên hạ xuống 411 cho chữ nằm gọn trong khung.
STATS_ROW2 = [(412, 411, 130), (630, 411, 130), (850, 411, 130)]   # PLAYTIME / MONEY / SHARDS
SKIN_CENTER_X, SKIN_GROUND_Y, SKIN_MAX_W, SKIN_MAX_H = 142, 338, 155, 245

# Header của nền: logo tròn tâm (75,56) bán kính ≤28; chữ "Drew Store - MFA" bắt đầu x≈123, giữa y≈55, hết x≈365.
HEADER_LOGO_C, HEADER_LOGO_R = (75, 56), 30            # icon server vẽ to hơn logo cũ một chút để che kín
HEADER_TEXT_X, HEADER_TEXT_Y, HEADER_TEXT_MAX_X = 123, 55, 835   # chữ mới được kéo dài tới trước "Listed Account" (x≈865)
HEADER_ERASE = (116, 40, 376, 72)                      # vùng chữ cũ cần xoá (x0, y0, x1, y1)
STORE_SUFFIX = "- MFA"


# ───────────────────────── tải ảnh (async) ─────────────────────────
async def _fetch_bytes(session, url: str, timeout: float = 5.0):
    import aiohttp
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            if r.status != 200:
                return None
            return await r.read()
    except Exception:
        return None


def _open_image(buf: bytes | None):
    if not buf:
        return None
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(buf))
        img.load()
        return img.convert("RGBA")
    except Exception:
        return None


async def _fetch_skin(session, username: str):
    """Ảnh skin toàn thân: tra UUID Mojang rồi thử lần lượt các API render (cái nào có ảnh trước dùng cái đó)."""
    uuid = None
    try:
        import aiohttp
        async with session.get(
            f"https://api.mojang.com/users/profiles/minecraft/{quote(username)}",
            timeout=aiohttp.ClientTimeout(total=3.5),
        ) as r:
            if r.status == 200:
                uuid = (await r.json()).get("id")
    except Exception:
        pass
    target = uuid or quote(username)
    urls = [
        f"https://mc-heads.net/body/{target}",
        f"https://crafatar.com/renders/body/{target}?overlay=true",
        f"https://visage.surgeplay.com/full/512/{target}",
        f"https://mineatar.io/render/body/{target}?scale=8",
        f"https://minotar.net/armor/body/{quote(username)}/300.png",
    ]
    for url in urls:
        img = _open_image(await _fetch_bytes(session, url))
        if img:
            return img
    return None


# ───────────────────────── vẽ (sync, chạy trong thread) ─────────────────────────
@lru_cache(maxsize=64)
def _font(size: int):
    from PIL import ImageFont
    for name in ("Minecraft.ttf", "font.ttf"):
        path = os.path.join(ASSET_DIR, name)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size)
    except TypeError:                      # Pillow < 10.1
        return ImageFont.load_default()


def _fit_font(draw, text: str, start: int, min_size: int, max_w: float, scale_x: float = 1.0):
    size = start
    f = _font(size)
    while draw.textlength(text, font=f) * scale_x > max_w and size > min_size:
        size -= 1
        f = _font(size)
    return f


def _text(img, xy, text, font, fill, anchor="mm", blur=4, offset=(0, 2), scale=(1.0, 1.0)):
    """Vẽ chữ có bóng mờ (Pillow không có shadowBlur → vẽ lớp bóng, làm mờ, dán dưới chữ)."""
    from PIL import Image, ImageDraw, ImageFilter
    probe = ImageDraw.Draw(img)
    l, t, r, b = probe.textbbox((0, 0), text, font=font, anchor="lt")
    pad = 12
    w, h = int(r - l) + pad * 2, int(b - t) + pad * 2
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((pad - l, pad - t), text, font=font, fill=fill, anchor="lt")
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((pad - l, pad - t), text, font=font, fill=(0, 0, 0, 215), anchor="lt")
    if blur:
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur / 2))
    if scale != (1.0, 1.0):
        nw, nh = max(1, int(w * scale[0])), max(1, int(h * scale[1]))
        layer, shadow = layer.resize((nw, nh), Image.LANCZOS), shadow.resize((nw, nh), Image.LANCZOS)
        w, h = nw, nh
    x, y = xy
    tw, th = (r - l) * scale[0], (b - t) * scale[1]
    if anchor == "mm":
        x0, y0 = x - tw / 2, y - th / 2
    else:                                  # "lm": trái, giữa theo chiều dọc
        x0, y0 = x, y - th / 2
    ox, oy = int(x0 - pad * scale[0]), int(y0 - pad * scale[1])
    img.alpha_composite(shadow, (ox + offset[0], oy + offset[1])) if ox + offset[0] >= 0 and oy + offset[1] >= 0 else None
    img.alpha_composite(layer, (ox, oy)) if ox >= 0 and oy >= 0 else None


def _rounded_mask(size, radius):
    from PIL import Image, ImageDraw
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return m


def _draw_cape(img, cape, slot):
    from PIL import Image
    x, y, w, h = slot
    bbox = cape.getchannel("A").point(lambda a: 255 if a > 15 else 0).getbbox()   # cắt phần trong suốt
    if bbox and bbox[2] > bbox[0] and bbox[3] > bbox[1]:
        cape = cape.crop(bbox)
    cape = cape.resize((w, h), Image.LANCZOS)
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tile.paste(cape, (0, 0), cape)
    tile.putalpha(Image.composite(tile.getchannel("A"), Image.new("L", (w, h), 0), _rounded_mask((w, h), 6)))
    img.alpha_composite(tile, (x, y))


def _erase_old_header_text(img) -> None:
    """Xoá chữ cũ bằng nội suy dọc: mỗi cột lấy màu 1 hàng 'kính' sạch phía trên và phía dưới chữ rồi pha dần — giữ đúng
    sắc xanh lá/xanh trời của nền ở từng vị trí (dán 1 mảng phẳng sẽ lộ). Chỉ sửa vùng chữ, không đụng thanh header."""
    from PIL import Image
    x0, y0, x1, y1 = HEADER_ERASE
    top = img.crop((x0, y0 - 3, x1, y0 - 2)).convert("RGBA")
    bot = img.crop((x0, y1 + 2, x1, y1 + 3)).convert("RGBA")
    for y in range(y0, y1 + 1):
        img.paste(Image.blend(top, bot, (y - y0) / (y1 - y0)), (x0, y))


def _round_icon(icon, name: str, size: int):
    """Icon server tròn; không có icon → hình tròn tối + chữ cái đầu tên server."""
    from PIL import Image, ImageDraw
    if icon is not None:
        w, h = icon.size
        side = min(w, h)
        icon = icon.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side)).resize((size, size), Image.LANCZOS)
    else:
        icon = Image.new("RGBA", (size, size), (38, 44, 64, 255))
        letter = (name.strip()[:1] or "?").upper()
        f = _font(int(size * 0.55))
        ImageDraw.Draw(icon).text((size / 2, size / 2), letter, font=f, fill=(255, 255, 255, 255), anchor="mm")
    mask = Image.new("L", (size * 4, size * 4), 0)       # vẽ mask 4x rồi thu nhỏ → viền tròn mịn
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(icon, (0, 0), mask.resize((size, size), Image.LANCZOS))
    return out


def _paint_header(img, store_name: str, store_icon) -> None:
    from PIL import Image, ImageDraw
    name = (store_name or "").strip()
    if not name and store_icon is None:
        return                                           # không có thông tin server → giữ nguyên nền gốc
    _erase_old_header_text(img)
    # logo (đè kín logo cũ) + viền mảnh
    size = HEADER_LOGO_R * 2
    cx, cy = HEADER_LOGO_C
    img.alpha_composite(_round_icon(store_icon, name, size), (cx - HEADER_LOGO_R, cy - HEADER_LOGO_R))
    ImageDraw.Draw(img).ellipse((cx - HEADER_LOGO_R, cy - HEADER_LOGO_R, cx + HEADER_LOGO_R, cy + HEADER_LOGO_R),
                                outline=(255, 255, 255, 110), width=2)
    # tên server (trắng) + " - MFA" (xám) cùng baseline
    draw = ImageDraw.Draw(img)
    suffix_font = _font(24)
    suffix_w = draw.textlength(f"  {STORE_SUFFIX}", font=suffix_font)
    f = _fit_font(draw, name, 32, 14, HEADER_TEXT_MAX_X - HEADER_TEXT_X - suffix_w)
    name_w = draw.textlength(name, font=f)
    _text(img, (HEADER_TEXT_X, HEADER_TEXT_Y), name, f, (255, 255, 255, 255), "lm", blur=5)
    _text(img, (HEADER_TEXT_X + name_w, HEADER_TEXT_Y), f"  {STORE_SUFFIX}", suffix_font, (168, 168, 168, 255), "lm", blur=4)


def _compose(data: dict, skin, capes: list, store_icon=None) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter

    name = str(data.get("username") or "NameAccount")
    price_num = parse_price_number(data.get("price"))
    abbr, full = format_price_abbr(price_num), fmt_vnd(price_num)

    bg_path = os.path.join(ASSET_DIR, "card_bg.png")
    try:
        img = Image.open(bg_path).convert("RGBA").resize((W, H), Image.LANCZOS)
    except Exception as e:
        log.warning(f"[AUTOBUY] không đọc được nền card ({e}) — dùng nền trơn")
        img = Image.new("RGBA", (W, H), (22, 26, 38, 255))
    _paint_header(img, str(data.get("store_name") or ""), store_icon)
    draw = ImageDraw.Draw(img)

    # tên account (dưới chân skin)
    _text(img, (142, 365), name, _fit_font(draw, name, 26, 12, 165), (255, 255, 255, 255), "mm", blur=6)
    # giá rút gọn + giá VND
    _text(img, (88, 484), abbr, _fit_font(draw, abbr, 28, 14, 75, 1.02), (255, 255, 255, 255),
          "lm", blur=4, scale=(1.02, 1.12))
    _text(img, (88, 510), full, _fit_font(draw, full, 15, 10, 135), (168, 168, 168, 255),
          "lm", blur=4, scale=(1.0, 1.05))

    # khung + cape
    for slot, cape in zip(CAPE_SLOTS, capes[:7]):
        x, y, w, h = slot
        box = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(box).rounded_rectangle((0, 0, w - 1, h - 1), radius=6, fill=(18, 22, 32, 209))
        img.alpha_composite(box, (x, y))
        if cape is not None:
            _draw_cape(img, cape, slot)
        border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(border).rounded_rectangle((0, 0, w - 1, h - 1), radius=6, outline=(255, 255, 255, 51), width=1)
        img.alpha_composite(border, (x, y))

    # rank + stats
    rank_text = format_rank(data.get("rank"))
    rx, ry, rmax = STATS_ROW1[2]
    _text(img, (rx, ry), rank_text, _fit_font(draw, rank_text, 20, 11, rmax), (255, 255, 255, 255), "mm")
    for (sx, sy, smax), val in zip(STATS_ROW1[:2], parse_stats(data.get("statshpx"))[:2]):
        _text(img, (sx, sy), val, _fit_font(draw, val, 22, 12, smax), (255, 255, 255, 255), "mm")
    for (sx, sy, smax), val in zip(STATS_ROW2, parse_stats(data.get("statsdonut"))):
        _text(img, (sx, sy), val, _fit_font(draw, val, 22, 12, smax), (255, 255, 255, 255), "mm")

    # skin 3D tĩnh + bóng dưới chân
    draw_w, draw_h = 120, 210
    if skin is not None:
        ratio = min(SKIN_MAX_W / skin.width, SKIN_MAX_H / skin.height)
        draw_w, draw_h = max(1, round(skin.width * ratio)), max(1, round(skin.height * ratio))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rx_, ry_ = round(draw_w * 0.36), 7
    cx, cy = SKIN_CENTER_X + 8, SKIN_GROUND_Y + 2
    ImageDraw.Draw(sh).ellipse((cx - rx_, cy - ry_, cx + rx_, cy + ry_), fill=(0, 0, 0, 115))
    img.alpha_composite(sh)
    if skin is not None:
        s = skin.resize((draw_w, draw_h), Image.LANCZOS)
        img.alpha_composite(s, (SKIN_CENTER_X - round(draw_w / 2), SKIN_GROUND_Y - draw_h))

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=False)
    return out.getvalue()


async def render_card(data: dict) -> bytes | None:
    """data: username, price, rank, capes, statshpx, statsdonut (đều là chuỗi); tuỳ chọn store_name, store_icon_url
    (tên + icon server → vẽ lên header). Trả về bytes PNG, None nếu lỗi."""
    try:
        import aiohttp
        username = str(data.get("username") or "NameAccount")
        emojis = extract_custom_emojis(data.get("capes"))
        if not emojis:
            emojis = extract_custom_emojis(data.get("rank"), data.get("statshpx"), data.get("statsdonut"))
        emojis = emojis[:7]
        async with aiohttp.ClientSession() as session:
            skin_task = asyncio.create_task(_fetch_skin(session, username))
            icon_url = str(data.get("store_icon_url") or "")
            icon_task = asyncio.create_task(_fetch_bytes(session, icon_url)) if icon_url else None
            cape_bufs = await asyncio.gather(*[_fetch_bytes(session, e["url"]) for e in emojis])
            skin = await skin_task
            store_icon = _open_image(await icon_task) if icon_task else None
        capes = [_open_image(b) for b in cape_bufs]
        return await asyncio.to_thread(_compose, data, skin, capes, store_icon)
    except Exception:
        log.exception("[AUTOBUY] render_card lỗi")
        return None
