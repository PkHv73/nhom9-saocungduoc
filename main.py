"""
ZaloPay CSKH Agent — HTTP Server cho GreenNode AgentBase
=========================================================
Nhận request từ AgentBase, gọi pipeline xử lý ticket, trả về kết quả JSON.
"""

import os
from dotenv import load_dotenv
from greennode_agentbase import GreenNodeAgentBaseApp, RequestContext, PingStatus
from agent import run_pipeline

load_dotenv()

app = GreenNodeAgentBaseApp()

# CORS middleware (cho phép test trực tiếp từ trình duyệt)
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
    """
    Xử lý ticket CSKH.

    Input payload:
        ticket (str): Nội dung ticket từ khách hàng. Bắt buộc.
        check_result (str): Kết quả kiểm tra hệ thống. Tùy chọn.

    Output:
        success (bool): Pipeline thành công hay không.
        error (str|null): Thông báo lỗi nếu có.
        classification (dict): Kết quả phân loại ticket.
        analysis (dict): Kết quả phân tích nghiệp vụ.
        final_response (str): Phản hồi chuẩn gửi khách hàng.
        needs_human_review (bool): True nếu cần nhân viên xem lại.
        session_id (str): Session ID từ AgentBase.
    """
    ticket = payload.get("ticket", "")
    check_result = payload.get("check_result", "")

    if not ticket.strip():
        return {
            "success": False,
            "error": "Trường 'ticket' không được để trống.",
            "classification": None,
            "analysis": None,
            "final_response": "",
            "needs_human_review": False,
            "session_id": context.session_id,
        }

    result = run_pipeline(ticket, check_result)

    return {
        "success": result.success,
        "error": result.error,
        "classification": result.classification.__dict__ if result.classification else None,
        "analysis": result.analysis.__dict__ if result.analysis else None,
        "final_response": result.final_response,
        "needs_human_review": result.needs_human_review,
        "session_id": context.session_id,
    }


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
