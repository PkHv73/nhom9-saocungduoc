"""
HTTP server cho ZaloPay Jira Analyzer Agent trên AgentBase.

Nhận:
  - { "excel_base64": "<base64 xlsx hoặc csv>", "limit": 10 }  — upload file
  - { "text": "<nội dung ticket dạng text>" }                  — nhập thủ công
"""

import os
import base64
import tempfile
from dotenv import load_dotenv
from greennode_agentbase import GreenNodeAgentBaseApp, RequestContext, PingStatus
from jira_agent import analyze_jira, analyze_from_excel

load_dotenv()

app = GreenNodeAgentBaseApp()

try:
    from fastapi.middleware.cors import CORSMiddleware
    app.app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
except Exception:
    pass


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    excel_b64 = payload.get("excel_base64", "")
    text_data = payload.get("text", "")

    if not excel_b64 and not text_data:
        return {"success": False, "error": "Can truyền 'excel_base64' hoặc 'text'."}

    try:
        if excel_b64:
            # Decode base64 → file tạm → phân tích từng ticket
            file_bytes = base64.b64decode(excel_b64)
            # Auto-detect: XLSX bắt đầu bằng PK (zip magic bytes), còn lại là CSV
            suffix = ".csv" if not file_bytes.startswith(b"PK") else ".xlsx"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            limit = int(payload.get("limit", 10))
            result = analyze_from_excel(tmp_path, limit=limit)
            os.unlink(tmp_path)
        else:
            result = analyze_jira(text_data)

        return {
            "success": True,
            "session_id": context.session_id,
            **result,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
