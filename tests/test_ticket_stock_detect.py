import sys, os, types, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stubs_discord; stubs_discord.install(); stubs_discord.install_optional_stubs()
import conftest_stubs
lg = types.ModuleType("cogs.logger")
async def _send_log(*a, **k): return None
lg.send_log = _send_log
sys.modules["cogs.logger"] = lg
import asyncio
import shared.data as D
import core.data as C
import cogs.ticket as T


class _B:
    class G: id = 1
    guilds = [G()]


def boot(stock_cat=555):
    col = conftest_stubs.FakeCol(); gw = conftest_stubs.FakeCol()
    D._get_mongo = lambda: (col, gw)
    D._data_cache = {}; D._global_cache = None; D._global_loaded = False
    D._persisted_keys.clear(); D._persisted_keys_global.clear(); D._data_cache_ready.clear(); D._LOAD_RETRY_DELAY = 0
    col.docs["guild_1"] = {"_id": "guild_1", "cfg_stock_category": stock_cat}
    col.docs["main"] = {"_id": "main"}
    C.get_db = lambda: {"bot_data": col}
    asyncio.run(D.init_data_cache(_B()))
    D.set_current_guild(1)
    return col


class Ch:
    def __init__(self, id=1, name="chat", topic=None, category_id=None):
        self.id, self.name, self.topic, self.category_id = id, name, topic, category_id


class DetectTests(unittest.TestCase):
    def test_name_with_ticket_is_ticket(self):
        for n in ("ticket-001", "Ticket-abc", "acc-ticket-9", "🎫ticket"):
            self.assertTrue(C.is_ticket_channel(Ch(name=n)), n)

    def test_bot_topic_is_ticket_even_without_name(self):
        self.assertTrue(C.is_ticket_channel(Ch(name="mua-012", topic="123||buy|stockpost|open")))

    def test_plain_channel_not_ticket(self):
        self.assertFalse(C.is_ticket_channel(Ch(name="general")))
        self.assertFalse(C.is_ticket_channel(Ch(name="general", topic="a | b")))  # '|' nhưng không phải topic bot

    def test_stock_category_channel_is_stock(self):
        boot(555); C.set_current_guild(1)
        self.assertTrue(C.is_stock_channel(Ch(name="✅•acc-100k", category_id=555)))
        self.assertFalse(C.is_stock_channel(Ch(name="✅•acc-100k", category_id=777)))

    def test_ticket_inside_stock_category_is_not_stock(self):
        boot(555); C.set_current_guild(1)
        self.assertFalse(C.is_stock_channel(Ch(name="ticket-acc1", category_id=555)))

    def test_no_stock_category_configured(self):
        boot(0); C.set_current_guild(1)
        self.assertFalse(C.is_stock_channel(Ch(name="x", category_id=0)))


class BuyerTests(unittest.TestCase):
    def test_buyer_from_bot_topic(self):
        self.assertEqual(T._ticket_buyer_id(Ch(topic="42||buy|donut|open")), 42)

    def test_name_only_ticket_has_no_buyer(self):
        boot(); C.set_current_guild(1)
        self.assertIsNone(T._ticket_buyer_id(Ch(id=9, name="ticket-x")))
        self.assertEqual(T._topic_parts(Ch(name="ticket-x")), [])

    def test_buyer_from_autobuy_record(self):
        boot(); C.set_current_guild(1)
        C.save_ab_ticket(9, {"buyer_id": 77, "username": "x"})
        self.assertEqual(T._ticket_buyer_id(Ch(id=9, name="ticket-x")), 77)


if __name__ == "__main__":
    unittest.main()
