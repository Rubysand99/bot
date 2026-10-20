"""
cogs/ai_chat.py — AI Chat tích hợp Groq (gpt-oss).
Lệnh: .ai (admin — điều khiển bot bằng ngôn ngữ tự nhiên), .aireset, .mychat
Kênh AI tự động trả lời mọi tin nhắn (khách hàng).

v4.14.0 — Function calling (xem CHANGELOG):
- GROQ_MODELS đổi sang openai/gpt-oss-20b / openai/gpt-oss-120b — Groq đã deprecate
  llama-3.1-8b-instant + llama-3.3-70b-versatile (shutdown 16/08/2026), gemma2-9b-it
  đã chết từ 08/10/2025 (fallback cũ trong code thực ra không hoạt động từ lâu).
- Xoá AI_EXEC_SYSTEM/_call_groq_exec/_call_groq_clarify/_call_groq_fill/_run_action —
  hệ thống prompt-JSON tự chế cũ CHƯA TỪNG được gọi ở đâu (dead code, không có lệnh
  nào trigger) và một số action trỏ tới lệnh KHÔNG TỒN TẠI (ticketpanel/gend/greroll).
  Thay bằng native tool calling của Groq — xem core/ai_tools.py.
- AI trong kênh chat khách giờ có thể tự tra cứu ticket/seller/invite/lịch sử mua
  hàng của CHÍNH người hỏi qua QUERY_TOOL_SCHEMAS.
- Thêm lệnh `.ai <yêu cầu>` cho admin — điều khiển bot bằng ngôn ngữ tự nhiên qua
  ADMIN_TOOL_SCHEMAS, có xác nhận cho hành động nguy hiểm (AIConfirmView).

v4.15.0 — Multi-agent (ý #8, xem core/ai_agents.py):
- `.ai` giờ có 1 bước router NHẸ (không tool) phân loại yêu cầu vào đúng agent
  (support/ops/report) trước khi chạy tool-calling thật, thay vì luôn nhồi hết
  QUERY + ADMIN tool vào 1 lần gọi như trước — dễ mở rộng thêm agent mới (vd #17
  Báo cáo, hiện để stub tools=[] chờ triển khai) mà không phải sửa ai_chat.py.
- `run_ai_tools_agent()` đổi signature: nhận thẳng `system_prompt` + `tools` thay
  vì cờ `is_admin` — mọi agent dùng chung 1 vòng lặp tool-calling.

v4.43.0 — Mở rộng GROQ_MODELS (thêm fallback, xem console.groq.com/docs/models):
- Thêm qwen/qwen3.6-27b làm fallback #3 — model Preview bên Groq (có thể bị gỡ bất
  kỳ lúc nào, KHÔNG như production models), nhưng vẫn hơn là fail hẳn khi cả 2
  gpt-oss đều hết quota cùng lúc. Giá cao hơn gpt-oss-120b (~4-5x) nên chỉ nên bị
  đụng tới khi 2 model đầu đều lỗi, không phải model chính.
- Thêm groq/compound-mini làm fallback #4 (cuối) — "system" của Groq, tự có sẵn
  web search + code execution riêng, không phải model thuần. Cùng đi qua endpoint
  /chat/completions như các model khác nên gắn thẳng vào GROQ_MODELS được, nhưng
  CHƯA rõ nó có tôn trọng đúng `tools=` (QUERY_TOOL_SCHEMAS/ADMIN_TOOL_SCHEMAS) hay
  chỉ dùng tool nội bộ của nó — nếu không trả `tool_calls` đúng định dạng, vòng lặp
  ở run_ai_tools_agent() tự coi như "trả lời xong" (an toàn, không crash), chỉ là
  fallback cuối này có thể không gọi được tool tra cứu ticket/seller như 3 model
  trước. Theo dõi log [AI] nếu nghi ngờ model này trả lời sai lệch.

v4.44.0 — Đảo thứ tự GROQ_MODELS mạnh trước (yêu cầu Ruby) + thêm groq/compound:
- Đảo hẳn thứ tự: compound → qwen3.6-27b → gpt-oss-120b → compound-mini →
  gpt-oss-20b (mạnh/đắt trước, thay vì rẻ/nhanh trước như bản gốc). Suy ra từ hạng
  mục Groq tự xếp (production/preview/system) + giá $/token niêm yết — Groq KHÔNG
  công bố bảng xếp hạng năng lực thống nhất giữa các model này nên đây là suy luận
  từ 2 tín hiệu có thật, không phải benchmark độc lập đã kiểm chứng.
- Thêm groq/compound (bản đầy đủ, không phải -mini) lên đầu danh sách.
- ĐÁNH ĐỔI: _call_groq_tools() thử GROQ_MODELS[0] cho MỌI tin nhắn, không riêng lúc
  lỗi — để compound lên đầu nghĩa là mọi tin AI chat đều tốn chi phí/độ trễ của
  model mạnh nhất trước, gpt-oss-20b gần như không còn được gọi tới. Xem comment
  ngay tại GROQ_MODELS để đổi lại nếu muốn tối ưu chi phí/tốc độ cho tin thường.

v4.45.0 — Đa provider: GROQ_MODELS → AI_MODELS, thêm Gemini (yêu cầu Ruby "muốn
nhiều model AI", xác nhận CHƯA có GEMINI_API_KEY, sẽ lấy nếu cần):
- Groq tự nó không còn model "mạnh" nào để thêm nữa (đã liệt kê hết trong comment
  v4.43.0/44.0) nên phải ra ngoài Groq mới có thêm lựa chọn thật. Đổi GROQ_MODELS
  (list string, ngầm định luôn gọi Groq) thành AI_MODELS (list dict, mỗi entry tự
  mang base_url + api_key riêng) để hỗ trợ nhiều hãng cùng lúc.
- Thêm gemini-3.7-flash (Google, qua endpoint OpenAI-compat chính thức của Gemini —
  xem ai.google.dev/gemini-api/docs/openai) ở vị trí #2. FREE, nhưng KHÔNG suy đoán
  số RPM/RPD cụ thể vì Google không công bố cố định 1 chỗ — xem AI Studio dashboard
  để biết số thật. KHÔNG dùng bản Pro (mạnh hơn Flash) vì Pro hiện thu phí ngay từ
  token đầu, không có free tier — ưu tiên giữ free.
- GEMINI_API_KEY hiện CHƯA được set trên Railway (Ruby xác nhận) — entry Gemini tự
  bị bỏ qua êm trong _call_ai_tools() cho tới khi biến này có giá trị, KHÔNG lỗi,
  KHÔNG cần sửa code thêm gì. Set biến trên Railway là kích hoạt ngay.
- Đổi tên _call_groq_tools() → _call_ai_tools() (đúng bản chất đa provider hơn) —
  cập nhật cả 3 chỗ gọi (run_ai_tools_agent, _call_groq legacy, route_agent() ở
  handle_ai_message) + comment liên quan ở core/ai_agents.py.

v4.46.0 — Routing theo độ phức tạp (Ruby: "hi" mà dùng model #1 thì phí thật):
- AI_MODELS (v4.45.0) tách thành AI_MODELS_STRONG (mạnh trước, y hệt thứ tự cũ) +
  AI_MODELS_FAST (rẻ/nhanh trước — cùng 6 model, đảo ngược ưu tiên).
- Thêm _looks_simple(text) — heuristic THUẦN (độ dài, danh sách từ chào hỏi, có
  code block/từ khoá cần tra cứu không) để quyết định dùng tier nào, KHÔNG gọi
  thêm AI nào để phân loại nên không tốn thêm chi phí/độ trễ. Cố tình THẬN TRỌNG:
  chỉ xếp "đơn giản" khi khá chắc — mọi trường hợp nghi ngờ mặc định vẫn STRONG.
- Chỉ áp dụng ở handle_ai_message() (kênh public, khối lượng tin nhắn lớn nhất).
  KHÔNG áp dụng cho lệnh `.ai` (admin) — đã có route_agent() phân loại agent
  riêng, và admin hiếm khi chỉ chào hỏi suông nên giữ nguyên STRONG luôn.
- Cân nhắc sau này (chưa làm — heuristic hiện đủ giải quyết ca "hi" cụ thể): nếu
  heuristic phân loại sai nhiều trong thực tế, có thể thêm 1 bước AI nhẹ phân loại
  cho ca lấp lửng (message không quá ngắn cũng không quá dài) giống route_agent(),
  đánh đổi lấy thêm 1 lần gọi model rẻ trước khi vào vòng lặp thật.
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands

from core.data import is_admin
from core.data import (
    ADMIN_IDS, get_cfg_ai_channel, _uname_plain,
    load_global_data, save_global_data,
    set_current_guild, reset_current_guild,
)
from core.rag import save_qa_to_rag, get_relevant_context
from core.ai_tools import (
    QUERY_TOOL_SCHEMAS, ADMIN_TOOL_SCHEMAS, DANGEROUS_TOOLS, TOOL_HANDLERS,
)
from core.ai_agents import AGENTS, route_agent
from cogs.logger import send_log

GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # optional — chưa cấu hình thì entry
                                                # Gemini bên dưới tự bị bỏ qua êm,
                                                # không lỗi gì, code vẫn chạy y như
                                                # trước khi thêm. Điền vào Railway env
                                                # là kích hoạt ngay, khỏi sửa code.

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

# ─────────────────────────────────────────────
# FORUM HỎI-ĐÁP ADMIN — kích hoạt khi RAG KHÔNG tìm được câu trả lời liên quan
# (không còn dựa vào AI tự đánh giá "chắc/không chắc" — model nhỏ tự đánh giá
# không đáng tin, xem CHANGELOG v4.13.1)
# ─────────────────────────────────────────────
AI_ASK_ADMIN_PENDING_FORUM_ID  = int(os.getenv("AI_ASK_ADMIN_PENDING_FORUM_ID", "0"))
AI_ASK_ADMIN_RESOLVED_FORUM_ID = int(os.getenv("AI_ASK_ADMIN_RESOLVED_FORUM_ID", "0"))

# Khi admin reply trong post Pending chỉ bằng 1 trong các từ này (không phân biệt
# hoa/thường, có thể kèm dấu câu cuối), coi như "không muốn trả lời" — bot tự thay
# bằng câu từ chối chuẩn thay vì lưu nguyên văn "kbt" làm câu trả lời cho khách.
NO_ANSWER_SHORTHANDS = {"kbt", "ko bt", "k bt", "không biết", "khong biet", "k biết", "no"}
DEFAULT_NO_ANSWER_REPLY = (
    "Mình chưa có thông tin cụ thể về vấn đề này. Bạn vui lòng mở ticket để "
    "được admin hỗ trợ trực tiếp nhé!"
)

# Thứ tự ưu tiên MẠNH TRƯỚC (yêu cầu của Ruby) — KHÔNG có bảng xếp hạng "mạnh yếu"
# thống nhất giữa các model từ NHIỀU HÃNG khác nhau (Groq host sẵn / Google), nên thứ
# tự dưới đây là suy luận có căn cứ thật (giá $/token, hạng production/preview/system
# của Groq, và việc Google xếp bản Pro thành trả phí-only còn Flash mới free) — không
# phải benchmark độc lập đã kiểm chứng giữa các hãng. Đổi thứ tự dễ dàng nếu không
# đồng ý, chỉ cần sắp lại list.
#
# 1. groq/compound       — "system" có web search + code execution riêng, năng lực
#                           thực tế cao nhất nhưng cũng chậm/đắt nhất (có thể tốn
#                           thêm vòng gọi tool ẩn trước khi trả lời).
# 2. gemini-3.7-flash     — model MỚI của Google (xem console.groq.com không có, đây
#                           là hãng khác — Gemini). FREE (Google trợ giá tier Flash),
#                           tool-calling chuẩn OpenAI-compat. Rate limit free tier
#                           CHÍNH XÁC bao nhiêu RPM/RPD thì Google không công bố cố
#                           định 1 chỗ (đổi theo thời điểm) — coi số liệu trong
#                           AI Studio dashboard của Ruby là chuẩn, không suy đoán ở
#                           đây. Lưu ý: bản Pro (mạnh hơn Flash) hiện KHÔNG free —
#                           gemini-3.1-pro-preview thu phí ngay từ token đầu, nên
#                           không đưa vào đây dù "mạnh hơn" — vẫn ưu tiên option free.
# 3. qwen/qwen3.6-27b     — giá $0.60/$3.00 mỗi 1M token, CAO NHẤT trong các model
#                           thuần bên Groq (kể cả hơn gpt-oss-120b dù ít tham số hơn).
#                           PREVIEW, Groq có thể gỡ bất kỳ lúc nào.
# 4. openai/gpt-oss-120b  — 120B tham số, production, $0.15/$0.60.
# 5. groq/compound-mini   — bản "system" nhỏ/nhanh hơn compound, vẫn có tool riêng.
# 6. openai/gpt-oss-20b   — 20B tham số, production, $0.075/$0.30 — nhanh/rẻ nhất,
#                           gần như KHÔNG bao giờ được gọi tới nữa với thứ tự này.
#
# ⚠️ ĐÁNH ĐỔI cũ (đã xử lý bằng AI_MODELS_FAST bên dưới, v4.46.0): vòng lặp
# _call_ai_tools() luôn thử models[0] TRƯỚC cho MỌI tin nhắn (không phải chỉ khi
# lỗi mới rớt xuống model sau) — nghĩa là nếu dùng list này (STRONG) cho MỌI tin,
# kể cả câu chào đơn giản cũng tốn chi phí + độ trễ của model mạnh/đắt nhất trước.
# handle_ai_message() giờ tự chọn AI_MODELS_FAST cho tin bị _looks_simple() nhận
# diện là xã giao, chỉ dùng AI_MODELS_STRONG (list này) cho tin có khả năng cần
# suy luận/tra cứu thật. Lệnh `.ai` (admin) vẫn LUÔN dùng STRONG — admin hiếm khi
# chỉ chào hỏi suông.
#
# Mỗi entry tự mang theo base_url + api_key riêng — entry nào api_key rỗng (chưa
# set biến môi trường tương ứng) sẽ tự bị BỎ QUA ÊM trong _call_ai_tools(), không
# lỗi, không cần xoá dòng khỏi list. GEMINI_API_KEY hiện CHƯA có trên Railway của
# Ruby (lúc thêm dòng này) — set biến đó vào là entry Gemini kích hoạt ngay.
#
# 2 TIER (v4.46.0 — routing theo độ phức tạp, xem _looks_simple() + comment tại
# handle_ai_message): AI_MODELS_STRONG dùng cho tin cần suy luận/tra cứu thật,
# AI_MODELS_FAST dùng cho tin xã giao ngắn (chào hỏi, cảm ơn...) để đỡ tốn model
# đắt/chậm nhất cho câu "hi" — cùng 6 model, chỉ đảo thứ tự ưu tiên khác nhau.
AI_MODELS_STRONG = [
    {"model": "groq/compound",       "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
    {"model": "gemini-3.7-flash",    "base_url": GEMINI_URL, "api_key": GEMINI_API_KEY},
    {"model": "qwen/qwen3.6-27b",    "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
    {"model": "openai/gpt-oss-120b", "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
    {"model": "groq/compound-mini",  "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
    {"model": "openai/gpt-oss-20b",  "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
]

AI_MODELS_FAST = [
    {"model": "openai/gpt-oss-20b",  "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
    {"model": "gemini-3.7-flash",    "base_url": GEMINI_URL, "api_key": GEMINI_API_KEY},
    {"model": "openai/gpt-oss-120b", "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
    {"model": "groq/compound-mini",  "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
    {"model": "qwen/qwen3.6-27b",    "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
    {"model": "groq/compound",       "base_url": GROQ_URL,   "api_key": GROQ_API_KEY},
]

# Ngưỡng phân loại "tin đơn giản" — càng THẬN TRỌNG càng tốt: chỉ xếp "đơn giản"
# khi khá chắc chắn, mọi trường hợp còn nghi ngờ mặc định vẫn đi AI_MODELS_STRONG
# như cũ (thà tốn thêm chút cho 1 tin lỡ đơn giản mà bị coi là phức tạp, còn hơn
# trả lời hời hợt 1 câu THẬT SỰ cần tra cứu/suy luận bằng model yếu). Đây là
# heuristic THUẦN — không gọi thêm AI nào để phân loại, nên KHÔNG tốn thêm chi
# phí/độ trễ cho bất kỳ tin nhắn nào (kể cả tin bị heuristic phân loại sai).
SIMPLE_MAX_CHARS = 25
SIMPLE_GREETING_WORDS = {
    "hi", "hello", "hey", "chào", "chao", "alo", "ê", "e oi", "êoi", "test",
    "oke", "ok", "oki", "cảm ơn", "cam on", "thanks", "thank you", "tks",
    "vâng", "vang", "được", "duoc", "ừ", "u", "ừm", "um", "haha", "hihi", "hmm",
}
# Có mấy từ này trong tin thì KHÔNG được coi là "đơn giản" dù ngắn — nhiều khả
# năng cần tool tra cứu thật (đơn hàng/tiền bạc), trả lời hời hợt ảnh hưởng khách.
LOOKUP_KEYWORDS = {
    "ticket", "đơn", "don ", "seller", "gói", "goi ", "invite", "lịch sử", "lich su",
    "mua", "hoàn tiền", "hoan tien", "sao rồi", "sao roi", "tiền", "tien",
    "thanh toán", "thanh toan", "lỗi", "loi ", "báo lỗi", "bao loi", "?",
}

def _looks_simple(text: str) -> bool:
    """True nếu tin nhắn nhiều khả năng CHỈ là xã giao/không cần tra cứu — dùng để
    chọn AI_MODELS_FAST thay AI_MODELS_STRONG ở handle_ai_message (kênh public).
    KHÔNG áp dụng cho `.ai` admin — lệnh admin hiếm khi là chào hỏi, cứ giữ mạnh."""
    cleaned = text.strip().lower()
    if not cleaned:
        return True
    if "```" in text:
        return False  # có code block — chắc chắn không đơn giản
    if any(kw in cleaned for kw in LOOKUP_KEYWORDS):
        return False  # có thể cần tra cứu thật — ưu tiên model mạnh
    if cleaned in SIMPLE_GREETING_WORDS:
        return True
    return len(cleaned) <= SIMPLE_MAX_CHARS

# System prompt của từng agent giờ nằm trong core/ai_agents.py (AGENTS registry) —
# xem ý #8 Multi-agent. GROQ_SYSTEM ở đây chỉ còn dùng cho hàm _call_groq() legacy.
GROQ_SYSTEM = AGENTS["support"]["system"]

AI_HISTORY_LIMIT = 10
_ai_chat_history: dict = {}   # user_id → {"messages": [...], "last_used": float timestamp}
AI_HISTORY_TTL = 7200  # 2 giờ — dọn history không hoạt động

# FIX (v4.59.1): chống spam kênh AI — mỗi tin nhắn gọi LLM (tốn quota) và có thể tạo 1 thread
# forum + 1 entry trong document global. Cooldown theo user + giới hạn hàng đợi pending.
AI_USER_COOLDOWN = 5.0          # giây giữa 2 tin của cùng 1 user được xử lý
_ai_user_last: dict = {}        # user_id → timestamp tin gần nhất được xử lý
AI_PENDING_TTL_DAYS = 14        # câu hỏi chờ admin quá hạn này sẽ bị dọn
AI_PENDING_MAX = 200            # tối đa số câu hỏi chờ lưu trong document global

def _prune_pending_questions(pending: dict) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=AI_PENDING_TTL_DAYS)
    for tid, v in list(pending.items()):
        try:
            created = datetime.fromisoformat(v.get("created_at", ""))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created < cutoff:
                pending.pop(tid, None)
        except (TypeError, ValueError):
            continue
    overflow = len(pending) - AI_PENDING_MAX
    if overflow > 0:
        for tid in sorted(pending, key=lambda t: str(pending[t].get("created_at", "")))[:overflow]:
            pending.pop(tid, None)
MAX_TOOL_ROUNDS = 4     # số vòng lặp tool-calling tối đa trước khi ép trả lời cuối


def normalize_admin_answer(content: str) -> str:
    """Nếu admin reply chỉ là 1 shorthand kiểu 'kbt'/'không biết' -> thay bằng câu
    từ chối chuẩn, tránh lưu nguyên văn shorthand vào RAG làm khách hoang mang."""
    cleaned = content.strip().lower().rstrip("!.?~ ")
    if cleaned in NO_ANSWER_SHORTHANDS:
        return DEFAULT_NO_ANSWER_REPLY
    return content


# ─────────────────────────────────────────────
# CONFIRM VIEW — cho tool nguy hiểm (DANGEROUS_TOOLS)
# ─────────────────────────────────────────────
class AIConfirmView(discord.ui.View):
    """Yêu cầu admin xác nhận trước khi chạy tool nguy hiểm (ban/kick/mute/xoá...)."""
    def __init__(self, ctx, tool_name: str, params: dict):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.tool_name = tool_name
        self.params = params
        self.message = None

    @discord.ui.button(label="✅ Xác nhận", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Chỉ người ra lệnh mới xác nhận được.", ephemeral=True)
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="⚙️ Đang thực thi...", embed=None, view=self)
        handler = TOOL_HANDLERS.get(self.tool_name)
        result = await handler(self.ctx, self.params) if handler else f"❌ Không tìm thấy tool `{self.tool_name}`."
        await interaction.followup.send(result)

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Chỉ người ra lệnh mới huỷ được.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(content="🚫 Đã huỷ.", embed=None, view=None)

    async def on_timeout(self):
        if not self.message:
            return
        try:
            await self.message.edit(content="⏰ Hết thời gian xác nhận — đã huỷ.", embed=None, view=None)
        except Exception:
            pass


# ─────────────────────────────────────────────
# AI TOOL CALLING — low-level API call (đa provider) + agent loop
# ─────────────────────────────────────────────
async def _call_ai_tools(messages: list, tools: list | None = None, models: list | None = None) -> dict:
    """Gọi lần lượt các entry trong `models` (mặc định AI_MODELS_STRONG nếu không
    truyền — mỗi entry tự mang base_url + api_key riêng, xem comment tại
    AI_MODELS_STRONG/AI_MODELS_FAST), trả về message dict của assistant (có thể
    chứa "tool_calls" nếu model quyết định gọi tool). Entry nào chưa cấu hình
    api_key thì tự bỏ qua êm, không tính là lỗi."""
    models = models if models is not None else AI_MODELS_STRONG
    import aiohttp
    body_base = {"messages": messages, "max_tokens": 1024, "temperature": 0.4}
    if tools:
        body_base["tools"] = tools
        body_base["tool_choice"] = "auto"

    tried_any = False
    last_err = "Unknown error"
    for entry in models:
        model, base_url, api_key = entry["model"], entry["base_url"], entry["api_key"]
        if not api_key:
            continue  # provider chưa có key trong env — bỏ qua êm, thử entry kế
        tried_any = True
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    base_url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, **body_base},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        last_err = f"Model `{model}` hết quota"
                        continue
                    if resp.status != 200:
                        err = await resp.text()
                        print(f"[AI] ⚠️ Model {model} lỗi {resp.status}: {err[:200]}")
                        last_err = f"Lỗi {resp.status}"
                        continue
                    data = await resp.json()
                    return data["choices"][0]["message"]
        except Exception as e:
            last_err = str(e)
            continue

    if not tried_any:
        return {
            "role": "assistant",
            "content": "❌ Chưa cấu hình API key cho bất kỳ AI provider nào "
                       "(GROQ_API_KEY / GEMINI_API_KEY) trong biến môi trường.",
        }
    return {"role": "assistant", "content": f"⚠️ AI tạm thời không khả dụng ({last_err}). Vui lòng thử lại sau ít phút."}


async def check_ai_connections() -> dict[str, tuple[bool, str]]:
    """Test kết nối THẬT (gọi API tối thiểu, max_tokens=1) tới từng provider ĐỘC
    NHẤT xuất hiện trong AI_MODELS_FAST — không test trùng nhiều lần cho cùng 1
    provider dù nó xuất hiện ở nhiều entry (Groq có 5/6 entry cùng chung 1
    base_url + key). Dùng model rẻ nhất của tier FAST cho việc ping này, không
    cần model mạnh chỉ để kiểm tra còn sống hay không.
    Trả về dict {tên_provider: (ok, chi_tiết)}. Gọi từ bot.py: on_ready() (khối
    `if first_boot:`) qua spawn_background() — KHÔNG block startup, KHÔNG gọi lại
    mỗi lần reconnect (tốn quota vô ích, xem AI_CONTEXT.md mục on_ready)."""
    import asyncio
    import aiohttp

    def _label(base_url: str) -> str:
        if base_url == GROQ_URL:
            return "Groq"
        if base_url == GEMINI_URL:
            return "Gemini"
        return base_url  # phòng khi thêm provider mới mà quên thêm nhãn ở đây

    seen: set[str] = set()
    to_test = []
    for entry in AI_MODELS_FAST:
        if entry["base_url"] in seen:
            continue
        seen.add(entry["base_url"])
        to_test.append(entry)

    async def _ping(entry: dict) -> tuple[str, bool, str]:
        label   = _label(entry["base_url"])
        model   = entry["model"]
        api_key = entry["api_key"]
        if not api_key:
            return label, False, "chưa cấu hình API key"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    entry["base_url"],
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        return label, True, f"OK ({model})"
                    err = (await resp.text())[:150]
                    return label, False, f"HTTP {resp.status}: {err}"
        except Exception as e:
            return label, False, str(e)

    results = await asyncio.gather(*(_ping(e) for e in to_test))
    return {label: (ok, detail) for label, ok, detail in results}


async def run_ai_tools_agent(ctx, system_prompt: str, tools: list, user_content: str,
                               history: list | None = None, models: list | None = None):
    """Vòng lặp tool-calling chính, dùng chung cho MỌI agent (v4.15.0, ý #8
    Multi-agent — xem core/ai_agents.py). Trả về tuple (final_text, pending_confirm):
    - pending_confirm là None nếu AI đã trả lời xong (final_text = câu trả lời).
    - pending_confirm là {"name": tool_name, "params": {...}} nếu gặp tool nguy hiểm
      cần admin xác nhận trước — final_text khi đó là None.
    `ctx` cần có .guild/.author/.channel/.message (dùng message thật hoặc commands.Context).
    `models` (v4.46.0) — truyền AI_MODELS_FAST/AI_MODELS_STRONG để chọn tier; không
    truyền thì _call_ai_tools() tự dùng AI_MODELS_STRONG mặc định.
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages += (history or [])
    messages.append({"role": "user", "content": user_content})

    for _ in range(MAX_TOOL_ROUNDS):
        msg = await _call_ai_tools(messages, tools, models)
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return (msg.get("content") or "").strip(), None

        # Tool nguy hiểm -> KHÔNG chạy ngay, trả về cho caller để hiện confirm view
        for call in tool_calls:
            name = call.get("function", {}).get("name")
            if name in DANGEROUS_TOOLS:
                try:
                    params = json.loads(call["function"].get("arguments") or "{}")
                except Exception:
                    params = {}
                return None, {"name": name, "params": params}

        # Tool an toàn -> chạy hết, feed kết quả lại cho model rồi lặp tiếp
        messages.append(msg)
        for call in tool_calls:
            name = call.get("function", {}).get("name")
            try:
                params = json.loads(call["function"].get("arguments") or "{}")
            except Exception:
                params = {}
            handler = TOOL_HANDLERS.get(name)
            result = await handler(ctx, params) if handler else f"Không tìm thấy tool `{name}`."
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "name": name,
                "content": result,
            })

    return "🤔 Yêu cầu cần quá nhiều bước xử lý, bạn thử mô tả đơn giản/cụ thể hơn nhé.", None


