"""core/vietqr.py: parse VietQR (NAPAS) + CRC + đọc QR từ ảnh (cần zxing-cpp/qrcode — không có thì bỏ qua phần ảnh)."""
import importlib.util, io, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import core.vietqr as V


def tlv(tag, val):
    return f"{tag}{len(val):02d}{val}"


def make_vietqr(bin_="970415", acc="0123456789", name=None, amount=None, service="QRIBFTTA", dynamic=False):
    napas = tlv("00", V.NAPAS_GUID) + tlv("01", tlv("00", bin_) + tlv("01", acc)) + tlv("02", service)
    p = tlv("00", "01") + tlv("01", "12" if dynamic else "11") + tlv("38", napas) + tlv("53", "704")
    if amount:
        p += tlv("54", str(amount))
    p += tlv("58", "VN")
    if name:
        p += tlv("59", name)
    p += "6304"
    return p + f"{V.crc16_ccitt(p):04X}"


class Parse(unittest.TestCase):
    def test_crc_reference_value(self):
        self.assertEqual(f"{V.crc16_ccitt('123456789'):04X}", "29B1")      # vector chuẩn CRC-16/CCITT-FALSE

    def test_parse_basic(self):
        r = V.parse_vietqr(make_vietqr())
        self.assertEqual((r["ok"], r["bin"], r["account_number"], r["holder"], r["service"]),
                         (True, "970415", "0123456789", "", "QRIBFTTA"))

    def test_parse_with_name_amount_dynamic(self):
        r = V.parse_vietqr(make_vietqr("970436", "9876543210", name="NGUYEN VAN A", amount=50000, dynamic=True))
        self.assertEqual((r["ok"], r["holder"], r["amount"]), (True, "NGUYEN VAN A", "50000"))
        self.assertEqual(V.bank_name_from_bin(r["bin"]), "Vietcombank")

    def test_unknown_bin_still_usable(self):
        r = V.parse_vietqr(make_vietqr("970999", "1112223334"))
        self.assertTrue(r["ok"])
        self.assertEqual(V.bank_name_from_bin("970999"), "Ngân hàng (BIN 970999)")

    def test_rejections(self):
        good = make_vietqr()
        self.assertEqual(V.parse_vietqr(good[:-1] + ("0" if good[-1] != "0" else "1"))["error"], "bad_crc")     # sai checksum
        self.assertEqual(V.parse_vietqr(make_vietqr(service="QRIBFTTC"))["error"], "card")                       # QR số thẻ
        self.assertEqual(V.parse_vietqr("https://momo.vn/pay/abc")["error"], "not_vietqr")                       # không phải EMV
        self.assertEqual(V.parse_vietqr("")["error"], "not_vietqr")
        wallet = tlv("00", "01") + tlv("01", "11") + tlv("26", tlv("00", "SOMEWALLET")) + "6304"
        self.assertEqual(V.parse_vietqr(wallet + f"{V.crc16_ccitt(wallet):04X}")["error"], "not_vietqr")         # QR ví khác
        self.assertEqual(V.parse_vietqr(make_vietqr("97041", "123"))["error"], "bad_account")                    # BIN sai độ dài
        self.assertIsNone(V.parse_tlv("0099abc"))                                                                # độ dài vượt chuỗi

    def test_pick_prefers_valid_and_reports_best_error(self):
        self.assertEqual(V.pick_vietqr([])["error"], "no_qr")
        self.assertEqual(V.pick_vietqr(["https://x.y", make_vietqr()])["bin"], "970415")
        self.assertEqual(V.pick_vietqr(["https://x.y", make_vietqr(service="QRIBFTTC")])["error"], "card")


