"""
core/vietqr.py — Đọc mã VietQR (chuẩn NAPAS 247 / EMVCo) từ ẢNH để đăng ký bank không cần gõ tay.

`.shopbank` + đính kèm ảnh QR nhận tiền của ngân hàng → decode_qr_texts() ra chuỗi payload → parse_vietqr() lấy
mã BIN ngân hàng + số tài khoản (+ tên chủ TK nếu QR có) → lưu vào `shop_orders_banks`.

Payload VietQR là chuỗi TLV (tag 2 ký tự + độ dài 2 chữ số + giá trị), kết thúc bằng tag 63 = CRC16-CCITT:
  00 01 01 02 11/12 | 38 (tài khoản NAPAS) { 00 "A000000727" | 01 { 00 BIN(6) | 01 số TK/thẻ } | 02 "QRIBFTTA"(TK)/"QRIBFTTC"(thẻ) }
  | 53 "704" | 54 số tiền (tuỳ chọn) | 58 "VN" | 59 tên (tuỳ chọn) | 60 thành phố | 62 thông tin thêm | 63 CRC
Mã ngân hàng lưu vào bot là chính BIN: img.vietqr.io nhận cả BIN lẫn mã chữ (vietinbank, vcb...) trong URL ảnh QR.
Module THUẦN (decode ảnh import thư viện lười, có fallback); test ở tests/test_vietqr.py.
"""
import io
import logging
import re
import unicodedata

log = logging.getLogger(__name__)

NAPAS_GUID = "A000000727"
SERVICE_ACCOUNT = "QRIBFTTA"      # chuyển nhanh tới TÀI KHOẢN
SERVICE_CARD = "QRIBFTTC"         # chuyển nhanh tới SỐ THẺ — không dùng được cho bot
ACCOUNT_MIN, ACCOUNT_MAX = 6, 19      # số tài khoản ngân hàng VN: 6–19 chữ số
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

# BIN → tên hiển thị (chỉ để hiển thị; BIN lạ vẫn dùng được, bot gọi là "Ngân hàng (BIN …)")
BANKS_BY_BIN = {
    "970436": "Vietcombank", "970415": "VietinBank", "970418": "BIDV", "970405": "Agribank", "970422": "MB Bank",
    "970407": "Techcombank", "970416": "ACB", "970432": "VPBank", "970423": "TPBank", "970403": "Sacombank",
    "970437": "HDBank", "970441": "VIB", "970443": "SHB", "970448": "OCB", "970426": "MSB", "970431": "Eximbank",
    "970429": "SCB", "970454": "BanVietBank", "970449": "LPBank", "970425": "ABBANK", "970409": "BacABank",
    "970412": "PVcomBank", "970414": "Oceanbank", "970419": "NCB", "970424": "Shinhan Bank", "970427": "VietABank",
    "970428": "Nam A Bank", "970430": "PG Bank", "970433": "VietBank", "970438": "BaoViet Bank", "970440": "SeABank",
    "970442": "Hong Leong Bank", "970446": "Co-opBank", "970452": "KienlongBank", "970457": "Woori Bank",
    "970458": "UOB Vietnam", "970434": "Indovina Bank", "970439": "Public Bank", "970406": "DongA Bank",
    "970408": "GPBank", "970410": "Standard Chartered", "970421": "VRB", "970444": "CBBank",
    "546034": "CAKE by VPBank", "546035": "Ubank by VPBank", "963388": "Timo", "970462": "Kookmin Bank HN",
    "970463": "Kookmin Bank HCM", "970455": "IBK Bank HN", "970456": "IBK Bank HCM",
}


# Chữ MẪU trong lời hướng dẫn mà người dùng hay copy nguyên văn (từng gây ra bank lưu sai: số TK = "ma_bank")
PLACEHOLDER_WORDS = {"ma_bank", "mabank", "ma-bank", "bank_code", "bankcode", "sotk", "so_tk", "stk", "ten_nh", "tennh",
                     "chu_tk", "chutk", "ma_vietqr", "mavietqr", "<ma_bank>", "<sotk>"}