async def _call_groq(user_id: int, user_message: str, extra_context: str | None = None) -> str:
    """Chat thường (không tool) — giữ lại cho tương thích, hiện KHÔNG còn dùng trực
    tiếp trong handle_ai_message (đã chuyển sang run_ai_tools_agent), nhưng vẫn hữu
    ích nếu cần gọi AI thuần text ở nơi khác. Tên hàm giữ "groq" vì lý do lịch sử —
    thật ra giờ đi qua _call_ai_tools() nên chạy được cả các provider khác trong
    AI_MODELS_STRONG (mặc định khi không truyền models), không riêng Groq."""
    system_content = GROQ_SYSTEM
    if extra_context:
        system_content += "\n\nThông tin đã xác nhận trước đó (ưu tiên dùng):\n" + extra_context
    messages = [{"role": "system", "content": system_content}, {"role": "user", "content": user_message}]
    msg = await _call_ai_tools(messages, tools=None)
    return (msg.get("content") or "").strip()


async def handle_ai_message(message: discord.Message):
    ai_ch_id = get_cfg_ai_channel()
    if not ai_ch_id or message.channel.id != ai_ch_id:
        return
    # Bỏ qua nếu là lệnh bot (bắt đầu bằng prefix . / / hoặc !)
    if message.content and message.content[0] in ('.', '/', '!'):
        return

    now = datetime.now(timezone.utc).timestamp()
    # Cooldown theo user — bỏ qua tin gửi dồn dập (không gọi LLM, không tạo thread forum).
    if now - _ai_user_last.get(message.author.id, 0.0) < AI_USER_COOLDOWN:
        try:
            await message.add_reaction("⏳")
        except Exception:
            pass
        return
    _ai_user_last[message.author.id] = now
    if len(_ai_user_last) > 2000:
        for uid in [u for u, t in _ai_user_last.items() if now - t > AI_HISTORY_TTL]:
            _ai_user_last.pop(uid, None)
    # Dọn TTL — xóa history cũ hơn AI_HISTORY_TTL
    stale = [uid for uid, v in _ai_chat_history.items() if now - v.get("last_used", 0) > AI_HISTORY_TTL]
    for uid in stale:
        del _ai_chat_history[uid]

    entry = _ai_chat_history.setdefault(message.author.id, {"messages": [], "last_used": now})
    history = entry["messages"]

    # Tra RAG trước — nếu có Q&A tương tự đã được admin xác nhận, AI sẽ ưu tiên dùng
    rag_context = await get_relevant_context(message.guild.id, message.content)
    user_content = message.content
    if rag_context:
        user_content = (
            f"{message.content}\n\n[Thông tin đã xác nhận trước đó — ưu tiên dùng]: {rag_context}"
        )

    async with message.channel.typing():
        support = AGENTS["support"]
        # v4.46.0 — tin xã giao ngắn (chào hỏi, "ok", "cảm ơn"...) đi AI_MODELS_FAST
        # thay vì để mọi tin nhắn (kể cả "hi") tốn model mạnh/đắt nhất (compound)
        # đầu tiên. Phân loại bằng message.content GỐC (chưa gắn rag_context) để
        # không bị lệch bởi đoạn context tự thêm vào.
        models = AI_MODELS_FAST if _looks_simple(message.content) else AI_MODELS_STRONG
        reply, pending = await run_ai_tools_agent(
            message, support["system"], support["tools"], user_content,
            history=history, models=models,
        )

    # Query tools không nằm trong DANGEROUS_TOOLS nên pending sẽ luôn None ở nhánh
    # khách hàng, nhưng vẫn xử lý phòng hờ nếu sau này thêm tool mới.
    if pending is not None:
        reply = "🤔 Yêu cầu này cần admin xử lý, bạn vui lòng mở ticket nhé."

    reply = (reply or "").strip()
    if not reply:
        reply = DEFAULT_NO_ANSWER_REPLY

    # Lưu vào history (KHÔNG lưu rag_context/tool messages vào history lâu dài,
    # chỉ lưu câu hỏi gốc + câu trả lời cuối, tránh phình context các lượt sau)
    history.append({"role": "user", "content": message.content})
    history.append({"role": "assistant", "content": reply})
    if len(history) > AI_HISTORY_LIMIT * 2:
        entry["messages"] = history[-(AI_HISTORY_LIMIT * 2):]
    entry["last_used"] = now

    # RAG KHÔNG tìm được gì liên quan đủ tin cậy -> LUÔN gửi cho admin xử lý,
    # không dựa vào AI tự đánh giá "chắc/không chắc" nữa (xem CHANGELOG v4.13.1)
    # FIX: tin xã giao ngắn ("hi", "ok", "cảm ơn") không có RAG nhưng KHÔNG cần admin trả lời →
    # trước đây mỗi tin như vậy tạo 1 thread forum + 1 entry trong document global.
    needs_admin = rag_context is None and not _looks_simple(message.content)

    if len(reply) <= 2000:
        await message.reply(reply, mention_author=False)
    else:
        for chunk in [reply[i:i+1990] for i in range(0, len(reply), 1990)]:
            await message.channel.send(chunk)

    bot_ref = message._state._get_client()

    if needs_admin:
        await create_pending_question(
            bot_ref,
            guild_id=message.guild.id,
            user=message.author,
            question=message.content,
            ai_draft=reply,
        )

    await send_log(
        bot_ref, "AI_USED", "AI Chat",
        fields=[
            ("👤 User",    f"{_uname_plain(message.author)} (`{message.author.id}`)", True),
            ("💬 Tin nhắn", f"`{message.content[:200]}`",                       False),
            ("🤖 Phản hồi", f"`{reply[:200]}`",                                 False),
            ("📚 Dùng RAG", "✅ Có" if rag_context else "Không",                True),
            ("❓ Cần admin", "✅ Có" if needs_admin else "Không",                True),
        ],
        user=message.author,
    )


