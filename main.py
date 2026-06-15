import os
from dotenv import load_dotenv
from greennode_agentbase import (
    GreenNodeAgentBaseApp,
    RequestContext,
    PingStatus,
)
from agent import run_pipeline

load_dotenv()

app = GreenNodeAgentBaseApp()

# Thêm CORS middleware để cho phép trình duyệt gọi API trực tiếp
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
    ticket = payload.get("ticket", "")
    check_result = payload.get("check_result", "")

    if not ticket.strip():
        return {"success": False, "error": "Trường 'ticket' không được để trống."}

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
