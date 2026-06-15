"""
ZaloPay CSKH Multi-Agent Pipeline
===================================
Pipeline 3 agents xử lý ticket chăm sóc khách hàng ZaloPay.

Sử dụng:
    # Chạy tương tác
    python agent.py

    # Chạy với đối số
    python agent.py --ticket "KH mua data Viettel thành công nhưng chưa nhận." \
                    --check-result "Nhà mạng xác nhận đã cấp dịch vụ thành công."

    # Chạy từ file JSON
    python agent.py --input input.json --output output.json
"""

import os
import json
import logging
import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Optional
from openai import OpenAI

# ─── CẤU HÌNH ─────────────────────────────────────────────────────────────────

MODEL            = os.getenv("LLM_MODEL", os.getenv("MODEL", "qwen/qwen3-5-27b"))
MAX_TOKENS       = int(os.getenv("MAX_TOKENS", "2048"))
MAX_TOKENS_JSON  = int(os.getenv("MAX_TOKENS_JSON", "512"))   # Agent 1+2: chỉ cần JSON nhỏ
LOG_LEVEL   = os.getenv("LOG_LEVEL", "INFO").upper()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1")
LLM_API_KEY  = os.getenv("LLM_API_KEY", "")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("zalopay.pipeline")


# ─── PROMPTS ──────────────────────────────────────────────────────────────────

AGENT12_SYSTEM = """Bạn là Agent Phân tích Ticket của hệ thống ZaloPay.
Nhiệm vụ: Đọc ticket khách hàng và kết quả kiểm tra hệ thống, thực hiện 2 việc cùng lúc: phân loại ticket VÀ phân tích nghiệp vụ.
Chỉ trả về JSON hợp lệ duy nhất, không giải thích, không thêm văn bản nào khác.
Cấu trúc JSON bắt buộc:
{
  "category": "string (ví dụ: TELCO, BANKING, WALLET, TOPUP, PAYMENT)",
  "sub_category": "string (ví dụ: DATA_SUCCESS_NO_SERVICE, WRONG_TRANSFER, REFUND_REQUEST)",
  "merchant": "string hoặc null",
  "transaction_id": "string hoặc null",
  "phone_number": "string hoặc null",
  "amount": "string hoặc null",
  "customer_request": "string mô tả yêu cầu của khách",
  "confidence": "high nếu ticket rõ ràng, medium nếu thiếu một số chi tiết, low nếu ticket mơ hồ",
  "root_cause": "string mô tả nguyên nhân gốc rễ",
  "refund_allowed": true hoặc false,
  "next_action": "string hướng xử lý cụ thể",
  "customer_responsibility": "string hoặc null nếu khách cần thực hiện thêm bước gì",
  "escalate": true hoặc false
}
Quy tắc nghiệp vụ bắt buộc:
- Nếu đối tác / nhà mạng xác nhận dịch vụ thành công → refund_allowed = false
- Nếu ngân hàng yêu cầu chủ tài khoản liên hệ → ghi rõ vào next_action
- Không suy diễn ngoài thông tin được cung cấp"""

