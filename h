[1mdiff --git a/cogs/logger.py b/cogs/logger.py[m
[1mindex 29071de..2a2dfd4 100644[m
[1m--- a/cogs/logger.py[m
[1m+++ b/cogs/logger.py[m
[36m@@ -12,6 +12,8 @@[m [mNhóm kênh:[m
   ai       → AI_USED[m
   admin    → CMD_USED, SLASH_USED, SETTINGS[m
   general  → INFO, ERROR, INVITE, RATING (fallback)[m
[32m+[m
[32m+[m[32mLog format: plain text thay vì embed để không đẩy trôi history.[m
 """[m
 [m
 from datetime import datetime, timezone, timedelta[m
[36m@@ -77,6 +79,7 @@[m [mLOG_ROUTES: dict[str, str] = {[m
     "CMD_USED":        "admin",[m
     "SLASH_USED":      "admin",[m
     "SETTINGS":        "admin",[m
[32m+[m[32m    "BANK_TXNS":       "general",[m
     "INVITE":          "general",[m
     "RATING":          "general",[m
     "ERROR":           "general",[m
[36m@@ -110,6 +113,58 @@[m [mdef get_log_channel(group: str) -> int | None:[m
 def get_all_log_channels() -> dict[str, int]:[m
     return get_log_channels()[m
 [m
[32m+[m[32m# ══════════════════════════════════════════[m
[32m+[m[32m# FORMAT PLAIN TEXT LOG[m
[32m+[m[32m# ══════════════════════════════════════════[m
[32m+[m
[32m+[m[32mdef _fmt_log_text([m
[32m+[m[32m    event_type: str,[m
[32m+[m[32m    title: str,[m
[32m+[m[32m    fields: list[tuple] = None,[m
[32m+[m[32m    description: str = None,[m
[32m+[m[32m    user: discord.Member | discord.User = None,[m
[32m+[m[32m) -> str:[m
[32m+[m[32m    """[m
[32m+[m[32m    Chuyển log thành plain text 1 dòng hoặc vài dòng nhỏ gọn.[m
[32m+[m[32m    Ví dụ:[m
[32m+[m[32m      🎫 [TICKET_CREATE] Ticket Tạo — money-042[m
[32m+[m[32m      › 🎫 Kênh: #money-042  › 🏷️ Loại: 🛒 MUA HÀNG  › 👤 Người tạo: @Ruby[m
[32m+[m[32m      🕐 05/06/2026 14:32 UTC+7[m
[32m+[m[32m    """[m
[32m+[m[32m    icon, _ = LOG_ICONS.get(event_type, ("📋", 0))[m
[32m+[m[32m    now_vn = datetime.now(timezone(timedelta(hours=7)))[m
[32m+[m[32m    time_str = now_vn.strftime("%d/%m/%Y %H:%M")[m
[32m+[m
[32m+[m[32m    lines = [][m
[32m+[m
[32m+[m[32m    # Dòng 1: header[m
[32m+[m[32m    header = f"{icon} `[{event_type}]` **{title}**"[m
[32m+[m[32m    if user:[m
[32m+[m[32m        header += f"  •  _{user}_"[m
[32m+[m[32m    lines.append(header)[m
[32m+[m
[32m+[m[32m    # Dòng 2: description (nếu có, cắt ngắn)[m
[32m+[m[32m    if description:[m
[32m+[m[32m        short_desc = description[:200].replace("\n", " ")[m
[32m+[m[32m        lines.append(f"> {short_desc}")[m
[32m+[m
[32m+[m[32m    # Dòng 3+: fields gộp trên cùng 1 dòng (ngắn gọn)[m
[32m+[m[32m    if fields:[m
[32m+[m[32m        field_parts = [][m
[32m+[m[32m        for f in fields:[m
[32m+[m[32m            name  = f[0][m
[32m+[m[32m            value = str(f[1])[:80]  # giới hạn độ dài value[m
[32m+[m[32m            field_parts.append(f"**{name}:** {value}")[m
[32m+[m[32m        # Tối đa 3 field/dòng[m
[32m+[m[32m        for i in range(0, len(field_parts), 3):[m
[32m+[m[32m            lines.append("› " + "  ·  ".join(field_parts[i:i+3]))[m
[32m+[m
[32m+[m[32m    # Dòng cuối: timestamp[m
[32m+[m[32m    lines.append(f"-# 🕐 {time_str} UTC+7")[m
[32m+[m
[32m+[m[32m    return "\n".join(lines)[m
[32m+[m
[32m+[m
 # ══════════════════════════════════════════[m
 # SEND LOG[m
 # ══════════════════════════════════════════[m
[36m@@ -127,31 +182,14 @@[m [masync def send_log([m
     Gửi log vào kênh tương ứng với nhóm của event_type.[m
     Fallback về kênh log_rudy nếu nhóm chưa được cài.[m
     fields: list of (name, value, inline?)[m
[32m+[m
[32m+[m[32m    Gửi dưới dạng plain text để tránh đẩy trôi history.[m
[32m+[m[32m    Báo cáo tổng hợp (daily report) vẫn dùng embed vì cần layout đẹp.[m
     """[m
     if bot is None:[m
         return[m
 [m
[31m-    icon, default_color = LOG_ICONS.get(event_type, ("📋", 0x5865F2))[m
[31m-    embed = discord.Embed([m
[31m-        title=f"{icon}  {title}",[m
[31m-        color=color or default_color,[m
[31m-        timestamp=datetime.now(timezone.utc),[m
[31m-    )[m
[31m-    if description:[m
[31m-        embed.description = description[m
[31m-    if user:[m
[31m-        embed.set_author([m
[31m-            name=str(user),[m
[31m-            icon_url=user.display_avatar.url if hasattr(user, "display_avatar") else None,[m
[31m-        )[m
[31m-    if fields:[m
[31m-        for f in fields:[m
[31m-            name   = f[0][m
[31m-            value  = f[1][m
[31m-            inline = f[2] if len(f) > 2 else True[m
[31m-            embed.add_field(name=name, value=value, inline=inline)[m
[31m-    embed.add_field(name="🕐 Thời gian", value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", inline=False)[m
[31m-    embed.set_footer(text=footer or f"TuyTam Store  •  {event_type}")[m
[32m+[m[32m    text = _fmt_log_text(event_type, title, fields, description, user)[m
 [m
     # Xác định kênh đích[m
     group   = LOG_ROUTES.get(event_type, "general")[m
[36m@@ -164,7 +202,7 @@[m [masync def send_log([m
         print(f"[LOG] ⚠️ Không tìm được kênh {ch_id} cho '{group}' ({event_type}), bỏ qua.")[m
         return[m
     try:[m
[31m-        await channel.send(embed=embed)[m
[32m+[m[32m        await channel.send(text)[m
     except Exception as e:[m
         print(f"[LOG] ❌ Không gửi được log {event_type} → #{channel.name}: {e}")[m
 [m
[36m@@ -202,7 +240,8 @@[m [mclass LoggerCog(commands.Cog):[m
         await self.bot.wait_until_ready()[m
 [m
     async def _send_daily_report(self):[m
[31m-        """Build và gửi embed báo cáo 24h qua vào kênh general log."""[m
[32m+[m[32m        """Build và gửi embed báo cáo 24h qua vào kênh general log.[m
[32m+[m[32m        Báo cáo này vẫn dùng embed vì cần layout đẹp để đọc tổng kết."""[m
         now       = datetime.now(timezone.utc)[m
         since     = now - timedelta(hours=24)[m
         date_label = now.strftime("%d/%m/%Y")[m
[36m@@ -223,9 +262,6 @@[m [mclass LoggerCog(commands.Cog):[m
         ticket_count  = len(day_recs)[m
         ticket_amount = sum(t.get("amount", 0) for t in day_recs)[m
 [m
[31m-[m
[31m-[m
[31m-[m
         # ── Banking (Casso): giao dịch ngân hàng 24h qua ──[m
         from core.data import _data_cache[m
         banking_txs = list((_data_cache or {}).get("_banking_txs", []))[m
[36m@@ -244,7 +280,7 @@[m [mclass LoggerCog(commands.Cog):[m
             except Exception:[m
                 pass[m
 [m
[31m-                # ── Giveaway: kết thúc trong 24h qua ──[m
[32m+[m[32m        # ── Giveaway: kết thúc trong 24h qua ──[m
         gw_data    = load_giveaways_data()[m
         gw_running = sum(1 for gw in gw_data.values() if not gw.get("ended"))[m
         gw_ended   = 0[m
[36m@@ -258,9 +294,6 @@[m [mclass LoggerCog(commands.Cog):[m
                 except Exception:[m
                     pass[m
 [m
[31m-        # ── Member: join/leave 24h qua (từ audit log nếu có quyền) ──[m
[31m-        # Không dùng audit log để tránh phức tạp — bỏ qua phần này[m
[31m-[m
         # ── Top buyer 24h qua ──[m
         buyer_totals: dict = {}[m
         for t in day_recs:[m
[36m@@ -269,7 +302,7 @@[m [mclass LoggerCog(commands.Cog):[m
                 buyer_totals[uid] = buyer_totals.get(uid, 0) + t.get("amount", 0)[m
         top3 = sorted(buyer_totals.items(), key=lambda x: x[1], reverse=True)[:3][m
 [m
[31m-        # ── Build embed ──[m
[32m+[m[32m        # ── Build embed (báo cáo tổng hợp dùng embed) ──[m
         embed = discord.Embed([m
             title=f"📊  Báo Cáo 24h — {date_label}",[m
             color=0x5865F2,[m
[36m@@ -286,8 +319,6 @@[m [mclass LoggerCog(commands.Cog):[m
             inline=True,[m
         )[m
 [m
[31m-[m
[31m-[m
         # Banking Casso[m
         embed.add_field([m
             name="🏦 Ngân hàng (Casso)",[m
[36m@@ -512,12 +543,10 @@[m [mclass LoggerCog(commands.Cog):[m
                         ("📌 Kênh test",   channel.mention,           True),[m
                     ],[m
                     description=([m
[31m-                        f"Đây là log **test** từ lệnh `.testlog`.\n"[m
[31m-                        f"Nếu bạn thấy tin này → kênh `{channel.name}` hoạt động bình thường ✅"[m
[31m-                        + (f"\n⚠️ *Dùng kênh fallback vì nhóm `{grp}` chưa được cài riêng.*" if using_fallback else "")[m
[32m+[m[32m                        f"Log test từ `.testlog` — kênh `{channel.name}` hoạt động bình thường ✅"[m
[32m+[m[32m                        + (f" ⚠️ Dùng fallback vì `{grp}` chưa cài riêng." if using_fallback else "")[m
                     ),[m
                     user=ctx.author,[m
[31m-                    footer=f"testlog • {grp} • {event_type}",[m
                 )[m
                 tag = " *(fallback)*" if using_fallback else ""[m
                 status_lines.append(f"✅ **{label}** → {channel.mention}{tag}")[m
