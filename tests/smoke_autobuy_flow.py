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
import importlib.util
import io
import test_vietqr as TV          # make_vietqr() — dựng payload VietQR hợp lệ để test


class FlowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"shop_orders_banks": {"100": {   # seller 100 đã `.shopbank` — đọc bằng get_shop_orders_bank THẬT
            "bank_code": "vietinbank", "bank_name": "Vietinbank", "account_number": "0123456789",
            "account_holder": "NGUYEN VAN A", "template": "compact2"}}}
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

    # ───────── quyền đăng bán: seller còn hạn / owner + đã .shopbank ─────────
    def _member(self, uid):
        m = MagicMock(spec=discord.Member); m.id = uid; m.name = f"u{uid}"; m.guild = self.guild
        return m

    def _slash(self, member):
        i = self._interaction(); i.user = member
        i.response.send_modal = AsyncMock()
        return i

    async def test_add_acc_denied_for_non_seller(self):
        i = self._slash(self._member(300))
        with patch.object(AB, "is_active_seller", lambda g, u: False):
            await self.cog.add_acc_cmd.callback(self.cog, i)
        self.assertEqual(i.response.send_message.await_args.args[0], AB.MSG_NOT_SELLER)
        i.response.send_modal.assert_not_awaited()

    async def test_add_acc_denied_when_seller_has_no_bank(self):
        i = self._slash(self._member(300))                       # seller còn hạn nhưng chưa .shopbank
        with patch.object(AB, "is_active_seller", lambda g, u: True):
            await self.cog.add_acc_cmd.callback(self.cog, i)
        self.assertIn("shopbank", i.response.send_message.await_args.args[0])
        i.response.send_modal.assert_not_awaited()

    async def test_add_acc_opens_modal_for_seller_with_bank_and_for_owner_with_bank(self):
        self.data["shop_orders_banks"]["300"] = self.data["shop_orders_banks"]["100"]
        self.data["shop_orders_banks"]["1"] = self.data["shop_orders_banks"]["100"]      # id 1 = ADMIN_RUBY_ID (owner)
        for uid, is_seller in ((300, True), (1, False)):
            i = self._slash(self._member(uid))
            with patch.object(AB, "is_active_seller", lambda g, u, v=is_seller: v):
                await self.cog.add_acc_cmd.callback(self.cog, i)
            i.response.send_modal.assert_awaited_once()

    async def test_owner_without_bank_is_denied(self):
        i = self._slash(self._member(1))
        with patch.object(AB, "is_active_seller", lambda g, u: False):
            await self.cog.add_acc_cmd.callback(self.cog, i)
        self.assertIn("shopbank", i.response.send_message.await_args.args[0])
        i.response.send_modal.assert_not_awaited()

    async def test_stock_acc_gates(self):
        stock = lambda i: AB.AutoBuyCog.stock_acc.callback(self.cog, i, username="Foo", price="140k")
        # 1) không phải seller/owner (dù là staff) → từ chối
        i = self._slash(self._member(300))
        with patch.object(AB, "is_active_seller", lambda g, u: False):
            await stock(i)
        self.assertEqual(i.response.send_message.await_args.args[0], AB.MSG_NOT_SELLER)
        # 2) seller của ACC (100) chưa có bank → từ chối, nêu rõ seller nào thiếu
        del self.data["shop_orders_banks"]["100"]
        i = self._slash(self._member(1))
        with patch.object(AB, "is_active_seller", lambda g, u: False):
            await stock(i)
        self.assertIn("<@100>", i.response.send_message.await_args.args[0])
        i.response.defer.assert_not_awaited()
        # 3) đủ điều kiện (owner đăng hộ acc của seller 100 đã có bank) → đi qua cổng, tới bước vẽ card (render_card patched → None)
        self.data["shop_orders_banks"]["100"] = {"bank_code": "vcb", "account_number": "1234567890"}
        i = self._slash(self._member(1))
        with patch.object(AB, "is_active_seller", lambda g, u: False):
            await stock(i)
        i.response.defer.assert_awaited()
        self.assertIn("ảnh card", i.followup.send.await_args.args[0])

    async def test_stock_acc_poster_must_have_bank_for_new_account(self):
        # acc chưa có trong kho → seller = chính người đăng → phải có bank
        i = self._slash(self._member(300))
        with patch.object(AB, "is_active_seller", lambda g, u: True):
            await AB.AutoBuyCog.stock_acc.callback(self.cog, i, username="Brand_New", price="1k")
        self.assertIn("shopbank", i.response.send_message.await_args.args[0])

    async def test_staff_can_still_confirm_but_not_sell(self):
        staff = self._member(777)
        with patch.object(AB.AutoBuyCog, "_is_staff", staticmethod(lambda m: True)):
            self.assertTrue(self.cog._can_handle_ticket(staff, {"seller_id": 100}))
        with patch.object(AB, "is_active_seller", lambda g, u: False):
            self.assertFalse(AB.can_sell_acc(staff))

    # ───────── .shopbank + ảnh QR: đăng ký bank không cần gõ thông tin ─────────
    def _qr_png(self, payload, box=8, border=4):
        import qrcode
        buf = io.BytesIO(); qrcode.make(payload, box_size=box, border=border).convert("RGB").save(buf, "PNG"); return buf.getvalue()

    def _bank_ctx(self, png, args=None, reply=False, uid=1):
        att = MagicMock(spec=discord.Attachment); att.filename = "qr.png"; att.content_type = "image/png"
        att.size = len(png); att.read = AsyncMock(return_value=png)
        ctx = MagicMock(); ctx.author = self._member(uid); ctx.reply = AsyncMock()
        ctx.message.delete = AsyncMock()
        if reply:                                           # lệnh reply vào tin nhắn có ảnh (ảnh không nằm trong tin gõ lệnh)
            ctx.message.attachments = []
            ref_msg = MagicMock(spec=discord.Message); ref_msg.attachments = [att]
            ctx.message.reference.resolved = ref_msg
        else:
            ctx.message.attachments = [att]; ctx.message.reference = None
        return ctx

    async def _shopbank(self, ctx, args=None):
        cog = SO.ShopOrdersCog.__new__(SO.ShopOrdersCog)      # bỏ qua __init__ — lệnh chỉ cần self để gọi _register_bank_from_qr
        await SO.ShopOrdersCog.shopbank_cmd.callback(cog, ctx, args=args)

    @unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("qrcode", "zxingcpp")), "cần qrcode + zxing-cpp")
    async def test_shopbank_from_qr_image_registers_bank_and_qr_uses_it(self):
        ctx = self._bank_ctx(self._qr_png(TV.make_vietqr("970422", "0369999888", name="TRAN THI B")))
        await self._shopbank(ctx)
        bank = C.get_shop_orders_bank(1)
        self.assertEqual((bank["bank_code"], bank["account_number"], bank["account_holder"], bank["bank_name"]),
                         ("970422", "0369999888", "TRAN THI B", "MB Bank"))
        self.assertEqual(bank["template"], "compact2")
        self.assertIn("MB Bank", ctx.reply.await_args.args[0])
        ctx.message.delete.assert_awaited()                     # đã xoá ảnh QR của người gõ
        self.assertTrue(AB.has_bank(1))                         # đủ điều kiện đăng bán Auto Buy
        # QR thanh toán sinh ra dùng đúng BIN + số TK này
        seller = self._member(1); seller.mention = "<@1>"
        embed, ref, warn = SO.build_payment_qr_embed(seller, self.buyer, 50000, 1, 555)
        self.assertIsNone(warn)
        self.assertIn("img.vietqr.io/image/970422-0369999888-compact2.png", embed.image.url)
        self.assertIn("accountName=TRAN%20THI%20B", embed.image.url)

    @unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("qrcode", "zxingcpp")), "cần qrcode + zxing-cpp")
    async def test_shopbank_qr_holder_from_args_and_reply_to_image(self):
        png = self._qr_png(TV.make_vietqr("970436", "1234567890"))          # QR không có tên chủ TK
        ctx = self._bank_ctx(png, reply=True)
        await self._shopbank(ctx, args="Nguyen Van A")
        bank = C.get_shop_orders_bank(1)
        self.assertEqual((bank["bank_code"], bank["account_holder"]), ("970436", "NGUYEN VAN A"))       # chuẩn hoá in hoa
        ctx.message.delete.assert_not_awaited()                 # ảnh của người khác (reply) thì KHÔNG xoá
        # không có tên ở cả QR lẫn lệnh → lưu rỗng + nhắc cách thêm tên
        self.data["shop_orders_banks"].pop("1")
        ctx = self._bank_ctx(png)
        await self._shopbank(ctx)
        self.assertEqual(C.get_shop_orders_bank(1)["account_holder"], "")
        self.assertIn("tên chủ TK", ctx.reply.await_args.args[0])

    @unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("qrcode", "zxingcpp")), "cần qrcode + zxing-cpp")
    async def test_shopbank_qr_rejects_bad_images_without_saving(self):
        from PIL import Image
        blank = io.BytesIO(); Image.new("RGB", (300, 300), (255, 255, 255)).save(blank, "PNG")
        cases = [
            (blank.getvalue(), "Không đọc được"),
            (self._qr_png("https://momo.vn/pay/abc"), "không phải mã **VietQR"),
            (self._qr_png(TV.make_vietqr(service="QRIBFTTC")), "số thẻ"),
            (self._qr_png(TV.make_vietqr()[:-1] + "0" if not TV.make_vietqr().endswith("0") else TV.make_vietqr()[:-1] + "1"), "sai mã kiểm tra"),
        ]
        for png, expect in cases:
            ctx = self._bank_ctx(png)
            await self._shopbank(ctx)
            self.assertIn(expect, ctx.reply.await_args.args[0])
            ctx.message.delete.assert_not_awaited()
        self.assertIsNone(C.get_shop_orders_bank(1))

    async def test_shopbank_typed_args_still_win_over_image(self):
        ctx = self._bank_ctx(b"not-an-image")
        with patch.object(SO, "decode_qr_texts", side_effect=AssertionError("không được đọc ảnh khi đã gõ đủ tham số")):
            await self._shopbank(ctx, args='"Vietinbank" vietinbank 0123456789 "Nguyen Van A"')
        bank = C.get_shop_orders_bank(1)
        self.assertEqual((bank["bank_code"], bank["account_number"]), ("vietinbank", "0123456789"))

    async def test_shopbank_qr_needs_decoder_library_message(self):
        ctx = self._bank_ctx(b"x")
        with patch.object(SO, "decode_qr_texts", side_effect=SO.QRDecoderMissing("thiếu")):
            await self._shopbank(ctx)
        self.assertIn("zxing-cpp", ctx.reply.await_args.args[0])
        self.assertIsNone(C.get_shop_orders_bank(1))

    # ───────── hồi quy từ ảnh chụp: bank lưu SAI (số TK = "ma_bank") → QR không hiện ─────────
    GARBAGE_BANK = {"bank_name": "MB", "bank_code": "mbbank", "account_number": "ma_bank", "account_holder": "80086266778899"}

    async def test_garbage_bank_builds_no_qr_and_explains(self):
        self.data["shop_orders_banks"]["100"] = dict(self.GARBAGE_BANK)
        seller = self._member(100); seller.mention = "<@100>"
        embed, ref, warn = SO.build_payment_qr_embed(seller, self.buyer, 170000, 1, 555)
        self.assertIsNone(embed); self.assertIsNone(ref)
        self.assertIn("sai", warn); self.assertIn("ma_bank", warn); self.assertIn("ảnh QR", warn)
        self.assertEqual(self.gdata.get("_shop_pending_orders", {}), {})       # không để lại đơn chờ cho QR hỏng

    async def test_buy_with_garbage_bank_falls_back_with_clear_reason(self):
        self.data["shop_orders_banks"]["100"] = dict(self.GARBAGE_BANK)
        await self._buy()
        t = C.get_ab_ticket(555)
        self.assertIsNone(t["ref_code"])
        embeds = self.ticket_ch.send.await_args.kwargs["embeds"]
        self.assertEqual(len(embeds), 1)                                        # không còn embed QR hỏng không hiện ảnh
        self.assertIn("sai", embeds[0].description)

    async def test_stock_acc_rejects_garbage_bank_with_reason(self):
        self.data["shop_orders_banks"]["100"] = dict(self.GARBAGE_BANK)
        i = self._slash(self._member(1))
        with patch.object(AB, "is_active_seller", lambda g, u: False):
            await AB.AutoBuyCog.stock_acc.callback(self.cog, i, username="Foo", price="140k")
        msg = i.response.send_message.await_args.args[0]
        self.assertIn("<@100>", msg); self.assertIn("sai", msg)
        i.response.defer.assert_not_awaited()

    async def test_shopbank_typed_garbage_is_rejected_not_saved(self):
        ctx = self._bank_ctx(b"x"); ctx.message.attachments = []; ctx.message.reference = None
        await self._shopbank(ctx, args="MB mbbank ma_bank 80086266778899")        # đúng kiểu gõ trong ảnh chụp
        self.assertIsNone(C.get_shop_orders_bank(1))
        msg = ctx.reply.await_args.args[0]
        self.assertIn("Chưa lưu", msg); self.assertIn("ma_bank", msg); self.assertIn("ảnh QR", msg)

    async def test_shopbank_typed_good_input_is_normalized_and_saved(self):
        ctx = self._bank_ctx(b"x"); ctx.message.attachments = []; ctx.message.reference = None
        await self._shopbank(ctx, args='"MB Bank" MBBANK "0123 456 789" "NGUYEN VAN A"')
        bank = C.get_shop_orders_bank(1)
        self.assertEqual((bank["bank_code"], bank["account_number"], bank["account_holder"]), ("mbbank", "0123456789", "NGUYEN VAN A"))

    async def test_shopbank_view_warns_when_saved_bank_is_broken(self):
        self.data["shop_orders_banks"]["1"] = dict(self.GARBAGE_BANK)
        ctx = self._bank_ctx(b"x"); ctx.message.attachments = []; ctx.message.reference = None
        await self._shopbank(ctx, args=None)
        self.assertIn("bị lỗi", ctx.reply.await_args.args[0])

    # ───────── `.shopbank name <tên>`: QR ngân hàng thường không chứa tên chủ TK ─────────
    def _plain_ctx(self, uid=1):
        ctx = self._bank_ctx(b"x", uid=uid); ctx.message.attachments = []; ctx.message.reference = None
        return ctx

    async def test_shopbank_name_sets_holder_normalized_and_qr_shows_it(self):
        self.data["shop_orders_banks"]["1"] = {"bank_name": "VietinBank", "bank_code": "970415", "account_number": "109885314930",
                                                "account_holder": "", "template": "compact2"}      # đúng như bank đăng ký từ QR VietinBank, chưa có tên
        view = self._plain_ctx(); await self._shopbank(view, args=None)
        self.assertIn("Chưa có **tên chủ TK**", view.reply.await_args.args[0])                   # màn xem gợi ý cách thêm tên
        ctx = self._plain_ctx()
        await self._shopbank(ctx, args="name Nguyễn Tấn Hoàng Quân")
        self.assertEqual(C.get_shop_orders_bank(1)["account_holder"], "NGUYEN TAN HOANG QUAN")
        self.assertIn("NGUYEN TAN HOANG QUAN", ctx.reply.await_args.args[0])
        self.assertEqual(C.get_shop_orders_bank(1)["account_number"], "109885314930")             # field khác giữ nguyên
        seller = self._member(1); seller.mention = "<@1>"
        embed, _ref, _warn = SO.build_payment_qr_embed(seller, self.buyer, 50000, 1, 555)
        self.assertIn("accountName=NGUYEN%20TAN%20HOANG%20QUAN", embed.image.url)
        self.assertIn("970415-109885314930", embed.image.url)
        view2 = self._plain_ctx(); await self._shopbank(view2, args=None)
        self.assertNotIn("Chưa có **tên chủ TK**", view2.reply.await_args.args[0])

    async def test_shopbank_name_requires_valid_bank_and_valid_name(self):
        ctx = self._plain_ctx(); await self._shopbank(ctx, args="name NGUYEN VAN A")                # chưa có bank
        self.assertIn("chưa có bank", ctx.reply.await_args.args[0]); self.assertIsNone(C.get_shop_orders_bank(1))
        self.data["shop_orders_banks"]["1"] = dict(self.GARBAGE_BANK)                               # bank đang sai
        ctx = self._plain_ctx(); await self._shopbank(ctx, args="name NGUYEN VAN A")
        self.assertIn("chưa có bank", ctx.reply.await_args.args[0]); self.assertEqual(C.get_shop_orders_bank(1)["account_holder"], "80086266778899")
        self.data["shop_orders_banks"]["1"] = {"bank_code": "970415", "account_number": "109885314930", "account_holder": ""}
        for bad in ("name 0123456789", "name @@@", "name x"):
            ctx = self._plain_ctx(); await self._shopbank(ctx, args=bad)
            self.assertIn("không hợp lệ", ctx.reply.await_args.args[0], bad)
        self.assertEqual(C.get_shop_orders_bank(1)["account_holder"], "")

    @unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("qrcode", "zxingcpp")), "cần qrcode + zxing-cpp")
    async def test_shopbank_qr_with_name_keyword_sets_holder(self):
        ctx = self._bank_ctx(self._qr_png(TV.make_vietqr("970415", "109885314930")))
        await self._shopbank(ctx, args="name Nguyễn Tấn Hoàng Quân")        # ảnh + "name <tên>" → đăng ký + đặt tên một lượt
        bank = C.get_shop_orders_bank(1)
        self.assertEqual((bank["bank_code"], bank["account_number"], bank["account_holder"]), ("970415", "109885314930", "NGUYEN TAN HOANG QUAN"))

    # ───────── `.setbank` (admin gán bank cho seller) ─────────
    SELLER_A, SELLER_B = 123456789012345678, 876543210987654321

    def _admin_ctx(self, uid=1):
        ctx = self._bank_ctx(b"x", uid=uid); ctx.message.attachments = []; ctx.message.reference = None
        ctx.guild = self.guild
        members = {}
        for mid, name in ((self.SELLER_A, "SellerA"), (self.SELLER_B, "SellerB")):
            m = MagicMock(spec=discord.Member); m.id = mid; m.name = name; m.display_name = name; m.mention = f"<@{mid}>"
            members[mid] = m
        self.guild.get_member = lambda uid_, _m=members: _m.get(uid_)
        self.guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404, reason="x"), "unknown"))
        return ctx, members

    async def _setbank(self, ctx, args):
        cog = SO.ShopOrdersCog.__new__(SO.ShopOrdersCog)
        await SO.ShopOrdersCog.setbank_cmd.callback(cog, ctx, args=args)

    async def test_setbank_assigns_bank_to_the_right_id_and_qr_uses_it(self):
        ctx, members = self._admin_ctx()
        await self._setbank(ctx, f"{self.SELLER_A} 970422 80086266778899 Trương Nguyễn Thanh Hùng")
        bank = C.get_shop_orders_bank(self.SELLER_A)
        self.assertEqual((bank["bank_name"], bank["bank_code"], bank["account_number"], bank["account_holder"], bank["source"]),
                         ("MB Bank", "970422", "80086266778899", "TRUONG NGUYEN THANH HUNG", "admin"))
        self.assertIsNone(C.get_shop_orders_bank(self.SELLER_B))                       # chỉ đúng ID được gán
        self.assertIn("✅", ctx.reply.await_args.args[0]); self.assertIn("chưa có gói seller", ctx.reply.await_args.args[0])
        self.assertTrue(AB.has_bank(self.SELLER_A))
        embed, _r, warn = SO.build_payment_qr_embed(members[self.SELLER_A], self.buyer, 170000, 1, 555)
        self.assertIsNone(warn)
        self.assertIn("970422-80086266778899", embed.image.url)
        self.assertIn("accountName=TRUONG%20NGUYEN%20THANH%20HUNG", embed.image.url)

    async def test_setbank_accepts_mention_multiline_and_reports_each_line(self):
        ctx, members = self._admin_ctx()
        await self._setbank(ctx, f"```\n<@{self.SELLER_A}> 970415 109885314930 NGUYEN TAN HOANG QUAN\n"
                                 f"<@!{self.SELLER_B}> mbbank 0369999888\n"
                                 f"999999999999999999 970422 0123456789 NGUOI LA\n"
                                 f"{self.SELLER_A} 970422 ma_bank X\n```")
        msg = ctx.reply.await_args.args[0]
        self.assertIn("2/4", msg)
        self.assertEqual(C.get_shop_orders_bank(self.SELLER_A)["account_number"], "109885314930")
        self.assertEqual(C.get_shop_orders_bank(self.SELLER_B)["bank_code"], "mbbank")
        self.assertIn("chưa có tên", msg)                                                # dòng B không có tên chủ TK
        self.assertIn("Dòng 3", msg); self.assertIn("không tìm thấy thành viên", msg)    # ID không có trong server
        self.assertIn("Dòng 4", msg); self.assertIn("không hợp lệ", msg)                 # chữ mẫu ma_bank bị chặn → KHÔNG ghi đè bank đúng ở dòng 1
        self.assertEqual(C.get_shop_orders_bank(self.SELLER_A)["bank_code"], "970415")

    async def test_setbank_overwrite_note_bad_input_and_usage(self):
        ctx, _m = self._admin_ctx()
        await self._setbank(ctx, f"{self.SELLER_A} 970422 111111111111")
        await self._setbank(ctx, f"{self.SELLER_A} 970422 222222222222 TEN MOI")
        self.assertIn("đã thay bank cũ …1111", ctx.reply.await_args.args[0])
        self.assertEqual(C.get_shop_orders_bank(self.SELLER_A)["account_holder"], "TEN MOI")
        await self._setbank(ctx, "abc 970422 111111111111"); self.assertIn("không phải @mention/ID", ctx.reply.await_args.args[0])
        await self._setbank(ctx, f"{self.SELLER_A} 970422"); self.assertIn("thiếu thông tin", ctx.reply.await_args.args[0])
        await self._setbank(ctx, None); self.assertIn("admin gán bank cho seller", ctx.reply.await_args.args[0])
        await self._setbank(ctx, "\n".join([f"{self.SELLER_A} 970422 111111111111"] * 26)); self.assertIn("Tối đa 25", ctx.reply.await_args.args[0])

    async def test_setbank_denied_for_non_admin(self):
        ctx, _m = self._admin_ctx(uid=300)
        await self._setbank(ctx, f"{self.SELLER_A} 970422 111111111111")
        self.assertIn("Chỉ admin", ctx.reply.await_args.args[0])
        self.assertIsNone(C.get_shop_orders_bank(self.SELLER_A))

    @unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("qrcode", "zxingcpp")), "cần qrcode + zxing-cpp")
    async def test_shopbank_alias_qr_explains_and_points_to_setbank(self):
        ctx = self._bank_ctx(self._qr_png(TV.make_vietqr("970422", "VQRQAXYZ1234")))      # QR kiểu MB: mã định danh thay số TK
        await self._shopbank(ctx)
        msg = ctx.reply.await_args.args[0]
        self.assertIn("mã định danh", msg); self.assertIn("970422", msg); self.assertIn(".setbank", msg); self.assertIn("MB Bank", msg)
        self.assertIsNone(C.get_shop_orders_bank(1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
