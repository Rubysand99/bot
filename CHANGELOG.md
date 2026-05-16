# 📋 CHANGELOG — TuyTam Bot (Rudeus Bot)

> Format: `## [vX.X.X] — YYYY-MM-DD`
> Tăng version: patch khi sửa lỗi, minor khi thêm tính năng, major khi thay đổi lớn.
> Cập nhật `BOT_VERSION` trong `bot.py` và `cogs/admin.py`.

---

## [v3.6.1] — 2026-05-16

### 🐛 Sửa lỗi

**`cogs/minigame.py`**
- **Race condition Nối Từ** — Thêm `asyncio.Lock()` per session: 2 người gửi cùng lúc không còn cả 2 đều pass
- **Cooldown Nối Từ** — Thêm `player_last_time` dict: mỗi người phải chờ 3s trước khi nối tiếp, tránh spam
- **Tự chơi một mình (Nối Từ)** — Chặn `last_player == uid` nối 2 lần liên tiếp
- **Session Vua Tiếng Việt treo** — Thay `asyncio.sleep` giữ coroutine bằng `expire_time` timestamp; session tự dọn khi hết hạn thay vì block người dùng
- **Dọn session ngay (Vua TV)** — `del vtv_sessions[cid]` ngay khi có người trả lời đúng, không cần chờ timeout
- **Alias không dấu** — Thêm alias đầy đủ cho Bầu Cua (`bau`, `ca`, `ga`, `tom`) và BKB (`bua`, `keo`)
- **`cog_unload`** — Dọn tất cả session khi bot restart/reload cog

---

## [v3.6.0] — 2026-05-16

### ✨ Thêm mới
- `cogs/minigame.py` — 4 minigame: Bầu Cua, Búa Kéo Bao, Nối Từ, Vua Tiếng Việt
- `data/words_vi.txt` — Từ điển nối từ

### 🔧 Thay đổi
- Thêm `cogs.minigame` vào COGS list trong `bot.py`
- `BOT_VERSION = "3.6.0"`

---

## [v3.5.2] — 2026-05-16
- `.clearshop` — Admin xoá toàn bộ item shop

## [v3.5.1] — 2026-05-16
- Hệ thống đổi quà: `.shop`, `.exchange`, `.addreward`, `.delreward`
- Point redesign: 1 lần vượt Work.ink = 1 point, chỉ dùng đổi quà

## [v3.5.0] — 2026-05-16
- Hệ thống tích điểm: `.redeem`, `.point`, `.addpoint`, `.gencode`, `.pointcfg`, `.pointlog`, `.buixong`
- FastAPI backend trên Render
- Tích hợp point vào `.done`

## [v3.4.1] — 2026-05-15
- `cogs/mod.py` — Ban/Kick/Mute/Warn/Automod

## [v3.4.0] — 2026-05-14
- `cogs/logger.py`, slash commands, `.ping`, `.userinfo`, `.serverinfo`

## [v3.3.5] — 2026-05-12
- Tách bot.py thành cấu trúc Cog, MongoDB, tất cả cog cơ bản

---

> **Cấu trúc file:**
> ```
> tuytam_bot/
> ├── bot.py
> ├── CHANGELOG.md
> ├── core/data.py
> ├── data/words_vi.txt     ← từ điển nối từ
> └── cogs/
>     ├── minigame.py       ← v3.6.1
>     ├── point.py
>     ├── ticket.py
>     ├── mod.py
>     ├── admin.py
>     └── ...
> ```