AGENT0_SYSTEM = """Bạn là Agent Soạn thảo và Chuẩn hóa Phản hồi của hệ thống Zalopay.
Nhận kết quả phân loại ticket và phân tích nghiệp vụ, viết phản hồi hoàn chỉnh gửi khách hàng theo đúng tiêu chuẩn CSKH Zalopay.

QUY TẮC CHUNG:
- Không dùng tiếng Anh trong bất kỳ câu nào.
- Luôn dùng thương hiệu "Zalopay" (không viết tắt, không thay đổi cách viết).
- Không dùng từ tiêu cực: "không biết", "không phải trách nhiệm của Zalopay", "khách hàng nhập sai".
- Khi đề cập việc kiểm tra với đối tác/nhà mạng/ngân hàng, luôn dùng chủ ngữ "Zalopay" — ví dụ: "Zalopay đã làm việc với nhà mạng Viettel...", "Zalopay đã xác nhận với ngân hàng..." (không dùng "đội ngũ hỗ trợ", "chúng tôi đã liên hệ").
- Giải thích rõ nguyên nhân và hướng xử lý cụ thể.
- Văn phong chuyên nghiệp, thân thiện, rõ ràng.

NẾU LÀ TƯ VẤN (khách hỏi thông tin, hướng dẫn sử dụng, chưa có sự cố):
- Mở đầu bằng:
  "Chào bạn,
  Cảm ơn bạn đã quan tâm và sử dụng dịch vụ của ứng dụng thanh toán Zalopay."
- Kết thúc bằng:
  "Nếu cần hỗ trợ thêm thông tin khác, bạn vui lòng gửi yêu cầu mới tại Trung tâm hỗ trợ để Zalopay phản hồi đến bạn nhanh chóng nhất.
  Cảm ơn bạn đã quan tâm và sử dụng dịch vụ của Zalopay."

NẾU LÀ KHIẾU NẠI (khách phản ánh sự cố, mất tiền, lỗi giao dịch, bức xúc):
- Mở đầu bằng:
  "Chào bạn,
  Zalopay xin lỗi vì đã để bạn có những trải nghiệm không tốt khi sử dụng dịch vụ."
- Kết thúc bằng:
  "Zalopay một lần nữa xin lỗi vì sự bất tiện này. Nếu cần hỗ trợ thêm, bạn vui lòng gửi yêu cầu mới tại Trung tâm hỗ trợ để Zalopay phản hồi đến bạn nhanh chóng nhất.
  Cảm ơn bạn đã tin tưởng và sử dụng dịch vụ của Zalopay."

Chỉ trả về nội dung phản hồi, không giải thích gì thêm."""


# ─── DATA CLASSES ─────────────────────────────────────────────────────────────

@dataclass
class TicketClassification:
    category: str
    sub_category: str
    merchant: Optional[str] = None
    transaction_id: Optional[str] = None
    phone_number: Optional[str] = None
    amount: Optional[str] = None
    customer_request: str = ""
    confidence: str = "medium"  # high / medium / low


@dataclass
class BusinessAnalysis:
    root_cause: str
    refund_allowed: bool
    next_action: str
    customer_responsibility: Optional[str] = None
    escalate: bool = False


@dataclass
class PipelineResult:
    classification: Optional[TicketClassification] = None
    analysis: Optional[BusinessAnalysis] = None
    final_response: str = ""
    success: bool = False
    error: Optional[str] = None
    needs_human_review: bool = False  # True khi confidence=low → route sang người thật


# ─── LỖI TÙY CHỈNH ───────────────────────────────────────────────────────────

class AgentParseError(Exception):
    """Lỗi khi Agent không trả về JSON hợp lệ."""


class AgentCallError(Exception):
    """Lỗi khi gọi Anthropic API thất bại."""


# ─── HÀM TIỆN ÍCH ─────────────────────────────────────────────────────────────

def safe_parse_json(text: str) -> dict:
    """Parse JSON từ text, loại bỏ markdown fences và thinking tokens nếu có."""
    # Strip <think>...</think> blocks (Qwen and similar reasoning models)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?|```", "", cleaned).strip()
    # Extract the first complete JSON object or array from the text
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
    if match:
        cleaned = match.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AgentParseError(f"Không thể parse JSON: {e}\nNội dung nhận được:\n{text}") from e


def call_claude(client: OpenAI, system: str, user_content: str, retries: int = 1, max_tokens: int = None) -> str:
    """Gọi LLM API (OpenAI-compatible) và trả về text response. Tự retry nếu lỗi."""
    tokens = max_tokens or MAX_TOKENS
    last_err = None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=tokens,
                messages=[
                    {"role": "system", "content": system + " /no_think"},
                    {"role": "user", "content": user_content},
                ],
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            last_err = e
            if attempt < retries:
                log.warning("LLM call thất bại (lần %d/%d): %s — thử lại...", attempt + 1, retries + 1, e)
    raise AgentCallError(f"Lỗi LLM API sau {retries + 1} lần thử: {last_err}") from last_err


