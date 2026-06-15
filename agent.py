"""
ZaloPay CSKH AI Agent
======================
Pipeline xử lý ticket chăm sóc khách hàng ZaloPay.
Thực hiện phân loại, phân tích nghiệp vụ và soạn phản hồi trong 1 lần gọi LLM duy nhất.

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
from dataclasses import dataclass
from typing import Optional
from openai import OpenAI

# ─── CẤU HÌNH ─────────────────────────────────────────────────────────────────

MODEL        = os.getenv("LLM_MODEL", os.getenv("MODEL", "minimax/minimax-m2.5"))
MAX_TOKENS   = int(os.getenv("MAX_TOKENS", "1500"))
LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO").upper()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1")
LLM_API_KEY  = os.getenv("LLM_API_KEY", "")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("zalopay.cskh")


# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Bạn là hệ thống xử lý ticket CSKH của ZaloPay.
Đọc ticket khách hàng và kết quả kiểm tra hệ thống, thực hiện 3 việc trong 1 lần:
1. Phân loại ticket
2. Phân tích nghiệp vụ
3. Soạn phản hồi chuẩn ZaloPay gửi khách hàng

Trả về JSON hợp lệ duy nhất theo cấu trúc sau, KHÔNG thêm bất kỳ văn bản nào ngoài JSON:
{
  "category": "TELCO | BANKING | WALLET | TOPUP | PAYMENT",
  "sub_category": "ví dụ: DATA_SUCCESS_NO_SERVICE, WRONG_TRANSFER, REFUND_REQUEST",
  "merchant": "string hoặc null",
  "transaction_id": "string hoặc null",
  "phone_number": "string hoặc null",
  "amount": "string hoặc null",
  "customer_request": "mô tả ngắn yêu cầu khách",
  "confidence": "high | medium | low",
  "root_cause": "nguyên nhân gốc rễ của vấn đề",
  "refund_allowed": true hoặc false,
  "next_action": "hướng xử lý cụ thể cho CSKH",
  "customer_responsibility": "string hoặc null",
  "escalate": true hoặc false,
  "final_response": "phản hồi hoàn chỉnh gửi khách hàng theo chuẩn ZaloPay"
}

QUY TẮC final_response:
- Không dùng tiếng Anh
- Luôn dùng thương hiệu "Zalopay"
- Không dùng từ tiêu cực: "không biết", "không phải trách nhiệm", "khách hàng nhập sai"
- Luôn dùng chủ ngữ "Zalopay" khi đề cập kiểm tra với đối tác/nhà mạng/ngân hàng
- Nếu là TƯ VẤN: bắt đầu "Chào bạn,\\nCảm ơn bạn đã quan tâm và sử dụng dịch vụ của ứng dụng thanh toán Zalopay."
- Nếu là KHIẾU NẠI: bắt đầu "Chào bạn,\\nZalopay xin lỗi vì đã để bạn có những trải nghiệm không tốt khi sử dụng dịch vụ."
- Kết thúc bằng lời cảm ơn của Zalopay

QUY TẮC NGHIỆP VỤ:
- Đối tác/nhà mạng xác nhận thành công → refund_allowed = false
- Ngân hàng yêu cầu chủ tài khoản liên hệ → ghi rõ vào next_action
- Không suy diễn ngoài thông tin được cung cấp
- confidence = "low" khi thiếu thông tin quan trọng hoặc tình huống phức tạp chưa rõ ràng"""


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
    confidence: str = "medium"


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
    needs_human_review: bool = False


# ─── LỖI TÙY CHỈNH ───────────────────────────────────────────────────────────

class AgentParseError(Exception):
    """Lỗi khi agent không trả về JSON hợp lệ."""


class AgentCallError(Exception):
    """Lỗi khi gọi LLM API thất bại."""


# ─── HÀM TIỆN ÍCH ─────────────────────────────────────────────────────────────

def safe_parse_json(text: str) -> dict:
    """Parse JSON từ text, loại bỏ thinking tokens và markdown fences."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```(?:json)?|```", "", cleaned).strip()
    match = re.search(r"(\{[\s\S]*\})", cleaned)
    if match:
        cleaned = match.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AgentParseError(
            f"Không thể parse JSON: {e}\nNội dung nhận được:\n{text[:500]}"
        ) from e


def normalize_brand(text: str) -> str:
    """Chuẩn hóa tên thương hiệu về 'Zalopay'."""
    text = re.sub(r'\bZaloPay\b', 'Zalopay', text)
    text = re.sub(r'\bzalopay\b', 'Zalopay', text, flags=re.IGNORECASE)
    return text


def call_llm(client: OpenAI, system: str, user_content: str, retries: int = 1) -> str:
    """Gọi LLM API và trả về text. Tự retry nếu lỗi."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
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


