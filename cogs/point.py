"""
cogs/point.py — Hệ thống Point: redeem mã, xem point, admin quản lý, bù tiền seller.
v1.0 — 2026-05-15
"""

import discord
from discord.ext import commands
from discord.ui import View, Button
from datetime import datetime, timezone, timedelta
import secrets
import string
import os
import httpx

from core.data import (
    ADMIN_IDS,
    get_user_points, add_user_points, set_user_points, get_point_cfg,
    save_point_code, get_point_code, mark_code_used, get_last_redeem_time,
    get_seller_compensation, get_all_seller_compensation, mark_seller_paid,
    get_reward_shop, get_reward_item, save_reward_shop, add_exchange_record,
    fmt_amount, is_staff_member, _uname_plain,
)

BOT_VERSION = "1.0"

# ══════════════════════════════════════════
# API CONFIG
# ══════════════════════════════════════════
POINT_API_URL    = os.getenv("POINT_API_URL", "")    # https://your-app.onrender.com
POINT_API_SECRET = os.getenv("POINT_API_SECRET", "") # Phải khớp với API_SECRET trên Render

def _api_headers():
    return {"X-API-Secret": POINT_API_SECRET, "Content-Type": "application/json"}

# ══════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════
async def _resolve_member(ctx, target: str) -> discord.Member | None:
    """Chấp nhận @mention, ID, hoặc username."""
    if not target:
        return None
    # Thử parse ID từ mention hoặc số
    raw = target.strip().strip("<@!>")
    if raw.isdigit():
        uid = int(raw)
        member = ctx.guild.get_member(uid)
        if not member:
            try: member = await ctx.guild.fetch_member(uid)
            except: pass
        return member
    # Thử tìm theo tên
    return discord.utils.find(
        lambda m: m.name.lower() == target.lower() or m.display_name.lower() == target.lower(),
        ctx.guild.members
    )



# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════
def _gen_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))

def _check_cooldown(user_id: int) -> int | None:
    """Trả về số giây còn lại nếu đang cooldown, None nếu OK."""
    cfg       = get_point_cfg()
    hours     = cfg.get("cooldown_hours", 24)
    last_time = get_last_redeem_time(user_id)
    if not last_time:
        return None
    try:
        last_dt = datetime.fromisoformat(last_time)
        diff    = datetime.now(timezone.utc) - last_dt
        cooldown = timedelta(hours=hours)
        if diff < cooldown:
            return int((cooldown - diff).total_seconds())
    except Exception:
        pass
    return None


class PointCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ══════════════════════════════════════
    # .gencode — Admin tạo mã cho user
    # ══════════════════════════════════════
    @commands.command(name="gencode")
    async def gencode_cmd(self, ctx, *, target: str = None):
        """Admin tạo mã point cho user cụ thể (hoặc không gán user nào)."""
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
        member = await _resolve_member(ctx, target) if target else None

        cfg         = get_point_cfg()
        expire_mins = cfg.get("code_expire_mins", 10)
        pts         = cfg.get("points_per_redeem", 100)
        code        = _gen_code()
        expires_at  = (datetime.now(timezone.utc) + timedelta(minutes=expire_mins)).isoformat()
        user_id     = member.id if member else 0  # 0 = không giới hạn user

        save_point_code(code, user_id, expires_at)

        embed = discord.Embed(title="🎟️ Mã Point Mới", color=0xF1C40F, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="🔑 Mã",        value=f"```{code}```",                   inline=False)
        embed.add_field(name="💎 Point",      value=f"**{pts:,} point**",             inline=True)
        embed.add_field(name="⏰ Hết hạn",   value=f"**{expire_mins} phút**",         inline=True)
        if member:
            embed.add_field(name="👤 Dành cho", value=member.mention, inline=True)
        else:
            embed.add_field(name="👤 Dành cho", value="Bất kỳ ai", inline=True)
        embed.set_footer(text="Dùng .redeem <mã> để nhận point")
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════
    # .redeem — User nhập mã nhận point
    # ══════════════════════════════════════
    @commands.command(name="redeem")
    async def redeem_cmd(self, ctx, code: str = None):
        if not code:
            return await ctx.reply("❌ Dùng: `.redeem <mã>`")

        code = code.strip().upper()

        # Nếu có API URL → gọi API, không thì fallback local
        if POINT_API_URL:
            async with httpx.AsyncClient(timeout=10) as client:
                try:
                    res  = await client.post(
                        f"{POINT_API_URL}/code/redeem",
                        json={"code": code, "user_id": ctx.author.id},
                        headers=_api_headers()
                    )
                    data = res.json()
                except Exception:
                    return await ctx.reply("❌ Không kết nối được server point. Thử lại sau.")

            if res.status_code == 429:
                return await ctx.reply(f"⏳ {data.get('detail', {}).get('message', 'Đang cooldown')}")
            if res.status_code == 404:
                return await ctx.reply("❌ Mã không tồn tại hoặc không hợp lệ.")
            if res.status_code == 400:
                err = data.get("detail", {}).get("error", "")
                if err == "used_code":    return await ctx.reply("❌ Mã này đã được sử dụng rồi.")
                if err == "expired_code": return await ctx.reply("❌ Mã đã hết hạn.")
                return await ctx.reply(f"❌ {data.get('detail', {}).get('message', 'Lỗi không xác định')}")
            if res.status_code == 403:
                return await ctx.reply("❌ Mã này không dành cho bạn.")
            if res.status_code != 200:
                return await ctx.reply("❌ Lỗi server. Thử lại sau.")

            pts      = data.get("points", 100)
            new_pts  = data.get("new_total", 0)
            cfg      = get_point_cfg()

        else:
            # ── Fallback: xử lý local (giữ nguyên logic cũ) ──
            remaining = _check_cooldown(ctx.author.id)
            if remaining is not None:
                h, m = divmod(remaining // 60, 60)
                return await ctx.reply(f"⏳ Bạn cần chờ thêm **{h}h {m}m** trước khi redeem tiếp.")
            record = get_point_code(code)
            if not record:                    return await ctx.reply("❌ Mã không tồn tại.")
            if record.get("used"):            return await ctx.reply("❌ Mã đã được sử dụng.")
            try:
                exp = datetime.fromisoformat(record["expires_at"])
                if datetime.now(timezone.utc) > exp: return await ctx.reply("❌ Mã đã hết hạn.")
            except Exception:
                return await ctx.reply("❌ Mã không hợp lệ.")
            if record.get("user_id") and record["user_id"] != 0 and record["user_id"] != ctx.author.id:
                return await ctx.reply("❌ Mã này không dành cho bạn.")
            cfg     = get_point_cfg()
            pts     = cfg.get("points_per_redeem", 100)
            mark_code_used(code)
            new_pts = add_user_points(ctx.author.id, pts, f"redeem:{code}")

        embed = discord.Embed(
            title="✅ Redeem Thành Công!",
            color=0x57F287, timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="💎 Nhận được",  value=f"**+{pts:,} point**",    inline=True)
        embed.add_field(name="💼 Tổng point", value=f"**{new_pts:,} point**", inline=True)
        embed.add_field(
            name="💡 Sử dụng",
            value="Point tự động áp dụng giảm giá khi staff dùng `.done` trong ticket của bạn.",
            inline=False
        )
        embed.set_footer(text=f"Cooldown: {cfg.get('cooldown_hours',24)}h trước lần redeem tiếp")
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════
    # .point — Xem point bản thân / người khác
    # ══════════════════════════════════════
    @commands.command(name="point", aliases=["points", "pts"])
    async def point_cmd(self, ctx, *, target: str = None):
        member = await _resolve_member(ctx, target) if target else ctx.author
        if not member:
            return await ctx.reply(f"❌ Không tìm thấy user `{target}`.")
        target_member = member
        pts      = get_user_points(target_member.id)
        cfg      = get_point_cfg()
        pt_val   = cfg.get("point_value", 100)
        max_pct  = cfg.get("max_discount_pct", 20)

        embed = discord.Embed(
            title=f"💎 Point — {target_member.display_name}",
            color=0xF1C40F, timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=target_member.display_avatar.url)
        embed.add_field(name="💼 Point hiện có",  value=f"**{pts:,} point**",                  inline=True)
        embed.add_field(name="💵 Giá trị",        value=f"**{fmt_amount(pts * pt_val)}**",      inline=True)
        embed.add_field(
            name="💡 Cách dùng",
            value=f"Point tự động giảm giá khi có đơn (tối đa **{max_pct}%** giá trị đơn)",
            inline=False
        )
        # Cooldown còn lại
        remaining = _check_cooldown(target_member.id)
        if remaining is not None:
            h, m = divmod(remaining // 60, 60)
            embed.add_field(name="⏳ Cooldown redeem", value=f"Còn **{h}h {m}m**", inline=False)
        else:
            embed.add_field(name="✅ Redeem", value="Sẵn sàng — dùng `.redeem <mã>`", inline=False)
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════
    # .addpoint — Admin cộng/trừ point thủ công
    # ══════════════════════════════════════
    @commands.command(name="addpoint")
    async def addpoint_cmd(self, ctx, target: str = None, amount: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
        if not target or not amount:
            return await ctx.reply("❌ Dùng: `.addpoint <@user|ID> <số>` (số âm để trừ)")
        member = await _resolve_member(ctx, target)
        if not member:
            return await ctx.reply(f"❌ Không tìm thấy user `{target}`.")
        try:
            pts = int(amount)
        except ValueError:
            return await ctx.reply("❌ Số point không hợp lệ.")

        new_pts = add_user_points(member.id, pts, f"admin:{_uname_plain(ctx.author)}")
        action  = f"+{pts:,}" if pts >= 0 else f"{pts:,}"
        color   = 0x57F287 if pts >= 0 else 0xED4245

        embed = discord.Embed(title="💎 Cập Nhật Point", color=color, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 User",       value=member.mention,          inline=True)
        embed.add_field(name="📊 Thay đổi",   value=f"**{action} point**",   inline=True)
        embed.add_field(name="💼 Tổng mới",   value=f"**{new_pts:,} point**",inline=True)
        embed.set_footer(text=f"Bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════
    # .pointcfg — Admin cấu hình hệ thống point
    # ══════════════════════════════════════
    @commands.command(name="pointcfg")
    async def pointcfg_cmd(self, ctx, key: str = None, value: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

        from core.data import load_data, save_data
        cfg_keys = {
            "pts":      "points_per_redeem",
            "value":    "point_value",
            "maxpct":   "max_discount_pct",
            "cooldown": "cooldown_hours",
            "expire":   "code_expire_mins",
        }

        if not key or not value:
            cfg = get_point_cfg()
            embed = discord.Embed(title="⚙️ Cấu Hình Point", color=0x5865F2, timestamp=datetime.now(timezone.utc))
            embed.add_field(name="💎 Point/lần redeem",   value=f"**{cfg.get('points_per_redeem',100):,}**", inline=True)
            embed.add_field(name="💵 Giá trị 1 point",   value=f"**{fmt_amount(cfg.get('point_value',100))}**", inline=True)
            embed.add_field(name="📉 Giảm tối đa",        value=f"**{cfg.get('max_discount_pct',20)}%**",   inline=True)
            embed.add_field(name="⏰ Cooldown",            value=f"**{cfg.get('cooldown_hours',24)}h**",     inline=True)
            embed.add_field(name="🔑 Mã hết hạn",         value=f"**{cfg.get('code_expire_mins',10)} phút**", inline=True)
            embed.add_field(
                name="💡 Sửa",
                value=(
                    "`.pointcfg pts <số>` — Point/lần redeem\n"
                    "`.pointcfg value <số>` — Giá trị 1 point (đơn vị đồng)\n"
                    "`.pointcfg maxpct <số>` — Giảm tối đa (%)\n"
                    "`.pointcfg cooldown <số>` — Cooldown (giờ)\n"
                    "`.pointcfg expire <số>` — Mã hết hạn (phút)"
                ),
                inline=False
            )
            return await ctx.reply(embed=embed)

        if key not in cfg_keys:
            return await ctx.reply(f"❌ Key không hợp lệ. Dùng: `{'`, `'.join(cfg_keys.keys())}`")
        try:
            val = int(value)
            if val <= 0: raise ValueError
        except ValueError:
            return await ctx.reply("❌ Giá trị phải là số nguyên dương.")

        data = load_data()
        data.setdefault("point_cfg", {})
        data["point_cfg"][cfg_keys[key]] = val
        save_data(data)
        await ctx.reply(f"✅ Đã cập nhật `{key}` = **{val}**")

    # ══════════════════════════════════════
    # .pointlog — Admin xem thống kê bù tiền seller
    # ══════════════════════════════════════
    @commands.command(name="pointlog", aliases=["sellerbuu", "buuseller"])
    async def pointlog_cmd(self, ctx, *, target: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")

        if target:
            member = await _resolve_member(ctx, target)
            if not member:
                return await ctx.reply(f"❌ Không tìm thấy user `{target}`.")
            # Xem 1 seller cụ thể
            comp    = get_seller_compensation(member.id)
            owed    = comp.get("total_owed", 0)
            paid    = comp.get("paid", 0)
            remain  = owed - paid
            records = comp.get("records", [])

            embed = discord.Embed(
                title=f"🔄 Bù Tiền Seller — {member.display_name}",
                color=0xF1C40F, timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="💰 Tổng cần bù",  value=f"**{fmt_amount(owed)}**",   inline=True)
            embed.add_field(name="✅ Đã bù",         value=f"**{fmt_amount(paid)}**",   inline=True)
            embed.add_field(name="⏳ Còn lại",       value=f"**{fmt_amount(remain)}**", inline=True)

            if records:
                recent = records[-5:][::-1]
                lines  = []
                for r in recent:
                    try:
                        dt   = datetime.fromisoformat(r.get("time",""))
                        tstr = dt.strftime("%d/%m %H:%M")
                    except Exception:
                        tstr = "?"
                    lines.append(f"`{tstr}` <@{r.get('buyer_id','?')}> — **{fmt_amount(r.get('amount',0))}** — `{r.get('ticket','?')}`")
                embed.add_field(name="📋 5 lần gần nhất", value="\n".join(lines), inline=False)

            embed.add_field(
                name="💡 Đánh dấu đã bù",
                value=f"`.buixong @{member.name} <số tiền>`",
                inline=False
            )
            return await ctx.reply(embed=embed)

        # Xem tổng tất cả seller
        all_comp = get_all_seller_compensation()
        if not all_comp:
            return await ctx.reply("✅ Không có khoản bù tiền nào cần xử lý.")

        embed = discord.Embed(
            title="🔄 Tổng Hợp Bù Tiền Seller",
            color=0xF1C40F, timestamp=datetime.now(timezone.utc)
        )
        total_owed = 0
        total_paid = 0
        lines      = []
        for sid, comp in all_comp.items():
            owed   = comp.get("total_owed", 0)
            paid   = comp.get("paid", 0)
            remain = owed - paid
            total_owed += owed
            total_paid += paid
            member_obj = ctx.guild.get_member(int(sid))
            name       = member_obj.mention if member_obj else f"`ID:{sid}`"
            status     = "✅" if remain <= 0 else "⏳"
            lines.append(f"{status} {name} — cần bù: **{fmt_amount(owed)}** | đã bù: **{fmt_amount(paid)}** | còn: **{fmt_amount(remain)}**")

        embed.description = "\n".join(lines)
        embed.add_field(name="💰 Tổng cần bù",  value=f"**{fmt_amount(total_owed)}**",          inline=True)
        embed.add_field(name="✅ Đã bù",         value=f"**{fmt_amount(total_paid)}**",          inline=True)
        embed.add_field(name="⏳ Còn lại",       value=f"**{fmt_amount(total_owed-total_paid)}**", inline=True)
        embed.set_footer(text="Dùng .pointlog @seller để xem chi tiết từng người")
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════
    # .buixong — Admin đánh dấu đã bù seller
    # ══════════════════════════════════════
    @commands.command(name="buixong")
    async def buixong_cmd(self, ctx, target: str = None, amount_str: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được lệnh này.")
        if not target or not amount_str:
            return await ctx.reply("❌ Dùng: `.buixong <@seller|ID> <số tiền>`")
        member = await _resolve_member(ctx, target)
        if not member:
            return await ctx.reply(f"❌ Không tìm thấy user `{target}`.")

        from core.data import parse_amount
        amount = parse_amount(amount_str)
        if not amount or amount <= 0:
            return await ctx.reply("❌ Số tiền không hợp lệ.")

        mark_seller_paid(member.id, amount)
        comp   = get_seller_compensation(member.id)
        remain = comp.get("total_owed", 0) - comp.get("paid", 0)

        embed = discord.Embed(title="✅ Đã Ghi Nhận Bù Tiền", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Seller",    value=member.mention,         inline=True)
        embed.add_field(name="💵 Đã bù",    value=f"**{fmt_amount(amount)}**", inline=True)
        embed.add_field(name="⏳ Còn lại",  value=f"**{fmt_amount(max(0,remain))}**", inline=True)
        embed.set_footer(text=f"Bởi {_uname_plain(ctx.author)}")
        await ctx.reply(embed=embed)


    # ══════════════════════════════════════
    # .shop — Xem cửa hàng đổi quà
    # ══════════════════════════════════════
    @commands.command(name="shop", aliases=["store", "cuahang"])
    async def shop_cmd(self, ctx):
        items  = get_reward_shop()
        pts    = get_user_points(ctx.author.id)

        embed = discord.Embed(
            title="🏪 Cửa Hàng Đổi Point",
            color=0xF1C40F, timestamp=datetime.now(timezone.utc)
        )
        embed.description = f"Point của bạn: **{pts:,} pt**\nDùng `.exchange <id>` để đổi quà.\n"

        if items:
            lines = []
            for item in items:
                can = "✅" if pts >= item["points"] else "❌"
                lines.append(
                    f"{can} `{item['id']}` — **{item['name']}**\n"
                    f"　　💎 {item['points']:,} point  •  {item['description']}"
                )
            embed.add_field(name="📦 Danh Sách Quà", value="\n\n".join(lines), inline=False)
        else:
            embed.description += "\n*(Chưa có quà nào trong shop)*"

        embed.set_footer(text="✅ = đủ point  •  ❌ = chưa đủ")
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════
    # .exchange — Đổi point lấy quà
    # ══════════════════════════════════════
    @commands.command(name="exchange", aliases=["doi", "redeemdoi"])
    async def exchange_cmd(self, ctx, item_id: str = None):
        if not item_id:
            return await ctx.reply("❌ Dùng: `.exchange <id>` — Xem danh sách: `.shop`")

        item = get_reward_item(item_id.lower().strip())
        if not item:
            return await ctx.reply(f"❌ Không tìm thấy item `{item_id}`. Xem `.shop` để biết danh sách.")

        pts = get_user_points(ctx.author.id)
        if pts < item["points"]:
            need = item["points"] - pts
            return await ctx.reply(
                f"❌ Bạn chưa đủ point!\n"
                f"Cần: **{item['points']:,} pt** | Hiện có: **{pts:,} pt** | Thiếu: **{need:,} pt**"
            )

        # Xác nhận trước khi đổi
        confirm_embed = discord.Embed(
            title="💎 Xác Nhận Đổi Quà",
            color=0xF1C40F, timestamp=datetime.now(timezone.utc)
        )
        confirm_embed.add_field(name="📦 Quà",         value=f"**{item['name']}**",         inline=True)
        confirm_embed.add_field(name="💎 Point dùng",  value=f"**{item['points']:,} pt**",  inline=True)
        confirm_embed.add_field(name="💼 Còn lại",     value=f"**{pts - item['points']:,} pt**", inline=True)
        confirm_embed.add_field(name="📝 Mô tả",       value=item["description"],           inline=False)
        confirm_embed.set_footer(text="Bấm ✅ để xác nhận hoặc ❌ để huỷ (60 giây)")

        class ConfirmView(View):
            def __init__(self):
                super().__init__(timeout=60)
                self.choice = None

            @discord.ui.button(label="✅ Xác nhận", style=discord.ButtonStyle.green)
            async def confirm(self, inter: discord.Interaction, btn: Button):
                if inter.user.id != ctx.author.id:
                    return await inter.response.send_message("❌ Không phải lệnh của bạn.", ephemeral=True)
                self.choice = True; self.stop()
                await inter.response.defer()

            @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.red)
            async def cancel(self, inter: discord.Interaction, btn: Button):
                if inter.user.id != ctx.author.id:
                    return await inter.response.send_message("❌ Không phải lệnh của bạn.", ephemeral=True)
                self.choice = False; self.stop()
                await inter.response.defer()

        view = ConfirmView()
        msg  = await ctx.reply(embed=confirm_embed, view=view)
        await view.wait()

        if not view.choice:
            await msg.edit(content="❌ Đã huỷ đổi quà.", embed=None, view=None)
            return

        # Trừ point và ghi log
        new_pts = add_user_points(ctx.author.id, -item["points"], f"exchange:{item_id}")
        add_exchange_record(ctx.author.id, item_id, item["name"], item["points"])

        # Tạo ticket tự động
        guild = ctx.guild
        try:
            from core.data import get_cfg_category, get_cfg_support_role
            from cogs.ticket import _build_ticket_overwrites, get_next_ticket_number, TicketButtons

            number     = await get_next_ticket_number(ctx.bot)
            overwrites = _build_ticket_overwrites(guild, ctx.author)
            category   = discord.utils.get(guild.categories, id=get_cfg_category())
            channel    = await guild.create_text_channel(
                name=f"exchange-{number}",
                overwrites=overwrites,
                category=category,
                topic=f"{ctx.author.id}||exchange|{item_id}|open"
            )

            created_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
            ticket_embed = discord.Embed(
                title=f"💎 ĐỔI QUÀ  •  #{number}",
                description=f"Xin chào {ctx.author.mention}! 👋\nYêu cầu đổi quà của bạn đã được ghi nhận.\nStaff sẽ xử lý sớm nhất có thể.",
                color=0xF1C40F, timestamp=datetime.now(timezone.utc)
            )
            ticket_embed.add_field(name="👤 Người dùng", value=ctx.author.mention,      inline=True)
            ticket_embed.add_field(name="📦 Quà",        value=f"**{item['name']}**",  inline=True)
            ticket_embed.add_field(name="💎 Point đã dùng", value=f"**{item['points']:,} pt**", inline=True)
            ticket_embed.add_field(name="📝 Mô tả",      value=item["description"],    inline=True)
            ticket_embed.add_field(name="🕐 Thời gian",  value=created_at,              inline=True)
            ticket_embed.set_thumbnail(url=ctx.author.display_avatar.url)
            ticket_embed.set_footer(text="TuyTam Store  •  Exchange System")

            await channel.send(f"<@&{get_cfg_support_role()}> | {ctx.author.mention}", embed=ticket_embed, view=TicketButtons())

            # Thông báo thành công
            success_embed = discord.Embed(title="✅ Đổi Quà Thành Công!", color=0x57F287, timestamp=datetime.now(timezone.utc))
            success_embed.add_field(name="📦 Quà",        value=f"**{item['name']}**",     inline=True)
            success_embed.add_field(name="💎 Đã dùng",    value=f"**{item['points']:,} pt**", inline=True)
            success_embed.add_field(name="💼 Point còn",  value=f"**{new_pts:,} pt**",      inline=True)
            success_embed.add_field(name="🎫 Ticket",     value=channel.mention,            inline=False)
            success_embed.set_footer(text="Staff sẽ xử lý đơn đổi quà của bạn trong ticket")
            await msg.edit(embed=success_embed, view=None)

        except Exception as e:
            # Nếu tạo ticket lỗi, vẫn thông báo thành công nhưng báo liên hệ admin
            success_embed = discord.Embed(title="✅ Đổi Quà Ghi Nhận!", color=0x57F287)
            success_embed.add_field(name="📦 Quà",       value=f"**{item['name']}**",      inline=True)
            success_embed.add_field(name="💎 Đã dùng",   value=f"**{item['points']:,} pt**", inline=True)
            success_embed.add_field(name="💼 Point còn", value=f"**{new_pts:,} pt**",       inline=True)
            success_embed.add_field(name="⚠️ Lưu ý",    value="Không tạo được ticket tự động. Vui lòng liên hệ admin để nhận quà!", inline=False)
            await msg.edit(embed=success_embed, view=None)

    # ══════════════════════════════════════
    # .addreward — Admin thêm quà vào shop
    # ══════════════════════════════════════
    @commands.command(name="addreward")
    async def addreward_cmd(self, ctx, item_id: str = None, points: str = None, *, name: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được.")
        if not item_id or not points or not name:
            return await ctx.reply(
                "❌ Dùng: `.addreward <id> <points> <tên>`\n\n"
                "**Ví dụ:**\n"
                "`.addreward money_1m 50 💰 1M In-game Money`\n"
                "`.addreward elytra 300 🦋 Elytra`\n\n"
                "**Lưu ý về giá trị point:**\n"
                "> 1 lần vượt link = **1 point**\n"
                "> 50 point = user phải vượt link **50 lần**\n"
                "> Bạn thu Work.ink: 50 lần × ~75–200đ = **~3.750–10.000đ**\n"
                "> Đặt point sao cho thu đủ bù giá vốn item!"
            )
        try: pts = int(points)
        except ValueError: return await ctx.reply("❌ Point phải là số nguyên.")

        items = get_reward_shop()
        if any(i["id"] == item_id for i in items):
            return await ctx.reply(f"❌ ID `{item_id}` đã có rồi.")
        items.append({"id": item_id, "name": name, "points": pts, "description": name})
        save_reward_shop(items)

        embed = discord.Embed(title="✅ Đã Thêm Quà Vào Shop", color=0x57F287, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="📦 Tên",        value=f"**{name}**",   inline=True)
        embed.add_field(name="🔑 ID",         value=f"`{item_id}`",  inline=True)
        embed.add_field(name="💎 Point cần",  value=f"**{pts:,} pt** ({pts} lần vượt link)", inline=True)
        earn_min = pts * 75
        earn_max = pts * 200
        embed.add_field(
            name="💰 Ước tính thu Work.ink",
            value=f"**{earn_min:,}đ – {earn_max:,}đ** trước khi user đổi được",
            inline=False
        )
        await ctx.reply(embed=embed)

    # ══════════════════════════════════════
    # .delreward — Admin xoá quà khỏi shop
    # ══════════════════════════════════════
    @commands.command(name="delreward")
    async def delreward_cmd(self, ctx, item_id: str = None):
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin mới dùng được.")
        if not item_id:
            return await ctx.reply("❌ Dùng: `.delreward <id>`")
        items = get_reward_shop()
        found = next((i for i in items if i["id"] == item_id), None)
        if not found: return await ctx.reply(f"❌ Không tìm thấy item `{item_id}`.")
        items.remove(found)
        save_reward_shop(items)
        await ctx.reply(f"✅ Đã xoá **{found['name']}** khỏi shop!")


async def setup(bot):
    await bot.add_cog(PointCog(bot))
