# ZaloPay CSKH AI Agent

## Tổng quan

Agent AI xử lý ticket chăm sóc khách hàng ZaloPay. Thực hiện phân loại ticket, phân tích nghiệp vụ và soạn phản hồi chuẩn trong **1 lần gọi LLM duy nhất**.

## Kiến trúc

```
Input: ticket + check_result
        ↓
  [Single LLM Call]
  - Phân loại ticket (category, sub_category, confidence...)
  - Phân tích nghiệp vụ (root_cause, refund_allowed, escalate...)
  - Soạn phản hồi chuẩn ZaloPay (final_response)
        ↓
Output: PipelineResult (classification + analysis + final_response + needs_human_review)
```

## Cấu trúc file

```
zalopay-cskh-agent/
├── CLAUDE.md           # File này — context cho Claude
├── agent.py            # Pipeline chính + CLI
├── main.py             # HTTP server cho GreenNode AgentBase
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container image
└── README.md           # Hướng dẫn deploy và sử dụng
```

## Biến môi trường

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `LLM_API_KEY` | API key VNG MaaS | *(bắt buộc)* |
| `LLM_BASE_URL` | Base URL của LLM API | `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` |
| `LLM_MODEL` | Model sử dụng | `minimax/minimax-m2.5` |
| `MAX_TOKENS` | Số token tối đa mỗi lần gọi | `1500` |
| `LOG_LEVEL` | Mức log: DEBUG/INFO/WARNING | `INFO` |

## Output schema

```json
{
  "success": true,
  "error": null,
  "classification": {
    "category": "TELCO",
    "sub_category": "DATA_SUCCESS_NO_SERVICE",
    "merchant": null,
    "transaction_id": "TXN123",
    "phone_number": "0901234567",
    "amount": "50000",
    "customer_request": "Mua data thành công nhưng chưa nhận",
    "confidence": "high"
  },
  "analysis": {
    "root_cause": "Nhà mạng đã cấp nhưng thiết bị chưa nhận",
    "refund_allowed": false,
    "next_action": "Hướng dẫn khách kiểm tra lại thiết bị",
    "customer_responsibility": null,
    "escalate": false
  },
  "final_response": "Chào bạn,\nZalopay xin lỗi...",
  "needs_human_review": false,
  "session_id": "abc123"
}
```

## Quy tắc Agent

### Phân loại (category)
- `TELCO`: Nạp tiền điện thoại, mua gói data, gói cước
- `BANKING`: Chuyển khoản ngân hàng, liên kết tài khoản
- `WALLET`: Ví ZaloPay, nạp/rút tiền
- `TOPUP`: Nạp tiền game, thẻ cào
- `PAYMENT`: Thanh toán hóa đơn, mua sắm

### Confidence
- `high`: Thông tin đầy đủ, tình huống rõ ràng
- `medium`: Đủ thông tin để xử lý nhưng còn một số điểm chưa chắc chắn
- `low`: Thiếu thông tin quan trọng → `needs_human_review = true`

### Chuẩn văn phong ZaloPay
- Bắt đầu: "Chào bạn,"
- Thương hiệu: "Zalopay" (không phải "ZaloPay")
- Không dùng từ tiêu cực hoặc đổ lỗi cho khách hàng
- Kết thúc bằng lời cảm ơn

## Lưu ý khi phát triển

- `agent.py` là module độc lập, có thể test riêng qua CLI
- `safe_parse_json()` xử lý thinking tokens và markdown fences
- `normalize_brand()` chuẩn hóa "ZaloPay" → "Zalopay" trong toàn bộ response
- Retry 1 lần tự động khi LLM call thất bại
- GreenNode AgentBase inject `LLM_API_KEY` và `LLM_BASE_URL` qua env vars khi deploy
