"""
core/ai_agents.py — Đăng ký "agent" AI chuyên biệt + router phân loại (v4.15.0, ý #8).

Vì sao cần: `.ai` giờ có 15 admin tool (ADMIN_TOOL_SCHEMAS), sắp tới sẽ có thêm
tool báo cáo (#17) rồi có thể nhiều hơn nữa. Nhồi TOÀN BỘ tool vào 1 lần gọi
model làm model dễ chọn nhầm tool + prompt phình to tốn quota. Multi-agent giải
quyết bằng cách: mỗi agent chỉ mang system prompt + tool subset của riêng lĩnh
vực đó; 1 bước router NHẸ (không tool, temperature=0) phân loại yêu cầu vào
đúng 1 agent trước khi chạy vòng lặp tool-calling thật.

CÁCH THÊM AGENT MỚI (vd khi làm #17 Báo cáo):
1. Viết REPORT_TOOL_SCHEMAS + handler trong core/ai_tools.py như các tool khác.
2. Sửa AGENTS["report"]["tools"] = REPORT_TOOL_SCHEMAS (đang để rỗng = stub).
3. Không cần sửa gì ở router hay ai_chat.py — tự động chạy được.
"""

from core.ai_tools import QUERY_TOOL_SCHEMAS, ADMIN_TOOL_SCHEMAS

SUPPORT_SYSTEM = (
    "Bạn là trợ lý AI của TuyTam Store — một cửa hàng game. "
    "Hãy trả lời ngắn gọn, thân thiện, bằng tiếng Việt. "
    "Nếu người dùng hỏi về ticket/gói seller/invite/lịch sử mua hàng của CHÍNH họ, "
    "hãy dùng tool tương ứng để tra cứu thay vì đoán."
)

OPS_SYSTEM = (
    "Bạn là AI điều khiển bot Discord TuyTam Store cho admin. Phân tích yêu cầu của "
    "admin (kể cả sai chính tả, thiếu dấu, viết tắt) và gọi tool phù hợp nhất. "
    "Nếu yêu cầu THIẾU thông tin bắt buộc (vd thiếu lý do ban, thiếu tên kênh...), "
    "ĐỪNG gọi tool — hãy hỏi lại admin bằng 1 câu ngắn gọn tiếng Việt. "
    "Nếu yêu cầu không rõ hành động nào, trả lời ngắn gọn rằng bạn không hiểu và "
    "gợi ý admin mô tả rõ hơn hoặc dùng lệnh trực tiếp."
)

REPORT_SYSTEM = (
    "Bạn là AI báo cáo vận hành cho admin TuyTam Store (doanh thu, thống kê đơn "
    "hàng, tăng trưởng...)."
)

# name -> {label hiển thị, system prompt, tool schema subset}
# "report" để tools=[] (stub) vì #17 chưa triển khai — router vẫn nhận diện được,
# ai_chat.py sẽ tự trả lời "chưa triển khai" khi thấy tools rỗng.
AGENTS = {
    "support": {
        "label": "Hỗ trợ khách hàng (tra cứu ticket/seller/invite/lịch sử mua)",
        "system": SUPPORT_SYSTEM,
        "tools": QUERY_TOOL_SCHEMAS,
    },
    "ops": {
        "label": "Điều hành server (kênh/role/mod/ticket/giveaway)",
        "system": OPS_SYSTEM,
        "tools": ADMIN_TOOL_SCHEMAS,
    },
    "report": {
        "label": "Báo cáo số liệu (doanh thu, thống kê) — #17, chưa triển khai",
        "system": REPORT_SYSTEM,
        "tools": [],
    },
}

ROUTER_SYSTEM = (
    "Phân loại yêu cầu của admin vào ĐÚNG 1 trong 3 nhóm sau. CHỈ trả lời DUY "
    "NHẤT 1 từ trong {ops, report, support}, không giải thích, không dấu câu:\n"
    "- ops: điều khiển bot/server — tạo/xoá/đổi tên kênh, tạo/xoá role, thêm/xoá "
    "role cho user, ban/kick/mute/warn, xoá tin nhắn, đóng/mở ticket, giveaway\n"
    "- report: hỏi số liệu/thống kê/báo cáo tổng quan — doanh thu, số đơn, tăng "
    "trưởng thành viên, hiệu suất seller...\n"
    "- support: tra cứu ticket/seller/invite/lịch sử mua hàng của CHÍNH admin đó "
    "(giống 1 khách hàng bình thường hỏi về tài khoản của họ)\n"
    "Nếu không chắc thuộc nhóm nào, trả lời 'ops'."
)


async def route_agent(call_groq_fn, prompt: str) -> str:
    """Gọi 1 lần Groq NHẸ (không kèm tool) để phân loại yêu cầu vào 1 trong
    AGENTS. `call_groq_fn` là hàm async(messages, tools) -> message dict, truyền
    vào từ ai_chat.py (_call_groq_tools) để tránh import vòng."""
    messages = [
        {"role": "system", "content": ROUTER_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    msg = await call_groq_fn(messages, None)
    raw = (msg.get("content") or "").strip().lower()
    for name in AGENTS:
        if name in raw:
            return name
    return "ops"
