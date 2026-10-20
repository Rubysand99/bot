import asyncio, sys, os, types, time, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install()
import conftest_stubs
lg = types.ModuleType("cogs.logger")
async def _send_log(*a, **k): return None
lg.send_log = _send_log
sys.modules["cogs.logger"] = lg
import shared.data as D
import core.data as C
import cogs.mod as M
dc = sys.modules["discord"]

M.ADMIN_IDS = [900]
M.is_admin = lambda m, quiet=False: m.id in M.ADMIN_IDS   # code giờ gọi is_admin() (gồm admin phụ .ad); test giả lập admin cố định id=900

class Role:
    def __init__(self, pos): self.pos = pos
    def __ge__(self, o): return self.pos >= o.pos
    def __gt__(self, o): return self.pos > o.pos
class Perms:
    def __init__(self, admin=False, ban=False, kick=False): self.administrator, self.ban_members, self.kick_members = admin, ban, kick
class Member:
    def __init__(self, i, pos, perms=None): self.id, self.top_role, self.guild_permissions = i, Role(pos), perms or Perms()
class Guild:
    def __init__(self): self.id = 1; self.owner_id = 1000; self.me = Member(5, 50); self.unbans = []; self.unban_exc = None
    async def unban(self, user, reason=None):
        if self.unban_exc: raise self.unban_exc
        self.unbans.append(user)
class Bot:
    def __init__(self, guild): self.g = guild
    def get_guild(self, i): return self.g if i == self.g.id else None
    async def fetch_guild(self, i): raise dc.NotFound()
    async def fetch_user(self, i): return types.SimpleNamespace(id=i)

class Perm(unittest.TestCase):
    def setUp(self): self.cog = M.ModCog(Bot(Guild())); self.g = self.cog.bot.g
    def test_low_mod_cannot_act_on_higher_role(self):
        low, high = Member(10, 10, Perms(kick=True)), Member(11, 20)
        self.assertIn("không cao hơn", self.cog._hierarchy_error(low, high, self.g))
    def test_higher_role_can_act_on_lower(self):
        self.assertIsNone(self.cog._hierarchy_error(Member(10, 30), Member(11, 20), self.g))
    def test_cannot_target_bot_admin_owner_self_or_above_bot(self):
        a = Member(10, 40)
        self.assertIsNotNone(self.cog._hierarchy_error(a, Member(900, 1), self.g))
        self.assertIsNotNone(self.cog._hierarchy_error(a, Member(1000, 1), self.g))
        self.assertIsNotNone(self.cog._hierarchy_error(a, a, self.g))
        self.assertIsNotNone(self.cog._hierarchy_error(a, Member(11, 60), self.g))   # >= bot (50)
    def test_bot_admin_bypasses_actor_rank(self):
        self.assertIsNone(self.cog._hierarchy_error(Member(900, 1), Member(11, 20), self.g))
    def test_kick_permission_is_not_enough_to_ban(self):
        self.assertFalse(self.cog._can_ban(Member(10, 10, Perms(kick=True))))
        self.assertTrue(self.cog._can_ban(Member(10, 10, Perms(ban=True))))
        self.assertTrue(self.cog._can_ban(Member(10, 10, Perms(admin=True))))
        self.assertTrue(self.cog._can_ban(Member(900, 1)))

def boot_env():
    col = conftest_stubs.FakeCol(); gw = conftest_stubs.FakeCol()
    D._get_mongo = lambda: (col, gw)
    D._data_cache = {}; D._global_cache = None; D._global_loaded = False
    D._persisted_keys.clear(); D._persisted_keys_global.clear(); D._data_cache_ready.clear(); D._LOAD_RETRY_DELAY = 0
    col.docs["guild_1"] = {"_id": "guild_1"}
    return col
class B:
    class G: id = 1
    guilds = [G()]

class Tempban(unittest.TestCase):
    def test_two_guilds_same_user_do_not_overwrite_and_remove_is_per_guild(self):
        async def go():
            boot_env(); await D.init_data_cache(B())
            C.add_tempban(42, 1, 9e9, "a"); C.add_tempban(42, 2, 9e9, "b")
            self.assertEqual(len(C.get_active_tempbans()), 2)
            C.remove_tempban(42, 1)
            left = list(C.get_active_tempbans().values())
            self.assertEqual([(x["user_id"], x["guild_id"]) for x in left], [(42, 2)])
        asyncio.run(go())
    def test_legacy_record_is_normalised(self):
        async def go():
            col = boot_env()
            col.docs["main"] = {"_id": "main", "_tempbans": {"42": {"guild_id": 1, "unban_at": 9e9, "reason": "x"}}}
            await D.init_data_cache(B())
            info = list(C.get_active_tempbans().values())[0]
            self.assertEqual((info["user_id"], info["guild_id"]), (42, 1))
        asyncio.run(go())

    def test_resume_waits_for_cache_then_schedules(self):
        async def go():
            col = boot_env()
            col.docs["main"] = {"_id": "main", "_tempbans": {"1:42": {"user_id": 42, "guild_id": 1, "unban_at": time.time() + 3600}}}
            cog = M.ModCog(Bot(Guild()))
            await cog.cog_load()                       # chạy TRƯỚC khi cache sẵn sàng (như thực tế)
            await asyncio.sleep(0.02)
            self.assertEqual(cog._unban_tasks, {})     # chưa đọc dữ liệu rỗng rồi bỏ qua
            await D.init_data_cache(B())
            await asyncio.sleep(0.05)
            self.assertIn((1, 42), cog._unban_tasks)
            await cog.cog_unload()
        asyncio.run(go())

    def test_failed_unban_keeps_record_not_found_removes_it(self):
        async def go():
            boot_env(); await D.init_data_cache(B())
            real_sleep = asyncio.sleep
            async def fast(*a, **k): await real_sleep(0)
            asyncio.sleep = fast
            try:
                g = Guild(); cog = M.ModCog(Bot(g))
                C.add_tempban(42, 1, 0, "x")
                g.unban_exc = dc.HTTPException()                 # lỗi tạm thời, mọi lần retry
                await cog._finish_tempban(1, 42)
                self.assertEqual(len(C.get_active_tempbans()), 1)   # GIỮ để thử lại sau restart
                g.unban_exc = dc.NotFound()                      # đã được unban tay
                await cog._finish_tempban(1, 42)
                self.assertEqual(len(C.get_active_tempbans()), 0)
                C.add_tempban(43, 1, 0, "x"); g.unban_exc = None
                await cog._finish_tempban(1, 43)
                self.assertEqual([u.id for u in g.unbans], [43]); self.assertEqual(len(C.get_active_tempbans()), 0)
            finally:
                asyncio.sleep = real_sleep
        asyncio.run(go())

    def test_reschedule_cancels_old_timer_and_permaban_cancels_all(self):
        async def go():
            boot_env(); await D.init_data_cache(B())
            cog = M.ModCog(Bot(Guild()))
            cog._schedule_unban(1, 42, time.time() + 100); first = cog._unban_tasks[(1, 42)]
            cog._schedule_unban(1, 42, time.time() + 200)
            await asyncio.sleep(0); self.assertTrue(first.cancelled())
            C.add_tempban(42, 1, time.time() + 200, "x")
            cog._cancel_tempban(1, 42)
            self.assertEqual(cog._unban_tasks, {}); self.assertEqual(len(C.get_active_tempbans()), 0)
        asyncio.run(go())

if __name__ == "__main__":
    unittest.main(verbosity=2)
