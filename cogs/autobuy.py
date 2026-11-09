"""
cogs/autobuy.py — Auto Buy: bán tài khoản Minecraft tự động qua ticket + VietQR/SePay.

Port từ bot autobuy (Node.js "Drew Store") sang cog Python, dùng lại hạ tầng có sẵn của bot:
  • QR/thanh toán: dùng bank của SELLER đăng ký bằng `.shopbank` + webhook SePay (shop_orders.py) →
    khi tiền về, đơn TỰ GIAO (DM thông tin đăng nhập). Seller/staff vẫn bấm "Confirm" tay được
    (trường hợp chưa bật Shop Orders hoặc seller chưa `.shopbank`, như bản Node).
  • Kênh stock / sold: dùng CHUNG cfg_stock_category / cfg_sold_category của `.st`.
  • Quyền: nạp kho/đăng bán (/add_acc, /stock acc) CHỈ seller còn hạn (`.seller list`) hoặc owner/admin VÀ phải đã
    `.shopbank` (can_sell_acc + has_bank). Confirm/Close ticket, /restock, .abresend: can_manage_listing() (staff/seller
    hoặc role "🛒 Quản lý Auto Buy" gán trong `.st`).
  • Doanh số: cộng add_user_spent (BXH `.bxh`) + add_seller_sale (thống kê seller) khi giao thành công.

Luồng: staff /add_acc (nạp thông tin đăng nhập vào kho) → /stock acc (đăng card ảnh + nút BUY) →
khách bấm BUY → ticket riêng + QR → thanh toán → giao DM + card thành SOLD + kênh chuyển sang sold + bill.

⚠️ Các nút (BUY/Confirm/Close) KHÔNG dùng discord.ui.View đăng ký (custom_id chứa username, mỗi card 1 id)
mà xử lý trong on_interaction theo prefix custom_id → sống qua restart, không cần resume. View gắn vào tin
nhắn chỉ để HIỆN nút (_InertView.interaction_check luôn False để không xử lý trùng).
Giữ nguyên custom_id cũ của bot Node (buy_acc_<user>, guide_how_to_buy) → card cũ đăng bởi bot Node vẫn
mua được sau khi chuyển sang bot này (nhập kho cũ bằng /ab_import).

Load bởi bot.py (pilot) VÀ bot_shop.py. Hook: shop_orders._notify_paid_order → on_paid(); shop_admin.handle_sold
→ on_manual_sold() (gõ "sold" tay trong kênh stock thì tài khoản cũng thành SOLD).
"""

import asyncio
import io
import json
import logging
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.listings import can_manage_listing
from cogs.logger import send_log
from cogs.seller import is_active_seller
from core.autobuy_card import render_card
from core.vietqr import bank_problem
from core.autobuy_logic import (
    CUSTOM_EMOJI_RE, ST_AVAILABLE, ST_PROCESSING, ST_SOLD,
    convert_node_account, count_capes, fmt_vnd, format_price_display, make_stock_channel_name,
    parse_account_form, parse_amount, swap_status_icon,
)
from core.data import (
    add_seller_sale, add_user_spent, claim_ab_account, delete_ab_ticket, find_ab_account_by_channel,
    get_ab_account, get_ab_cfg, get_ab_ticket, get_all_ab_accounts, get_cfg_shop_orders_enabled, get_cfg_sold_category,
    get_cfg_stock_category, get_or_fetch_channel, get_pending_shop_order, get_shop_orders_bank, is_admin,
    pop_pending_shop_order, save_ab_account, save_ab_ticket, save_pending_shop_order, set_ab_cfg,
    set_current_guild, update_ab_account,
)
from shared.data import GuildContextModal, guild_ui_gate

log = logging.getLogger(__name__)

COLOR_MAIN = 0x00FFAA
COLOR_OK = 0x00FF00
COLOR_DARK = 0x2B2D31

# custom_id — bản mới + bản cũ của bot Node (card cũ vẫn dùng được)
ID_BUY = ("ab_buy:", "buy_acc_")
ID_GUIDE = ("ab_guide", "guide_how_to_buy")
ID_CONFIRM = "ab_confirm:"
ID_CLOSE = "ab_close:"

VOUCH_REMIND_EVERY = 5 * 60
VOUCH_REMIND_MAX = 24            # tối đa 24 lần (2 giờ) rồi thôi — bản Node nhắc vô hạn tới khi kênh bị xoá

# cfg key (lệnh .abset) → (key lưu, mô tả, kiểu)
CFG_KEYS = {
    "ticket":  ("ticket_category_id", "Danh mục chứa kênh ticket mua hàng", "category"),
    "bill":    ("bill_channel_id",    "Kênh gửi bill khi bán xong", "channel"),
    "youtube": ("kenh_youtube",       "Kênh hướng dẫn (YouTube) hiện trong DM giao hàng", "channel"),
    "2fa":     ("kenh_2fa",           "Kênh hướng dẫn 2FA hiện trong DM giao hàng", "channel"),
    "lock":    ("kenh_lock",          "Kênh hướng dẫn lock acc hiện trong DM giao hàng", "channel"),
    "vouch":   ("kenh_vouch",         "Kênh vouch/legit nhắc khách", "channel"),
    "qr":      ("fallback_qr",        "URL ảnh QR dự phòng khi seller chưa .shopbank", "url"),
}


class _InertView(discord.ui.View):
    """Chỉ để HIỆN nút — mọi lượt bấm xử lý ở AutoBuyCog.on_interaction, view này không tự xử lý gì."""
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return False


def _btn(label, style, custom_id, emoji=None, disabled=False) -> discord.ui.Button:
    return discord.ui.Button(label=label, style=style, custom_id=custom_id, emoji=emoji, disabled=disabled)


def card_view(state: str, username: str) -> discord.ui.View:
    """Hàng nút dưới card: [BUY|Đang giao dịch|SOLD] + [Cách mua]."""
    v = _InertView()
    key = username.lower()
    if state == ST_SOLD:
        v.add_item(_btn("         SOLD         ", discord.ButtonStyle.secondary, f"ab_sold:{key}", "🔒", True))
    elif state == ST_PROCESSING:
        v.add_item(_btn("    Đang Giao Dịch    ", discord.ButtonStyle.secondary, f"ab_pending:{key}", "⏳", True))
    else:
        v.add_item(_btn("         BUY         ", discord.ButtonStyle.success, f"{ID_BUY[0]}{key}", "🛒"))
    v.add_item(_btn("      Cách mua      ", discord.ButtonStyle.secondary, ID_GUIDE[0], "ℹ️"))
    return v


