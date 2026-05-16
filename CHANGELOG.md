# 📋 CHANGELOG — TuyTam Bot (Rudeus Bot)

---

## [v3.6.3] — 2026-05-17

### ✨ Thêm mới
- **Cá cược point** cho tất cả minigame:
  - Tỉ lệ: thắng **+0.9x** tiền cược, thua **-1x** tiền cược
  - `.baucua <mặt> <point>` — VD: `.baucua bầu 10`
  - `.bkb <lựa chọn> <point>` — VD: `.bkb búa 10`
  - `.vtviet <point>` — VD: `.vtviet 10` rồi `.vtviet A`
  - `.start <point>` — Nối Từ kèm cược, winner nhận khi thắng bot
  - Kiểm tra đủ point trước khi cho cược
  - Hòa (BKB) không trừ/cộng point
  - Bầu Cua thắng x2/x3 nhân hệ số tương ứng
- **Bảng xếp hạng** (`.rank` / `.xephang`):
  - `.rank` — Top 10 tổng tất cả game
  - `.rank baucua` / `.rank bkb` / `.rank noitu` / `.rank vtv` — Từng game
  - Huy chương 🥇🥈🥉🏅
- **Thống kê cá nhân** (`.mgstats` / `.mystats`):
  - Số lần thắng từng game + tổng
  - Point hiện có
  - Xem của người khác: `.mgstats @user`
- `core/data.py` — Thêm `minigame_stats: {}` vào `_default_data()`

### 🔧 Thay đổi
- `.minigame` / `.mg` — Cập nhật help đầy đủ thông tin cá cược và tỉ lệ
- `BOT_VERSION = "3.6.3"`

---

## [v3.6.2] — 2026-05-16
- Kênh nối từ chỉ định — user nhắn thẳng không cần prefix
- `.setnoitu #kênh` — Admin cài kênh
- `.start` / `.stop` thay `.noitu start` / `.noitu stop`

## [v3.6.1] — 2026-05-16
- Fix race condition, cooldown per-user, session safety

## [v3.6.0] — 2026-05-16
- 4 minigame: Bầu Cua, Búa Kéo Bao, Nối Từ, Vua Tiếng Việt

## [v3.5.2] — 2026-05-16
- `.clearshop`

## [v3.5.1] — 2026-05-16
- Hệ thống đổi quà

## [v3.5.0] — 2026-05-16
- Hệ thống tích điểm

## [v3.4.1] — 2026-05-15
- cogs/mod.py

## [v3.4.0] — 2026-05-14
- logger, slash commands

## [v3.3.5] — 2026-05-12
- Cấu trúc Cog, MongoDB