def normalize_account(account: str) -> str:
    """'0123 456.789' → '0123456789' (bỏ khoảng trắng, dấu chấm, gạch ngang)."""
    return "".join(ch for ch in (account or "") if ch not in " .-_\t")


def normalize_holder(name: str) -> str:
    """Tên chủ TK dạng ngân hàng dùng: IN HOA, không dấu, gọn khoảng trắng ("Nguyễn Tấn Hoàng Quân" → "NGUYEN TAN HOANG QUAN")."""
    s = unicodedata.normalize("NFD", name or "").replace("đ", "d").replace("Đ", "D")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^A-Za-z0-9\s.&'-]", " ", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def validate_bank(bank_code: str, account_number: str, account_holder: str = "") -> str | None:
    """Kiểm tra bank NHẬP TAY / ĐÃ LƯU có dùng được để dựng QR không. None = hợp lệ, ngược lại trả lý do (tiếng Việt).
    Chặn các lỗi thật đã gặp: copy nguyên chữ mẫu `ma_bank` làm số TK, nhập lộn thứ tự (số TK nằm ở ô chủ TK)."""
    code = (bank_code or "").strip()
    acc_raw = (account_number or "").strip()
    holder = (account_holder or "").strip()
    acc = normalize_account(acc_raw)
    if code.lower() in PLACEHOLDER_WORDS or not re.fullmatch(r"[A-Za-z0-9_.\-]{2,32}", code):
        return f"mã ngân hàng `{code or '(trống)'}` không hợp lệ (dùng mã VietQR như `mbbank`, `vietinbank`, hoặc mã BIN 6 số như `970422`)"
    if not (acc.isdigit() and ACCOUNT_MIN <= len(acc) <= ACCOUNT_MAX):
        return (f"số tài khoản `{acc_raw or '(trống)'}` không hợp lệ (phải là {ACCOUNT_MIN}–{ACCOUNT_MAX} chữ số"
                + (", bạn đang để chữ mẫu/chữ không phải số" if acc_raw and not any(c.isdigit() for c in acc_raw) else "") + ")")
    if holder and normalize_account(holder).isdigit() and len(normalize_account(holder)) >= ACCOUNT_MIN:
        return f"tên chủ tài khoản `{holder}` toàn là số — có thể bạn nhập lộn thứ tự (tên NH, mã NH, SỐ TK, tên chủ TK)"
    return None


def bank_problem(bank: dict | None) -> str | None:
    """Bank đã lưu của 1 user: None = dùng được; chuỗi = lý do không dùng được ("chưa đăng ký" hoặc dữ liệu sai)."""
    if not bank:
        return "chưa đăng ký ngân hàng"
    return validate_bank(bank.get("bank_code"), bank.get("account_number"), bank.get("account_holder", ""))


class QRDecoderMissing(RuntimeError):
    """Không có thư viện đọc QR nào cài trên máy (zxing-cpp / opencv / pyzbar)."""