def ticket_view(username: str) -> discord.ui.View:
    v = _InertView()
    key = username.lower()
    v.add_item(_btn("Confirm", discord.ButtonStyle.success, f"{ID_CONFIRM}{key}", "✅"))
    v.add_item(_btn("Close", discord.ButtonStyle.danger, f"{ID_CLOSE}{key}", "🔒"))
    return v


def _fmt_ref(val, placeholder: str) -> str:
    if not val or not str(val).strip():
        return placeholder
    s = str(val).strip()
    return f"<#{s}>" if s.isdigit() else s


def can_sell_acc(member) -> bool:
    """Chỉ SELLER (gói `.seller` còn hạn — xem `.seller list`) hoặc OWNER/admin mới được nạp kho + đăng bán acc.
    (Confirm/Close ticket, /restock, .abresend vẫn mở cho cả staff — xem _is_staff.)"""
    return isinstance(member, discord.Member) and (is_admin(member, quiet=True) or is_active_seller(member.guild.id, member.id))


def bank_issue(user_id) -> str | None:
    """None = bank dùng được. Ngược lại là lý do: chưa đăng ký, hoặc đã lưu nhưng SAI (số TK không phải số, nhập lộn ô...)."""
    try:
        bank = get_shop_orders_bank(int(user_id)) if user_id else None
    except (TypeError, ValueError):
        return "chưa đăng ký ngân hàng"
    return bank_problem(bank)


def has_bank(user_id) -> bool:
    """User đã `.shopbank` và dữ liệu DÙNG ĐƯỢC (không chỉ là có mã + số — bank lưu số TK `ma_bank` từng lọt qua kiểm tra cũ)."""
    return bank_issue(user_id) is None


MSG_NOT_SELLER = ("❌ Chỉ **seller** (đang có gói seller còn hạn — xem `.seller list`) hoặc **owner/admin** "
                  "mới được nạp kho và đăng bán tài khoản.")
SHOPBANK_HINT = '`.shopbank` kèm **ảnh QR nhận tiền** của ngân hàng (bot tự đọc), hoặc nhờ **admin gán giúp** bằng `.setbank`'


def msg_no_bank(owner_id, me_id) -> str:
    issue = bank_issue(owner_id)
    wrong = issue is not None and issue != "chưa đăng ký ngân hàng"       # đã lưu nhưng dữ liệu sai
    if str(owner_id) == str(me_id):
        if wrong:
            return (f"❌ Bank bạn đang lưu bị **sai** — {issue}. Sửa lại: {SHOPBANK_HINT} "
                    "(gõ `.shopbank` không kèm gì để xem đang lưu gì).")
        return (f"❌ Bạn chưa đăng ký **tài khoản ngân hàng** nhận tiền. Gõ {SHOPBANK_HINT} rồi thử lại "
                "(tiền khách chuyển khoản sẽ vào đúng bank này).")
    if wrong:
        return f"❌ Bank của seller tài khoản này (<@{owner_id}>) đang lưu **sai** — {issue}. Họ cần đăng ký lại: {SHOPBANK_HINT}."
    return (f"❌ Seller của tài khoản này (<@{owner_id}>) chưa đăng ký **ngân hàng** nhận tiền — "
            f"họ cần gõ {SHOPBANK_HINT} trước khi đăng bán.")


