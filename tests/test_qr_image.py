"""core/qr_image.py + cogs.shop_orders.attach_qr_image — tải ảnh QR VietQR về rồi đính kèm file.
Hồi quy: img.vietqr.io trả SVG (dù đuôi .png) → Discord không hiện ảnh → bot phải đổi sang PNG và đính kèm."""
import asyncio, io, logging, os, sys, types, unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install()
import conftest_stubs
if "cogs.logger" not in sys.modules:           # stub cogs.logger (chỉ cần send_log) để khỏi import tasks.loop
    lg = types.ModuleType("cogs.logger")
    async def _send_log(*a, **k): return None
    lg.send_log = _send_log
    sys.modules["cogs.logger"] = lg
import core.qr_image as Q
import cogs.shop_orders as S
from PIL import Image

QR_URL = "https://img.vietqr.io/image/970422-0369999888-compact2.png?amount=50000&addInfo=DH123456&accountName=NGUYEN"
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'


def png_bytes(size=(20, 20), color=(0, 0, 0, 255), mode="RGBA"):
    out = io.BytesIO(); Image.new(mode, size, color).save(out, format="PNG"); return out.getvalue()


def fetcher_of(status=200, ctype="image/png", data=b""):
    async def f(url):
        return status, ctype, data
    return f


def run(coro):
    return asyncio.run(coro)


class Sniff(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(Q.sniff_image(png_bytes()), "png")
        self.assertEqual(Q.sniff_image(b"\xff\xd8\xff\xe0abcd"), "jpeg")
        self.assertEqual(Q.sniff_image(b"GIF89a...."), "gif")
        self.assertEqual(Q.sniff_image(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp")
        self.assertEqual(Q.sniff_image(SVG), "svg")
        self.assertEqual(Q.sniff_image(b"<SVG xmlns='x'></SVG>"), "svg")        # viết hoa vẫn nhận
        self.assertEqual(Q.sniff_image(b""), "rong")
        self.assertEqual(Q.sniff_image(b"<html>404</html>"), "khong_ro")

    def test_safe_url_hides_account_and_query(self):
        s = Q.safe_url(QR_URL)
        self.assertNotIn("0369999888", s); self.assertNotIn("DH123456", s); self.assertNotIn("amount", s)
        self.assertIn("img.vietqr.io", s); self.assertIn("***888", s)


class SvgToPng(unittest.TestCase):
    """Bộ đổi SVG thật có thể chưa cài → giả module resvg_py / cairosvg bằng sys.modules."""
    def _mods(self, resvg=None, cairo=None):
        return patch.dict(sys.modules, {"resvg_py": resvg, "cairosvg": cairo})   # None → import ném ImportError

    def test_resvg_used_and_flattened_on_white_and_enlarged(self):
        fake = types.SimpleNamespace(svg_to_bytes=lambda svg_string: list(png_bytes((10, 10), (0, 0, 0, 0))))   # trong suốt, trả list[int]
        with self._mods(resvg=fake):
            out = Q.svg_to_png(SVG)
        img = Image.open(io.BytesIO(out))
        self.assertEqual(img.format, "PNG"); self.assertGreaterEqual(img.width, Q.MIN_WIDTH)
        self.assertEqual(img.convert("RGB").getpixel((0, 0)), (255, 255, 255))   # nền trong suốt → TRẮNG (QR quét được)

    def test_falls_back_to_cairosvg_when_resvg_fails(self):
        def boom(**k): raise RuntimeError("resvg hỏng")
        resvg = types.SimpleNamespace(svg_to_bytes=boom)
        cairo = types.SimpleNamespace(svg2png=lambda bytestring: png_bytes((700, 700), (0, 0, 0, 255)))
        with self._mods(resvg=resvg, cairo=cairo):
            out = Q.svg_to_png(SVG)
        self.assertEqual(Image.open(io.BytesIO(out)).size, (700, 700))            # đủ rộng → không phóng to

    def test_no_converter_raises(self):
        with self._mods():
            with self.assertRaises(Q.SVGConvertError) as cm:
                Q.svg_to_png(SVG)
        self.assertIn("resvg_py", str(cm.exception)); self.assertIn("cairosvg", str(cm.exception))


class Fetch(unittest.TestCase):
    def test_png_passthrough(self):
        data = png_bytes()
        self.assertEqual(run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(data=data))), (data, "png"))

    def test_jpeg_gets_jpg_ext(self):
        data = b"\xff\xd8\xff\xe0" + b"x" * 50
        self.assertEqual(run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(ctype="image/jpeg", data=data))), (data, "jpg"))

    def test_svg_is_converted_to_png(self):
        """Đúng kịch bản lỗi thật: server trả SVG (Content-Type image/svg+xml hoặc cả image/png giả) → phải ra PNG."""
        for ctype in ("image/svg+xml", "image/png"):
            with patch.object(Q, "svg_to_png", return_value=b"\x89PNG-converted") as conv:
                out = run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(ctype=ctype, data=SVG)))
            self.assertEqual(out, (b"\x89PNG-converted", "png"), ctype)
            conv.assert_called_once_with(SVG)

    def test_svg_unconvertible_returns_none_and_logs_error(self):
        with patch.object(Q, "svg_to_png", side_effect=Q.SVGConvertError("thiếu resvg")):
            with self.assertLogs(Q.log, level="ERROR") as cm:
                self.assertIsNone(run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(data=SVG))))
        self.assertIn("resvg-py", "\n".join(cm.output))
        self.assertNotIn("0369999888", "\n".join(cm.output))                       # log không lộ số tài khoản

    def test_bad_responses_return_none(self):
        self.assertIsNone(run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(status=404, ctype="text/plain", data=b"not found"))))
        self.assertIsNone(run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(data=b""))))
        self.assertIsNone(run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(data=b"<html>oops</html>"))))
        self.assertIsNone(run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(data=png_bytes() + b"0" * Q.MAX_BYTES))))
        self.assertIsNone(run(Q.fetch_qr_image("")))

    def test_network_error_never_raises(self):
        async def boom(url): raise asyncio.TimeoutError("quá hạn")
        with self.assertLogs(Q.log, level="WARNING"):
            self.assertIsNone(run(Q.fetch_qr_image(QR_URL, fetcher=boom)))