# ───────────────────────── payload ─────────────────────────
def crc16_ccitt(data: str) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) — chuẩn của EMVCo QR."""
    crc = 0xFFFF
    for b in data.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def verify_crc(payload: str) -> bool:
    payload = (payload or "").strip()
    if len(payload) < 8 or payload[-8:-4] != "6304":
        return False
    return f"{crc16_ccitt(payload[:-4]):04X}" == payload[-4:].upper()


def parse_tlv(s: str) -> dict | None:
    """'TTLLvvvv…' → {tag: value} (lấy lần xuất hiện đầu của mỗi tag). None nếu sai cấu trúc."""
    out, i = {}, 0
    s = s or ""
    while i < len(s):
        if i + 4 > len(s):
            return None
        tag, ln = s[i:i + 2], s[i + 2:i + 4]
        if not ln.isdigit():
            return None
        end = i + 4 + int(ln)
        if end > len(s):
            return None
        out.setdefault(tag, s[i + 4:end])
        i = end
    return out


def parse_vietqr(payload: str) -> dict:
    """Trả về {"ok": True, bin, account_number, holder, amount, service} hoặc {"ok": False, "error": mã}.
    error: "not_vietqr" (không phải QR NAPAS) | "bad_crc" | "card" (QR số thẻ) | "bad_account" | "alias" (QR chứa mã định danh, kèm "bin")."""
    payload = (payload or "").strip()
    fields = parse_tlv(payload)
    if not fields or "38" not in fields:
        return {"ok": False, "error": "not_vietqr"}
    napas = parse_tlv(fields["38"])
    if not napas or (napas.get("00") or "").upper() != NAPAS_GUID:
        return {"ok": False, "error": "not_vietqr"}
    if not verify_crc(payload):
        return {"ok": False, "error": "bad_crc"}
    acq = parse_tlv(napas.get("01", "")) or {}
    bin_, acc = (acq.get("00") or "").strip(), (acq.get("01") or "").strip()
    service = (napas.get("02") or "").upper()
    if service == SERVICE_CARD:
        return {"ok": False, "error": "card"}
    if not (bin_.isdigit() and len(bin_) == 6):
        return {"ok": False, "error": "bad_account"}
    if acc.isalnum() and not acc.isdigit():
        # Một số ngân hàng (vd MB) nhúng MÃ ĐỊNH DANH (VQRQ…) thay cho số TK thật → không lấy được số TK từ QR
        # (số TK thật chỉ in trên hình) → admin dùng `.setbank`/nhập tay với số TK in trên ảnh.
        return {"ok": False, "error": "alias", "bin": bin_}
    if not (acc.isdigit() and ACCOUNT_MIN <= len(acc) <= ACCOUNT_MAX):
        return {"ok": False, "error": "bad_account"}
    return {"ok": True, "bin": bin_, "account_number": acc, "holder": (fields.get("59") or "").strip(),
            "amount": (fields.get("54") or "").strip(), "service": service or SERVICE_ACCOUNT}


def bank_name_from_bin(bin_: str) -> str:
    return BANKS_BY_BIN.get(bin_) or f"Ngân hàng (BIN {bin_})"


def pick_vietqr(texts: list[str]) -> dict:
    """Trong các QR tìm thấy trên ảnh lấy cái VietQR hợp lệ đầu tiên; không có thì trả lỗi 'đáng nói nhất'."""
    if not texts:
        return {"ok": False, "error": "no_qr"}
    best = None
    rank = {"alias": 4, "bad_crc": 3, "card": 3, "bad_account": 2, "not_vietqr": 1}
    for t in texts:
        r = parse_vietqr(t)
        if r["ok"]:
            return r
        if best is None or rank.get(r["error"], 0) > rank.get(best["error"], 0):
            best = r
    return best


# ───────────────────────── ảnh → chuỗi QR ─────────────────────────
def _decode_one(img) -> list[str]:
    errors = []
    try:
        import zxingcpp
        res = zxingcpp.read_barcodes(img)
        texts = [r.text for r in res if "QR" in str(r.format).upper()]
        return texts or [r.text for r in res]
    except ImportError:
        errors.append("zxing-cpp")
    try:
        import cv2
        import numpy as np
        arr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        text, _pts, _ = cv2.QRCodeDetector().detectAndDecode(arr)
        return [text] if text else []
    except ImportError:
        errors.append("opencv")
    try:
        from pyzbar.pyzbar import decode as zbar_decode
        return [r.data.decode("utf-8", "ignore") for r in zbar_decode(img)]
    except ImportError:
        errors.append("pyzbar")
    raise QRDecoderMissing("thiếu thư viện đọc QR (" + ", ".join(errors) + ")")


def decode_qr_texts(data: bytes) -> list[str]:
    """Ảnh (bytes) → danh sách chuỗi QR đọc được. Thử ảnh gốc, ảnh xám, ảnh thu nhỏ/phóng to. Chạy trong thread."""
    from PIL import Image
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("ảnh quá lớn")
    img = Image.open(io.BytesIO(data))
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise ValueError("ảnh quá lớn")
    img.load()
    base = img.convert("RGB")
    variants = [base, base.convert("L")]
    big = max(base.size)
    if big > 1600:
        small = base.copy(); small.thumbnail((1600, 1600), Image.LANCZOS); variants.append(small)
    elif big < 600:
        variants.append(base.resize((base.width * 3, base.height * 3), Image.LANCZOS))
    for v in variants:
        texts = _decode_one(v)
        if texts:
            return texts
    return []
