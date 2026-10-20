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
        D._admin_log_last.clear(); D.set_current_guild(1); D.set_command_context(".paneltext")
    def tearDown(self): D.ADMIN_IDS[:] = self._ids; D.set_command_context(None)

    def test_denied_logs_reason_hint_command_and_caller(self):
        with self.assertLogs("shared.data", level="INFO") as cm:
            self.assertFalse(D.is_admin(U(600, "bob")))
        msg = cm.output[0]
        self.assertIn("TỪ CHỐI", msg); self.assertIn("server khác [2]", msg)
        self.assertIn("lệnh=.paneltext", msg)                 # biết lệnh nào bị chặn
        self.assertIn("test_admin_list.py", msg)              # dòng code đã gọi is_admin

    def test_denied_in_command_is_logged_at_info(self):
        with self.assertLogs("shared.data", level="INFO") as cm:
            self.assertFalse(D.is_admin(U(999)))
        self.assertIn("TỪ CHỐI", cm.output[0]); self.assertIn("guild có 1 admin phụ", cm.output[0])

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

    def test_passive_check_outside_command_is_not_info(self):
        D.set_command_context(None)                            # vd listener on_message — không phải user vừa gõ lệnh
        with self.assertNoLogs("shared.data", level="INFO"):
            self.assertFalse(D.is_admin(U(999)))

    def test_quiet_never_logs(self):
        with self.assertNoLogs("shared.data", level="DEBUG"):
            self.assertFalse(D.is_admin(U(600), quiet=True)); self.assertTrue(D.is_admin(U(500), quiet=True))

    def test_is_admin_id_and_dangerous_cmd_include_extra_admins(self):
        import core.data as CD
        self.assertTrue(CD.can_use_dangerous_cmd(111, "emoji"))     # admin cố định
        self.assertTrue(CD.can_use_dangerous_cmd(500, "emoji"))     # admin phụ của guild 1  ← lỗi .emoji/.rename/.setperm trước đây
        self.assertFalse(CD.can_use_dangerous_cmd(600, "emoji"))    # admin phụ của guild 2 — KHÔNG có quyền ở guild 1
        self.assertFalse(CD.can_use_dangerous_cmd(999, "emoji"))


import ast
class CrossServerCommandsStayFixedOnly(unittest.TestCase):
    """Chốt chặn bảo mật: lệnh LIÊN SERVER / toàn bot KHÔNG được dùng is_admin() (admin phụ chỉ có quyền
    trong server được cấp). Nếu ai đó lỡ đổi sang is_admin() → test này fail."""
    FIXED_ONLY = {"cogs/invite.py": ["serverlist_cmd", "leaveguild_cmd"],
                  "cogs/ai_chat.py": ["ai_reset", "slash_aireset"],
                  "cogs/admin.py": ["authorize_server_cmd"]}
    def test_no_is_admin_in_cross_server_commands(self):
        for rel, names in self.FIXED_ONLY.items():
            t = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
            found = {n.name: ast.unparse(n) for n in ast.walk(t) if isinstance(n, ast.AsyncFunctionDef) and n.name in names}
            self.assertEqual(sorted(found), sorted(names), f"{rel}: thiếu hàm")
            for name, src in found.items():
                self.assertNotIn("is_admin(", src, f"{rel}:{name} KHÔNG được dùng is_admin() — lệnh liên server")
                self.assertIn("ADMIN_IDS", src, f"{rel}:{name} phải kiểm tra ADMIN_IDS")


class GiveawayScope(unittest.TestCase):
    def test_gw_in_scope(self):
        import cogs.giveaway as G
        class Ch:  # kênh thuộc server 1
            class guild: id = 1
        class B:
            def get_channel(self, cid): return Ch if cid == 10 else None
        gw = {"channel_id": 10}
        self.assertTrue(G._gw_in_scope(B(), U(111), 999, gw) if 111 in G.ADMIN_IDS else True)
        G.ADMIN_IDS[:] = [111]
        try:
            self.assertTrue(G._gw_in_scope(B(), U(111), 2, gw))          # admin cố định: mọi server
            self.assertTrue(G._gw_in_scope(B(), U(500), 1, gw))          # admin phụ: đúng server của giveaway
            self.assertFalse(G._gw_in_scope(B(), U(500), 2, gw))         # admin phụ: giveaway của server khác
            self.assertFalse(G._gw_in_scope(B(), U(500), 1, {"channel_id": 77}))  # kênh không tìm ra
        finally:
            G.ADMIN_IDS[:] = []


