"""Giới hạn kích thước ticket_history / ratings / seller_sales (core/data.py)."""
import os, sys, types, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install()
import conftest_stubs
lg = types.ModuleType("cogs.logger")
async def _send_log(*a, **k): return None
lg.send_log = _send_log
sys.modules["cogs.logger"] = lg
import core.data as C


class Store:
    """Thay load_data/save_data của core.data bằng 1 dict trong RAM (restore ở restore())."""
    def __init__(self):
        self.data = {}
        self.saves = 0
        self._orig = (C.load_data, C.save_data)
        C.load_data = lambda: self.data
        C.save_data = self._save
    def _save(self, d):
        self.data = d; self.saves += 1
    def restore(self):
        C.load_data, C.save_data = self._orig


class HistoryCaps(unittest.TestCase):
    def setUp(self):
        self._stores = []
    def tearDown(self):
        for st in reversed(self._stores):
            st.restore()
    def _store(self):
        st = Store(); self._stores.append(st); return st

    def test_trim_list_keeps_newest(self):
        d = {"x": list(range(10))}
        removed = C._trim_list(d, "x", 4)
        self.assertEqual(d["x"], [6, 7, 8, 9])
        self.assertEqual(removed, [0, 1, 2, 3, 4, 5])

    def test_trim_list_noop_when_under_limit_or_missing(self):
        d = {"x": [1, 2, 3]}
        self.assertEqual(C._trim_list(d, "x", 3), [])
        self.assertEqual(C._trim_list(d, "missing", 3), [])
        self.assertEqual(d["x"], [1, 2, 3])

    def test_ticket_history_capped(self):
        s = self._store(); old = C.MAX_TICKET_HISTORY; C.MAX_TICKET_HISTORY = 5
        try:
            for i in range(8):
                C.save_ticket_record({"user_id": i, "closed_at": "2026-10-01T00:00:00"})
        finally:
            C.MAX_TICKET_HISTORY = old
        self.assertEqual([t["user_id"] for t in s.data["ticket_history"]], [3, 4, 5, 6, 7])

    def test_ratings_capped(self):
        s = self._store(); old = C.MAX_RATINGS; C.MAX_RATINGS = 3
        try:
            for i in range(5):
                C.save_rating(f"t{i}", i, 5)
        finally:
            C.MAX_RATINGS = old
        self.assertEqual([r["ticket"] for r in s.data["ratings"]], ["t2", "t3", "t4"])

    def test_seller_sales_alltime_preserved_after_trim(self):
        s = self._store(); old = C.MAX_SELLER_SALES; C.MAX_SELLER_SALES = 3
        try:
            for i in range(7):
                C.add_seller_sale(9, 1000, f"ch{i}", i)       # seller 9: 7 đơn × 1000
            C.add_seller_sale(8, 500, "other", 99)             # seller 8: 1 đơn
        finally:
            C.MAX_SELLER_SALES = old
        self.assertEqual(len(s.data["seller_sales"]), 3)       # list đã bị cắt
        stats = C.get_seller_sales_stats()
        self.assertEqual(stats["9"]["count_all"], 7)           # nhưng all-time vẫn đủ
        self.assertEqual(stats["9"]["amount_all"], 7000)
        self.assertEqual(stats["8"]["count_all"], 1)
        self.assertEqual(stats["8"]["amount_all"], 500)

    def test_no_archive_when_not_trimmed(self):
        s = self._store()
        C.add_seller_sale(9, 1000, "a", 1)
        self.assertNotIn("seller_sales_archive", s.data)
        self.assertEqual(C.get_seller_sales_stats()["9"]["count_all"], 1)


if __name__ == "__main__":
    unittest.main()
