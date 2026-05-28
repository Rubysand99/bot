# TuyTam Bot (Rudeus Bot) — Python/discord.py/MongoDB
**Deploy:** Railway ← GitHub `main` | **DB:** MongoDB Atlas `tuytam_bot.bot_data` (_id:"main") + `tuytam_bot.giveaways`
**Backend:** Render (FastAPI, LootLabs postback → Discord webhook)

---

## Cấu trúc

```
bot.py          # Entry: load cogs, on_ready→init_data_cache(), on_message (legit/vouch), auto-backfill
core/data.py    # MongoDB + _data_cache, get_or_fetch_channel(), parse_amount(), fmt_amount(), cfg getters/setters
cogs/
  admin.py      # .st (settings UI), .help, .backfill, .mkchannel, mod cmds, slash admin
  ticket.py     # Panel → ticket kênh, .done/.sellerchannel/.sch, QR seller
  giveaway.py   # /giveaway /gend /greroll /gwlist, _gw_tasks dict
  balance.py    # Cộng/trừ/set/reset balance (VNĐ)
  point.py      # .gencode .redeem .addpoint .setpoint .pointall .shop .exchange
  minigame.py   # Bầu Cua nhiều người (.bc open/cancel), Búa Kéo Bao (.bkb)
  ai_chat.py    # Groq AI, bỏ qua msg bắt đầu . hoặc !
  invite.py     # Tracking invite, leaderboard, .resetinvite
  mod.py        # Ban/Kick/Mute/Unmute/Warn/Automod
  logger.py     # send_log(bot, "CAT", "title", fields=[("k","v",inline)])
data/words_vi.txt
```

## Conventions
- **Admin gate:** `if ctx.author.id not in ADMIN_IDS: return` (import từ `core.data`)
- **Staff check:** `is_staff_member()` — ADMIN_IDS + `BUILDER_BASE_ROLE_ID=1484158340849205308`
- **Log:** `await send_log(bot, "TICKET", "title", fields=[...])`→ kênh `cfg_log_rudy`
- **Channel fetch:** dùng `get_or_fetch_channel(bot, id)` — KHÔNG dùng `bot.get_channel()`
- **Response:** PUBLIC (bỏ ephemeral), trừ ticket panel button
- **Const:** `CODE_GEN_LOG_CHANNEL_ID = 1504434579967316021`
- discord.py 2.x (app_commands cho slash)

## Cách dùng file này
Mỗi chat mới: upload file này + mô tả vấn đề + upload file .py liên quan.

---

## Changelog

### [v3.8.0] 2026-05-22
- `ticket.py` — Xóa `.mkchannel` trùng → fix `CommandRegistrationError` (admin.py không load được)

### [v3.7.9] 2026-05-22
- `core/data.py` — Thêm `get_or_fetch_channel()` (cache → fetch_channel)
- `admin/ticket/giveaway/bot` — Thay toàn bộ `bot.get_channel()` → `get_or_fetch_channel()`
- `.backfill` + auto-backfill: xử lý đúng thứ tự cũ→mới, thả ✅ + đổi tên kênh +1

### [v3.7.8] 2026-05-22
- `admin.py` — `.backfill [số]`: quét kênh legit, thả ✅ cho tin +1legit bị bỏ sót (mặc định 25, max 100)

### [v3.7.7] 2026-05-22
- `admin.py` — `.help` overview + `.help <mục>` chi tiết (mod/ticket/point/minigame/ai/invite/dichvu/giveaway/admin), alias tiếng Việt

### [v3.7.6] 2026-05-22
- `giveaway.py` — Embed giveaway giữ nguyên sau khi kết thúc, disable nút + gửi tin winner riêng (có link)

### [v3.7.5] 2026-05-22
- `admin.py` — Xóa `.qr` prefix trùng với `ticket.py`
- `ticket.py` — `.mkchannel` → `.sellerchannel`/`.sch`; `.done` chỉ ADMIN_IDS
- `core/data.py` — Thêm `get_seller_qr`, `save_seller_qr`, `get_all_seller_qr`

### [v3.7.4] 2026-05-20
- `core/data.py` — `BUILDER_BASE_ROLE_ID`, cập nhật `is_staff_member()`
- `ticket.py` — Builder Base tự động vào overwrites khi tạo ticket

### [v3.7.3] 2026-05-18
- `backend/main.py` — LootLabs postback → Discord webhook embed (mã/point/hạn/unique_id)

### [v3.7.2] 2026-05-18
- `point.py` — Redeem thành công + `.gencode` → log embed vào `CODE_GEN_LOG_CHANNEL_ID`

### [v3.7.1] 2026-05-17
- `.setpoint <ID> <số>`, `.pointall`/`.allpoints`/`.pointlist` (top 20, tổng point)

### [v3.7.0] 2026-05-17
- Bầu Cua nhiều người: `.bc open/cancel`, `.setbaucua`, 4-6 người, 30s, tỉ lệ x1→+0.9pt
- Xóa: Nối Từ, Vua Tiếng Việt

### [v3.6.x] 2026-05-16
- Cá cược point minigame (WIN_RATE 0.9x), `.rank`, `.mgstats`
- Kênh nối từ chỉ định, fix race condition, cooldown per-user

### [v3.5.x] 2026-05-16
- Point system đầy đủ, FastAPI/Render, Linkvertise, `.shop .exchange .addreward .delreward .clearshop`

### [v3.4.x] 2026-05-14–15
- `mod.py` Ban/Kick/Mute/Warn/Automod; `logger.py`; slash commands; `.ping .userinfo .serverinfo`

### [v3.3.5] 2026-05-12
- Tách bot.py 6000 dòng → cấu trúc Cog, MongoDB + cache