class HttpGetReadsWholeBody(unittest.TestCase):
    """Hồi quy v4.66.1: `content.read(n)` chỉ trả phần đã về → SVG cụt → resvg "unexpected end of stream".
    Giả aiohttp trả body theo NHIỀU khúc: _http_get phải gom đủ."""
    def _fake_aiohttp(self, chunks, status=200):
        class Content:
            async def iter_chunked(self_, n):
                for c in chunks:
                    yield c
            async def read(self_, n=-1):                      # hành vi thật của aiohttp: chỉ trả khúc đầu
                return chunks[0]
        class Resp:
            def __init__(s): s.status = status; s.headers = {"Content-Type": "image/svg+xml"}; s.content = Content()
            async def __aenter__(s): return s
            async def __aexit__(s, *a): return False
        class Session:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): return False
            def get(s, url, timeout=None): return Resp()
        return types.SimpleNamespace(ClientSession=Session, ClientTimeout=lambda total: total)

    def test_joins_all_chunks(self):
        chunks = [SVG[:40], SVG[40:90], SVG[90:]]
        with patch.dict(sys.modules, {"aiohttp": self._fake_aiohttp(chunks)}):
            status, ctype, data = run(Q._http_get(QR_URL))
        self.assertEqual((status, ctype, data), (200, "image/svg+xml", SVG))      # đủ cả file, không phải khúc đầu

    def test_stops_early_when_too_large(self):
        big = [b"x" * (1024 * 1024)] * 7                                          # 7MB > MAX_BYTES (5MB)
        with patch.dict(sys.modules, {"aiohttp": self._fake_aiohttp(big)}):
            _s, _t, data = run(Q._http_get(QR_URL))
        self.assertGreater(len(data), Q.MAX_BYTES); self.assertLess(len(data), 7 * 1024 * 1024)
        self.assertIsNone(run(Q.fetch_qr_image(QR_URL, fetcher=fetcher_of(data=data))))     # bị từ chối do quá lớn


class FakeEmbed:
    def __init__(self, url): self.image = types.SimpleNamespace(url=url)
    def set_image(self, url): self.image = types.SimpleNamespace(url=url)


class AttachQrImage(unittest.TestCase):
    def test_success_swaps_embed_to_attachment_and_returns_file(self):
        e = FakeEmbed(QR_URL)
        async def fake_fetch(url, ctx=None): return b"PNGDATA", "png"
        with patch.object(S, "fetch_qr_image", fake_fetch):
            files = run(S.attach_qr_image(e, guild=1))
        self.assertEqual(len(files), 1)
        self.assertEqual(e.image.url, "attachment://qr.png")

    def test_failure_keeps_link_and_returns_no_files(self):
        e = FakeEmbed(QR_URL)
        async def fake_fetch(url, ctx=None): return None
        with patch.object(S, "fetch_qr_image", fake_fetch):
            self.assertEqual(run(S.attach_qr_image(e)), [])
        self.assertEqual(e.image.url, QR_URL)                                       # giữ link như cũ — không tệ hơn trước

    def test_unexpected_exception_is_swallowed(self):
        e = FakeEmbed(QR_URL)
        async def fake_fetch(url, ctx=None): raise RuntimeError("bất ngờ")
        with patch.object(S, "fetch_qr_image", fake_fetch):
            with self.assertLogs(S.log, level="ERROR"):
                self.assertEqual(run(S.attach_qr_image(e)), [])
        self.assertEqual(e.image.url, QR_URL)

    def test_embed_without_image(self):
        self.assertEqual(run(S.attach_qr_image(FakeEmbed(None))), [])


if __name__ == "__main__":
    unittest.main()
