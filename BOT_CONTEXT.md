# TuyTam Bot (Rudeus Bot) — Python/discord.py/MongoDB
**Deploy:** Railway ← GitHub `main` | **DB:** MongoDB Atlas `tuytam_bot.bot_data` (_id:"main") + `tuytam_bot.giveaways`

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
  banking.py    # Casso webhook, txlog, stats
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
- discord.py 2.x (app_commands cho slash)

## Cách dùng file này
Mỗi chat mới: upload file này + mô tả vấn đề + upload file .py liên quan.

---

## Changelog

### [v3.9.5] 2026-06-01
- `giveaway.py` — `.gwstatus`: xem giveaway đang chạy & đã kết thúc
- `admin.py` — Cập nhật `.help giveaway` thêm `.gwstatus`

### [v3.9.4] 2026-05-23
- `admin.py` — Cập nhật `.help` toàn bộ
- `bot.py` — Parse CHANGELOG.md khi khởi động, hiển thị entry mới nhất

### [v3.8.2] 2026-05-29
- `logger.py` — Thay `bot.get_channel()` → `get_or_fetch_channel()`
- `logger.py` — Fix `interaction.channel.mention` tránh lỗi PartialMessageable/DM
- `logger.py` — `.setuplog` nhận arg `[category_id]` tùy chọn

### [v3.8.1] 2026-05-29
- `ticket.py` — Ticket **Order Base** ping thêm role `BUILDER_BASE_ROLE_ID` khi tạo kênh

### [v3.8.0] 2026-05-22
- `ticket.py` — Xóa `.mkchannel` trùng → fix `CommandRegistrationError`

### [v3.7.9] 2026-05-22
- `core/data.py` — Thêm `get_or_fetch_channel()` (cache → fetch_channel)
- `admin/ticket/giveaway/bot` — Thay toàn bộ `bot.get_channel()` → `get_or_fetch_channel()`

### [v3.7.8] 2026-05-22
- `admin.py` — `.backfill [số]`: quét kênh legit, thả ✅ cho tin +1legit bị bỏ sót

### [v3.7.7] 2026-05-22
- `admin.py` — `.help` overview + `.help <mục>` chi tiết, alias tiếng Việt

### [v3.7.6] 2026-05-22
- `giveaway.py` — Embed giveaway giữ nguyên sau khi kết thúc, disable nút + gửi tin winner riêng

### [v3.7.5] 2026-05-22
- `admin.py` — Xóa `.qr` prefix trùng với `ticket.py`
- `ticket.py` — `.mkchannel` → `.sellerchannel`/`.sch`; `.done` chỉ ADMIN_IDS
- `core/data.py` — Thêm `get_seller_qr`, `save_seller_qr`, `get_all_seller_qr`

### [v3.7.4] 2026-05-20
- `core/data.py` — `BUILDER_BASE_ROLE_ID`, cập nhật `is_staff_member()`
- `ticket.py` — Builder Base tự động vào overwrites khi tạo ticket

### [v3.4.x] 2026-05-14–15
- `mod.py` Ban/Kick/Mute/Warn/Automod; `logger.py`; slash commands

### [v3.3.5] 2026-05-12
- Tách bot.py 6000 dòng → cấu trúc Cog, MongoDB + cache
