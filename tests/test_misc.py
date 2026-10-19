import asyncio, sys, os, types, unittest
from datetime import datetime, timezone, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install(); stubs_discord.install_optional_stubs()
import conftest_stubs
lg = types.ModuleType("cogs.logger")
async def _send_log(*a, **k): return None
lg.send_log = _send_log
sys.modules["cogs.logger"] = lg
import shared.data as D
import core.data as C
import cogs.ticket as T
import cogs.invite as I
import cogs.ai_chat as A
import core.ai_tools as AT

def boot():
    col = conftest_stubs.FakeCol(); gw = conftest_stubs.FakeCol()
    D._get_mongo = lambda: (col, gw)
    D._data_cache = {}; D._global_cache = None; D._global_loaded = False
    D._persisted_keys.clear(); D._persisted_keys_global.clear(); D._data_cache_ready.clear(); D._LOAD_RETRY_DELAY = 0
    col.docs["guild_1"] = {"_id": "guild_1", "ticket": 10}
    return col
class B:
    class G: id = 1
    guilds = [G()]

class DoneGuard(unittest.TestCase):
    def test_retype_after_warning_runs(self):
        g = {}
        self.assertFalse(T._dup_check(g, ("c", 1, 5)))     # lần 1: chạy
        self.assertTrue(T._dup_check(g, ("c", 1, 5)))      # lần 2 trong 15s: cảnh báo
        self.assertFalse(T._dup_check(g, ("c", 1, 5)))     # lần 3 ("gõ lại 1 lần nữa"): chạy
    def test_old_entries_are_purged(self):
        g = {("old",): -10_000.0}
        T._dup_check(g, ("new",))
        self.assertNotIn(("old",), g)
    def test_completed_msg_keys_are_capped_keeping_newest(self):
        data = {f"completed_msg_{i}": True for i in range(1, 700)}
        data["completed_12345"] = True; data["ticket"] = 3
        T._prune_completed_msg_keys(data)
        self.assertEqual(len([k for k in data if k.startswith("completed_msg_")]), T._COMPLETED_MSG_KEEP)
        self.assertIn("completed_msg_699", data); self.assertNotIn("completed_msg_1", data)
        self.assertIn("completed_12345", data); self.assertIn("ticket", data)

class TicketCounter(unittest.TestCase):
    def test_get_ticket_number_refuses_when_guild_not_loaded(self):
        async def go2():
            col = boot(); col.fail_reads = 99
            C.get_db = lambda: {"bot_data": col}
            ok = await D.ensure_guild_loaded(1)
            self.assertFalse(ok)
            with self.assertRaises(RuntimeError):
                await C.get_ticket_number(1)
            self.assertEqual(col.docs["guild_1"]["ticket"], 10)   # bộ đếm thật không bị đè
        asyncio.run(go2())
    def test_get_ticket_number_increments_when_loaded(self):
        async def go():
            col = boot(); col.docs["main"] = {"_id": "main"}
            C.get_db = lambda: {"bot_data": col}
            await D.init_data_cache(B())
            self.assertEqual(await C.get_ticket_number(1), "011")
            self.assertEqual(col.docs["guild_1"]["ticket"], 11)
        asyncio.run(go())

class InviteLoad(unittest.TestCase):
    def test_inviters_not_overwritten_by_empty_dict_after_restart(self):
        async def go():
            col = boot()
            col.docs["main"] = {"_id": "main", "_member_inviters": {"500": {"inviter_id": 7, "guild_id": 1}}}
            I._member_inviters = {}; I._inviters_loaded = False
            await I.InviteCog(None).cog_load()                    # chạy trước khi cache sẵn sàng
            await D.init_data_cache(B())
            I._ensure_inviters_loaded()
            I._member_inviters[501] = {"inviter_id": 8, "guild_id": 1}
            C.save_member_inviters(I._member_inviters)
            await asyncio.sleep(0.05)
            saved = col.docs["main"]["_member_inviters"]
            self.assertIn("500", saved); self.assertIn("501", saved)
        asyncio.run(go())

class AiGuards(unittest.TestCase):
    def test_dangerous_tools_cover_privileged_and_irreversible(self):
        for t in ("role_add", "role_remove", "ticket_close", "mod_warn", "purge", "mod_ban"):
            self.assertIn(t, AT.DANGEROUS_TOOLS)
    def test_purge_amount_is_clamped(self):
        calls = []
        class Ch:
            async def purge(self, limit): calls.append(limit); return []
        ctx = types.SimpleNamespace(channel=Ch())
        asyncio.run(AT._h_purge(ctx, {"amount": 100000}))
        asyncio.run(AT._h_purge(ctx, {"amount": -5}))
        self.assertEqual(calls, [100, 1])
    def test_pending_questions_pruned_by_age_and_cap(self):
        now = datetime.now(timezone.utc)
        p = {"old": {"created_at": (now - timedelta(days=30)).isoformat()}}
        for i in range(A.AI_PENDING_MAX + 20):
            p[f"t{i}"] = {"created_at": (now - timedelta(seconds=A.AI_PENDING_MAX + 20 - i)).isoformat()}
        A._prune_pending_questions(p)
        self.assertNotIn("old", p); self.assertEqual(len(p), A.AI_PENDING_MAX)
        self.assertIn(f"t{A.AI_PENDING_MAX + 19}", p); self.assertNotIn("t0", p)

if __name__ == "__main__":
    unittest.main(verbosity=2)


class PanelText(unittest.TestCase):
    """`.paneltext` — sửa chữ panel theo guild, mặc định giữ nguyên khi chưa chỉnh."""
    def setUp(self):
        async def go():
            col = boot(); col.docs["main"] = {"_id": "main"}
            C.get_db = lambda: {"bot_data": col}
            await D.init_data_cache(B())
        asyncio.run(go()); D.set_current_guild(1)

    def test_default_unchanged(self):
        t = T.get_panel_text("main")
        self.assertEqual(t["title"], T.PANEL_TEXT_DEFAULTS["main"]["title"])
        self.assertEqual(len(t["fields"]), 3)

    def test_override_and_reset(self):
        T.set_panel_text("main", base={"title": "Shop Mới", "color": "FF0000"})
        T.set_panel_text("main", field_idx=1, field={"name": "A", "value": "B"})
        t = T.get_panel_text("main")
        self.assertEqual((t["title"], t["color"]), ("Shop Mới", "FF0000"))
        self.assertEqual(t["fields"][1]["name"], "A")
        self.assertEqual(t["fields"][0]["name"], T.PANEL_TEXT_DEFAULTS["main"]["fields"][0]["name"])
        self.assertEqual(T.get_panel_text("mm")["title"], T.PANEL_TEXT_DEFAULTS["mm"]["title"])
        T.reset_panel_text("main")
        self.assertEqual(T.get_panel_text("main")["title"], T.PANEL_TEXT_DEFAULTS["main"]["title"])

    def test_color_parse(self):
        self.assertEqual(T._parse_color("#ff00aa", "000000"), "FF00AA")
        self.assertEqual(T._parse_color("", "123456"), "123456")
        self.assertIsNone(T._parse_color("zzz", "123456"))
