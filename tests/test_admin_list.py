"""`.admin` (danh sách admin cố định + admin phụ MỌI server) + log chi tiết của is_admin()."""
import asyncio, sys, os, types, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install(); stubs_discord.install_optional_stubs()
import conftest_stubs
lg = types.ModuleType("cogs.logger")
async def _send_log(*a, **k): return None
lg.send_log = _send_log
sys.modules["cogs.logger"] = lg
import shared.data as D
import cogs.admin as AD

dc = sys.modules["discord"]

class FakeEmbed:
    def __init__(self, **kw):
        self.title = kw.get("title"); self.description = kw.get("description"); self.fields = []; self.footer = None
    def add_field(self, name, value, inline=True): self.fields.append((name, value)); return self
    def set_footer(self, text=None, **k): self.footer = text; return self
    def text(self): return "\n".join(filter(None, [self.title, self.description] + [f"{n}\n{v}" for n, v in self.fields]))

class U:
    def __init__(self, uid, name="u"): self.id = uid; self.name = name
class Perm: administrator = kick_members = ban_members = manage_channels = False
class Mem(U):
    guild_permissions = Perm()
    class _R: mention = "@role"
    top_role = _R()
class Guild:
    def __init__(self, gid, name, members=()): self.id = gid; self.name = name; self._m = {m: Mem(m) for m in members}
    def get_member(self, uid): return self._m.get(uid)
class Bot:
    def __init__(self, guilds): self.guilds = guilds
    def get_user(self, uid): return None
    def get_guild(self, gid): return next((g for g in self.guilds if g.id == gid), None)
class Ctx:
    def __init__(self, guild, author): self.guild = guild; self.author = author; self.sent = []
    async def reply(self, *a, **k): self.sent.append(k.get("embed"))
    async def send(self, *a, **k): self.sent.append(k.get("embed"))

class AdminList(unittest.TestCase):
    def setUp(self):
        self._embed = dc.Embed; dc.Embed = FakeEmbed
        self._ids = list(D.ADMIN_IDS); D.ADMIN_IDS[:] = [111]
        self._ruby = AD.ADMIN_RUBY_ID; AD.ADMIN_RUBY_ID = 111
        D._data_cache = {1: {"extra_admin_ids": [500]}, 2: {"extra_admin_ids": [600, 700]}, 3: {}}
        D._global_cache = {"_authorized_guilds": [1, 2]}; D._global_loaded = True
        D._admin_log_last.clear()
        D.set_current_guild(1)
        self.g1 = Guild(1, "Shop A", members=[500, 111]); self.g2 = Guild(2, "Shop B", members=[600])
        self.g3 = Guild(3, "Shop C"); self.bot = Bot([self.g1, self.g2, self.g3])
        self.cog = AD.AdminCog.__new__(AD.AdminCog); self.cog.bot = self.bot
    def tearDown(self):
        dc.Embed = self._embed; D.ADMIN_IDS[:] = self._ids; AD.ADMIN_RUBY_ID = self._ruby

    def test_get_all_extra_admins(self):
        self.assertEqual(D.get_all_extra_admins(), {1: [500], 2: [600, 700]})

    def test_overview_fixed_viewer_sees_all_servers_with_warnings(self):
        txt = "\n".join(e.text() for e in self.cog._admin_overview_embeds(1, True, "Ruby"))
        for must in ("<@111>", "Ruby", "<@500>", "<@600>", "<@700>", "Shop B · 2", "◀ server này", "Shop C"):
            self.assertIn(must, txt)
        self.assertIn("không thấy trong server", txt)       # 700 không ở Shop B
        self.assertIn("1** admin cố định · **3** admin phụ ở **2** server · bot đang ở **3** server", txt)

    def test_overview_extra_admin_only_sees_own_server(self):
        txt = "\n".join(e.text() for e in self.cog._admin_overview_embeds(1, False, "x"))
        self.assertIn("<@500>", txt); self.assertIn("<@111>", txt)
        self.assertNotIn("<@600>", txt); self.assertNotIn("Shop B", txt)

    def test_overview_flags_unauthorized_server_and_left_server(self):
        D._data_cache[99] = {"extra_admin_ids": [800]}       # bot đã rời server 99
        D._data_cache[3] = {"extra_admin_ids": [900]}        # Shop C chưa ủy quyền
        txt = "\n".join(e.text() for e in self.cog._admin_overview_embeds(1, True, "Ruby"))
        self.assertIn("bot không còn ở server này", txt); self.assertIn("chưa ủy quyền", txt)

    def test_many_servers_split_into_valid_embeds(self):
        for i in range(10, 60): D._data_cache[i] = {"extra_admin_ids": [1000 + i]}; self.bot.guilds.append(Guild(i, f"S{i}"))
        embeds = self.cog._admin_overview_embeds(1, True, "Ruby")
        self.assertGreater(len(embeds), 1)
        for e in embeds:
            self.assertLessEqual(len(e.fields), 24)
            self.assertLessEqual(len(e.text()), 5500)
            for _, v in e.fields: self.assertLessEqual(len(v), 1024)

    def test_missing_env_is_reported(self):
        AD.ADMIN_RUBY_ID = None
        txt = "\n".join(e.text() for e in self.cog._admin_overview_embeds(1, True, "x"))
        self.assertIn("ADMIN_RUBY_ID", txt)

    def test_diagnose_user_admin_elsewhere(self):
        ctx = Ctx(self.g1, U(111))
        asyncio.run(self.cog._admin_diagnose(ctx, 600, True))
        txt = ctx.sent[0].text()
        self.assertIn("KHÔNG có quyền admin", txt); self.assertIn("Shop B", txt); self.assertIn(".ad 600", txt)

    def test_diagnose_extra_admin_is_ok(self):
        ctx = Ctx(self.g1, U(111))
        asyncio.run(self.cog._admin_diagnose(ctx, 500, True))
        self.assertIn("CÓ quyền admin", ctx.sent[0].text())

