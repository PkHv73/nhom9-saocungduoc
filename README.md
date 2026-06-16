# ZaloPay CSKH AI Agent

Agent AI xử lý ticket chăm sóc khách hàng ZaloPay — phân loại, phân tích nghiệp vụ và soạn phản hồi chuẩn trong 1 lần gọi LLM.

## Yêu cầu

- Python 3.12+
- Docker (để build và deploy)
- API key VNG MaaS (LLM_API_KEY)

## Chạy local

```bash
# Cài dependencies
pip install -r requirements.txt

# Thiết lập biến môi trường
export LLM_API_KEY=your_api_key
export LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1

# Chạy tương tác
python agent.py

# Chạy với đối số
python agent.py \
  --ticket "KH mua data Viettel thành công nhưng chưa nhận." \
  --check-result "Nhà mạng xác nhận đã cấp dịch vụ thành công."

# Chạy từ file JSON
python agent.py --input input.json --output output.json --pretty
```

### Ví dụ input.json

```json
{
  "ticket": "Tôi chuyển tiền 500k cho bạn nhưng chuyển nhầm số tài khoản. Mã giao dịch TXN20240615001.",
  "check_result": "Giao dịch đã thành công, tiền đã vào tài khoản người nhận."
}
```

## Deploy lên GreenNode AgentBase

### Bước 1: Build và push Docker image

```bash
# Build image
docker build -t vcr.vngcloud.vn/<project-id>/zalopay-cskh-agent:v$(date +%Y%m%d%H%M%S) .

# Login VCR
docker login vcr.vngcloud.vn -u <username>

# Push image
docker push vcr.vngcloud.vn/<project-id>/zalopay-cskh-agent:v<timestamp>
```

### Bước 2: Cập nhật agent trên GreenNode

1. Vào GreenNode Console → AgentBase → zalopay-cskh-agent
2. Nhấn **Thay đổi**
3. Cập nhật **Đường dẫn image** với tag mới
4. Nhập credentials VCR → **Lưu**
5. Kiểm tra tab **Phiên bản** — version mới sẽ được tạo tự động

## API

### Endpoint

```
POST /invocations
Content-Type: application/json
```

### Request

```json
{
  "ticket": "Nội dung ticket từ khách hàng",
  "check_result": "Kết quả kiểm tra hệ thống (tùy chọn)"
}
```

### Response

```json
{
  "success": true,
  "error": null,
  "classification": {
    "category": "TELCO",
    "sub_category": "DATA_SUCCESS_NO_SERVICE",
    "merchant": null,
    "transaction_id": null,
    "phone_number": "0901234567",
    "amount": "50000",
    "customer_request": "Mua data thành công nhưng chưa nhận",
    "confidence": "high"
  },
  "analysis": {
    "root_cause": "Nhà mạng đã cấp nhưng thiết bị chưa cập nhật",
    "refund_allowed": false,
    "next_action": "Hướng dẫn khách tắt bật dữ liệu di động và khởi động lại thiết bị",
    "customer_responsibility": null,
    "escalate": false
  },
  "final_response": "Chào bạn,\nZalopay xin lỗi vì đã để bạn có những trải nghiệm không tốt...",
  "needs_human_review": false,
  "session_id": "session-abc123"
}
```

### Trường `needs_human_review`

- `true`: Ticket có confidence thấp → cần nhân viên CSKH xem lại
- `false`: Đã xử lý tự động thành công

## Biến môi trường

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `LLM_API_KEY` | API key VNG MaaS | *(bắt buộc)* |
| `LLM_BASE_URL` | Base URL LLM API | `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` |
| `LLM_MODEL` | Model sử dụng | `minimax/minimax-m2.5` |
| `MAX_TOKENS` | Token tối đa mỗi lần gọi | `1500` |
| `LOG_LEVEL` | DEBUG / INFO / WARNING | `INFO` |

## Kiến trúc

```
[GreenNode AgentBase]
        │
        ▼
   main.py (HTTP server)
        │
        ▼
   agent.py → run_pipeline()
        │
        ▼
   [VNG MaaS LLM API]
   minimax/minimax-m2.5
        │
        ▼
   PipelineResult
   (classification + analysis + final_response)
```
