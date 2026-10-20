import asyncio, sys, os, time, types, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install(); stubs_discord.install_optional_stubs()
import conftest_stubs
import shared.data as D
import core.data as C
dc = sys.modules["discord"]

class FakeEmbed:
    def __init__(self, **kw):
        self.title = kw.get("title"); self.description = kw.get("description"); self.color = kw.get("color")
        self.timestamp = kw.get("timestamp"); self.fields = []; self.footer = None; self.author = None; self.thumb = None
    def add_field(self, name, value, inline=True): self.fields.append((name, value, inline)); return self
    def set_footer(self, text=None, **k): self.footer = text; return self
    def set_author(self, name=None, **k): self.author = name; return self
    def set_thumbnail(self, url=None): self.thumb = url; return self
    def text(self): return "\n".join(filter(None, [self.title, self.description, self.footer, self.author] + [f"{n}\n{v}" for n, v, _ in self.fields]))
dc.Embed = FakeEmbed
import cogs.leaderboard as L
L.ADMIN_IDS = [1]
L.is_admin = lambda m: m.id in L.ADMIN_IDS   # code giờ gọi is_admin() (gồm admin phụ .ad); test giả lập admin cố định id=1

def boot(spent=None):
    col = conftest_stubs.FakeCol(); gw = conftest_stubs.FakeCol()
    D._get_mongo = lambda: (col, gw)
    D._data_cache = {}; D._global_cache = None; D._global_loaded = False
    D._persisted_keys.clear(); D._persisted_keys_global.clear(); D._data_cache_ready.clear(); D._LOAD_RETRY_DELAY = 0
    col.docs["guild_1"] = {"_id": "guild_1", "user_total_spent": spent or {}}
    col.docs["main"] = {"_id": "main", "_authorized_guilds": [1]}
    return col
class B:
    class G: id = 1
    guilds = [G()]

SPENT = {str(1000 + i): (20 - i) * 100_000 for i in range(15)}     # 15 người, 2.0tr … 0.6tr, không trùng
class Member:
    def __init__(self, i, name): self.id, self.display_name = i, name
class Guild:
    id = 1; name = "Cookie Store"; icon = None
    def __init__(self, members=None): self.members = members or {}
    def get_member(self, i): return self.members.get(i)
class Bot:
    def __init__(self, users=None, fail=False): self.users, self.fail = users or {}, fail
    def get_user(self, i): return None
    async def fetch_user(self, i):
        if self.fail or i not in self.users: raise dc.NotFound()
        return self.users[i]

class Pure(unittest.TestCase):
    def test_fmt_vnd(self):
        self.assertEqual(L.fmt_vnd(21_120_000), "21.120.000đ"); self.assertEqual(L.fmt_vnd(0), "0đ")
    def test_ranking_ties_zero_and_bad_data(self):
        r = L.build_ranking({"1": 500, "2": 900, "3": 500, "4": 0, "5": -3, "x": 10, "6": "abc", "7": 100})
        self.assertEqual([(a, b) for a, b, _ in r], [(1, 2), (2, 1), (2, 3), (4, 7)])   # 1,2,2,4
    def test_clean_name(self):
        self.assertNotIn("@everyone", L.clean_name("@everyone"))
        self.assertIn("\\*", L.clean_name("**bold**")); self.assertEqual(L.clean_name(""), "Ẩn danh")
        self.assertLessEqual(len(L.clean_name("x" * 100)), 24)
    def test_my_rank_not_found(self):
        small = L.build_ranking({"1": 5, "2": 3})
        i = L.my_rank_info(small, 99); self.assertFalse(i["found"]); self.assertEqual(i["slots_left"], 8)
        full = L.build_ranking(SPENT); i = L.my_rank_info(full, 99)
        self.assertEqual(i["slots_left"], 0); self.assertEqual(i["tenth_amount"], full[9][2])
    def test_my_rank_leader_middle_and_outside_top10(self):
        rk = L.build_ranking(SPENT)
        top = L.my_rank_info(rk, 1000); self.assertEqual(top["rank"], 1); self.assertIsNone(top["gap_above"])
        self.assertEqual(top["gap_below"], 100_000); self.assertEqual(top["below_uid"], 1001)
        mid = L.my_rank_info(rk, 1004); self.assertEqual(mid["rank"], 5)
        self.assertEqual((mid["above_rank"], mid["above_uid"], mid["gap_above"]), (4, 1003, 100_000))
        self.assertIsNone(mid["gap_top10"])
        out = L.my_rank_info(rk, 1012); self.assertEqual(out["rank"], 13)
        self.assertEqual((out["amount"], rk[9][2], out["gap_top10"]), (800_000, 1_100_000, 300_000))
        self.assertIsNone(out["above_uid"])                        # người ngoài Top 10 KHÔNG bị lộ danh tính
    def test_my_rank_gap_skips_equal_amounts(self):
        rk = L.build_ranking({"1": 900, "2": 500, "3": 500})
        i = L.my_rank_info(rk, 3); self.assertEqual((i["rank"], i["above_rank"], i["gap_above"]), (2, 1, 400))

