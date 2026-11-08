"""AutoBuy: hàm thuần (core/autobuy_logic.py), data layer kho/ticket (core/data.py), vẽ card (core/autobuy_card.py)."""
import os, sys, types, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install()
import conftest_stubs
lg = types.ModuleType("cogs.logger")
async def _send_log(*a, **k): return None
lg.send_log = _send_log
sys.modules.setdefault("cogs.logger", lg)
import core.autobuy_logic as L
import core.data as C


class Logic(unittest.TestCase):
    def test_parse_amount(self):
        for raw, want in [("140k", 140000), ("250000", 250000), ("1.2M", 1200000), ("1tr", 1000000),
                          ("140", 140000), ("", 0), (None, 0), ("abc", 0)]:
            self.assertEqual(L.parse_amount(raw), want, raw)

    def test_price_display_handles_million_suffix(self):
        # bản Node ra "1k" cho "1.2M" — ở đây phải đúng
        self.assertEqual(L.format_price_display("1.2M"), "1.2M")
        self.assertEqual(L.format_price_display("140"), "140k")
        self.assertEqual(L.format_price_display("140000"), "140k")
        self.assertEqual(L.format_price_display(""), "0k")
        self.assertEqual(L.format_price_abbr(999_600), "1M")
        self.assertEqual(L.parse_price_number("1.2M"), 1200000)
        self.assertEqual(L.parse_price_number(""), 100000)

    def test_capes_and_emojis(self):
        self.assertEqual(L.count_capes("<:a:1> <a:b:2> <:a:1>"), 3)
        self.assertEqual(L.count_capes("🔥🔥"), 2)
        self.assertEqual(L.count_capes(""), 0)
        urls = L.extract_custom_emojis("<:a:111> <:a:111> <a:b:222>")
        self.assertEqual([u["name"] for u in urls], ["a", "b"])
        self.assertEqual(L.strip_emojis("MVP+ <:x:1> 🔥"), "MVP+")

    def test_rank_and_stats(self):
        self.assertEqual(L.format_rank("mvp+"), "MVP+-RANK")
        self.assertEqual(L.format_rank("VIP-RANK"), "VIP-RANK")
        self.assertEqual(L.format_rank(""), "NON-RANK")
        self.assertEqual(L.parse_stats("150, 4500"), ["150", "4500", "-"])
        self.assertEqual(L.parse_stats("120h 50M 1500"), ["120h", "50M", "1500"])
        self.assertEqual(L.parse_stats(""), ["-", "-", "-"])

    def test_parse_account_form(self):
        raw = "Username: Foo\nCapes: <:x:1>\nRecovery Code: R1\nPrimary Email: a@b.c\nSecurity Email: s@b.c\nSecret Key: K\nPassword: p w"
        d = L.parse_account_form(raw)
        self.assertEqual((d["username"], d["password"], d["primary_email"], d["recovery_code"], d["secret_key"]),
                         ("Foo", "p w", "a@b.c", "R1", "K"))
        self.assertIsNone(L.parse_account_form("Password: x"))
        self.assertIsNone(L.parse_account_form(""))

    def test_channel_names(self):
        self.assertEqual(L.make_stock_channel_name("AVAILABLE", "140k", 3), "✅・140k・3-cape")
        self.assertEqual(L.swap_status_icon("✅・140k・3-cape", "PROCESSING"), "⌛・140k・3-cape")
        self.assertEqual(L.swap_status_icon("⌛・140k・3-cape", "SOLD"), "❌・140k・3-cape")
        self.assertEqual(L.swap_status_icon("general", "SOLD"), "❌-general")

    def test_convert_node_account(self):
        d = L.convert_node_account({"username": "Foo", "primaryEmail": "a@b.c", "sellerId": 123, "status": "PROCESSING",
                                    "cardChannelId": "9", "recoveryCode": "R", "secretKey": "K", "price": "140k"})
        self.assertEqual((d["primary_email"], d["seller_id"], d["status"], d["card_channel_id"]), ("a@b.c", "123", "AVAILABLE", "9"))
        self.assertEqual(L.convert_node_account({"username": "X", "status": "SOLD"})["status"], "SOLD")
        self.assertIsNone(L.convert_node_account({"price": "1"}))
        self.assertIsNone(L.convert_node_account("nope"))


