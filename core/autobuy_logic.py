"""
core/autobuy_logic.py — Hàm THUẦN (không đụng discord/Mongo) của tính năng Auto Buy.

Port từ bot autobuy (Node.js, "Drew Store"): utils/db.js (parseAccountForm), index.js
(parseAmount), commands/stock.js (countCapes/formatPriceDisplay), utils/cardRenderer.js
(parseStats/formatRank/parsePrice...). Tách riêng để unit-test được mà không cần discord.
"""
import re

# ── Trạng thái tài khoản trong kho ──
ST_AVAILABLE = "AVAILABLE"
ST_PROCESSING = "PROCESSING"
ST_SOLD = "SOLD"

CUSTOM_EMOJI_RE = re.compile(r"<a?:[a-zA-Z0-9_]+:\d+>")
CUSTOM_EMOJI_ID_RE = re.compile(r"<a?:([a-zA-Z0-9_]+):(\d+)>")
# Gần đúng \p{Extended_Pictographic} của JS (module `re` của Python không hỗ trợ \p{...}).
UNICODE_EMOJI_RE = re.compile(
    "[\u2190-\u21ff\u2300-\u23ff\u25a0-\u27bf\u2900-\u297f\u2b00-\u2bff\u3030\u303d\u3297\u3299"
    "\U0001f000-\U0001faff\ufe0f\u200d]+"
)


def parse_amount(raw) -> int:
    """'140k' → 140000, '1.2M'/'1tr2' → 1200000, số < 1000 coi là nghìn. Y hệt parseAmount() của bot Node."""
    if not raw:
        return 0
    s = str(raw).lower().strip()
    digits = re.sub(r"[^0-9.]", "", s)
    try:
        num = float(digits) if digits else 0.0
    except ValueError:
        num = 0.0
    if "m" in s or "tr" in s:
        num *= 1_000_000
    elif "k" in s or (0 < num < 1000):
        num *= 1000
    return int(round(num))


def fmt_vnd(amount: int) -> str:
    return f"{int(amount):,}".replace(",", ".") + " VND"


def parse_price_number(raw) -> int:
    """Giá để vẽ card (mặc định 100k khi trống).
    FIX so với bot Node: parsePrice() của cardRenderer không hiểu đuôi 'M'/'tr' ('1.2M' ra 1.200đ) —
    ở đây dùng chung parse_amount()."""
    if not raw:
        return 100000
    return parse_amount(raw) or 100000


def format_price_abbr(num: int, upper: bool = True) -> str:
    """Giá rút gọn: 1_200_000 → '1.2M', 140000 → '140K' (hoặc '140k' khi upper=False)."""
    if num >= 999_500:   # 999.5K trở lên làm tròn thành 1M (tránh hiện '1000K')
        return re.sub(r"\.0$", "", f"{num / 1_000_000:.1f}") + "M"
    k = f"{round(num / 1000)}K"
    return k if upper else k.lower()


def format_price_display(raw) -> str:
    """Dạng ngắn dùng đặt tên kênh: '140k', '1.2M'.
    FIX so với bot Node: formatPriceDisplay() của stock.js không hiểu đuôi 'M'/'tr' nên '1.2M'
    ra '1k' — ở đây dùng chung parse_amount() nên '1.2M' → '1.2M'."""
    if not raw:
        return "0k"
    return format_price_abbr(parse_amount(raw), upper=False)


def count_capes(capes_text: str) -> int:
    if not capes_text:
        return 0
    custom = CUSTOM_EMOJI_RE.findall(capes_text)
    if custom:
        return len(custom)
    return sum(len(m) for m in UNICODE_EMOJI_RE.findall(capes_text) if m not in ("\ufe0f", "\u200d"))


def strip_emojis(text: str) -> str:
    if not text:
        return ""
    return UNICODE_EMOJI_RE.sub("", CUSTOM_EMOJI_RE.sub("", text)).strip()


