"""
core/qr_image.py — Tải ảnh QR VietQR về phía BOT rồi đính kèm thẳng vào tin nhắn (thay vì để Discord tự tải link).

Vì sao cần: `img.vietqr.io/image/...png` có thể trả về ảnh **SVG** dù đuôi link là .png. Discord KHÔNG hiển thị được
SVG (cả dạng link `embed.set_image(url=...)` lẫn dạng đính kèm) → khung "Quét mã để thanh toán" hiện ra nhưng KHÔNG có
ảnh QR. Cách sửa (giống dự án bot-sleep): bot tự tải ảnh, nhận diện định dạng qua vài byte đầu, nếu là SVG thì đổi sang
PNG (nền trắng để quét được), rồi gửi như file đính kèm `attachment://qr.png`.

Mọi lỗi (mạng, SVG không đổi được, thiếu thư viện) đều KHÔNG ném ra ngoài: `fetch_qr_image()` trả None và người gọi giữ
nguyên embed dùng link như cũ — không bao giờ tệ hơn trước. Log `[QR]` ghi rõ status / content-type / định dạng /
kích thước (đã che số tài khoản) để lần sau nhìn log bot (journalctl) là biết vì sao ảnh không hiện.

Bộ đổi SVG→PNG (thử lần lượt, cái nào có thì dùng): `resvg-py` (wheel dựng sẵn, không cần thư viện hệ thống) rồi `cairosvg`
(cần libcairo trên máy). Cả hai đều import lười — thiếu thì chỉ mất phần đổi SVG.
Module THUẦN (không import discord); test ở tests/test_qr_image.py.
"""
import io
import logging
import re
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

FETCH_TIMEOUT = 8                 # giây — lệnh `.done`/nút Done phải trả lời nhanh
MAX_BYTES = 5 * 1024 * 1024
MIN_WIDTH = 600                   # ảnh nhỏ hơn thì phóng to (giữ nét, QR dễ quét hơn trên điện thoại)
EXT_BY_FORMAT = {"png": "png", "jpeg": "jpg", "gif": "gif", "webp": "webp"}


class SVGConvertError(RuntimeError):
    """Không đổi được SVG sang PNG (thiếu thư viện hoặc SVG hỏng)."""


def sniff_image(buf: bytes) -> str:
    """Nhận diện định dạng ảnh qua vài byte đầu: png / jpeg / gif / webp / svg / rong / khong_ro (không tin Content-Type)."""
    if not buf or len(buf) < 4:
        return "rong"
    if buf[:4] == b"\x89PNG":
        return "png"
    if buf[:2] == b"\xff\xd8":
        return "jpeg"
    if buf[:3] == b"GIF":
        return "gif"
    if buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
        return "webp"
    if b"<svg" in buf[:1000].lower():
        return "svg"
    return "khong_ro"


def safe_url(url: str) -> str:
    """URL VietQR chứa số TK, số tiền, nội dung CK → chỉ giữ host + path, che dãy ≥5 chữ số (…***789) trước khi ghi log."""
    try:
        u = urlsplit(url)
        return f"{u.scheme}://{u.netloc}" + re.sub(r"\d{5,}", lambda m: "***" + m.group(0)[-3:], u.path)
    except Exception:
        return "(url không hợp lệ)"


def _flatten_on_white(png: bytes) -> bytes:
    """PNG (có thể nền trong suốt) → PNG nền trắng, phóng to nguyên số lần nếu nhỏ hơn MIN_WIDTH. Dùng Pillow (đã có)."""
    from PIL import Image
    img = Image.open(io.BytesIO(png))
    img.load()
    rgba = img.convert("RGBA")
    if 0 < rgba.width < MIN_WIDTH:
        k = -(-MIN_WIDTH // rgba.width)                     # làm tròn lên
        rgba = rgba.resize((rgba.width * k, rgba.height * k), Image.NEAREST)
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.split()[3])
    out = io.BytesIO()
    bg.save(out, format="PNG")
    return out.getvalue()


def svg_to_png(svg: bytes) -> bytes:
    """SVG (bytes) → PNG nền trắng (bytes). Ném SVGConvertError nếu không bộ đổi nào dùng được."""
    errors, png = [], None
    try:
        import resvg_py
        png = bytes(resvg_py.svg_to_bytes(svg_string=svg.decode("utf-8", "replace")))
    except Exception as e:                       # ImportError, hoặc API khác phiên bản, hoặc SVG lỗi
        errors.append(f"resvg_py: {type(e).__name__}: {e}")
    if not png:
        try:
            import cairosvg
            png = cairosvg.svg2png(bytestring=svg)
        except Exception as e:                   # ImportError / OSError (thiếu libcairo) / SVG lỗi
            errors.append(f"cairosvg: {type(e).__name__}: {e}")
    if not png:
        raise SVGConvertError("; ".join(errors) or "không có bộ đổi SVG")
    try:
        return _flatten_on_white(png)
    except Exception as e:
        raise SVGConvertError(f"PNG sau khi đổi không đọc được: {type(e).__name__}: {e}")


async def _http_get(url: str, timeout: float = FETCH_TIMEOUT):
    """(status, content_type, bytes). aiohttp import lười (test có thể truyền fetcher riêng)."""
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            data = await r.content.read(MAX_BYTES + 1)
            return r.status, r.headers.get("Content-Type", ""), data


async def fetch_qr_image(url: str, *, fetcher=None, ctx: dict | None = None):
    """Tải ảnh QR → (bytes, "png"|"jpg"|"gif"|"webp") sẵn sàng đính kèm; None nếu không làm được (người gọi giữ link cũ).
    KHÔNG BAO GIỜ ném lỗi. `fetcher(url)` (async → (status, content_type, bytes)) để test; mặc định dùng aiohttp."""
    ctx = ctx or {}
    if not url:
        return None
    shown = safe_url(url)
    try:
        status, ctype, data = await (fetcher or _http_get)(url)
    except Exception as e:
        log.warning("[QR] không tải được ảnh VietQR từ máy chủ bot: %s: %s | %s %s", type(e).__name__, e, shown, ctx)
        return None
    data = data or b""
    fmt = sniff_image(data)
    log.info("[QR] tải ảnh VietQR: status=%s type=%s bytes=%d dinhdang=%s | %s %s", status, ctype, len(data), fmt, shown, ctx)
    if status != 200 or not data or len(data) > MAX_BYTES:
        log.warning("[QR] VietQR không trả ảnh hợp lệ (status=%s, %d bytes) — kiểm tra mã ngân hàng / số TK | %s %s",
                    status, len(data), shown, ctx)
        return None
    if fmt == "svg":
        try:
            png = svg_to_png(data)
        except SVGConvertError as e:
            log.error("[QR] ảnh là SVG nhưng đổi sang PNG THẤT BẠI → Discord sẽ không hiện ảnh. Cài `resvg-py` "
                      "(hoặc cairosvg + libcairo). Chi tiết: %s | %s %s", e, shown, ctx)
            return None
        log.info("[QR] đã đổi SVG → PNG (%d bytes) %s", len(png), ctx)
        return png, "png"
    if fmt in EXT_BY_FORMAT:
        return data, EXT_BY_FORMAT[fmt]
    log.warning("[QR] định dạng ảnh không nhận ra (%s) | %s %s", fmt, shown, ctx)
    return None
