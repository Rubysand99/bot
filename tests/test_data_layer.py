import asyncio, sys, os, types, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conftest_stubs
conftest_stubs.install()
import shared.data as D

class Guild:
    def __init__(self, i): self.id = i
class Bot:
    def __init__(self, ids): self.guilds = [Guild(i) for i in ids]

def reset(col_data=None):
    D._data_cache = {}; D._global_cache = None; D._global_loaded = False
    D._persisted_keys.clear(); D._persisted_keys_global.clear()
    D._data_cache_ready.clear(); D._save_locks.clear()
    D._LOAD_RETRY_DELAY = 0
    col = col_data or conftest_stubs.FakeCol()
    gw = conftest_stubs.FakeCol()
    D._get_mongo = lambda: (col, gw)
    return col

REAL_GUILD = {"_id": "guild_1", "ticket": 57, "sellers": [{"id": 9}], "user_total_spent": {"5": 100000},
              "cfg_done_role": 777}
REAL_GLOBAL = {"_id": "main", "_tempbans": {"42": {"guild_id": 1, "unban_at": 9e9}},
               "_shop_pending_orders": {"DH123456": {"amount": 50000}}, "_authorized_guilds": [1]}

class DataLayer(unittest.TestCase):
    def run_async(self, coro): return asyncio.run(coro)

    def test_guild_load_failure_never_overwrites_real_data(self):
        col = reset(); col.docs["guild_1"] = dict(REAL_GUILD); col.docs["main"] = dict(REAL_GLOBAL)
        col.fail_reads = 4  # hết lượt retry của guild
        async def go():
            await D.init_data_cache(Bot([1]))
            self.assertFalse(D.is_guild_loaded(1))
            tok = D.set_current_guild(1)
            data = D.load_data()          # default tạm
            data["ticket"] = 1
            D.save_data(data)             # phải bị từ chối
            await asyncio.sleep(0.05)
        self.run_async(go())
        self.assertEqual(col.docs["guild_1"]["ticket"], 57)
        self.assertEqual(col.docs["guild_1"]["sellers"], [{"id": 9}])
        self.assertEqual([w for w in col.writes if w[0] == "guild_1"], [])   # không ghi gì vào guild lỗi

    def test_transient_failure_is_retried(self):
        col = reset(); col.docs["guild_1"] = dict(REAL_GUILD); col.docs["main"] = dict(REAL_GLOBAL)
        col.fail_reads = 2
        async def go():
            await D.init_data_cache(Bot([1]))
            self.assertTrue(D.is_guild_loaded(1))
            D.set_current_guild(1)
            self.assertEqual(D.load_data()["ticket"], 57)
        self.run_async(go())

    def test_global_load_failure_blocks_ready_and_writes(self):
        col = reset(); col.docs["guild_1"] = dict(REAL_GUILD); col.docs["main"] = dict(REAL_GLOBAL)
        async def go():
            col.fail_reads = 0
            orig = col.find_one
            async def flaky(flt):
                if flt["_id"] == "main": raise RuntimeError("down")
                return await orig(flt)
            col.find_one = flaky
            with self.assertRaises(RuntimeError):
                await D.init_data_cache(Bot([1]))
            self.assertFalse(D.is_data_cache_ready())
            D.save_global_data({"_tempbans": {}})   # webhook "trước khi sẵn sàng" → bị từ chối
            await asyncio.sleep(0.05)
        self.run_async(go())
        self.assertEqual(col.docs["main"]["_tempbans"], REAL_GLOBAL["_tempbans"])
        self.assertEqual(col.docs["main"]["_shop_pending_orders"], REAL_GLOBAL["_shop_pending_orders"])

    def test_save_global_before_init_is_refused(self):
        col = reset(); col.docs["main"] = dict(REAL_GLOBAL)
        async def go():
            data = D.load_global_data()
            data["_shop_processed_webhook_ids"] = {"1": "x"}
            D.save_global_data(data)
            await asyncio.sleep(0.05)
        self.run_async(go())
        self.assertEqual(col.writes, [])
        self.assertEqual(col.docs["main"]["_tempbans"], REAL_GLOBAL["_tempbans"])

    def test_deleted_toplevel_key_is_unset_in_mongo(self):
        col = reset(); col.docs["guild_1"] = dict(REAL_GUILD, completed_555=True); col.docs["main"] = dict(REAL_GLOBAL)
        async def go():
            await D.init_data_cache(Bot([1]))
            D.set_current_guild(1)
            data = D.load_data()
            del data["completed_555"]
            D.save_data(data)
            await asyncio.sleep(0.05)
        self.run_async(go())
        self.assertNotIn("completed_555", col.docs["guild_1"])
        self.assertEqual(col.docs["guild_1"]["ticket"], 57)

    def test_legacy_migration_runs_once_only(self):
        col = reset()
        gid = D.LEGACY_MAIN_GUILD_ID
        col.docs[f"guild_{gid}"] = {"_id": f"guild_{gid}", "ticket": 3}
        col.docs["main"] = dict(REAL_GLOBAL)
        async def go():
            await D.init_data_cache(Bot([gid]))
            D.set_current_guild(gid)
            self.assertEqual(D.load_data()["cfg_done_role"], D._TUYTAM_LEGACY_CFG_MIGRATION["cfg_done_role"])
            # admin cố ý xoá cấu hình → restart không được điền lại
            d = D.load_data(); d["cfg_done_role"] = 0; D.save_data(d); await asyncio.sleep(0.05)
        self.run_async(go())
        reset_col = col
        D._data_cache = {}; D._persisted_keys.clear(); D._data_cache_ready.clear(); D._global_loaded = False
        async def again():
            await D.init_data_cache(Bot([gid]))
            D.set_current_guild(gid)
            self.assertEqual(D.load_data()["cfg_done_role"], 0)
        self.run_async(again())

    def test_write_retry_then_success(self):
        col = reset(); col.docs["guild_1"] = dict(REAL_GUILD); col.docs["main"] = dict(REAL_GLOBAL)
        async def go():
            await D.init_data_cache(Bot([1]))
            D.set_current_guild(1)
            col.fail_writes = 2
            d = D.load_data(); d["ticket"] = 58; D.save_data(d)
            await asyncio.sleep(4)
        self.run_async(go())
        self.assertEqual(col.docs["guild_1"]["ticket"], 58)

if __name__ == "__main__":
    unittest.main(verbosity=2)
