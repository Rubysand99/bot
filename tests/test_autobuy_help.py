"""Nội dung `.help autobuy` (core/autobuy_help_data.py): giới hạn Discord + khớp với lệnh thật trong cogs/autobuy.py."""
import os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import core.autobuy_help_data as H

COG_SRC = open(os.path.join(ROOT, "cogs", "autobuy.py"), encoding="utf-8").read()


class HelpData(unittest.TestCase):
    def test_pages_consistent(self):
        self.assertEqual(set(H.PAGE_ORDER), set(H.PAGES))
        self.assertEqual(len(H.PAGE_ORDER), len(set(H.PAGE_ORDER)))
        for alias, key in H.PAGE_ALIASES.items():
            self.assertIn(key, H.PAGES, alias)
        for key in H.PAGE_ORDER:              # mỗi trang gõ được bằng chính tên + số thứ tự
            self.assertEqual(H.PAGE_ALIASES[key], key)
            self.assertEqual(H.PAGE_ALIASES[str(H.PAGE_ORDER.index(key) + 1)], key)

    def test_discord_embed_limits(self):
        for key, p in H.PAGES.items():
            self.assertLessEqual(len(p["title"]) + 4, 256, key)
            self.assertLessEqual(len(p["description"]), 4096, key)
            self.assertLessEqual(len(p["fields"]), 25, key)
            for name, value in p["fields"]:
                self.assertTrue(name.strip() and value.strip(), key)
                self.assertLessEqual(len(name), 256, f"{key}: {name}")
                self.assertLessEqual(len(value), 1024, f"{key}: {name} ({len(value)})")
            self.assertLessEqual(H.embed_size(p), 6000, f"{key}: {H.embed_size(p)}")

    def test_select_menu_limits(self):
        self.assertLessEqual(len(H.PAGE_ORDER), 25)
        for k in H.PAGE_ORDER:
            self.assertLessEqual(len(H.PAGES[k]["label"]) + 3, 100)

    def test_commands_mentioned_exist_in_cog(self):
        text = " ".join(p["description"] + " ".join(n + " " + v for n, v in p["fields"]) for p in H.PAGES.values())
        for slash in ("add_acc", "restock", "ab_import"):
            self.assertIn(f"`/{slash}", text)
            self.assertIn(f'name="{slash}"', COG_SRC, slash)
        self.assertIn("`/stock acc", text)
        self.assertIn('Group(name="stock"', COG_SRC); self.assertIn('name="acc"', COG_SRC)
        for pre in ("abset", "abresend"):
            self.assertIn(f"`.{pre}", text)
            self.assertIn(f'name="{pre}"', COG_SRC, pre)

    def test_abset_keys_documented_exist(self):
        keys = re.search(r"CFG_KEYS = \{(.*?)\n\}", COG_SRC, re.S).group(1)
        for k in ("ticket", "bill", "youtube", "2fa", "lock", "vouch", "qr"):
            self.assertIn(f'"{k}":', keys, k)

    def test_stock_acc_params_documented_match_cog(self):
        sig = re.search(r"async def stock_acc\(self, interaction[^)]*\)", COG_SRC, re.S).group(0)
        text = " ".join(" ".join(n + " " + v for n, v in p["fields"]) for p in H.PAGES.values())
        for param in ("username", "price", "capes", "rank", "statshpx", "statsdonut"):
            self.assertIn(param, sig)
            self.assertIn(f"`{param}`", text, param)


if __name__ == "__main__":
    unittest.main()