# ─── PIPELINE CHÍNH ───────────────────────────────────────────────────────────

def run_pipeline(ticket: str, check_result: str = "") -> PipelineResult:
    """
    Xử lý ticket CSKH: phân loại + phân tích + soạn phản hồi trong 1 lần gọi LLM.

    Args:
        ticket:       Nội dung ticket từ khách hàng.
        check_result: Kết quả kiểm tra hệ thống / đối tác / ngân hàng.

    Returns:
        PipelineResult chứa đầy đủ kết quả xử lý.
    """
    if not LLM_API_KEY:
        return PipelineResult(
            success=False,
            error="Thiếu biến môi trường LLM_API_KEY.",
        )

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    result = PipelineResult()

    try:
        log.info("Bắt đầu xử lý ticket (%d ký tự)...", len(ticket))

        prompt = (
            f"Ticket khách hàng:\n{ticket}\n\n"
            f"Kết quả kiểm tra hệ thống:\n{check_result or '(Chưa có kết quả kiểm tra)'}"
        )
        raw = call_llm(client, SYSTEM_PROMPT, prompt)
        log.debug("Raw LLM output:\n%s", raw)

        data = safe_parse_json(raw)

        # Confidence validation
        confidence = data.get("confidence", "medium").lower()
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"

        result.classification = TicketClassification(
            category=data.get("category", "UNKNOWN"),
            sub_category=data.get("sub_category", "UNKNOWN"),
            merchant=data.get("merchant"),
            transaction_id=data.get("transaction_id"),
            phone_number=data.get("phone_number"),
            amount=data.get("amount"),
            customer_request=data.get("customer_request", ""),
            confidence=confidence,
        )

        result.analysis = BusinessAnalysis(
            root_cause=data.get("root_cause", ""),
            refund_allowed=bool(data.get("refund_allowed", False)),
            next_action=data.get("next_action", ""),
            customer_responsibility=data.get("customer_responsibility"),
            escalate=bool(data.get("escalate", False)),
        )

        # Xử lý final_response
        final = data.get("final_response", "")
        if final and not final.lstrip().startswith("Chào bạn"):
            final = "Chào bạn,\n" + final.lstrip()
        result.final_response = normalize_brand(final)

        # Human routing: confidence thấp → cần nhân viên xem lại
        if confidence == "low":
            log.warning("Confidence thấp — ticket cần nhân viên xem lại.")
            result.needs_human_review = True

        result.success = True
        log.info(
            "Xử lý hoàn tất. category=%s | confidence=%s | refund=%s | escalate=%s | human_review=%s",
            result.classification.category,
            confidence,
            result.analysis.refund_allowed,
            result.analysis.escalate,
            result.needs_human_review,
        )

    except (AgentParseError, AgentCallError) as e:
        log.error("Pipeline thất bại: %s", e)
        result.error = str(e)

    return result


# ─── CLI ──────────────────────────────────────────────────────────────────────

def interactive_mode() -> tuple[str, str]:
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
    print("\nNhập kết quả kiểm tra (bỏ trống nếu chưa có):")
    check_result = input().strip()
    return ticket, check_result


def print_result(result: PipelineResult) -> None:
    sep = "─" * 60
    print(f"\n{sep}")
    if not result.success:
        print(f"❌ Pipeline thất bại: {result.error}")
        return

    print("✅ PIPELINE HOÀN TẤT\n")
    if result.needs_human_review:
        print("⚠️  Confidence thấp — cần nhân viên xem lại\n")

    print("[Phân loại Ticket]")
    print(json.dumps(result.classification.__dict__, ensure_ascii=False, indent=2))
    print(f"\n{sep}")
    print("[Phân tích Nghiệp vụ]")
    print(json.dumps(result.analysis.__dict__, ensure_ascii=False, indent=2))
    print(f"\n{sep}")
    print("[Phản hồi chuẩn ZaloPay]\n")
    print(result.final_response)
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(description="ZaloPay CSKH AI Agent")
    parser.add_argument("--ticket", type=str, help="Nội dung ticket khách hàng")
    parser.add_argument("--check-result", type=str, default="", help="Kết quả kiểm tra hệ thống")
    parser.add_argument("--input", type=str, help="File JSON đầu vào {ticket, check_result}")
    parser.add_argument("--output", type=str, help="Lưu kết quả ra file JSON")
    parser.add_argument("--pretty", action="store_true", help="In JSON đẹp ra stdout")
    args = parser.parse_args()

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

    result = run_pipeline(ticket, check_result)

    if args.output or args.pretty:
        output_data = {
            "success": result.success,
            "error": result.error,
            "classification": result.classification.__dict__ if result.classification else None,
            "analysis": result.analysis.__dict__ if result.analysis else None,
            "final_response": result.final_response,
            "needs_human_review": result.needs_human_review,
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