class BankValidation(unittest.TestCase):
    def test_valid_banks(self):
        for code, acc, holder in [("mbbank", "0123456789", "NGUYEN VAN A"), ("970422", "0369 999 888", ""), ("vietinbank", "1.234.567.890", "TRAN B")]:
            self.assertIsNone(V.validate_bank(code, acc, holder), (code, acc))
        self.assertEqual(V.normalize_account("0123 456.789-0"), "01234567890")

    def test_screenshot_regression_placeholder_account_and_shifted_holder(self):
        # Dữ liệu thật từng bị lưu: tên "MB", số TK = "ma_bank" (copy chữ mẫu), chủ TK = dãy số
        err = V.validate_bank("mbbank", "ma_bank", "80086266778899")
        self.assertIn("ma_bank", err)
        self.assertIsNotNone(V.bank_problem({"bank_name": "MB", "bank_code": "mbbank", "account_number": "ma_bank", "account_holder": "80086266778899"}))

    def test_invalid_variants(self):
        self.assertIn("mã ngân hàng", V.validate_bank("ma_bank", "0123456789"))             # chữ mẫu ở ô mã NH
        self.assertIn("mã ngân hàng", V.validate_bank("", "0123456789"))
        self.assertIn("số tài khoản", V.validate_bank("mbbank", "SoTK"))
        self.assertIn("số tài khoản", V.validate_bank("mbbank", "123"))                    # quá ngắn
        self.assertIn("số tài khoản", V.validate_bank("mbbank", "1" * 20))                 # quá dài
        self.assertIn("nhập lộn", V.validate_bank("mbbank", "0123456789", "80086266778899"))   # số TK nằm ở ô chủ TK

    def test_bank_problem_for_missing_and_ok(self):
        self.assertEqual(V.bank_problem(None), "chưa đăng ký ngân hàng")
        self.assertEqual(V.bank_problem({}), "chưa đăng ký ngân hàng")
        self.assertIsNone(V.bank_problem({"bank_code": "970422", "account_number": "0369999888", "account_holder": ""}))

    def test_normalize_holder(self):
        self.assertEqual(V.normalize_holder("Nguyễn Tấn Hoàng Quân"), "NGUYEN TAN HOANG QUAN")
        self.assertEqual(V.normalize_holder("  nguyen   van a "), "NGUYEN VAN A")
        self.assertEqual(V.normalize_holder("CÔNG TY ABC & Đạt"), "CONG TY ABC & DAT")
        self.assertEqual(V.normalize_holder("@@@"), "")
        self.assertEqual(V.normalize_holder(""), "")

    def test_alias_qr_like_mb_is_reported_with_bin(self):
        # MB nhúng MÃ ĐỊNH DANH (VQRQ…) thay số TK → không đọc được số TK thật từ QR, nhưng biết ngân hàng (BIN)
        r = V.parse_vietqr(make_vietqr("970422", "VQRQAXYZ1234"))
        self.assertEqual((r["ok"], r["error"], r["bin"]), (False, "alias", "970422"))
        self.assertEqual(V.pick_vietqr(["https://x.y", make_vietqr("970422", "VQRQAXYZ1234")])["error"], "alias")
        self.assertEqual(V.parse_vietqr(make_vietqr("970422", "12"))["error"], "bad_account")        # quá ngắn


HAVE_LIBS = all(importlib.util.find_spec(m) for m in ("PIL", "qrcode", "zxingcpp"))


@unittest.skipUnless(HAVE_LIBS, "cần Pillow + qrcode + zxing-cpp")
class ImageDecode(unittest.TestCase):
    def _png(self, text, box=10, border=4, pad=0):
        import qrcode
        from PIL import Image
        im = qrcode.make(text, box_size=box, border=border).convert("RGB")
        if pad:                                   # nền rộng quanh QR như ảnh chụp màn hình
            canvas = Image.new("RGB", (im.width + pad * 2, im.height + pad * 2), (240, 240, 240))
            canvas.paste(im, (pad, pad)); im = canvas
        buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()

    def test_decode_and_parse_roundtrip(self):
        payload = make_vietqr("970422", "0369999888", name="TRAN THI B")
        r = V.pick_vietqr(V.decode_qr_texts(self._png(payload)))
        self.assertEqual((r["ok"], r["bin"], r["account_number"], r["holder"]), (True, "970422", "0369999888", "TRAN THI B"))

    def test_decode_with_big_margin_and_small_image(self):
        payload = make_vietqr("970436", "1234567890")
        self.assertEqual(V.pick_vietqr(V.decode_qr_texts(self._png(payload, box=3, pad=200)))["account_number"], "1234567890")

    def test_non_qr_image_returns_empty(self):
        from PIL import Image
        buf = io.BytesIO(); Image.new("RGB", (400, 400), (255, 255, 255)).save(buf, "PNG")
        self.assertEqual(V.decode_qr_texts(buf.getvalue()), [])

    def test_rejects_oversized_input(self):
        with self.assertRaises(ValueError):
            V.decode_qr_texts(b"x" * (V.MAX_IMAGE_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
