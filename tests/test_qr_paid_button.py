"""Nút "Đã nhận tiền" trên embed QR của .done — xác nhận tay thay SePay."""
import asyncio, sys, os, types, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_sepay as TS            # dùng lại Env/User/Chan/Guild đã dựng sẵn (stub discord, FakeCol, cog)
S, C = TS.S, TS.C

class Resp:
    def __init__(self): self.done = False; self.sent = []
    def is_done(self): return self.done
    async def defer(self, **k): self.done = True
    async def send_message(self, text, **k): self.done = True; self.sent.append(text)
class Followup:
    def __init__(self): self.sent = []
    async def send(self, text, **k): self.sent.append(text)
class Msg:
    def __init__(self): self.edits = []; self.embeds = [types.SimpleNamespace(set_footer=lambda **k: None)]
    async def edit(self, **k): self.edits.append(k)
class Inter:
    def __init__(self, user, guild_id=1, channel_id=99):
        self.user = user; self.channel_id = channel_id; self.guild_id = guild_id
        self.guild = types.SimpleNamespace(id=guild_id)
        self.channel = types.SimpleNamespace(mention="#c")
        self.response = Resp(); self.followup = Followup(); self.message = Msg(); self.client = None

class QRPaidButton(unittest.TestCase):
    def setUp(self):
        self.allowed = set()
        S.is_staff_member = lambda m: m.id in self.allowed

    def go(self, coro): return asyncio.run(coro)

    def test_staff_confirms_and_order_is_consumed(self):
        async def run():
            e = TS.Env(); await e.boot(); e.add_order(); self.allowed = {TS.ADMIN}
            i = Inter(e.admin)
            await e.cog._on_qr_paid(i, "DH123456")
            self.assertIsNone(C.get_pending_shop_order("DH123456"))   # SePay về sau sẽ không xử lý lại
            self.assertEqual(len(e.chan.sent), 1)                      # embed xác nhận vào ticket
            self.assertEqual(len(e.queue_calls), 1)                    # vào hàng đợi như SePay
            self.assertEqual(len(i.message.edits), 1)                  # embed QR bị bỏ nút
            self.assertIsNone(i.message.edits[0]["view"])
            self.assertIn("✅", i.followup.sent[0])
        self.go(run())

    def test_order_seller_can_confirm_even_without_staff_role(self):
        async def run():
            e = TS.Env(); await e.boot(); e.add_order()
            i = Inter(e.seller)                                        # seller_id=30 của đơn
            await e.cog._on_qr_paid(i, "DH123456")
            self.assertEqual(len(e.queue_calls), 1)
        self.go(run())

    def test_random_member_is_rejected_and_order_stays(self):
        async def run():
            e = TS.Env(); await e.boot(); e.add_order()
            i = Inter(e.buyer)                                         # khách không được tự bấm
            await e.cog._on_qr_paid(i, "DH123456")
            self.assertIn("Từ chối", i.response.sent[0])
            self.assertIsNotNone(C.get_pending_shop_order("DH123456"))
            self.assertEqual(e.queue_calls, [])
        self.go(run())

    def test_double_click_only_confirms_once(self):
        async def run():
            e = TS.Env(); await e.boot(); e.add_order(); self.allowed = {TS.ADMIN}
            await e.cog._on_qr_paid(Inter(e.admin), "DH123456")
            i2 = Inter(e.admin)
            await e.cog._on_qr_paid(i2, "DH123456")
            self.assertEqual(len(e.queue_calls), 1)
            self.assertIn("đã được xác nhận", i2.response.sent[0])
        self.go(run())

    def test_wrong_channel_is_rejected(self):
        async def run():
            e = TS.Env(); await e.boot(); e.add_order(); self.allowed = {TS.ADMIN}
            i = Inter(e.admin, channel_id=555)
            await e.cog._on_qr_paid(i, "DH123456")
            self.assertEqual(e.queue_calls, [])
            self.assertIsNotNone(C.get_pending_shop_order("DH123456"))
        self.go(run())

    def test_button_helper(self):
        self.assertIsNone(S.qr_paid_view(None))
        self.assertIsNotNone(S.qr_paid_view("DH123456"))

if __name__ == "__main__":
    unittest.main()
