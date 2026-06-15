"""
ZaloPay Jira Ticket Analyzer
=============================
Agent phân tích ticket Jira từ file Excel (.xlsx) hoặc CSV export.

Sử dụng:
    python jira_agent.py --file tickets.xlsx --limit 10
    python jira_agent.py --file tickets.csv --limit 10
    python jira_agent.py --text "nội dung ticket..."
"""

import os
import csv
import json
import logging
import argparse
import re
import sys
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ─── CẤU HÌNH ─────────────────────────────────────────────────────────────────

MODEL        = os.getenv("LLM_MODEL", "qwen/qwen3-5-27b")
MAX_TOKENS   = int(os.getenv("MAX_TOKENS", "1024"))
LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO").upper()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1")
LLM_API_KEY  = os.getenv("LLM_API_KEY", "")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("zalopay.jira")

# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────

JIRA_AGENT_SYSTEM = """Bạn là chuyên gia phân tích ticket Jira ZaloPay. Trả về JSON duy nhất, KHÔNG giải thích thêm:

{
  "suggestion": "gợi ý xử lý cụ thể cho CS bằng tiếng Việt",
  "sla_status": "OK | BREACH | AT_RISK",
  "priority_action": true/false,
  "escalate_to": "team cần escalate hoặc để trống"
}

Quy tắc:
- "Human - Configuration" → kiểm tra cấu hình, escalate team cấu hình
- "User misunderstanding" → hướng dẫn lại KH
- "User need more Information" → liên hệ KH lấy thêm thông tin
- "External Factors" → theo dõi third-party/ngân hàng, thông báo KH
- "Infrastructure - Software" → escalate Dev/Infra ngay, priority_action=true
- "Others" → xem xét mô tả, liên hệ team phụ trách

sla_status: dựa vào trường "Break SLA" (Yes → BREACH, No → OK)
priority_action = true khi BREACH hoặc root cause là Infrastructure/Software

Chỉ trả về JSON, không thêm text ngoài."""

# Các trường quan trọng — hỗ trợ cả tên cột Excel và CSV
IMPORTANT_FIELDS = [
    # --- Định danh ---
    "Issue key", "Issue Key", "Key",
    "Summary",
    # --- Loại vấn đề ---
    "Customer Request Type",
    "Custom field (Customer Request Type)",
    # --- Mô tả ---
    "Description",
    "Mô tả",
    # --- SLA ---
    "Break SLA",
    "Custom field (Break SLA)",
    "Custom field (Reason for SLA Breach)",
    "SLA breach reason",
    # --- Root cause ---
    "Root Cause Type",
    "Custom field (Root Cause Type)",
    "Custom field (Root Cause Description)",
    # --- Xử lý ---
    "Custom field (Zalo Pay Resolution)",
    "Tóm tắt HXL",
    "Custom field (Note)",
    # --- Metadata ---
    "Status",
    "Priority",
    "Created",
    "Resolved",
    "Custom field (Resolved Date)",
]


# ─── TIỆN ÍCH ─────────────────────────────────────────────────────────────────

def safe_parse_json(text: str) -> dict:
    """Parse JSON từ output LLM, xử lý markdown code block và <think> tags."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```(?:json)?|```", "", cleaned).strip()
    match = re.search(r"(\{[\s\S]*\})", cleaned)
    if match:
        cleaned = match.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Không thể parse JSON: {e}\nNội dung:\n{text[:300]}") from e


def call_llm(client: OpenAI, user_content: str, retries: int = 3) -> str:
    """Gọi LLM với retry khi nhận được response rỗng."""
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[
                    {"role": "system", "content": JIRA_AGENT_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
            )
            content = response.choices[0].message.content or ""
            if content.strip():
                return content
            log.warning("LLM trả về rỗng (lần %d/%d), thử lại...", attempt + 1, retries)
            time.sleep(1)
        except Exception as e:
            log.warning("Lỗi LLM lần %d/%d: %s", attempt + 1, retries, e)
            if attempt == retries - 1:
                raise RuntimeError(f"Lỗi LLM API sau {retries} lần thử: {e}") from e
            time.sleep(2)
    raise RuntimeError("LLM trả về phản hồi rỗng sau nhiều lần thử.")


# ─── ĐỌC FILE ─────────────────────────────────────────────────────────────────

def read_excel_rows(file_path: str, limit: int = 10) -> list[dict]:
    """Đọc file Excel (.xlsx), trả về list dict {header: value}."""
    try:
        import openpyxl
    except ImportError:
        raise ImportError("Cần cài openpyxl: pip install openpyxl")

    wb = openpyxl.load_workbook(file_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        raise ValueError("File Excel trống.")

    headers = [str(h).strip() if h is not None else f"Col{i}" for i, h in enumerate(rows[0])]
    result = []
    for row in rows[1:limit + 1]:
        cells = {headers[j]: (str(c).strip() if c is not None else "") for j, c in enumerate(row)}
        result.append(cells)
    return result


def read_csv_rows(file_path: str, limit: int = 10) -> list[dict]:
    """Đọc file CSV (Jira export), trả về list dict {header: value}."""
    result = []
    # Thử UTF-8 BOM trước, fallback UTF-8
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(file_path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i >= limit:
                        break
                    # Làm sạch giá trị
                    cells = {k.strip(): v.strip() for k, v in row.items() if k}
                    result.append(cells)
            if result:
                log.info("Đọc CSV với encoding=%s, %d rows", encoding, len(result))
                return result
        except UnicodeDecodeError:
            continue
    raise ValueError("Không thể đọc file CSV — thử encoding UTF-8, UTF-8 BOM, Latin-1 đều thất bại.")


def read_file_rows(file_path: str, limit: int = 10) -> list[dict]:
    """Auto-detect CSV hoặc XLSX và đọc rows."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        return read_csv_rows(file_path, limit)
    else:
        return read_excel_rows(file_path, limit)