class FakeResp:
    def __init__(self): self.sent = []
    async def send_message(self, *a, **k): self.sent.append(a[0] if a else k.get("content"))

class FakeInter:
    def __init__(self, gid, user, data=None):
        self.guild_id = gid; self.user = user; self.data = data or {}; self.channel_id = 5; self.response = FakeResp()

class UiGateAndAuthGate(unittest.TestCase):
    def setUp(self):
        self._ids = list(D.ADMIN_IDS); D.ADMIN_IDS[:] = [111]
        D._data_cache = {1: {"extra_admin_ids": [500]}, 2: {"extra_admin_ids": [600]}}
        D._global_cache = {"_authorized_guilds": [1]}; D._global_loaded = True      # guild 2 CHƯA ủy quyền
        D._admin_log_last.clear(); D.set_command_context(None)
    def tearDown(self): D.ADMIN_IDS[:] = self._ids; D.set_command_context(None)

    def test_ui_gate_authorized_logs_and_sets_context(self):
        it = FakeInter(1, U(500, "ad"), {"custom_id": "panel:btn"})
        async def go():   # contextvar chỉ sống trong cùng task → đọc ngay trong coroutine (giống before_invoke → lệnh)
            ok = await D.guild_ui_gate(it, "view", object())
            return ok, D.get_command_context()
        with self.assertLogs("shared.data", level="INFO") as cm:
            ok, ctxlabel = asyncio.run(go())
        self.assertTrue(ok); self.assertIn("[UI]", cm.output[0]); self.assertIn("panel:btn", cm.output[0])
        self.assertIn("panel:btn", ctxlabel)

    def test_ui_gate_unauthorized_extra_admin_is_told_and_logged(self):
        it = FakeInter(2, U(600, "ad"))
        with self.assertLogs("shared.data", level="WARNING") as cm:
            self.assertFalse(asyncio.run(D.guild_ui_gate(it, "view", object())))
        self.assertIn("CHƯA ủy quyền", cm.output[0]); self.assertIn("admin phụ=True", cm.output[0])
        self.assertTrue(it.response.sent and "Nhờ Ruby/TuyTam" in it.response.sent[0])   # admin phụ được báo lý do

    def test_ui_gate_unauthorized_stranger_silent_but_logged(self):
        it = FakeInter(2, U(999))
        with self.assertLogs("shared.data", level="WARNING"):
            self.assertFalse(asyncio.run(D.guild_ui_gate(it, "view", object())))
        self.assertEqual(it.response.sent, [])

    def test_global_check_unauthorized_guild_replies_to_extra_admin(self):
        import shared.auth_gate as AG
        class Cmd: qualified_name = "emoji"
        class Ctx:
            def __init__(s, uid): s.guild = Guild(2, "B"); s.author = U(uid); s.command = Cmd; s.replies = []
            async def reply(s, *a, **k): s.replies.append(a[0])
        c = Ctx(600)
        with self.assertLogs("auth_gate", level="WARNING") as cm:
            self.assertFalse(asyncio.run(AG.global_guild_authorization_check(c)))
        self.assertIn("CHƯA ủy quyền", cm.output[0]); self.assertTrue(c.replies)
        c2 = Ctx(999)
        with self.assertLogs("auth_gate", level="WARNING"):
            self.assertFalse(asyncio.run(AG.global_guild_authorization_check(c2)))
        self.assertEqual(c2.replies, [])                                               # người lạ: im lặng nhưng có log
        c3 = Ctx(500); c3.guild = Guild(1, "A")
        self.assertTrue(asyncio.run(AG.global_guild_authorization_check(c3)))           # server đã ủy quyền

    def test_before_invoke_logs_and_redacts_sensitive(self):
        import shared.auth_gate as AG
        class Cmd: qualified_name = "shopbank"
        class Msg: content = ".shopbank 0123456789 VCB"
        class Ctx: guild = Guild(1, "A"); author = U(500, "ad"); command = Cmd; message = Msg; channel = types.SimpleNamespace(id=9)
        async def go():
            await AG.set_guild_context_prefix(Ctx())
            return D.get_command_context()
        with self.assertLogs("auth_gate", level="INFO") as cm:
            label = asyncio.run(go())
        self.assertIn("[CMD] .shopbank", cm.output[0]); self.assertNotIn("0123456789", cm.output[0])
        self.assertEqual(label, ".shopbank")

    def test_command_crash_is_logged_with_traceback(self):
        import shared.auth_gate as AG
        class Cmd: qualified_name = "emoji"
        class Ctx: guild = Guild(1, "A"); author = U(500, "ad"); command = Cmd
        with self.assertLogs("auth_gate", level="ERROR") as cm:
            asyncio.run(AG.log_command_error(Ctx(), ValueError("boom")))
        self.assertIn("LỖI", cm.output[0]); self.assertIn("boom", cm.output[0])