# ─────────────────────────────────────────────
# FORUM PENDING — AI không chắc, chờ admin trả lời
# ─────────────────────────────────────────────
async def create_pending_question(bot, guild_id: int, user: discord.abc.User,
                                    question: str, ai_draft: str) -> None:
    if not AI_ASK_ADMIN_PENDING_FORUM_ID:
        return
    forum = bot.get_channel(AI_ASK_ADMIN_PENDING_FORUM_ID)
    if not isinstance(forum, discord.ForumChannel):
        logging.getLogger("ai").warning("[AI] ⚠️ AI_ASK_ADMIN_PENDING_FORUM_ID không phải Forum Channel.")
        return

    # Dedupe: cùng user hỏi y hệt câu đang chờ admin → không tạo thêm thread.
    _qn = question.strip().lower()
    for _v in load_global_data().get("ai_pending_questions", {}).values():
        if _v.get("user_id") == user.id and str(_v.get("question", "")).strip().lower() == _qn:
            return

    guild = bot.get_guild(guild_id)
    embed = discord.Embed(
        title="🤔 AI chưa chắc câu trả lời này",
        color=0xF0A500,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="👤 Người hỏi", value=f"{user} (`{user.id}`)", inline=False)
    embed.add_field(name="🏠 Server", value=guild.name if guild else str(guild_id), inline=True)
    embed.add_field(name="💬 Câu hỏi", value=question[:1000], inline=False)
    embed.add_field(name="🤖 AI đã trả lời tạm", value=ai_draft[:1000], inline=False)
    embed.set_footer(text="Reply trong post này để giải đáp — sẽ tự chuyển sang forum Đã xử lý")

    thread_name = question.strip()[:90] or f"Câu hỏi từ {user}"
    try:
        result = await forum.create_thread(name=thread_name, embed=embed)
    except discord.HTTPException as e:
        # FIX: lỗi/rate-limit tạo thread không được làm văng handle_ai_message (bỏ qua send_log).
        logging.getLogger("ai").warning(f"[AI] ⚠️ Không tạo được thread forum pending: {e}")
        return
    thread = result.thread

    gdata = load_global_data()
    pending = gdata.setdefault("ai_pending_questions", {})
    _prune_pending_questions(pending)
    pending[str(thread.id)] = {
        "guild_id": guild_id,
        "user_id": user.id,
        "question": question[:1500],
        "ai_draft": ai_draft[:1000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_global_data(gdata)


# ─────────────────────────────────────────────
# FORUM RESOLVED — admin đã trả lời, lưu vào RAG
# ─────────────────────────────────────────────
async def create_resolved_post(bot, guild_id: int, user_id: int, question: str,
                                 ai_draft: str, admin_answer: str, answered_by: int) -> int | None:
    if not AI_ASK_ADMIN_RESOLVED_FORUM_ID:
        return None
    forum = bot.get_channel(AI_ASK_ADMIN_RESOLVED_FORUM_ID)
    if not isinstance(forum, discord.ForumChannel):
        return None

    guild = bot.get_guild(guild_id)
    embed = discord.Embed(
        title="✅ Đã giải đáp",
        color=0x57F287,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🏠 Server", value=guild.name if guild else str(guild_id), inline=True)
    embed.add_field(name="💬 Câu hỏi", value=question[:1000], inline=False)
    embed.add_field(name="🤖 AI đã nghĩ", value=ai_draft[:1000], inline=False)
    embed.add_field(name="✅ Giải đáp của admin", value=admin_answer[:1000], inline=False)
    embed.set_footer(text="Nhắn tin mới trong post này để SỬA câu trả lời — AI sẽ cập nhật theo")

    thread_name = question.strip()[:90] or "Đã giải đáp"
    result = await forum.create_thread(name=thread_name, embed=embed)
    thread = result.thread

    gdata = load_global_data()
    resolved = gdata.setdefault("ai_resolved_threads", {})
    resolved[str(thread.id)] = {
        "guild_id": guild_id,
        "user_id": user_id,
        "question": question,
        "ai_draft": ai_draft,
        "starter_message_id": thread.id,  # trong forum, id tin nhắn mở đầu == id thread
    }
    save_global_data(gdata)

    await save_qa_to_rag(doc_id=str(thread.id), guild_id=guild_id, question=question, answer=admin_answer)
    return thread.id


async def _handle_pending_reply(bot, message: discord.Message) -> bool:
    """Admin reply trong post PENDING -> tạo post RESOLVED + lưu RAG + archive post cũ.
    Trả về True nếu đã xử lý (để listener chính không xử lý tiếp)."""
    gdata = load_global_data()
    pending = gdata.get("ai_pending_questions", {})
    entry = pending.get(str(message.channel.id))
    if not entry:
        return False

    token = set_current_guild(entry["guild_id"])
    try:
        resolved_id = await create_resolved_post(
            bot,
            guild_id=entry["guild_id"],
            user_id=entry["user_id"],
            question=entry["question"],
            ai_draft=entry["ai_draft"],
            admin_answer=normalize_admin_answer(message.content),
            answered_by=message.author.id,
        )
        if resolved_id:
            await message.add_reaction("✅")
            try:
                await message.channel.send(
                    f"✅ Đã lưu vào forum **Đã xử lý** và dạy AI. Post này sẽ đóng lại."
                )
                await message.channel.edit(archived=True, locked=True)
            except discord.HTTPException:
                pass

        # Xoá khỏi hàng đợi pending.
        # FIX (v4.59.1): load LẠI sau các await ở trên (tạo post resolved, react, edit thread...) —
        # `gdata` đầu hàm đã cũ; ghi nó lại sẽ đè mất thay đổi do create_resolved_post() (vd entry
        # ai_resolved_threads đầu tiên) hoặc do .as/tempban xảy ra trong lúc chờ.
        gdata = load_global_data()
        pending = gdata.get("ai_pending_questions", {})
        pending.pop(str(message.channel.id), None)
        gdata["ai_pending_questions"] = pending
        save_global_data(gdata)
    finally:
        reset_current_guild(token)
    return True


async def _handle_resolved_edit(bot, message: discord.Message) -> bool:
    """Admin nhắn tin MỚI trong post RESOLVED (không phải tin mở đầu) -> coi là
    sửa câu trả lời, cập nhật embed gốc + ghi đè lại vector trong RAG."""
    gdata = load_global_data()
    resolved = gdata.get("ai_resolved_threads", {})
    entry = resolved.get(str(message.channel.id))
    if not entry:
        return False

    token = set_current_guild(entry["guild_id"])
    try:
        new_answer = normalize_admin_answer(message.content.strip())
        if not new_answer:
            return True

        ok = await save_qa_to_rag(
            doc_id=str(message.channel.id),
            guild_id=entry["guild_id"],
            question=entry["question"],
            answer=new_answer,
        )

        try:
            starter = await message.channel.fetch_message(message.channel.id)
            if starter.embeds:
                embed = starter.embeds[0]
                for i, field in enumerate(embed.fields):
                    if field.name == "✅ Giải đáp của admin":
                        embed.set_field_at(i, name=field.name, value=new_answer[:1000], inline=field.inline)
                        break
                await starter.edit(embed=embed)
        except discord.HTTPException:
            pass

        await message.add_reaction("✅" if ok else "⚠️")
    finally:
        reset_current_guild(token)
    return True


class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cleanup_task = bot.loop.create_task(self._cleanup_history_loop())

    def cog_unload(self):
        self._cleanup_task.cancel()

    async def _cleanup_history_loop(self):
        """Dọn history AI không hoạt động sau AI_HISTORY_TTL giây (mặc định 2h)."""
        import asyncio as _asyncio
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await _asyncio.sleep(1800)  # kiểm tra mỗi 30 phút
            now = datetime.now(timezone.utc).timestamp()
            stale = [uid for uid, v in _ai_chat_history.items()
                     if now - v.get("last_used", 0) > AI_HISTORY_TTL]
            for uid in stale:
                _ai_chat_history.pop(uid, None)
            if stale:
                print(f"[AI] 🧹 Đã dọn {len(stale)} history cũ")

    @commands.command(name="ai")
    async def ai_command(self, ctx, *, prompt: str = None):
        """Admin điều khiển bot bằng ngôn ngữ tự nhiên qua tool calling.
        VD: .ai tạo kênh test riêng tư | .ai ban @user spam | .ai đóng ticket này"""
        if not is_admin(ctx.author):   # admin cố định + admin phụ (.ad) của server này; tool AI chỉ tác động server hiện tại
            return await ctx.reply("❌ Chỉ admin dùng được lệnh này.")
        if not prompt:
            return await ctx.reply("❓ Dùng: `.ai <yêu cầu>` — vd `.ai tạo kênh test riêng tư`")

        async with ctx.typing():
            # Router (#8 Multi-agent) — phân loại yêu cầu vào đúng agent trước khi
            # chạy tool-calling, tránh nhồi hết 15+ admin tool vào 1 lần gọi.
            agent_name = await route_agent(_call_ai_tools, prompt)
            agent = AGENTS.get(agent_name, AGENTS["ops"])
            if not agent["tools"]:
                return await ctx.reply(
                    f"🚧 Yêu cầu này thuộc nhóm **{agent['label']}**, nhưng nhóm này "
                    f"chưa được triển khai. Vui lòng thử lại với yêu cầu điều hành "
                    f"server hoặc tra cứu ticket/seller/invite."
                )
            reply, pending = await run_ai_tools_agent(
                ctx, agent["system"], agent["tools"], prompt, history=[]
            )

        if pending:
            tool_name, params = pending["name"], pending["params"]
            # FIX: các tool mod_*/role_* lấy MỤC TIÊU từ @mention đầu tiên trong tin nhắn (không nằm
            # trong params) → trước đây màn xác nhận không hiện ai sẽ bị tác động.
            _tgt = ""
            if tool_name.startswith("mod_") or tool_name in ("role_add", "role_remove"):
                _m = ctx.message.mentions[0] if ctx.message.mentions else None
                _tgt = (f"**Mục tiêu:** {_m.mention} (`{_m.id}`)\n" if _m
                        else "**Mục tiêu:** ⚠️ không có @mention trong tin nhắn\n")
            embed = discord.Embed(
                title="⚠️ Xác nhận hành động nguy hiểm",
                description=(
                    f"**Yêu cầu:** {prompt}\n**Tool:** `{tool_name}`\n{_tgt}**Params:** `{params}`\n\n"
                    f"⏰ Tự động huỷ sau 30 giây."
                ),
                color=0xED4245,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"Bởi {_uname_plain(ctx.author)}")
            view = AIConfirmView(ctx, tool_name, params)
            view.message = await ctx.reply(embed=embed, view=view)
            return

        await ctx.reply((reply or "✅ Đã xử lý.")[:2000])

    @commands.command(name="aireset", aliases=["airst"])
    async def ai_reset(self, ctx):
        # ⚠️ Xoá lịch sử AI của TOÀN BOT (mọi server) → chỉ admin cố định, không dùng is_admin().
        if ctx.author.id not in ADMIN_IDS:
            return await ctx.reply("❌ Chỉ admin.")
        _ai_chat_history.clear()
        await ctx.reply("✅ Đã xoá toàn bộ lịch sử hội thoại AI.")

    @commands.command(name="mychat")
    async def my_chat_reset(self, ctx):
        if ctx.author.id in _ai_chat_history:
            del _ai_chat_history[ctx.author.id]
            await ctx.reply("✅ Đã xoá lịch sử chat AI của bạn.", delete_after=10)
        else:
            await ctx.reply("ℹ️ Bạn chưa có lịch sử chat AI.", delete_after=10)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Bắt câu trả lời khi admin reply trong forum Pending/Resolved."""
        if message.author.bot:
            return
        if message.author.id not in ADMIN_IDS:
            return
        # AUTH_GATE — server chưa được admin ủy quyền qua .as → bỏ qua (xem bot.py + AI_CONTEXT.md)
        if message.guild:
            from core.data import is_guild_authorized
            if not is_guild_authorized(message.guild.id):
                return

        # Reply trong forum PENDING (câu hỏi AI không chắc) hoặc RESOLVED (sửa đáp án)
        if isinstance(message.channel, discord.Thread):
            if message.channel.parent_id == AI_ASK_ADMIN_PENDING_FORUM_ID:
                if await _handle_pending_reply(self.bot, message):
                    return
            elif message.channel.parent_id == AI_ASK_ADMIN_RESOLVED_FORUM_ID:
                # Tin nhắn ĐẦU TIÊN trong thread (id == thread.id) là embed do bot gửi,
                # không phải admin -> bỏ qua, chỉ xử lý các tin nhắn SAU đó
                if message.id != message.channel.id:
                    if await _handle_resolved_edit(self.bot, message):
                        return

    # ── SLASH COMMANDS ──
    @discord.app_commands.command(name="aireset", description="Xoá toàn bộ lịch sử AI (admin)")
    async def slash_aireset(self, interaction: discord.Interaction):
        # ⚠️ Xoá lịch sử AI của TOÀN BOT (mọi server) → chỉ admin cố định, không dùng is_admin().
        if interaction.user.id not in ADMIN_IDS:
            return await interaction.response.send_message("❌ Chỉ admin.", ephemeral=True)
        _ai_chat_history.clear()
        await interaction.response.send_message("✅ Đã xoá toàn bộ lịch sử AI.", ephemeral=True)

    @discord.app_commands.command(name="mychat", description="Xoá lịch sử chat AI của bạn")
    async def slash_mychat(self, interaction: discord.Interaction):
        if interaction.user.id in _ai_chat_history:
            del _ai_chat_history[interaction.user.id]
            await interaction.response.send_message("✅ Đã xoá lịch sử chat AI của bạn.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ Bạn chưa có lịch sử chat AI.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AICog(bot))
