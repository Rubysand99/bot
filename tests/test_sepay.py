import asyncio, sys, os, types, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install()
import conftest_stubs
# stub cogs.logger (chỉ cần send_log) để khỏi import tasks.loop
lg = types.ModuleType("cogs.logger")
async def _send_log(*a, **k): return None
lg.send_log = _send_log
sys.modules["cogs.logger"] = lg
import shared.data as D
import core.data as C
import cogs.shop_orders as S

ADMIN = 111
S.ADMIN_IDS = [ADMIN]

class Chan:
    def __init__(self): self.sent = []
    async def send(self, **kw): self.sent.append(kw)
class User:
    def __init__(self, i): self.id = i; self.dms = []; self.mention = f"<@{i}>"; self.name = f"u{i}"
    async def send(self, text): self.dms.append(text)
class Guild:
    id = 1
    def __init__(self, members): self.members = members
    def get_member(self, i): return self.members.get(i)
    async def fetch_member(self, i): raise sys.modules["discord"].NotFound()
class Bot:
    def __init__(self, guild, users): self.guild, self.users = guild, users
    def get_guild(self, gid): return self.guild if gid == 1 else None
    async def fetch_user(self, i): return self.users[i]

class Env:
    def __init__(self, chan_ok=True, buyer_in_guild=True, queue_raises=False):
        self.col = conftest_stubs.FakeCol(); gw = conftest_stubs.FakeCol()
        D._get_mongo = lambda: (self.col, gw)
        D._data_cache = {}; D._global_cache = None; D._global_loaded = False
        D._persisted_keys.clear(); D._persisted_keys_global.clear(); D._data_cache_ready.clear()
        D._LOAD_RETRY_DELAY = 0
        self.col.docs["guild_1"] = {"_id": "guild_1"}
        self.admin = User(ADMIN); self.buyer = User(20); self.seller = User(30)
        members = {30: self.seller}
        if buyer_in_guild: members[20] = self.buyer
        self.bot = Bot(Guild(members), {ADMIN: self.admin, 20: self.buyer, 30: self.seller})
        self.chan = Chan() if chan_ok else None
        self.queue_calls = []
        async def get_chan(bot, cid): return self.chan
        async def send_to_queue(*a, **k):
            if queue_raises: raise RuntimeError("queue boom")
            self.queue_calls.append(a)
        S.get_or_fetch_channel = get_chan
        S.send_to_queue = send_to_queue
        S.build_payment_confirmed_embed = lambda *a, **k: {"embed": True}
        self.cog = S.ShopOrdersCog(self.bot)
    async def boot(self):
        class G: id = 1
        class B: guilds = [G()]
        await D.init_data_cache(B())
    def add_order(self, code="DH123456", amount=50000):
        C.save_pending_shop_order(code, guild_id=1, channel_id=99, seller_id=30, buyer_id=20,
                                  amount=amount, account_number="0123",
                                  created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())

def payload(**kw):
    p = {"id": 7001, "transferType": "in", "transferAmount": 50000, "accountNumber": "0123",
         "code": "DH123456", "content": "DH123456 thanh toan"}
    p.update(kw); return p

class SepayTests(unittest.TestCase):
    def run_async(self, coro): return asyncio.run(coro)

    def test_happy_path(self):
        async def go():
            e = Env(); await e.boot(); e.add_order()
            await e.cog._handle_sepay_webhook(payload())
            self.assertEqual(len(e.chan.sent), 1); self.assertEqual(len(e.queue_calls), 1)
            self.assertEqual(e.admin.dms, [])
            self.assertIsNone(C.get_pending_shop_order("DH123456"))
            self.assertTrue(C.is_webhook_id_processed(7001))
            await e.cog._handle_sepay_webhook(payload())     # trùng id → bỏ qua
            self.assertEqual(len(e.chan.sent), 1)
        self.run_async(go())

    def test_channel_deleted_alerts_admin_instead_of_silent_loss(self):
        async def go():
            e = Env(chan_ok=False); await e.boot(); e.add_order()
            await e.cog._handle_sepay_webhook(payload())
            self.assertEqual(len(e.admin.dms), 1)
            self.assertIn("DH123456", e.admin.dms[0]); self.assertIn("ĐÃ THANH TOÁN", e.admin.dms[0])
        self.run_async(go())

    def test_buyer_left_guild_still_confirmed_via_fetch_user(self):
        async def go():
            e = Env(buyer_in_guild=False); await e.boot(); e.add_order()
            await e.cog._handle_sepay_webhook(payload())
            self.assertEqual(len(e.chan.sent), 1); self.assertEqual(e.admin.dms, [])
        self.run_async(go())

    def test_underpayment_alerts_and_keeps_order(self):
        async def go():
            e = Env(); await e.boot(); e.add_order()
            await e.cog._handle_sepay_webhook(payload(transferAmount=49000))
            self.assertEqual(len(e.admin.dms), 1); self.assertIn("LỆCH", e.admin.dms[0])
            self.assertIsNotNone(C.get_pending_shop_order("DH123456"))
            self.assertEqual(e.chan.sent, [])
        self.run_async(go())

    def test_queue_failure_is_reported(self):
        async def go():
            e = Env(queue_raises=True); await e.boot(); e.add_order()
            await e.cog._handle_sepay_webhook(payload())
            self.assertEqual(len(e.chan.sent), 1)
            self.assertEqual(len(e.admin.dms), 1); self.assertIn("hàng đợi", e.admin.dms[0])
        self.run_async(go())

    def test_unknown_code_alerts_but_plain_transfer_does_not(self):
        async def go():
            e = Env(); await e.boot()
            await e.cog._handle_sepay_webhook(payload(id=1, code="DH999999", content="DH999999"))
            self.assertEqual(len(e.admin.dms), 1)
            await e.cog._handle_sepay_webhook(payload(id=2, code="", content="chuyen tien an trua"))
            self.assertEqual(len(e.admin.dms), 1)
        self.run_async(go())

    def test_unexpected_exception_is_reported(self):
        async def go():
            e = Env(); await e.boot(); e.add_order()
            async def boom(bot, cid): raise RuntimeError("discord down")
            S.get_or_fetch_channel = boom
            await e.cog._handle_sepay_webhook(payload())
            self.assertEqual(len(e.admin.dms), 1); self.assertIn("discord down", e.admin.dms[0])
        self.run_async(go())

    def test_pending_orders_expire(self):
        async def go():
            e = Env(); await e.boot()
            old = (__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                   - __import__("datetime").timedelta(days=30)).isoformat()
            C.save_pending_shop_order("DH111111", guild_id=1, channel_id=1, seller_id=1, buyer_id=1, amount=1, created_at=old)
            e.add_order("DH222222")
            self.assertIsNone(C.get_pending_shop_order("DH111111"))
            self.assertIsNotNone(C.get_pending_shop_order("DH222222"))
        self.run_async(go())

if __name__ == "__main__":
    unittest.main(verbosity=2)
