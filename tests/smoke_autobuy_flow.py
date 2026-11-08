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
import cogs.shop_orders as SO


class FlowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {}
        self.gdata = {}                      # "global data" — nơi shop_orders lưu đơn chờ thanh toán (_shop_pending_orders)
        # ⚠️ KHÔNG thay save/get/pop_pending_shop_order và build_payment_qr_embed bằng hàm giả: bug v4.63.0–3
        # ("got multiple values for argument 'ref_code'") lọt qua test vì hàm giả nuốt **fields. Dùng hàm THẬT,
        # chỉ giả lớp lưu trữ + bank của seller.
        self._patches = [
            patch.object(C, "load_data", lambda: self.data),
            patch.object(C, "save_data", lambda d: self.data.update(d)),
            patch.object(C, "load_global_data", lambda: self.gdata),
            patch.object(C, "save_global_data", lambda d: self.gdata.update(d)),
            patch.object(SO, "get_cfg_shop_orders_enabled", lambda: True),
            patch.object(SO, "get_shop_orders_bank", lambda uid: {
                "bank_code": "vietinbank", "bank_name": "Vietinbank", "account_number": "0123456789",
                "account_holder": "NGUYEN VAN A", "template": "compact2"}),
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
        i = self._interaction()
        await self.cog._on_buy(i, "foo")          # build_payment_qr_embed THẬT → lưu đơn chờ thật
        return i

    def _ref(self):
        return C.get_ab_ticket(555)["ref_code"]

    async def test_buy_creates_ticket_and_pending_order(self):
        i = await self._buy()
        acc = C.get_ab_account("Foo")
        self.assertEqual(acc["status"], "PROCESSING")
        t = C.get_ab_ticket(555)
        self.assertEqual((t["username"], t["buyer_id"], t["amount"]), ("Foo", 200, 140000))
        self.assertRegex(t["ref_code"], r"^DH\d{6}$")
        order = C.get_pending_shop_order(t["ref_code"])        # đơn chờ do build_payment_qr_embed lưu + autobuy gắn thêm
        self.assertEqual(order["autobuy_username"], "Foo")
        self.assertEqual((order["guild_id"], order["channel_id"], order["seller_id"], order["buyer_id"], order["amount"]),
                         (1, 555, 100, 200, 140000))        # các field gốc còn nguyên
        self.assertEqual(order["ref_code"], t["ref_code"])
        # QR thật đã gửi vào ticket (embed thứ 2)
        sent = self.ticket_ch.send.await_args.kwargs
        self.assertEqual(len(sent["embeds"]), 2)
        self.assertIn(t["ref_code"], sent["embeds"][1].image.url)
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
        await self.cog._on_buy(i, "foo")
        self.assertEqual(C.get_ab_account("Foo")["status"], "AVAILABLE")
        self.assertIsNone(C.get_ab_ticket(555))
        self.assertEqual(self.gdata.get("_shop_pending_orders", {}), {})

    async def test_failure_after_qr_saved_drops_pending_order(self):
        with patch.object(AB, "save_ab_ticket", side_effect=RuntimeError("db down")):
            i = self._interaction()
            await self.cog._on_buy(i, "foo")
        self.assertEqual(C.get_ab_account("Foo")["status"], "AVAILABLE")
        self.assertEqual(self.gdata.get("_shop_pending_orders", {}), {})   # đơn chờ đã lưu bởi QR phải bị huỷ
        self.ticket_ch.delete.assert_awaited()
        self.assertIn("Không thể tạo ticket", i.followup.send.await_args.args[0])

    async def test_no_bank_falls_back_to_manual(self):
        with patch.object(SO, "get_shop_orders_bank", lambda uid: None):
            i = self._interaction()
            await self.cog._on_buy(i, "foo")
        t = C.get_ab_ticket(555)
        self.assertIsNone(t["ref_code"])
        self.assertEqual(C.get_ab_account("Foo")["status"], "PROCESSING")
        self.assertEqual(len(self.ticket_ch.send.await_args.kwargs["embeds"]), 1)   # không QR, có hướng dẫn thủ công

    async def test_sepay_paid_delivers_once(self):
        await self._buy()
        order = C.pop_pending_shop_order(self._ref())          # giống _process_sepay_payload: pop khi khớp tiền
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

    async def test_shop_orders_hook_routes_autobuy_orders(self):
        """Đường THẬT SePay → ShopOrdersCog._notify_paid_order → AutoBuyCog.on_paid → giao acc."""
        await self._buy()
        ref = self._ref()
        order = C.pop_pending_shop_order(ref)
        fake_self = MagicMock()
        fake_self.bot.get_guild = lambda gid: self.guild
        fake_self.bot.get_cog = lambda name: self.cog if name == "AutoBuyCog" else None
        self.bot.get_guild = lambda gid: self.guild
        self.bot.fetch_user = AsyncMock(return_value=self.buyer)
        problems = await SO.ShopOrdersCog._notify_paid_order(fake_self, order, ref, 140000, 140000)
        self.assertEqual(problems, [])
        self.assertEqual(C.get_ab_account("Foo")["status"], "SOLD")
        self.buyer.send.assert_awaited_once()
        # cog AutoBuy chưa load → báo rõ thay vì rơi vào luồng .done
        order2 = {**order, "ref_code": "DH000000"}
        fake_self.bot.get_cog = lambda name: None
        self.assertTrue(any("AutoBuy chưa load" in p for p in await SO.ShopOrdersCog._notify_paid_order(fake_self, order2, "DH000000", 1, 1)))

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
        self.assertEqual(self.gdata.get("_shop_pending_orders", {}), {})

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