class _AddAccModal(GuildContextModal, title="Nhập Tài Khoản Minecraft"):
    account_data = discord.ui.TextInput(
        label="Nhập đúng form thông tin tài khoản:",
        style=discord.TextStyle.paragraph,
        placeholder="Username: \nCapes: \nRecovery Code: \nPrimary Email: \nSecurity Email: \nSecret Key: \nPassword:",
        required=True, max_length=2000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not can_sell_acc(interaction.user):
            return await interaction.response.send_message(MSG_NOT_SELLER, ephemeral=True)
        if not has_bank(interaction.user.id):
            return await interaction.response.send_message(msg_no_bank(interaction.user.id, interaction.user.id), ephemeral=True)
        parsed = parse_account_form(str(self.account_data.value))
        if not parsed:
            return await interaction.response.send_message(
                "❌ **Lỗi:** Không tìm thấy dòng `Username: <tên>` trong nội dung dán vào!", ephemeral=True)

        old = get_ab_account(parsed["username"])
        doc = {**parsed, "seller_id": interaction.user.id, "status": ST_AVAILABLE}
        if old and old.get("status") != ST_SOLD:
            # nạp lại thông tin cho acc đang bán/đang giao dịch → giữ nguyên card + giá + trạng thái, chỉ đổi bí mật
            for k in ("price", "rank", "statshpx", "statsdonut", "card_channel_id", "card_message_id", "status", "seller_id"):
                if old.get(k) not in (None, ""):
                    doc[k] = old[k]
            if not doc.get("capes") and old.get("capes"):
                doc["capes"] = old["capes"]
        save_ab_account(doc)
        await interaction.response.send_message(
            f"✅ **Đã thêm tài khoản vào kho!**\n"
            f"👤 **Username:** `{parsed['username']}`\n"
            f"✨ **Capes:** {parsed['capes'] or '(Không có)'}\n"
            f"🔒 **Trạng thái:** {doc['status']}\n"
            f"*Dùng `/stock acc username:{parsed['username']} price:<giá>` để đăng card bán.*",
            ephemeral=True)


def store_info(guild: discord.Guild) -> dict:
    """Tên + icon của SERVER → vẽ lên header card (thay cho logo/chữ "Drew Store" của bản Node)."""
    icon = ""
    if guild.icon:
        try:
            icon = str(guild.icon.replace(size=128, static_format="png").url)
        except Exception:
            icon = str(guild.icon.url)
    return {"store_name": guild.name, "store_icon_url": icon}


class AutoBuyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._vouch_tasks: dict[int, asyncio.Task] = {}

    async def cog_unload(self):
        for t in self._vouch_tasks.values():
            t.cancel()
        self._vouch_tasks.clear()

    # ═════════════ helpers ═════════════
    @staticmethod
    def _is_staff(member) -> bool:
        return isinstance(member, discord.Member) and can_manage_listing(member)

    def _can_handle_ticket(self, member, ticket: dict) -> bool:
        return self._is_staff(member) or str(member.id) == str(ticket.get("seller_id"))

    async def _resolve_user(self, guild: discord.Guild, user_id):
        if not user_id:
            return None
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return None
        m = guild.get_member(uid)
        if m:
            return m
        try:
            return await guild.fetch_member(uid)
        except (discord.NotFound, discord.HTTPException):
            pass
        try:
            return await self.bot.fetch_user(uid)
        except (discord.NotFound, discord.HTTPException):
            return None

    async def _rename_if_icon(self, channel, state: str) -> None:
        """Đổi emoji trạng thái ✅/⌛/❌ ở đầu tên kênh — CHỈ khi kênh đang có sẵn emoji đó (card đăng vào kênh thường thì giữ nguyên)."""
        try:
            if channel and re.match(r"^[✅⌛❌]", channel.name or ""):
                new = swap_status_icon(channel.name, state)
                if new != channel.name:
                    await channel.edit(name=new, reason="AutoBuy: đổi trạng thái")
        except Exception as e:
            log.warning(f"[AUTOBUY] không đổi được tên kênh: {e}")

    async def _set_card_state(self, channel_id, message_id, username: str, state: str,
                              rename: bool = True) -> discord.abc.GuildChannel | None:
        """Sửa nút trên card (+ đổi emoji tên kênh nếu rename). Trả về kênh card (hoặc None)."""
        if not channel_id:
            return None
        ch = await get_or_fetch_channel(self.bot, int(channel_id))
        if not ch:
            return None
        if message_id:
            try:
                msg = await ch.fetch_message(int(message_id))
                await msg.edit(view=card_view(state, username))
            except Exception as e:
                log.warning(f"[AUTOBUY] không sửa được nút card {username}: {e}")
        if rename:
            await self._rename_if_icon(ch, state)
        return ch

    def _ticket_overwrites(self, guild: discord.Guild, buyer, seller) -> dict:
        rw = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True)
        ow: dict = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True,
                                                  attach_files=True, read_message_history=True, manage_channels=True),
            buyer: rw,
        }
        if seller is not None and isinstance(seller, discord.Member):
            ow[seller] = rw
        # staff được gán vai trò "🤖 Auto Buy" trong `.st` (role hoặc user)
        try:
            from core.data import get_ticket_role_ids
            from shared.data import is_user_id
            for rid in get_ticket_role_ids("listing_manage"):
                target = guild.get_member(rid) if is_user_id(rid) else guild.get_role(rid)
                if target:
                    ow[target] = rw
        except Exception as e:
            log.warning(f"[AUTOBUY] không gắn được quyền staff vào ticket: {e}")
        return ow

    # ═════════════ interaction router ═════════════
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        cid = str((interaction.data or {}).get("custom_id") or "")
        handler = None
        arg = None
        if cid in ID_GUIDE:
            handler = self._on_guide
        elif cid.startswith(ID_BUY):
            handler, arg = self._on_buy, cid.split(":", 1)[1] if cid.startswith("ab_buy:") else cid[len("buy_acc_"):]
        elif cid.startswith(ID_CONFIRM):
            handler, arg = self._on_confirm, cid[len(ID_CONFIRM):]
        elif cid.startswith(ID_CLOSE):
            handler, arg = self._on_close, cid[len(ID_CLOSE):]
        if handler is None:
            return
        if not interaction.guild:
            return
        if not await guild_ui_gate(interaction, "view", self):
            return
        try:
            if arg is None:
                await handler(interaction)
            else:
                await handler(interaction, arg.lower())
        except Exception:
            log.exception(f"[AUTOBUY] lỗi xử lý nút {cid}")
            try:
                msg = "❌ Có lỗi xảy ra, vui lòng thử lại hoặc báo staff."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                pass

    async def _on_guide(self, interaction: discord.Interaction):
        name = interaction.guild.name
        e = discord.Embed(color=COLOR_MAIN, description=(
            f"# Cách mua tài khoản tại {name}  ✅\n"
            "> Nếu bạn thấy tài khoản ưng ý hãy bấm **BUY** 🛒\n"
            "> Bot sẽ tự động tạo ticket giao dịch riêng cho bạn và Seller\n"
            "> Sau đó chuyển khoản theo mã QR và nội dung chỉ định\n"
            "> Khi thanh toán hoàn tất, bot gửi thông tin tài khoản qua tin nhắn riêng (DM)\n"
            "> ⚠️ **Lưu ý:** Hãy bật \"Cho phép tin nhắn trực tiếp từ thành viên máy chủ\"!"))
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ═════════════ KHÁCH BẤM BUY ═════════════
    async def _on_buy(self, interaction: discord.Interaction, username: str):
        guild, buyer = interaction.guild, interaction.user
        result, acc = claim_ab_account(username)      # đồng bộ: chiếm acc trước khi await bất cứ gì
        if result == "missing":
            return await interaction.response.send_message("❌ Không tìm thấy thông tin tài khoản này trong hệ thống!", ephemeral=True)
        if result == "sold":
            return await interaction.response.send_message("❌ Tài khoản này đã được bán!", ephemeral=True)
        if result == "processing":
            return await interaction.response.send_message("⏳ Tài khoản này hiện đang có người mở đơn giao dịch!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        channel = None
        ref_code = None
        try:
            seller_id = acc.get("seller_id")
            seller = await self._resolve_user(guild, seller_id)

            parent = None
            cat_id = get_ab_cfg("ticket_category_id")
            if cat_id:
                c = guild.get_channel(int(cat_id))
                if isinstance(c, discord.CategoryChannel):
                    parent = c
            channel = await guild.create_text_channel(
                name=f"ticket-{acc['username'].lower()}", category=parent,
                overwrites=self._ticket_overwrites(guild, buyer, seller),
                reason=f"AutoBuy: {buyer} mua {acc['username']}")

            card_channel_id = interaction.channel_id or acc.get("card_channel_id")
            card_message_id = interaction.message.id if interaction.message else acc.get("card_message_id")
            amount = parse_amount(acc.get("price"))
            display_price = fmt_vnd(amount) if amount > 0 else (acc.get("price") or "Thoả thuận")

            # ── QR: dùng lại hạ tầng Shop Orders (bank của seller + mã DHxxxxxx + webhook SePay) ──
            qr_embed = ref_code = warn = None
            if amount > 0 and seller is not None:
                from cogs.shop_orders import build_payment_qr_embed
                qr_embed, ref_code, warn = build_payment_qr_embed(seller, buyer, amount, guild.id, channel.id)
                if ref_code:
                    # save_pending_shop_order(ref_code, **fields) tự thêm "ref_code" vào doc → phải bỏ khỏi fields,
                    # nếu không "got multiple values for argument 'ref_code'" (lỗi ở v4.63.0–v4.63.3).
                    order = {k: v for k, v in (get_pending_shop_order(ref_code) or {}).items() if k != "ref_code"}
                    save_pending_shop_order(ref_code, **order, autobuy_username=acc["username"])

            save_ab_ticket(channel.id, {
                "username": acc["username"], "buyer_id": buyer.id, "seller_id": seller_id,
                "price": acc.get("price"), "amount": amount, "ref_code": ref_code,
                "card_channel_id": card_channel_id, "card_message_id": card_message_id,
            })
            update_ab_account(acc["username"], card_channel_id=card_channel_id, card_message_id=card_message_id)
        except Exception as e:
            # hoàn tác: trả acc về AVAILABLE, dọn kênh dở
            update_ab_account(acc["username"], status=ST_AVAILABLE)
            if ref_code:
                pop_pending_shop_order(ref_code)      # QR đã lưu đơn chờ → huỷ, tránh đơn mồ côi trỏ vào kênh đã xoá
            if channel:
                delete_ab_ticket(channel.id)
                try:
                    await channel.delete(reason="AutoBuy: tạo ticket lỗi")
                except Exception:
                    pass
            log.exception("[AUTOBUY] tạo ticket lỗi")
            return await interaction.followup.send(f"❌ **Không thể tạo ticket!** Lỗi: `{e}`", ephemeral=True)

        # card → "Đang giao dịch"
        await self._set_card_state(card_channel_id, card_message_id, acc["username"], ST_PROCESSING)

        seller_mention = f"<@{seller_id}>" if seller_id else "Seller"
        info = [f"💰 **Số tiền:** `{display_price}`"]
        embeds = []
        if qr_embed is not None:
            info.append("*Quét mã QR bên dưới và ghi ĐÚNG nội dung chuyển khoản — hệ thống tự nhận tiền và giao tài khoản qua DM.*")
        else:
            fb = get_ab_cfg("fallback_qr")
            if warn:
                info.append(warn)
            else:
                info.append(f"⚠️ Chưa có QR tự động — vui lòng liên hệ {seller_mention} để lấy STK, rồi gửi ảnh bill tại kênh này.")
            if fb:
                info.append("*Mã QR thanh toán của shop ở bên dưới:*")
        main = discord.Embed(
            title=f"🛒 ĐƠN MUA TÀI KHOẢN: {acc['username'].upper()}", color=COLOR_MAIN,
            description=f"Xin chào {buyer.mention}! Bạn đang tạo đơn mua tài khoản **{acc['username']}**.\n\n" + "\n".join(info))
        main.set_footer(text=f"{guild.name} AutoBuy • " + ("Thanh toán xong bot tự giao" if qr_embed else "Chờ người bán xác nhận"))
        main.timestamp = datetime.now(timezone.utc)
        if qr_embed is None and get_ab_cfg("fallback_qr"):
            main.set_image(url=get_ab_cfg("fallback_qr"))
        embeds.append(main)
        qr_files = []
        if qr_embed is not None:
            # Tải ảnh QR về rồi đính kèm file (img.vietqr.io có thể trả SVG mà Discord không hiện) — xem core/qr_image.py
            from cogs.shop_orders import attach_qr_image
            qr_files = await attach_qr_image(qr_embed, guild=guild.id, ref=ref_code)
            embeds.append(qr_embed)
        await channel.send(content=f"👋 {buyer.mention} đã tạo đơn mua tài khoản từ {seller_mention}!",
                           embeds=embeds, files=qr_files, view=ticket_view(acc["username"]),
                           allowed_mentions=discord.AllowedMentions(users=True))
        await interaction.followup.send(f"✅ Đã tạo kênh ticket cho bạn: {channel.mention}", ephemeral=True)

    # ═════════════ CONFIRM / CLOSE ═════════════
    async def _on_confirm(self, interaction: discord.Interaction, username: str):
        ticket = get_ab_ticket(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message("❌ Không tìm thấy dữ liệu ticket của kênh này.", ephemeral=True)
        if not self._can_handle_ticket(interaction.user, ticket):
            return await interaction.response.send_message("❌ **Từ chối:** Bạn không có quyền Confirm đơn này!", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        problems = await self.complete_purchase(interaction.guild, interaction.channel, ticket,
                                                confirmed_by=interaction.user)
        if problems == ["__already__"]:
            return await interaction.followup.send("ℹ️ Đơn này đã được xác nhận trước đó.", ephemeral=True)
        if problems:
            return await interaction.followup.send(
                "⚠️ Đơn đã xác nhận nhưng có vấn đề:\n" + "\n".join(f"• {p}" for p in problems), ephemeral=True)
        await interaction.followup.send("✅ Đơn hàng đã được xác nhận! Thông tin tài khoản đã gửi qua DM.", ephemeral=True)

    async def _on_close(self, interaction: discord.Interaction, username: str):
        ticket = get_ab_ticket(interaction.channel_id)
        if not ticket or not self._can_handle_ticket(interaction.user, ticket):
            return await interaction.response.send_message(
                "❌ **Từ chối:** Bạn không có quyền đóng đơn hàng này! (Chỉ Staff hoặc Seller)", ephemeral=True)
        await self.cancel_ticket(interaction.channel_id)
        await interaction.response.send_message("🔒 Kênh ticket này đã được đóng và sẽ xoá sau 5 giây...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"AutoBuy: {interaction.user} đóng ticket")
        except Exception:
            pass

    async def cancel_ticket(self, channel_id: int) -> None:
        """Huỷ/đóng ticket CHƯA bán: trả acc về AVAILABLE, khôi phục nút BUY, huỷ mã QR còn chờ (port handleCancelTicket)."""
        task = self._vouch_tasks.pop(channel_id, None)
        if task:
            task.cancel()
        ticket = get_ab_ticket(channel_id)
        if not ticket:
            return
        delete_ab_ticket(channel_id)
        ref = ticket.get("ref_code")
        if ref:
            pop_pending_shop_order(ref)       # QR cũ không còn khớp được → tiền về muộn sẽ báo admin xử lý tay
        acc = get_ab_account(ticket.get("username"))
        if acc and acc.get("status") != ST_SOLD:
            update_ab_account(acc["username"], status=ST_AVAILABLE)
            await self._set_card_state(ticket.get("card_channel_id") or acc.get("card_channel_id"),
                                       ticket.get("card_message_id") or acc.get("card_message_id"),
                                       acc["username"], ST_AVAILABLE)

    # ═════════════ GIAO HÀNG ═════════════
    def _credentials_embed(self, guild: discord.Guild, acc: dict) -> discord.Embed:
        user = acc.get("username") or "?"
        capes = (acc.get("capes") or "").strip() or "None"
        yt, fa = _fmt_ref(get_ab_cfg("kenh_youtube"), ""), _fmt_ref(get_ab_cfg("kenh_2fa"), "")
        lock, vouch = _fmt_ref(get_ab_cfg("kenh_lock"), ""), _fmt_ref(get_ab_cfg("kenh_vouch"), "")
        guides = "\n".join(x for x in (yt, fa, lock) if x)
        desc = (
            f"### 🏷️ Capes\n{capes}\n\n### 🔐 Thông Tin Đăng Nhập\n```text\n"
            f"Username: {user}\nPassword: {acc.get('password') or 'N/A'}\n"
            f"Primary Email: {acc.get('primary_email') or 'N/A'}\nSecurity Email: {acc.get('security_email') or 'N/A'}\n"
            f"Recovery Code: {acc.get('recovery_code') or 'N/A'}\nSecret Key: {acc.get('secret_key') or 'N/A'}\n```\n"
            "⚠️ *Vui lòng lưu lại và thay đổi thông tin bảo mật ngay lập tức!*")
        if guides:
            desc += f"\n\n---\n\n## Cách Thay Thông Tin\n{guides}"
        if vouch:
            desc += f"\n\n## Hãy nhớ VOUCH cho {guild.name}\n{vouch}"
        e = discord.Embed(title=f"🎉 THÔNG TIN TÀI KHOẢN: {user}", color=COLOR_OK, description=desc[:4000])
        e.set_author(name=f"{guild.name} - Giao Dịch Hoàn Tất", icon_url=guild.icon.url if guild.icon else None)
        e.set_thumbnail(url=f"https://mc-heads.net/avatar/{user}/100.png")
        e.set_footer(text=f"{guild.name} • Cảm ơn bạn đã tin tưởng và ủng hộ!")
        e.timestamp = datetime.now(timezone.utc)
        return e

    async def _dm_credentials(self, guild: discord.Guild, buyer, acc: dict) -> bool:
        try:
            await buyer.send(content=f"Cảm ơn bạn đã mua tài khoản tại **{guild.name}**! Dưới đây là thông tin tài khoản của bạn:",
                             embed=self._credentials_embed(guild, acc))
            return True
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            return False

    async def complete_purchase(self, guild: discord.Guild, channel, ticket: dict, confirmed_by=None) -> list[str]:
        """Hoàn tất 1 đơn (dùng chung cho nút Confirm tay VÀ SePay tự động). Trả về danh sách vấn đề
        (rỗng = trọn vẹn); ["__already__"] nếu đơn đã được xác nhận trước đó (idempotent)."""
        problems: list[str] = []
        username = ticket.get("username")
        acc = get_ab_account(username)
        if not acc:
            return [f"tài khoản `{username}` không còn trong kho"]
        if acc.get("status") == ST_SOLD:
            return ["__already__"]
        # chiếm trạng thái SOLD ĐỒNG BỘ (không await giữa kiểm tra và ghi) → Confirm tay + SePay cùng lúc không giao 2 lần
        buyer_id = ticket.get("buyer_id")
        update_ab_account(username, status=ST_SOLD, sold_at=datetime.now(timezone.utc).isoformat(), buyer_id=buyer_id)
        acc = get_ab_account(username)

        amount = int(ticket.get("amount") or 0) or parse_amount(acc.get("price"))
        buyer = await self._resolve_user(guild, buyer_id)
        seller_id = ticket.get("seller_id") or acc.get("seller_id")

        # doanh số: BXH chi tiêu + thống kê seller (giống luồng sold/.done có sẵn)
        card_ch = None
        try:
            if buyer_id and amount > 0:
                add_user_spent(int(buyer_id), amount)
        except Exception as e:
            problems.append(f"không cộng được chi tiêu của khách: {e}")
        try:
            card_ch = await get_or_fetch_channel(self.bot, int(ticket.get("card_channel_id") or acc.get("card_channel_id") or 0))
            if seller_id and amount > 0 and is_active_seller(guild.id, int(seller_id)):
                add_seller_sale(int(seller_id), amount, (card_ch.name if card_ch else f"autobuy-{username}"),
                                (card_ch.id if card_ch else channel.id))
        except Exception as e:
            problems.append(f"không ghi được thống kê seller: {e}")

        # thông báo trong ticket
        try:
            await channel.send(
                content=f"🎉 Chúc mừng <@{buyer_id}> đã hoàn tất giao dịch!" if buyer_id else "🎉 Giao dịch hoàn tất!",
                embed=discord.Embed(title="✅ GIAO DỊCH THÀNH CÔNG", color=COLOR_OK, description=(
                    f"Thông tin tài khoản đã được gửi qua tin nhắn riêng (DM) của <@{buyer_id}> để bảo mật!\n\n"
                    "*Vui lòng kiểm tra hộp thư tin nhắn riêng (DMs) của bạn.*")))
        except Exception as e:
            problems.append(f"không gửi được thông báo vào ticket: {e}")

        # giao thông tin đăng nhập qua DM
        if not buyer or not await self._dm_credentials(guild, buyer, acc):
            problems.append(f"không DM được thông tin cho <@{buyer_id}> (đang tắt DM?) — dùng `.abresend {username}` sau khi khách bật DM")
            try:
                await channel.send(f"⚠️ <@{buyer_id}> Bot không gửi được tin nhắn riêng cho bạn (đang tắt DM từ thành viên máy chủ)! "
                                   "Hãy bật lại tin nhắn riêng — staff sẽ gửi lại thông tin tài khoản cho bạn.")
            except Exception:
                pass

        # card → SOLD, kênh → ❌ + chuyển sang danh mục sold
        try:
            await self._set_card_state(ticket.get("card_channel_id") or acc.get("card_channel_id"),
                                       ticket.get("card_message_id") or acc.get("card_message_id"), username, ST_SOLD)
            if card_ch:
                sold_cat = guild.get_channel(get_cfg_sold_category() or 0)
                if isinstance(sold_cat, discord.CategoryChannel) and getattr(card_ch, "category_id", None) != sold_cat.id:
                    await card_ch.edit(category=sold_cat, reason="AutoBuy: đã bán")
                await card_ch.send(embed=discord.Embed(color=COLOR_DARK, description="## Acc đã được bán ❌").set_author(
                    name=guild.name, icon_url=guild.icon.url if guild.icon else None))
        except Exception as e:
            problems.append(f"không cập nhật được card/kênh stock: {e}")

        # bill
        await self._send_bill(guild, acc, buyer_id)

        # giữ ticket mở để khách vouch; nhắc vouch qua DM
        current = get_ab_ticket(channel.id)
        if current is not None:
            save_ab_ticket(channel.id, {**current, "completed": True})
        self._start_vouch_reminder(guild, channel, buyer, seller_id)
        try:
            await send_log(self.bot, "INFO", f"🛒 AutoBuy — đã bán `{username}`",
                           fields=[("Khách", f"<@{buyer_id}>", True), ("Giá", fmt_vnd(amount), True),
                                   ("Xác nhận", "tự động (SePay)" if confirmed_by is None else str(confirmed_by), True)],
                           guild_id=guild.id)
        except Exception:
            pass
        return problems

    async def _send_bill(self, guild: discord.Guild, acc: dict, buyer_id) -> None:
        bill_id = get_ab_cfg("bill_channel_id")
        if not bill_id:
            return
        try:
            ch = await get_or_fetch_channel(self.bot, int(bill_id))
            if not ch:
                return
            text = f"(<@{buyer_id}>) Đã Mua tài khoản ( {acc['username']} ) với giá ( {acc.get('price') or 'N/A'} )"
            png = await render_card({**{k: acc.get(k) or "" for k in ("username", "price", "rank", "capes", "statshpx", "statsdonut")},
                                     **store_info(guild)})
            if png:
                e = discord.Embed(color=COLOR_DARK).set_image(url="attachment://bill_card.png")
                await ch.send(content=text, embed=e, file=discord.File(io.BytesIO(png), "bill_card.png"),
                              allowed_mentions=discord.AllowedMentions.none())
            else:
                await ch.send(content=text, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            log.warning(f"[AUTOBUY] gửi bill lỗi: {e}")

    def _start_vouch_reminder(self, guild, channel, buyer, seller_id) -> None:
        old = self._vouch_tasks.pop(channel.id, None)
        if old:
            old.cancel()
        if buyer is None:
            return
        self._vouch_tasks[channel.id] = asyncio.create_task(self._vouch_loop(guild, channel, buyer, seller_id))

    async def _vouch_loop(self, guild, channel, buyer, seller_id) -> None:
        try:
            for _ in range(VOUCH_REMIND_MAX):
                await asyncio.sleep(VOUCH_REMIND_EVERY)
                try:
                    ch = await get_or_fetch_channel(self.bot, channel.id)
                except Exception:
                    ch = None
                if not ch:
                    return
                spoke = False
                async for m in ch.history(limit=20):
                    if m.author.id == buyer.id:
                        spoke = True
                        break
                if spoke:
                    return
                try:
                    await buyer.send(f"👋 Bạn đừng quên vouch cho **{guild.name}** nhé!\n\n**Mẫu copy:**\n"
                                     f"```text\n+1 legit <@{seller_id}> mfa\n```")
                except Exception:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("[AUTOBUY] vouch reminder lỗi")
        finally:
            self._vouch_tasks.pop(channel.id, None)

    # ═════════════ HOOK TỪ shop_orders / shop_admin ═════════════
    async def on_paid(self, order: dict, transfer_amount: int, expected_amount: int) -> list[str]:
        """Gọi từ shop_orders._notify_paid_order khi SePay báo ĐÃ NHẬN TIỀN cho 1 đơn có autobuy_username."""
        guild = self.bot.get_guild(order["guild_id"])
        channel = await get_or_fetch_channel(self.bot, order["channel_id"])
        if not guild or not channel:
            return ["kênh ticket AutoBuy đã bị xoá / bot không truy cập được — tiền đã vào, cần xử lý tay"]
        ticket = get_ab_ticket(channel.id)
        if not ticket:
            return ["không còn dữ liệu ticket AutoBuy của kênh này — tiền đã vào, cần xử lý tay"]
        try:
            await channel.send(embed=discord.Embed(
                title="💰 Đã nhận thanh toán", color=COLOR_OK,
                description=f"Hệ thống đã nhận **{fmt_vnd(transfer_amount)}** (mã `{order.get('ref_code')}`). Đang giao tài khoản…"))
        except Exception:
            pass
        problems = await self.complete_purchase(guild, channel, ticket, confirmed_by=None)
        return [] if problems == ["__already__"] else problems

    async def on_manual_sold(self, channel) -> None:
        """Gọi từ shop_admin.handle_sold khi staff gõ "sold" trong kênh stock: acc có card ở kênh này cũng thành SOLD."""
        acc = find_ab_account_by_channel(channel.id)
        if not acc or acc.get("status") == ST_SOLD:
            return
        update_ab_account(acc["username"], status=ST_SOLD, sold_at=datetime.now(timezone.utc).isoformat())
        # rename=False: handle_sold() sẽ tự đổi tên + chuyển kênh ngay sau đó — đổi 2 lần liên tiếp dễ dính rate limit
        await self._set_card_state(acc.get("card_channel_id"), acc.get("card_message_id"), acc["username"], ST_SOLD,
                                   rename=False)

    # ═════════════ SỰ KIỆN ═════════════
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        try:
            set_current_guild(channel.guild.id)
            if get_ab_ticket(channel.id):
                await self.cancel_ticket(channel.id)
        except Exception:
            log.exception("[AUTOBUY] lỗi dọn ticket khi kênh bị xoá")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Khách nhắn trong ticket SAU KHI đã bán (thường là vouch) → báo legit + xoá kênh sau 3 giây."""
        if not message.guild or message.author.bot:
            return
        try:
            set_current_guild(message.guild.id)
            ticket = get_ab_ticket(message.channel.id)
        except Exception:
            return
        if not ticket or str(message.author.id) != str(ticket.get("buyer_id")):
            return
        acc = get_ab_account(ticket.get("username"))
        if not acc or acc.get("status") != ST_SOLD:
            return
        task = self._vouch_tasks.pop(message.channel.id, None)
        if task:
            task.cancel()
        delete_ab_ticket(message.channel.id)
        try:
            await message.channel.send(f"{message.author.mention} đã legit")
            await asyncio.sleep(3)
            await message.channel.delete(reason="AutoBuy: khách đã vouch, đóng ticket")
        except Exception:
            pass

    # ═════════════ LỆNH ═════════════
    @app_commands.command(name="add_acc", description="[Seller/Owner] Nhập thông tin tài khoản Minecraft vào kho")
    @app_commands.guild_only()
    async def add_acc_cmd(self, interaction: discord.Interaction):
        if not can_sell_acc(interaction.user):
            return await interaction.response.send_message(MSG_NOT_SELLER, ephemeral=True)
        if not has_bank(interaction.user.id):
            return await interaction.response.send_message(msg_no_bank(interaction.user.id, interaction.user.id), ephemeral=True)
        await interaction.response.send_modal(_AddAccModal())

    stock = app_commands.Group(name="stock", description="Quản lý kho tài khoản", guild_only=True)

    @stock.command(name="acc", description="[Seller/Owner] Đăng card tài khoản Minecraft kèm nút BUY")
    @app_commands.describe(username="Tên tài khoản Minecraft", price="Giá bán (vd: 100k, 140000, 1.2M)",
                           capes="Emoji capes (trống = lấy từ kho nếu đã /add_acc)",
                           rank="Rank Hypixel (VIP, MVP, MVP+, NON)",
                           statshpx="Hypixel: Level, Achievements (vd: 150, 4500)",
                           statsdonut="DonutSMP: Playtime, Money, Shards (vd: 120h, 50M, 1500)")
    async def stock_acc(self, interaction: discord.Interaction, username: str, price: str, capes: str = "",
                        rank: str = "", statshpx: str = "", statsdonut: str = ""):
        if not can_sell_acc(interaction.user):
            return await interaction.response.send_message(MSG_NOT_SELLER, ephemeral=True)
        stored_seller = (get_ab_account(username.strip()) or {}).get("seller_id") or interaction.user.id
        if not has_bank(stored_seller):            # QR chạy về bank của SELLER CỦA ACC (có thể khác người đang đăng)
            return await interaction.response.send_message(msg_no_bank(stored_seller, interaction.user.id), ephemeral=True)
        username, price = username.strip(), price.strip()
        if parse_amount(price) <= 0:
            return await interaction.response.send_message("❌ Giá không hợp lệ (vd: `140k`, `1.2M`).", ephemeral=True)
        stored = get_ab_account(username)
        if stored and stored.get("status") == ST_SOLD:
            return await interaction.response.send_message(f"❌ `{username}` đã bán rồi. Muốn bán lại hãy `/add_acc` nạp lại.", ephemeral=True)
        if stored and stored.get("status") == ST_PROCESSING:
            return await interaction.response.send_message(f"⏳ `{username}` đang có người mở đơn, chưa thể đăng lại card.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        seller_id = (stored or {}).get("seller_id") or interaction.user.id
        # tách emoji nếu staff dán vào ô rank/stats (giống bản Node)
        rank_emojis = " ".join(CUSTOM_EMOJI_RE.findall(rank))
        hpx_emojis = " ".join(CUSTOM_EMOJI_RE.findall(statshpx))
        donut_emojis = " ".join(CUSTOM_EMOJI_RE.findall(statsdonut))
        rank = CUSTOM_EMOJI_RE.sub("", rank).strip() or "NON"
        statshpx = CUSTOM_EMOJI_RE.sub("", statshpx).strip()
        statsdonut = CUSTOM_EMOJI_RE.sub("", statsdonut).strip()
        capes = capes.strip() or ((stored or {}).get("capes") or "").strip() or f"{rank_emojis} {hpx_emojis} {donut_emojis}".strip()
        capes = " ".join(dict.fromkeys(CUSTOM_EMOJI_RE.findall(capes)))     # bỏ trùng, giữ thứ tự

        png = await render_card({"username": username, "price": price, "rank": rank, "capes": capes,
                                 "statshpx": statshpx, "statsdonut": statsdonut, **store_info(interaction.guild)})
        if not png:
            return await interaction.followup.send("❌ Không thể tạo ảnh card!", ephemeral=True)

        guild = interaction.guild
        target = interaction.channel
        stock_cat = guild.get_channel(get_cfg_stock_category() or 0)
        if isinstance(stock_cat, discord.CategoryChannel):
            name = make_stock_channel_name(ST_AVAILABLE, format_price_display(price), count_capes(capes))
            ow = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, read_message_history=True,
                                                                send_messages=False, add_reactions=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True,
                                                      attach_files=True, manage_channels=True, manage_messages=True),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True,
                                                              embed_links=True, read_message_history=True, manage_messages=True),
            }
            try:
                target = await guild.create_text_channel(name=name, category=stock_cat, overwrites=ow,
                                                         reason=f"AutoBuy: đăng {username}")
            except discord.HTTPException as e:
                return await interaction.followup.send(f"❌ Không tạo được kênh stock: `{e}`", ephemeral=True)

        embed = discord.Embed(color=COLOR_DARK, description=f"**Seller:** <@{seller_id}>")
        embed.set_image(url="attachment://card.png")
        msg = await target.send(embed=embed, file=discord.File(io.BytesIO(png), "card.png"),
                                view=card_view(ST_AVAILABLE, username),
                                allowed_mentions=discord.AllowedMentions.none())
        base = stored or {"username": username, "note": "Chưa nạp thông tin bí mật qua /add_acc"}
        save_ab_account({**base, "username": username, "price": price, "rank": rank, "capes": capes,
                         "statshpx": statshpx, "statsdonut": statsdonut, "seller_id": seller_id,
                         "card_channel_id": msg.channel.id, "card_message_id": msg.id, "status": ST_AVAILABLE})
        note = "" if stored else "\n⚠️ Tài khoản này chưa có thông tin đăng nhập trong kho — hãy `/add_acc` trước khi có người mua!"
        if not get_cfg_shop_orders_enabled():
            note += "\n⚠️ **Shop Orders đang tắt** nên ticket sẽ KHÔNG có QR tự động (phải bấm Confirm tay) — bật trong `.st`."
        await interaction.followup.send(f"✅ Đã đăng card `{username}` tại {target.mention}.{note}", ephemeral=True)

    @app_commands.command(name="restock", description="[Staff] Thông báo danh sách các kênh trong kho stock")
    @app_commands.guild_only()
    async def restock_cmd(self, interaction: discord.Interaction):
        if not self._is_staff(interaction.user):
            return await interaction.response.send_message("❌ Chỉ Staff/Seller mới dùng được lệnh này.", ephemeral=True)
        guild = interaction.guild
        cat = guild.get_channel(get_cfg_stock_category() or 0)
        if not isinstance(cat, discord.CategoryChannel):
            return await interaction.response.send_message("❌ Chưa cài danh mục stock trong `.st`.", ephemeral=True)
        chans = sorted(cat.text_channels, key=lambda c: c.position)
        body = f"> Có {len(chans)} account\n\n" + "\n".join(c.mention for c in chans)
        if len(body) > 4000:
            body = body[:3950] + "\n\n*...*"
        e = discord.Embed(title="Stock Account MFA", color=COLOR_MAIN, description=body)
        e.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        e.set_footer(text=f"Tổng số: {len(chans)} tài khoản • {guild.name}")
        e.timestamp = datetime.now(timezone.utc)
        await interaction.channel.send(embed=e)
        await interaction.response.send_message("✅ Đã gửi danh sách stock.", ephemeral=True)

    @app_commands.command(name="ab_import", description="[Admin] Nhập kho từ file kho.json của bot autobuy cũ (Node)")
    @app_commands.describe(file="File kho.json (hoặc data/accounts.json) của bot Node")
    @app_commands.guild_only()
    async def ab_import_cmd(self, interaction: discord.Interaction, file: discord.Attachment):
        if not is_admin(interaction.user):
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        if file.size > 5 * 1024 * 1024:
            return await interaction.response.send_message("❌ File quá lớn (>5MB).", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            raw = json.loads((await file.read()).decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("file phải là JSON object {username: {...}}")
        except Exception as e:
            return await interaction.followup.send(f"❌ Không đọc được file: `{e}`", ephemeral=True)
        added = skipped = 0
        for key, doc in raw.items():
            if not isinstance(doc, dict):
                continue
            conv = convert_node_account({"username": key, **doc})
            if not conv or get_ab_account(conv["username"]):
                skipped += 1          # đã có trong kho → không ghi đè
                continue
            save_ab_account(conv)
            added += 1
        await interaction.followup.send(
            f"✅ Đã nhập **{added}** tài khoản, bỏ qua **{skipped}** (đã có/không hợp lệ).\n"
            "Tài khoản đang `PROCESSING` bên Node được đặt lại `AVAILABLE` (ticket Node không mang sang). "
            "Nhớ **tắt bot Node** để 2 bot không cùng xử lý nút BUY.", ephemeral=True)

    @commands.command(name="abset")
    async def abset_cmd(self, ctx: commands.Context, key: str = None, *, value: str = None):
        """.abset — xem cấu hình AutoBuy | .abset <ticket|bill|youtube|2fa|lock|vouch|qr> <#kênh/ID/URL | off>"""
        if not is_admin(ctx.author):
            return await ctx.reply("❌ Chỉ admin mới có quyền.")
        if not key:
            lines = []
            for k, (store, desc, kind) in CFG_KEYS.items():
                cur = get_ab_cfg(store)
                shown = (f"<#{cur}>" if str(cur).isdigit() else str(cur)) if cur else "*(chưa cài)*"
                lines.append(f"`{k}` — {desc}: {shown}")
            lines.append(f"\nStock: {get_cfg_stock_category() or '*(chưa cài)*'} · Sold: {get_cfg_sold_category() or '*(chưa cài)*'} "
                         "*(dùng chung `.st`)*")
            return await ctx.reply("**⚙️ Cấu hình AutoBuy**\n" + "\n".join(lines) + "\n\nĐặt: `.abset <khoá> <#kênh/ID/URL>` · Xoá: `.abset <khoá> off`")
        key = key.lower()
        if key not in CFG_KEYS:
            return await ctx.reply(f"❌ Khoá không hợp lệ. Dùng: {', '.join(f'`{k}`' for k in CFG_KEYS)}")
        store, desc, kind = CFG_KEYS[key]
        if value is None:
            return await ctx.reply("❌ Thiếu giá trị. Dùng `off` để xoá.")
        value = value.strip()
        if value.lower() in ("off", "none", "0", "xoa", "xoá"):
            set_ab_cfg(store, None)
            return await ctx.reply(f"✅ Đã xoá `{key}`.")
        if kind == "url":
            if not re.match(r"^https?://\S+$", value):
                return await ctx.reply("❌ Cần URL ảnh bắt đầu bằng http(s)://")
            set_ab_cfg(store, value)
            return await ctx.reply(f"✅ Đã đặt `{key}`.")
        m = re.search(r"\d{15,20}", value)
        if not m:
            return await ctx.reply("❌ Cần #kênh hoặc ID kênh/danh mục.")
        ch = ctx.guild.get_channel(int(m.group()))
        if not ch:
            return await ctx.reply("❌ Không tìm thấy kênh/danh mục này trong server.")
        if kind == "category" and not isinstance(ch, discord.CategoryChannel):
            return await ctx.reply("❌ Khoá này cần ID **danh mục** (category).")
        if kind == "channel" and isinstance(ch, discord.CategoryChannel):
            return await ctx.reply("❌ Khoá này cần **kênh**, không phải danh mục.")
        set_ab_cfg(store, str(ch.id))
        await ctx.reply(f"✅ Đã đặt `{key}` = {ch.mention if hasattr(ch, 'mention') else ch.name}")

    @commands.command(name="abresend")
    async def abresend_cmd(self, ctx: commands.Context, username: str = None):
        """.abresend <username> — gửi lại DM thông tin tài khoản cho người đã mua (khi lần đầu khách tắt DM)."""
        if not self._is_staff(ctx.author):
            return await ctx.reply("❌ Chỉ Staff/Seller mới dùng được lệnh này.")
        if not username:
            return await ctx.reply("Dùng: `.abresend <username>`")
        acc = get_ab_account(username)
        if not acc or acc.get("status") != ST_SOLD or not acc.get("buyer_id"):
            return await ctx.reply("❌ Không có tài khoản ĐÃ BÁN với username này (hoặc thiếu người mua).")
        buyer = await self._resolve_user(ctx.guild, acc["buyer_id"])
        if not buyer:
            return await ctx.reply("❌ Không tìm thấy người mua.")
        ok = await self._dm_credentials(ctx.guild, buyer, acc)
        await ctx.reply("✅ Đã gửi lại thông tin qua DM." if ok else "❌ Vẫn không DM được — khách chưa bật tin nhắn riêng.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoBuyCog(bot))
