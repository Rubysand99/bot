"""
verify_server.py — Web server RÚT GỌN, giờ CHỈ còn webhook SePay (báo thanh toán) +
/health. Route /verify (xác minh thành viên qua IP, kèm _tokens/VERIFY_CALLBACKS/
create_token/check_ip_info) đã BỊ XOÁ cùng đợt với việc bỏ tính năng verify/IP ở
cogs/invite.py — xem CHANGELOG.md.

Chạy song song với bot trên Railway (cùng process qua asyncio — bot.py gọi
start_verify_server() lúc on_ready/first_boot).

⚠️ File này BẮT BUỘC chạy CHUNG process với cogs/shop_orders.py — route
/webhook/sepay chỉ forward payload cho PAYMENT_CALLBACK (biến RAM ở module này,
đăng ký 1 lần lúc cog_load() của shop_orders.py). Tách khác process (ví dụ đưa vào
bot_growth.py/bot_shop.py riêng mà KHÔNG mang theo cogs.shop_orders + không đổi lại
URL webhook trên SePay dashboard cho đúng service mới) → webhook SePay vẫn nhận được
nhưng KHÔNG ai xử lý (2 biến PAYMENT_CALLBACK ở 2 process khác nhau, không thấy nhau)
— cùng lớp bug mà VERIFY_CALLBACKS/cogs.invite từng gặp trước khi verify bị bỏ hẳn.

Env vars cần trên Railway:
  SEPAY_WEBHOOK_API_KEY — chuỗi bí mật TỰ ĐẶT, điền y hệt vào SePay dashboard (API Key
                          auth) khi tạo Webhook trỏ về <domain>/webhook/sepay
  PORT                  — Railway tự set, KHÔNG cần khai tay
(VERIFY_BASE_URL / VERIFY_SECRET của bản cũ không còn code nào đọc nữa — để lại trên
Railway cũng không sao, xoá đi cũng không ảnh hưởng gì.)
"""

import asyncio
import logging
import os
from typing import Callable, Awaitable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("verify_server")

SEPAY_WEBHOOK_API_KEY = os.getenv("SEPAY_WEBHOOK_API_KEY", "")

app = FastAPI(docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    return {"status": "ok"}


# ══════════════════════════════════════════
# SEPAY PAYMENT WEBHOOK — báo có tiền vào, chuyển tiếp cho callback xử lý
# ══════════════════════════════════════════
# Đăng ký ở dashboard SePay: URL = <domain>/webhook/sepay, Auth = API Key,
# header "Authorization: Apikey <SEPAY_WEBHOOK_API_KEY>".
#
# File này CỐ TÌNH không import core.data/discord (xem docstring đầu file — verify_server
# chỉ làm phần web thô, mọi xử lý Mongo/Discord nằm ở callback bên cogs/). Route dưới đây
# giữ đúng convention đó: chỉ auth + đọc payload rồi giao hết cho PAYMENT_CALLBACK (đăng ký
# 1 lần lúc cog_load() của cogs/shop_orders.py).
#
# Contract bắt buộc theo docs SePay: phải trả JSON {"success": true} + HTTP 200 trong
# 30s, nếu không SePay coi là lỗi và tự retry (Fibonacci backoff, tối đa 7 lần/5 tiếng).
# Vì vậy route LUÔN trả success=True ngay sau khi payload hợp lệ, xử lý thật chạy nền
# (create_task) — không chờ Mongo/Discord xong mới phản hồi, tránh timeout 30s.
PAYMENT_CALLBACK: Callable[[dict], Awaitable[None]] | None = None

def register_payment_callback(fn: Callable[[dict], Awaitable[None]]) -> None:
    global PAYMENT_CALLBACK
    PAYMENT_CALLBACK = fn


@app.post("/webhook/sepay")
async def sepay_webhook(request: Request):
    auth = request.headers.get("authorization", "")
    if not SEPAY_WEBHOOK_API_KEY or auth != f"Apikey {SEPAY_WEBHOOK_API_KEY}":
        log.warning("[SEPAY] ❌ Webhook auth sai hoặc chưa cấu hình SEPAY_WEBHOOK_API_KEY.")
        return JSONResponse({"success": False}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"success": False}, status_code=400)

    if PAYMENT_CALLBACK and payload.get("transferType") == "in":
        asyncio.create_task(PAYMENT_CALLBACK(payload))
    elif not PAYMENT_CALLBACK:
        log.warning("[SEPAY] ⚠️ Nhận được webhook nhưng chưa có PAYMENT_CALLBACK đăng ký "
                    "(cogs/shop_orders.py chưa load xong?).")

    return {"success": True}


# ══════════════════════════════════════════
# RUNNER — gọi từ bot.py
# ══════════════════════════════════════════

async def start_verify_server(host: str = "0.0.0.0", port: int = 8080):
    """Chạy FastAPI server trong event loop của bot."""
    import uvicorn
    import socket

    # Kiểm tra port trước khi bind — tránh uvicorn gọi sys.exit
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
    except OSError as e:
        log.warning(f"[VERIFY] Port {port} đang bị chiếm: {e}. Verify server không khởi động.")
        return  # Thoát nhẹ nhàng, không crash

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    await server.serve()