class AdminCheckLogs(unittest.TestCase):
    def setUp(self):
        self._ids = list(D.ADMIN_IDS); D.ADMIN_IDS[:] = [111]
        D._data_cache = {1: {"extra_admin_ids": [500]}, 2: {"extra_admin_ids": [600]}}
        D._admin_log_last.clear(); D.set_current_guild(1)
    def tearDown(self): D.ADMIN_IDS[:] = self._ids

    def test_denied_logs_reason_hint_and_caller(self):
        with self.assertLogs("shared.data", level="INFO") as cm:
            self.assertFalse(D.is_admin(U(600, "bob")))
        msg = cm.output[0]
        self.assertIn("TỪ CHỐI", msg); self.assertIn("server khác [2]", msg)
        self.assertIn("test_admin_list.py", msg)              # dòng code đã gọi is_admin

    def test_extra_admin_allowed_is_logged(self):
        with self.assertLogs("shared.data", level="INFO") as cm:
            self.assertTrue(D.is_admin(U(500)))
        self.assertIn("CHO PHÉP", cm.output[0]); self.assertIn("admin phụ", cm.output[0])

    def test_no_guild_context_is_warning(self):
        D._current_guild_id.set(None)
        with self.assertLogs("shared.data", level="WARNING") as cm:
            self.assertFalse(D.is_admin(U(500)))
        self.assertIn("KHÔNG có guild context", cm.output[0])

    def test_repeated_denials_are_throttled(self):
        with self.assertLogs("shared.data", level="INFO") as cm:
            for _ in range(5): D.is_admin(U(999))
        self.assertEqual(len(cm.output), 1)

    def test_fixed_admin_silent_unless_debug(self):
        with self.assertNoLogs("shared.data", level="INFO"):
            self.assertTrue(D.is_admin(U(111)))

if __name__ == "__main__":
    unittest.main()
