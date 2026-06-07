"""
verify_server.py — Web server xác minh thành viên Discord + IP tracking.
Chạy song song với bot trên Railway (cùng process qua asyncio).

Luồng:
  1. Bot gửi DM link: /verify?token=<token>
  2. User click → server lưu IP, check VPN, check IP trùng
  3. Callback về bot qua shared dict VERIFY_CALLBACKS
  4. Bot xử lý kết quả: đánh dấu fake nếu IP trùng inviter/member khác

Env vars cần thêm vào Railway:
  VERIFY_BASE_URL  — URL public của Railway app, vd: https://tuytam-bot.up.railway.app
  VERIFY_SECRET    — chuỗi bí mật bất kỳ để sign token, vd: mysecret123
"""

import asyncio
import hashlib
import hmac
import logging
import os
import time
from typing import Callable, Awaitable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

log = logging.getLogger("verify_server")

VERIFY_SECRET  = os.getenv("VERIFY_SECRET", "changeme")
VERIFY_BASE_URL = os.getenv("VERIFY_BASE_URL", "http://localhost:8080")

# ── Token store: token → {user_id, guild_id, inviter_id, expires_at} ──
_tokens: dict[str, dict] = {}

# ── IP records: ip → list of user_ids đã dùng IP này (persist qua MongoDB từ invite.py) ──
# Đây là in-memory mirror, invite.py sẽ sync với MongoDB

# ── Callbacks: token → coroutine function(result_dict) ──
# invite.py đăng ký callback khi tạo token, server gọi khi verify xong
VERIFY_CALLBACKS: dict[str, Callable[[dict], Awaitable[None]]] = {}

app = FastAPI(docs_url=None, redoc_url=None)


# ══════════════════════════════════════════
# TOKEN HELPERS
# ══════════════════════════════════════════

def create_token(user_id: int, guild_id: int, inviter_id: int | None, ttl: int = 600) -> str:
    """Tạo token HMAC có thời hạn TTL giây (mặc định 10 phút)."""
    raw     = f"{user_id}:{guild_id}:{int(time.time())}"
    sig     = hmac.new(VERIFY_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    token   = f"{raw}:{sig}"
    _tokens[token] = {
        "user_id":    user_id,
        "guild_id":   guild_id,
        "inviter_id": inviter_id,
        "expires_at": time.time() + ttl,
    }
    return token


def get_token_data(token: str) -> dict | None:
    data = _tokens.get(token)
    if not data:
        return None
    if time.time() > data["expires_at"]:
        _tokens.pop(token, None)
        return None
    return data


def build_verify_url(token: str) -> str:
    return f"{VERIFY_BASE_URL}/verify?token={token}"


# ══════════════════════════════════════════
# IP CHECK — ip-api.com (miễn phí, 1000 req/phút)
# ══════════════════════════════════════════

async def check_ip_info(ip: str) -> dict:
    """
    Trả về dict:
      is_vpn   : bool — đang dùng VPN/Proxy/Tor/Hosting
      country  : str  — mã quốc gia (VN, US, ...)
      isp      : str  — nhà mạng
      raw      : dict — toàn bộ response ip-api
    """
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,proxy,hosting,query,country,isp,org"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r    = await client.get(url)
            data = r.json()
        is_vpn = bool(data.get("proxy") or data.get("hosting"))
        return {
            "is_vpn":  is_vpn,
            "country": data.get("country", "?"),
            "isp":     data.get("isp", "?"),
            "raw":     data,
        }
    except Exception as e:
        log.warning(f"[VERIFY] ip-api lỗi: {e}")
        return {"is_vpn": False, "country": "?", "isp": "?", "raw": {}}


# ══════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════

@app.get("/verify", response_class=HTMLResponse)
async def verify_page(request: Request, token: str = ""):
    ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()

    # ── Kiểm tra token ──
    data = get_token_data(token)
    if not data:
        return HTMLResponse(_html_error("Link xác minh không hợp lệ hoặc đã hết hạn.<br>Vui lòng yêu cầu bot gửi lại."), status_code=400)

    # ── Xóa token (1 lần dùng) ──
    _tokens.pop(token, None)

    # ── Check IP ──
    ip_info = await check_ip_info(ip)

    # ── Gọi callback về invite.py ──
    cb = VERIFY_CALLBACKS.pop(token, None)
    if cb:
        asyncio.create_task(cb({
            "user_id":    data["user_id"],
            "guild_id":   data["guild_id"],
            "inviter_id": data["inviter_id"],
            "ip":         ip,
            "is_vpn":     ip_info["is_vpn"],
            "country":    ip_info["country"],
            "isp":        ip_info["isp"],
        }))

    if ip_info["is_vpn"]:
        return HTMLResponse(_html_vpn_warning(ip_info["country"], ip_info["isp"]))

    return HTMLResponse(_html_success())


@app.get("/health")
async def health():
    return {"status": "ok"}


# ══════════════════════════════════════════
# HTML TEMPLATES
# ══════════════════════════════════════════

def _base_html(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — TuyTam Store</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee;
           display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
    .card {{ background: #16213e; border-radius: 16px; padding: 40px 32px;
             max-width: 420px; width: 90%; text-align: center; box-shadow: 0 8px 32px #0005; }}
    .icon {{ font-size: 56px; margin-bottom: 16px; }}
    h1 {{ font-size: 1.4rem; margin-bottom: 10px; }}
    p  {{ color: #aaa; line-height: 1.6; font-size: 0.95rem; }}
    .badge {{ display: inline-block; margin-top: 20px; background: #0f3460;
              padding: 6px 16px; border-radius: 20px; font-size: 0.85rem; color: #7eb8ff; }}
  </style>
</head>
<body><div class="card">{body}</div></body>
</html>"""


def _html_success() -> str:
    return _base_html("Xác minh thành công", """
      <div class="icon">✅</div>
      <h1>Xác minh thành công!</h1>
      <p>Bạn đã được xác minh trên <strong>TuyTam Store</strong>.<br>
         Quay lại Discord để tiếp tục.</p>
      <span class="badge">TuyTam Store</span>
    """)


def _html_vpn_warning(country: str, isp: str) -> str:
    return _base_html("Phát hiện VPN/Proxy", f"""
      <div class="icon">⚠️</div>
      <h1>Phát hiện VPN / Proxy</h1>
      <p>Hệ thống phát hiện bạn đang dùng <strong>VPN hoặc Proxy</strong>
         ({isp}, {country}).<br><br>
         Vui lòng <strong>tắt VPN</strong> rồi quay lại Discord và yêu cầu bot
         gửi lại link xác minh.</p>
      <span class="badge">TuyTam Store</span>
    """)


def _html_error(msg: str) -> str:
    return _base_html("Lỗi xác minh", f"""
      <div class="icon">❌</div>
      <h1>Xác minh thất bại</h1>
      <p>{msg}</p>
      <span class="badge">TuyTam Store</span>
    """)


# ══════════════════════════════════════════
# RUNNER — gọi từ bot.py
# ══════════════════════════════════════════

async def start_verify_server(host: str = "0.0.0.0", port: int = 8080):
    """Chạy FastAPI server trong event loop của bot."""
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
