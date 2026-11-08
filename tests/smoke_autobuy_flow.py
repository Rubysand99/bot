"""
Smoke test LUỒNG AutoBuy với discord.py THẬT (không kết nối Discord, không cần Mongo).
KHÔNG tên test_*.py nên `unittest discover` không chạy — các test khác dùng stubs_discord thay thế module discord,
còn file này cần discord.py thật (isinstance với discord.Member/CategoryChannel...). Chạy riêng:
    python3 tests/smoke_autobuy_flow.py
"""
import asyncio, os, sys, unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("MONGO_URI", "mongodb://localhost:1/none")
os.environ.setdefault("ADMIN_RUBY_ID", "1"); os.environ.setdefault("ADMIN_TUYTAM_ID", "2")
import discord
from discord.ext import commands

import core.data as C
import cogs.autobuy as AB


class FlowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {}
        self.pending = {}
        self._patches = [
            patch.object(C, "load_data", lambda: self.data),
            patch.object(C, "save_data", lambda d: self.data.update(d)),
            patch.object(AB, "get_pending_shop_order", lambda ref: self.pending.get(ref)),
            patch.object(AB, "save_pending_shop_order", lambda ref, **f: self.pending.__setitem__(ref, {**f, "ref_code": ref})),
            patch.object(AB, "pop_pending_shop_order", lambda ref: self.pending.pop(ref, None)),
            patch.object(AB, "get_cfg_sold_category", lambda: 0),
            patch.object(AB, "is_active_seller", lambda g, u: True),
            patch.object(AB, "send_log", AsyncMock()),
            patch.object(AB, "render_card", AsyncMock(return_value=None)),
            patch.object(AB, "guild_ui_gate", AsyncMock(return_value=True)),
        ]
        for p in self._patches:
            p.start()
        self.spent, self.sales = [], []
        self._patches += [patch.object(AB, "add_user_spent", lambda u, a: self.spent.append((u, a))),
                          patch.object(AB, "add_seller_sale", lambda u, a, n, c: self.sales.append((u, a, n, c)))]
        for p in self._patches[-2:]:
            p.start()
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = AB.AutoBuyCog(self.bot)
        self.cog._set_card_state = AsyncMock(return_value=None)

        self.buyer = MagicMock(spec=discord.Member); self.buyer.id = 200; self.buyer.mention = "<@200>"
        self.buyer.send = AsyncMock()
        self.seller = MagicMock(spec=discord.Member); self.seller.id = 100; self.seller.mention = "<@100>"
        self.guild = MagicMock(spec=discord.Guild); self.guild.id = 1; self.guild.name = "Shop"; self.guild.icon = None
        self.guild.default_role = MagicMock(); self.guild.me = MagicMock()
        self.guild.get_member = lambda uid: {100: self.seller, 200: self.buyer}.get(uid)
        self.guild.get_channel = lambda cid: None
        self.ticket_ch = MagicMock(spec=discord.TextChannel); self.ticket_ch.id = 555
        self.ticket_ch.send = AsyncMock(); self.ticket_ch.delete = AsyncMock()
        self.guild.create_text_channel = AsyncMock(return_value=self.ticket_ch)
        AB.get_or_fetch_channel = AsyncMock(return_value=self.ticket_ch)
        C.save_ab_account({"username": "Foo", "price": "140k", "status": "AVAILABLE", "seller_id": "100",
                           "password": "pw", "primary_email": "a@b.c", "card_channel_id": "9", "card_message_id": "8"})

    async def asyncTearDown(self):
        for p in reversed(self._patches):
            p.stop()
        for t in self.cog._vouch_tasks.values():
            t.cancel()

    def _interaction(self):
        i = MagicMock(spec=discord.Interaction)
        i.guild, i.user, i.channel_id = self.guild, self.buyer, 9
        i.message = MagicMock(); i.message.id = 8
        i.response = MagicMock(); i.response.defer = AsyncMock(); i.response.send_message = AsyncMock()
        i.response.is_done = lambda: True
        i.followup = MagicMock(); i.followup.send = AsyncMock()
        return i

    async def _buy(self):
        qr = discord.Embed(title="qr")
        with patch("cogs.shop_orders.build_payment_qr_embed", return_value=(qr, "DH123456", None)):
            i = self._interaction()
            await self.cog._on_buy(i, "foo")
        return i

    async def test_buy_creates_ticket_and_pending_order(self):
        i = await self._buy()
        acc = C.get_ab_account("Foo")
        self.assertEqual(acc["status"], "PROCESSING")
        t = C.get_ab_ticket(555)
        self.assertEqual((t["username"], t["buyer_id"], t["ref_code"], t["amount"]), ("Foo", 200, "DH123456", 140000))
        self.assertEqual(self.pending["DH123456"]["autobuy_username"], "Foo")
        self.ticket_ch.send.assert_awaited()
        i.followup.send.assert_awaited()

    async def test_double_buy_rejected(self):
        await self._buy()
        i2 = self._interaction()
        await self.cog._on_buy(i2, "foo")
        self.assertIn("đang có người mở đơn", i2.response.send_message.await_args.args[0])
        self.guild.create_text_channel.assert_awaited_once()

    async def test_buy_failure_rolls_back(self):
        self.guild.create_text_channel = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500, reason="x"), "boom"))
        i = self._interaction()
        with patch("cogs.shop_orders.build_payment_qr_embed", return_value=(None, None, None)):
            await self.cog._on_buy(i, "foo")
        self.assertEqual(C.get_ab_account("Foo")["status"], "AVAILABLE")
        self.assertIsNone(C.get_ab_ticket(555))

    async def test_sepay_paid_delivers_once(self):
        await self._buy()
        order = self.pending.pop("DH123456")
        order.update(guild_id=1, channel_id=555)
        self.bot.get_guild = lambda gid: self.guild
        self.bot.fetch_user = AsyncMock(return_value=self.buyer)
        problems = await self.cog.on_paid(order, 140000, 140000)
        self.assertEqual(problems, [])
        self.assertEqual(C.get_ab_account("Foo")["status"], "SOLD")
        self.assertEqual(self.spent, [(200, 140000)])
        self.assertEqual(self.sales[0][:2], (100, 140000))
        self.buyer.send.assert_awaited_once()
        self.assertIn("Password: pw", self.buyer.send.await_args.kwargs["embed"].description)
        # SePay retry / Confirm tay sau đó → KHÔNG giao lần 2, không cộng tiền lần 2
        self.assertEqual(await self.cog.on_paid(order, 140000, 140000), [])
        self.buyer.send.assert_awaited_once()
        self.assertEqual(len(self.spent), 1)

    async def test_confirm_and_sepay_concurrent_deliver_once(self):
        await self._buy()
        t = C.get_ab_ticket(555)
        r = await asyncio.gather(self.cog.complete_purchase(self.guild, self.ticket_ch, t),
                                 self.cog.complete_purchase(self.guild, self.ticket_ch, t))
        self.assertEqual(sorted(map(tuple, r)), [(), ("__already__",)])
        self.buyer.send.assert_awaited_once()

    async def test_dm_closed_is_reported(self):
        await self._buy()
        self.buyer.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "closed"))
        p = await self.cog.complete_purchase(self.guild, self.ticket_ch, C.get_ab_ticket(555))
        self.assertTrue(any("abresend" in x for x in p))
        self.assertEqual(C.get_ab_account("Foo")["status"], "SOLD")   # vẫn SOLD, staff dùng .abresend gửi lại

    async def test_cancel_restores_and_drops_pending_order(self):
        await self._buy()
        await self.cog.cancel_ticket(555)
        self.assertEqual(C.get_ab_account("Foo")["status"], "AVAILABLE")
        self.assertIsNone(C.get_ab_ticket(555))
        self.assertNotIn("DH123456", self.pending)

    async def test_cancel_after_sold_keeps_sold(self):
        await self._buy()
        await self.cog.complete_purchase(self.guild, self.ticket_ch, C.get_ab_ticket(555))
        await self.cog.cancel_ticket(555)
        self.assertEqual(C.get_ab_account("Foo")["status"], "SOLD")

    async def test_manual_sold_marks_sold(self):
        ch = MagicMock(spec=discord.TextChannel); ch.id = 9
        await self.cog.on_manual_sold(ch)
        self.assertEqual(C.get_ab_account("Foo")["status"], "SOLD")

    async def test_confirm_permission(self):
        await self._buy()
        i = self._interaction(); i.channel_id = 555; i.channel = self.ticket_ch
        i.user = MagicMock(spec=discord.Member); i.user.id = 999     # người lạ
        with patch.object(AB.AutoBuyCog, "_is_staff", staticmethod(lambda m: False)):
            await self.cog._on_confirm(i, "foo")
        self.assertIn("Từ chối", i.response.send_message.await_args.args[0])
        self.assertEqual(C.get_ab_account("Foo")["status"], "PROCESSING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