def format_ticket_text(cells: dict) -> str:
    """Chuyển dict ticket thành text gửi LLM — chỉ giữ trường quan trọng."""
    lines = []
    seen_values = set()

    for field in IMPORTANT_FIELDS:
        val = cells.get(field, "")
        if not val or val in ("None", "nan", ""):
            continue
        # Bỏ qua giá trị trùng (cột duplicate trong CSV)
        key = (field.replace("Custom field (", "").replace(")", "").strip(), val[:50])
        if key in seen_values:
            continue
        seen_values.add(key)
        # Rút gọn Description dài
        if "Description" in field and len(val) > 600:
            val = val[:600] + "..."
        lines.append(f"{field}: {val}")

    return "\n".join(lines)


def get_ticket_key(cells: dict) -> str:
    for f in ("Issue key", "Issue Key", "Key"):
        v = cells.get(f, "")
        if v:
            return v
    return "UNKNOWN"


def get_ticket_type(cells: dict) -> str:
    for f in ("Custom field (Customer Request Type)", "Customer Request Type", "Loại vấn đề"):
        v = cells.get(f, "")
        if v:
            return v
    return ""


# ─── PIPELINE CHÍNH ───────────────────────────────────────────────────────────

def analyze_ticket(client: OpenAI, cells: dict) -> dict:
    """Phân tích một ticket đơn lẻ."""
    ticket_text = format_ticket_text(cells)
    issue_key = get_ticket_key(cells)

    log.info("Đang phân tích: %s", issue_key)
    raw = call_llm(client, f"Phân tích ticket sau:\n\n{ticket_text}")
    log.debug("Raw output for %s:\n%s", issue_key, raw[:300])

    result = safe_parse_json(raw)
    result["key"] = issue_key
    result["type"] = get_ticket_type(cells)
    return result


def analyze_from_file(file_path: str, limit: int = 10) -> dict:
    """Đọc file (Excel hoặc CSV) và phân tích từng ticket riêng lẻ."""
    if not LLM_API_KEY:
        raise RuntimeError("Thiếu biến môi trường LLM_API_KEY.")

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    log.info("Đọc file: %s (tối đa %d tickets)", file_path, limit)
    rows = read_file_rows(file_path, limit=limit)
    log.info("Đọc xong — %d rows", len(rows))

    tickets = []
    for i, cells in enumerate(rows):
        issue_key = get_ticket_key(cells)
        try:
            result = analyze_ticket(client, cells)
            tickets.append(result)
            log.info("✅ %s (%d/%d)", issue_key, i + 1, len(rows))
        except Exception as e:
            log.error("❌ %s: %s", issue_key, e)
            tickets.append({
                "key": issue_key,
                "type": get_ticket_type(cells),
                "suggestion": f"Lỗi phân tích: {str(e)[:200]}",
                "sla_status": "OK",
                "priority_action": False,
                "escalate_to": "",
                "error": str(e)[:200],
            })

    log.info("Hoàn tất — %d tickets", len(tickets))
    return {"tickets": tickets}


# Alias để tương thích ngược với jira_main.py cũ
def analyze_from_excel(file_path: str, limit: int = 10) -> dict:
    return analyze_from_file(file_path, limit=limit)


def analyze_jira(data: str) -> dict:
    """Phân tích dữ liệu Jira từ text (dùng cho input thủ công)."""
    if not LLM_API_KEY:
        raise RuntimeError("Thiếu biến môi trường LLM_API_KEY.")

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    log.info("Phân tích text (%d ký tự)...", len(data))
    raw = call_llm(client, f"Phân tích ticket sau:\n\n{data}")
    result = safe_parse_json(raw)
    if "tickets" not in result:
        result = {"tickets": [result]}
    return result


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ZaloPay Jira Ticket Analyzer")
    parser.add_argument("--file", type=str, help="File Excel (.xlsx) hoặc CSV Jira export")
    parser.add_argument("--text", type=str, help="Nội dung ticket dạng text")
    parser.add_argument("--output", type=str, help="Lưu kết quả ra file JSON")
    parser.add_argument("--limit", type=int, default=10, help="Số ticket tối đa (default: 10)")
    args = parser.parse_args()

    if args.file:
        result = analyze_from_file(args.file, limit=args.limit)
    elif args.text:
        result = analyze_jira(args.text)
    else:
        print("Lỗi: Cần --file hoặc --text")
        sys.exit(1)

    output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Kết quả đã lưu: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