class DataLayer(unittest.TestCase):
    def setUp(self):
        self.data = {}
        self._o = (C.load_data, C.save_data)
        C.load_data = lambda: self.data
        C.save_data = lambda d: self.data.update(d)

    def tearDown(self):
        C.load_data, C.save_data = self._o

    def test_account_crud_case_insensitive(self):
        self.assertTrue(C.save_ab_account({"username": "FooBar", "price": "1k", "status": "AVAILABLE"}))
        self.assertEqual(C.get_ab_account("foobar")["username"], "FooBar")
        self.assertTrue(C.update_ab_account("FOOBAR", price="2k"))
        self.assertEqual(C.get_ab_account("foobar")["price"], "2k")
        self.assertFalse(C.update_ab_account("nope", price="1"))
        self.assertFalse(C.save_ab_account({"username": "  "}))

    def test_claim_is_single_winner(self):
        C.save_ab_account({"username": "Foo", "status": "AVAILABLE"})
        self.assertEqual(C.claim_ab_account("foo")[0], "ok")
        self.assertEqual(C.claim_ab_account("FOO")[0], "processing")
        C.update_ab_account("foo", status="SOLD")
        self.assertEqual(C.claim_ab_account("foo")[0], "sold")
        self.assertEqual(C.claim_ab_account("ghost")[0], "missing")

    def test_find_by_channel_and_tickets_and_cfg(self):
        C.save_ab_account({"username": "Foo", "card_channel_id": "77", "status": "AVAILABLE"})
        self.assertEqual(C.find_ab_account_by_channel(77)["username"], "Foo")
        self.assertIsNone(C.find_ab_account_by_channel(78))
        C.save_ab_ticket(5, {"username": "Foo", "buyer_id": 1})
        self.assertEqual(C.get_ab_ticket(5)["buyer_id"], 1)
        self.assertTrue(C.delete_ab_ticket(5)); self.assertFalse(C.delete_ab_ticket(5))
        C.set_ab_cfg("bill_channel_id", "123"); self.assertEqual(C.get_ab_cfg("bill_channel_id"), "123")
        C.set_ab_cfg("bill_channel_id", None); self.assertIsNone(C.get_ab_cfg("bill_channel_id"))


@unittest.skipUnless(__import__("importlib").util.find_spec("PIL"), "cần Pillow")
class CardRender(unittest.TestCase):
    def test_compose_returns_png_with_expected_size(self):
        import io
        from PIL import Image, ImageDraw
        import core.autobuy_card as K
        skin = Image.new("RGBA", (200, 400), (0, 0, 0, 0)); ImageDraw.Draw(skin).rectangle((60, 0, 140, 390), fill=(40, 120, 220, 255))
        cape = Image.new("RGBA", (128, 128), (200, 30, 30, 255))
        png = K._compose({"username": "A_Very_Long_Account_Name_123", "price": "1.2M", "rank": "mvp+",
                          "statshpx": "150, 4500", "statsdonut": "120h, 50M, 1500"}, skin, [cape] * 9)   # 9 cape → chỉ vẽ 7
        im = Image.open(io.BytesIO(png))
        self.assertEqual(im.size, (1036, 600))
        self.assertEqual(im.format, "PNG")


    def test_header_uses_server_name_and_icon(self):
        import io
        from PIL import Image, ImageChops
        import core.autobuy_card as K
        bg = Image.open(os.path.join(K.ASSET_DIR, "card_bg.png")).convert("RGB").resize((K.W, K.H), Image.LANCZOS)
        icon = Image.new("RGBA", (128, 128), (220, 60, 120, 255))
        base = {"username": "x", "price": "100k"}

        def header(data, ic=None):
            im = Image.open(io.BytesIO(K._compose(data, None, [], ic))).convert("RGB")
            return im.crop((20, 20, 900, 90))
        orig = bg.crop((20, 20, 900, 90))
        # không có thông tin server → giữ nguyên nền gốc (logo/chữ gốc còn đó)
        self.assertIsNone(ImageChops.difference(header(base), orig).getbbox())
        # có tên + icon server → header khác nền gốc ở vùng logo + chữ
        with_store = header({**base, "store_name": "Nobi Shop"}, icon)
        d = ImageChops.difference(with_store, orig).getbbox()
        self.assertIsNotNone(d)
        # icon server (đỏ-hồng) phải xuất hiện ở tâm logo (75,56)
        px = Image.open(io.BytesIO(K._compose({**base, "store_name": "Nobi Shop"}, None, [], icon))).convert("RGB").getpixel((75, 56))
        self.assertGreater(px[0], 180); self.assertLess(px[1], 120)
        # vùng "Listed Account" bên phải không bị đụng tới
        right = (880, 30, 1000, 75)
        a = Image.open(io.BytesIO(K._compose({**base, "store_name": "Nobi Shop"}, None, [], icon))).convert("RGB").crop(right)
        self.assertIsNone(ImageChops.difference(a, bg.crop(right)).getbbox())

    def test_header_survives_long_name_and_no_icon(self):
        import core.autobuy_card as K
        self.assertTrue(K._compose({"username": "x", "price": "1", "store_name": "Cửa Hàng " * 12}, None, [], None).startswith(b"\x89PNG"))

    def test_compose_survives_missing_skin_and_capes(self):
        import core.autobuy_card as K
        self.assertTrue(K._compose({"username": "x", "price": ""}, None, [None, None]).startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