class Embeds(unittest.TestCase):
    def names(self, n=15): return {1000 + i: f"Người {i}" for i in range(n)}
    def test_board_has_expected_parts_and_no_raw_mentions(self):
        rk = L.build_ranking(SPENT); e = L.build_board_embed("Cookie Store", None, rk, self.names(), len(rk), sum(a for *_, a in rk), 1_790_000_000)
        t = e.text()
        self.assertIn("TOP 10", e.title); self.assertIn("Top 1:", t); self.assertIn("`#01`", t); self.assertIn("`#10`", t)
        self.assertNotIn("`#11`", t); self.assertNotIn("<@", t)                       # không mention thô, không ping
        self.assertIn("Thứ Hạng Của Tôi", t); self.assertIn("<t:1790000000:R>", t); self.assertIn("5 giờ", e.footer)
        self.assertEqual(e.description.count("`#"), 10)
    def test_empty_board(self):
        e = L.build_board_embed("S", None, [], {}, 0, 0, 1_790_000_000)
        self.assertIn("Chưa có ai", e.description)
    def test_my_rank_embeds_never_name_people_outside_top10(self):
        rk = L.build_ranking(SPENT); info = L.my_rank_info(rk, 1012)
        e = L.build_my_rank_embed("Tôi", info, {}); t = e.text()
        self.assertIn("#13", t); self.assertIn("Vào Top 10", t); self.assertNotIn("Người", t)
    def test_my_rank_leader_and_new_user(self):
        rk = L.build_ranking(SPENT)
        e = L.build_my_rank_embed("Tôi", L.my_rank_info(rk, 1000), {1001: "Người 1"}); self.assertIn("dẫn đầu", e.text()); self.assertIn("Người 1", e.text())
        e = L.build_my_rank_embed("Tôi", L.my_rank_info(rk, 99), {}); self.assertIn("chưa có đơn", e.text())
        e = L.build_my_rank_embed("Tôi", L.my_rank_info(L.build_ranking({"1": 5}), 99), {}); self.assertIn("chỗ trống", e.text())

class Glue(unittest.TestCase):
    def test_resolve_names_member_fetch_and_failure(self):
        async def go():
            L._name_cache.clear()
            g = Guild({10: Member(10, "Alice *x*")})
            b = Bot({20: types.SimpleNamespace(global_name="Bob", name="bob")})
            n = await L.resolve_names(b, g, [10, 20, 30])
            self.assertIn("Alice", n[10]); self.assertNotIn("*x*", n[10].replace("\\*", ""))
            self.assertEqual(n[20], "Bob"); self.assertTrue(n[30].startswith("Người dùng …"))
            self.assertNotIn("<@", "".join(n.values()))
        asyncio.run(go())

    def _interaction(self, user_id=1004, msg_id=555):
        calls = types.SimpleNamespace(deferred=None, sent=[], follow=[], edited=[])
        async def defer(ephemeral=False): calls.deferred = ephemeral
        async def send_message(*a, **k): calls.sent.append((a, k))
        async def follow(*a, **k): calls.follow.append(k)
        async def edit(**k): calls.edited.append(k)
        it = types.SimpleNamespace(
            guild=Guild(), user=Member(user_id, "Tôi"), client=Bot(), message=types.SimpleNamespace(id=msg_id),
            response=types.SimpleNamespace(defer=defer, send_message=send_message),
            followup=types.SimpleNamespace(send=follow), edit_original_response=edit)
        return it, calls

    def test_my_rank_button_replies_ephemeral(self):
        async def go():
            boot(SPENT); await D.init_data_cache(B()); D.set_current_guild(1)
            it, calls = self._interaction(1004)
            await L.handle_my_rank(it)
            self.assertTrue(calls.deferred)                                      # defer ephemeral
            self.assertTrue(calls.follow[0]["ephemeral"]); self.assertIn("#5", calls.follow[0]["embed"].text())
        asyncio.run(go())

    def test_refresh_button_updates_and_has_cooldown(self):
        async def go():
            boot(SPENT); await D.init_data_cache(B()); D.set_current_guild(1)
            L._refresh_last.clear()
            it, calls = self._interaction(msg_id=777)
            await L.handle_refresh(it)
            self.assertEqual(len(calls.edited), 1)
            await L.handle_refresh(it)                                           # ngay sau đó → bị chặn
            self.assertEqual(len(calls.edited), 1); self.assertTrue(calls.sent[-1][1]["ephemeral"]); self.assertIn("thử lại", calls.sent[-1][0][0])
            L._refresh_last[777] -= L.REFRESH_COOLDOWN + 1                       # hết cooldown
            await L.handle_refresh(it); self.assertEqual(len(calls.edited), 2)
        asyncio.run(go())