def extract_custom_emojis(*texts) -> list[dict]:
    """Danh sách {name, url} emoji custom Discord (bỏ trùng, giữ thứ tự) — dùng làm ảnh cape trên card."""
    seen, out = set(), []
    for text in texts:
        if not text:
            continue
        for m in CUSTOM_EMOJI_ID_RE.finditer(text):
            url = f"https://cdn.discordapp.com/emojis/{m.group(2)}.png?size=128&quality=lossless"
            if url not in seen:
                seen.add(url)
                out.append({"name": m.group(1), "url": url})
    return out


def format_rank(raw_rank: str) -> str:
    stripped = strip_emojis(raw_rank)
    if not stripped:
        return "NON-RANK"
    clean = re.sub(r"-?RANK$", "", stripped.upper(), flags=re.I).strip() or "NON"
    return f"{clean}-RANK"


def parse_stats(raw_text: str) -> list[str]:
    """'150, 4500' hoặc '120h 50M 1500' → đúng 3 giá trị (thiếu thì '-')."""
    stripped = strip_emojis(raw_text)
    if not stripped:
        return ["-", "-", "-"]
    parts = [p.strip() for p in re.split(r"[,/|]+", stripped) if p.strip()]
    if len(parts) == 1 and " " in parts[0]:
        parts = parts[0].split()
    parts += ["-"] * (3 - len(parts))
    return parts[:3]


_FORM_FIELDS = {
    "username": "Username",
    "capes": "Capes",
    "recovery_code": "Recovery Code",
    "primary_email": "Primary Email",
    "security_email": "Security Email",
    "secret_key": "Secret Key",
    "password": "Password",
}


def parse_account_form(raw_text: str) -> dict | None:
    """Parse form dán vào /add_acc (mỗi dòng 'Nhãn: giá trị'). None nếu thiếu Username."""
    if not raw_text:
        return None
    out = {}
    for key, label in _FORM_FIELDS.items():
        m = re.search(rf"(?:^|\n)\s*{re.escape(label)}\s*:\s*(.*)", raw_text, flags=re.I)
        out[key] = m.group(1).strip() if m else ""
    if not out["username"]:
        return None
    return out


def make_stock_channel_name(state: str, price_display: str, cape_count: int) -> str:
    """✅・140k・3-cape (còn hàng) / ⌛ (đang giao dịch) / ❌ (đã bán)."""
    icon = {ST_AVAILABLE: "✅", ST_PROCESSING: "⌛", ST_SOLD: "❌"}.get(state, "✅")
    return f"{icon}・{price_display}・{cape_count}-cape"


def swap_status_icon(name: str, state: str) -> str:
    """Đổi emoji trạng thái ở ĐẦU tên kênh (✅/⌛/❌), giữ nguyên phần còn lại."""
    icon = {ST_AVAILABLE: "✅", ST_PROCESSING: "⌛", ST_SOLD: "❌"}[state]
    if re.match(r"^[✅⌛❌]", name):
        return re.sub(r"^[✅⌛❌]", icon, name, count=1)
    return f"{icon}-{name}"


_NODE_FIELD_MAP = {
    "username": "username", "capes": "capes", "rank": "rank", "price": "price", "status": "status",
    "password": "password", "statshpx": "statshpx", "statsdonut": "statsdonut", "note": "note",
    "primaryEmail": "primary_email", "securityEmail": "security_email", "recoveryCode": "recovery_code",
    "secretKey": "secret_key", "sellerId": "seller_id", "cardChannelId": "card_channel_id",
    "cardMessageId": "card_message_id",
}


def convert_node_account(d: dict) -> dict | None:
    """Đổi 1 bản ghi kho.json của bot Node (camelCase) sang schema ab_accounts (snake_case).
    Tài khoản đang PROCESSING bên Node → AVAILABLE (ticket Node không mang sang). None nếu thiếu username."""
    if not isinstance(d, dict):
        return None
    out = {}
    for src, dst in _NODE_FIELD_MAP.items():
        v = d.get(src)
        if v not in (None, ""):
            out[dst] = str(v) if dst in ("seller_id", "card_channel_id", "card_message_id") else v
    uname = str(out.get("username") or "").strip()
    if not uname:
        return None
    out["username"] = uname
    out["status"] = ST_SOLD if out.get("status") == ST_SOLD else ST_AVAILABLE
    return out