# ─── CÁC AGENT ────────────────────────────────────────────────────────────────

def agent12_analyze(
    client: OpenAI,
    ticket: str,
    check_result: str,
) -> tuple:
    """Agent 1+2 gộp: Phân loại + Phân tích nghiệp vụ trong 1 lần gọi LLM."""
    log.info("[Agent 1+2] Đang phân loại và phân tích ticket (1 lần gọi)...")
    prompt = (
        f"Ticket khách hàng:\n{ticket}\n\n"
        f"Kết quả kiểm tra hệ thống:\n{check_result or '(Chưa có kết quả kiểm tra)'}"
    )
    raw = call_claude(client, AGENT12_SYSTEM, prompt, max_tokens=MAX_TOKENS_JSON)
    log.debug("[Agent 1+2] Raw output:\n%s", raw)

    data = safe_parse_json(raw)

    confidence = data.get("confidence", "medium").lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    classification = TicketClassification(
        category=data.get("category", "UNKNOWN"),
        sub_category=data.get("sub_category", "UNKNOWN"),
        merchant=data.get("merchant"),
        transaction_id=data.get("transaction_id"),
        phone_number=data.get("phone_number"),
        amount=data.get("amount"),
        customer_request=data.get("customer_request", ""),
        confidence=confidence,
    )
    analysis = BusinessAnalysis(
        root_cause=data.get("root_cause", ""),
        refund_allowed=bool(data.get("refund_allowed", False)),
        next_action=data.get("next_action", ""),
        customer_responsibility=data.get("customer_responsibility"),
        escalate=bool(data.get("escalate", False)),
    )
    log.info(
        "[Agent 1+2] ✓ category=%s | confidence=%s | refund_allowed=%s | escalate=%s",
        classification.category, classification.confidence,
        analysis.refund_allowed, analysis.escalate,
    )
    return classification, analysis


def agent0_respond(
    client: OpenAI,
    classification: TicketClassification,
    analysis: BusinessAnalysis,
) -> str:
    """Agent 0: Soạn thảo và chuẩn hóa phản hồi trực tiếp từ kết quả phân tích."""
    log.info("[Agent 0] Đang soạn thảo phản hồi...")
    prompt = (
        f"Kết quả phân loại ticket:\n{json.dumps(classification.__dict__, ensure_ascii=False, indent=2)}\n\n"
        f"Kết quả phân tích nghiệp vụ:\n{json.dumps(analysis.__dict__, ensure_ascii=False, indent=2)}"
    )
    final = call_claude(client, AGENT0_SYSTEM, prompt)
    # Đảm bảo luôn có câu chào
    if not final.lstrip().startswith("Chào bạn"):
        final = "Chào bạn,\n" + final.lstrip()
        log.warning("[Agent 0] Đã thêm câu chào 'Chào bạn,' do model không tự thêm.")
    # Chuẩn hóa brandname
    final = re.sub(r'\bZaloPay\b', 'Zalopay', final)
    final = re.sub(r'\bzalopay\b', 'Zalopay', final, flags=re.IGNORECASE)
    log.debug("[Agent 0] Final:\n%s", final)
    log.info("[Agent 0] ✓ Hoàn tất (%d ký tự)", len(final))
    return final


# ─── PIPELINE CHÍNH ───────────────────────────────────────────────────────────