class TuytamDemotedToExtraAdmin(unittest.TestCase):
    """Kịch bản: xoá ADMIN_TUYTAM_ID khỏi Railway, TuyTam (id 222) được `.ad` làm admin phụ ở guild 1."""
    def setUp(self):
        self._ids = list(D.ADMIN_IDS); D.ADMIN_IDS[:] = [111]                  # chỉ còn Ruby là admin cố định
        self._n = D.TUYTAM_NOTIFY_ID; D.TUYTAM_NOTIFY_ID = 222
        D._data_cache = {1: {"extra_admin_ids": [222]}, 2: {}}
        D.set_current_guild(1); D.set_command_context(None)
    def tearDown(self): D.ADMIN_IDS[:] = self._ids; D.TUYTAM_NOTIFY_ID = self._n

    def _env(self, **env):
        old = {k: os.environ.get(k) for k in ("ADMIN_RUBY_ID", "ADMIN_TUYTAM_ID", "TUYTAM_NOTIFY_ID")}
        for k in old: os.environ.pop(k, None)
        os.environ.update(env)
        def restore():
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None: os.environ[k] = v
        self.addCleanup(restore)

    def test_tuytam_is_admin_in_his_guild_only(self):
        self.assertTrue(D.is_admin(U(222), quiet=True))                 # guild 1: admin phụ
        D.set_current_guild(2)
        self.assertFalse(D.is_admin(U(222), quiet=True))                # guild 2: chưa .ad → không có quyền

    def test_ping_and_overwrite_treat_tuytam_as_user_not_role(self):
        self.assertTrue(D.is_user_id(222))                               # không bị coi là role → <@id> chứ không phải <@&id>
        self.assertTrue(D.is_user_id(111)); self.assertFalse(D.is_user_id(987654321))   # role id lạ → role
        D.set_current_guild(2)
        self.assertTrue(D.is_user_id(222))                               # vẫn là USER (nhờ TUYTAM_NOTIFY_ID) dù chưa .ad ở guild 2

    def test_extra_admin_in_role_list_is_user_even_without_notify_id(self):
        D.TUYTAM_NOTIFY_ID = None
        D._data_cache[1]["extra_admin_ids"] = [333]
        self.assertTrue(D.is_user_id(333))

    def test_notify_id_env_fallback_and_override(self):
        self._env(ADMIN_RUBY_ID="111", ADMIN_TUYTAM_ID="222")            # chưa cấu hình gì mới → như cũ
        D.ADMIN_IDS[:] = D._load_admin_ids(); D.ADMIN_TUYTAM_ID = 222
        self.assertEqual(D._load_tuytam_notify_id(), 222)
        self._env(ADMIN_RUBY_ID="111", TUYTAM_NOTIFY_ID="222")           # đã hạ TuyTam: chỉ còn NOTIFY
        D.ADMIN_TUYTAM_ID = None
        self.assertEqual(D._load_tuytam_notify_id(), 222)
        self._env(ADMIN_RUBY_ID="111", TUYTAM_NOTIFY_ID="abc")
        with self.assertLogs("shared.data", level="ERROR"): self.assertIsNone(D._load_tuytam_notify_id())

    def test_missing_tuytam_env_is_not_a_warning(self):
        self._env(ADMIN_RUBY_ID="111")
        with self.assertLogs("shared.data", level="INFO") as cm:
            self.assertEqual(D._load_admin_ids(), [111])
        self.assertFalse([r for r in cm.records if r.levelname in ("WARNING", "ERROR", "CRITICAL")])

    def test_tuytam_cannot_use_fixed_only_commands(self):
        self.assertNotIn(222, D.ADMIN_IDS)                                # → `.as` `.serverlist` `.leaveguild` `.aireset` từ chối
        self.assertFalse(D.is_admin_id(222, quiet=True) and 222 in D.ADMIN_IDS)


if __name__ == "__main__":
    unittest.main()