class PanelFlow(unittest.TestCase):
    def setUp(self):
        class Chan:
            def __init__(s, cid): s.id = cid; s.mention = f"<#{cid}>"; s.msgs = {}; s.n = 0
            def permissions_for(s, me): return types.SimpleNamespace(send_messages=True, embed_links=True)
            async def send(s, embed=None, view=None):
                s.n += 1; m = types.SimpleNamespace(id=s.n * 100 + s.id); m.edits = []; m.deleted = False
                async def edit(embed=None, m=m): m.edits.append(embed)
                async def delete(m=m): m.deleted = True
                m.edit, m.delete = edit, delete; s.msgs[m.id] = m; return m
            async def fetch_message(s, mid):
                if mid not in s.msgs: raise dc.NotFound()
                return s.msgs[mid]
        self.Chan = Chan
        self.chan = Chan(5)
        class Bot2(Bot):
            def __init__(s, ch): super().__init__(); s.ch = ch
            def get_channel(s, cid): return s.ch if cid == s.ch.id else None
        self.bot = Bot2(self.chan)
        self.replies = []
        async def reply(text=None, **k): self.replies.append(text if text is not None else k)
        self.ctx = types.SimpleNamespace(author=types.SimpleNamespace(id=1), channel=self.chan, guild=Guild(),
                                         reply=reply)
        self.ctx.guild.me = object()
        self.cog = L.LeaderboardCog(self.bot)

    def test_panel_create_replace_off_and_permissions(self):
        async def go():
            boot(SPENT); await D.init_data_cache(B()); D.set_current_guild(1)
            self.ctx.author.id = 99                                              # không phải admin
            await self.cog._do_panel(self.ctx, ""); self.assertIn("Chỉ admin", self.replies[-1]); self.assertEqual(self.chan.msgs, {})
            self.ctx.author.id = 1
            await self.cog._do_panel(self.ctx, "")
            first = load_panel(); self.assertEqual(first["channel_id"], 5); self.assertEqual(len(self.chan.msgs), 1)
            await self.cog._do_panel(self.ctx, "")                               # tạo lại → xoá message cũ
            second = load_panel(); self.assertNotEqual(first["message_id"], second["message_id"])
            self.assertTrue(self.chan.msgs[first["message_id"]].deleted)
            await self.cog._do_panel(self.ctx, "off")
            self.assertIsNone(load_panel()); self.assertTrue(self.chan.msgs[second["message_id"]].deleted)
            await self.cog._do_panel(self.ctx, "off"); self.assertIn("chưa bật", self.replies[-1])
        def load_panel(): return C.load_data().get("leaderboard_panel")
        asyncio.run(go())

    def test_auto_update_waits_5h_and_handles_deleted_message(self):
        async def go():
            boot(SPENT); await D.init_data_cache(B()); D.set_current_guild(1)
            self.ctx.author.id = 1
            await self.cog._do_panel(self.ctx, "")
            panel = C.load_data()["leaderboard_panel"]; msg = self.chan.msgs[panel["message_id"]]
            key = (1, panel["message_id"]); g = self.ctx.guild
            now = time.time()
            await self.cog._auto_update_guild(g, now + 3600)                     # mới 1h → chưa cập nhật
            self.assertEqual(msg.edits, [])
            await self.cog._auto_update_guild(g, now + 5 * 3600 + 5)             # đủ 5h → cập nhật
            self.assertEqual(len(msg.edits), 1)
            await self.cog._auto_update_guild(g, now + 5 * 3600 + 60)            # vừa cập nhật → không lặp
            self.assertEqual(len(msg.edits), 1)
            del self.chan.msgs[panel["message_id"]]                              # admin xoá message
            L._last_update[key] = 0
            await self.cog._auto_update_guild(g, now + 99999)
            self.assertIsNone(C.load_data().get("leaderboard_panel"))            # tự ngừng theo dõi
        asyncio.run(go())

if __name__ == "__main__":
    unittest.main(verbosity=2)