def run_pipeline(ticket: str, check_result: str = "") -> PipelineResult:
    """
    Chạy toàn bộ pipeline 3 agents.

    Args:
        ticket:       Nội dung ticket từ khách hàng.
        check_result: Kết quả kiểm tra hệ thống / đối tác / ngân hàng.

    Returns:
        PipelineResult chứa output của tất cả các bước.
    """
    api_key = LLM_API_KEY
    if not api_key:
        return PipelineResult(
            success=False,
            error="Thiếu biến môi trường LLM_API_KEY.",
        )

    client = OpenAI(api_key=api_key, base_url=LLM_BASE_URL)
    result = PipelineResult()

    try:
        # Bước 1+2 gộp (1 lần gọi LLM thay vì 2)
        result.classification, result.analysis = agent12_analyze(client, ticket, check_result)

        # Routing: ticket mơ hồ → flag human review, vẫn tiếp tục
        if result.classification.confidence == "low":
            log.warning("Confidence thấp — ticket cần được nhân viên xem lại.")
            result.needs_human_review = True

        # Bước 0: soạn thảo phản hồi
        result.final_response = agent0_respond(client, result.classification, result.analysis)

        result.success = True
        log.info("Pipeline hoàn tất thành công. needs_human_review=%s", result.needs_human_review)

    except (AgentParseError, AgentCallError) as e:
        log.error("Pipeline thất bại: %s", e)
        result.error = str(e)

    return result


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ZaloPay CSKH Multi-Agent Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ticket", type=str, help="Nội dung ticket khách hàng")
    parser.add_argument("--check-result", type=str, default="", help="Kết quả kiểm tra hệ thống")
    parser.add_argument("--input", type=str, help="File JSON đầu vào {ticket, check_result}")
    parser.add_argument("--output", type=str, help="Lưu kết quả ra file JSON")
    parser.add_argument("--pretty", action="store_true", help="In JSON đẹp ra stdout")
    return parser


def interactive_mode() -> tuple[str, str]:
    """Chế độ nhập tương tác."""
    print("\n" + "=" * 60)
    print("  ZaloPay CSKH Agent — Chế độ tương tác")
    print("=" * 60)
    print("Nhập nội dung ticket (Enter 2 lần để kết thúc):")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    ticket = "\n".join(lines).strip()

    print("\nNhập kết quả kiểm tra (bỏ trống nếu chưa có, Enter để tiếp tục):")
    check_result = input().strip()
    return ticket, check_result


def print_result(result: PipelineResult) -> None:
    """In kết quả pipeline ra console."""
    sep = "─" * 60
    print(f"\n{sep}")

    if not result.success:
        print(f"❌ Pipeline thất bại: {result.error}")
        return

    print("✅ PIPELINE HOÀN TẤT\n")

    print("[Agent 1] Phân loại Ticket:")
    print(json.dumps(result.classification.__dict__, ensure_ascii=False, indent=2))

    print(f"\n{sep}")
    print("[Agent 2] Phân tích Nghiệp vụ:")
    print(json.dumps(result.analysis.__dict__, ensure_ascii=False, indent=2))

    print(f"\n{sep}")
    print("[Agent 0] Phản hồi chuẩn ZaloPay:\n")
    print(result.final_response)
    print(sep)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Xác định đầu vào
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
        ticket = data.get("ticket", "")
        check_result = data.get("check_result", "")
    elif args.ticket:
        ticket = args.ticket
        check_result = args.check_result or ""
    else:
        ticket, check_result = interactive_mode()

    if not ticket.strip():
        print("Lỗi: Nội dung ticket không được để trống.")
        sys.exit(1)

    # Chạy pipeline
    result = run_pipeline(ticket, check_result)

    # Xuất kết quả
    if args.output or args.pretty:
        output_data = {
            "success": result.success,
            "error": result.error,
            "classification": result.classification.__dict__ if result.classification else None,
            "analysis": result.analysis.__dict__ if result.analysis else None,
            "final_response": result.final_response,
        }
        json_str = json.dumps(output_data, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"Kết quả đã lưu vào: {args.output}")
        if args.pretty:
            print(json_str)
    else:
        print_result(result)

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
