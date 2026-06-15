# ZaloPay CSKH Multi-Agent Pipeline

Hệ thống AI đa tác nhân xử lý ticket chăm sóc khách hàng ZaloPay theo pipeline 4 bước tuần tự, sử dụng Claude của Anthropic.

## Kiến trúc

```
Ticket + Kết quả kiểm tra
        ↓
  [Agent 1] Phân loại Ticket
        ↓  JSON: category, sub_category, merchant, transaction_id...
  [Agent 2] Phân tích Nghiệp vụ
        ↓  JSON: root_cause, refund_allowed, next_action...
  [Agent 3] Soạn thảo Phản hồi
        ↓  Văn bản thô
  [Agent 0] Chuẩn hóa Văn phong ZaloPay
        ↓
  Phản hồi hoàn chỉnh gửi khách hàng
```

## Yêu cầu

- Python 3.10+
- Anthropic API Key — lấy tại [console.anthropic.com](https://console.anthropic.com)

## Cài đặt nhanh

```bash
# 1. Clone hoặc copy thư mục
cd zalopay-agent

# 2. Tạo virtualenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Cài thư viện
pip install -r requirements.txt

# 4. Cấu hình API key
cp .env.example .env
# Mở .env và điền ANTHROPIC_API_KEY=sk-ant-...
```

## Sử dụng

### Chế độ tương tác (nhập thủ công)

```bash
python agent.py
```

Hệ thống sẽ hỏi tuần tự nội dung ticket và kết quả kiểm tra.

---

### Truyền tham số trực tiếp

```bash
python agent.py \
  --ticket "KH mua data Viettel thành công nhưng chưa nhận. Mã GD 260611004463951." \
  --check-result "Nhà mạng xác nhận gói 1N_TMDT đã được cộng thành công."
```

---

### Đọc từ file JSON đầu vào

Tạo file `input.json`:

```json
{
  "ticket": "KH mua data Viettel thành công nhưng chưa nhận. Mã GD 260611004463951.",
  "check_result": "Nhà mạng xác nhận gói 1N_TMDT đã được cộng thành công."
}
```

Chạy:

```bash
python agent.py --input input.json
```

---

### Xuất kết quả ra file JSON

```bash
python agent.py --input input.json --output output.json
```

File `output.json` sẽ có cấu trúc:

```json
{
  "success": true,
  "error": null,
  "classification": { "category": "TELCO", "sub_category": "DATA_SUCCESS_NO_SERVICE", ... },
  "analysis": { "root_cause": "...", "refund_allowed": false, ... },
  "draft_response": "...",
  "final_response": "Chào bạn, ..."
}
```

---

### In JSON đẹp ra stdout

```bash
python agent.py --ticket "..." --pretty
```

---

## Chạy với Docker

### Build image

```bash
docker build -t zalopay-agent .
```

### Chạy tương tác

```bash
docker run -it \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  zalopay-agent
```

### Truyền tham số

```bash
docker run --rm \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  zalopay-agent \
  --ticket "KH mua data Viettel thành công nhưng chưa nhận." \
  --check-result "Nhà mạng xác nhận đã cấp dịch vụ."
```

### Dùng file đầu vào / đầu ra

```bash
docker run --rm \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v $(pwd)/data:/data \
  zalopay-agent \
  --input /data/input.json \
  --output /data/output.json
```

---

## Biến môi trường

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `ANTHROPIC_API_KEY` | API key Anthropic (**bắt buộc**) | — |
| `MODEL` | Model Claude | `claude-sonnet-4-6` |
| `MAX_TOKENS` | Token tối đa mỗi lần gọi | `1000` |
| `LOG_LEVEL` | Mức log (`DEBUG` / `INFO` / `WARNING`) | `INFO` |

---

## Ví dụ đầu ra

```
────────────────────────────────────────────────────────────
✅ PIPELINE HOÀN TẤT

[Agent 1] Phân loại Ticket:
{
  "category": "TELCO",
  "sub_category": "DATA_SUCCESS_NO_SERVICE",
  "merchant": "VIETTEL",
  "transaction_id": "260611004463951",
  ...
}

────────────────────────────────────────────────────────────
[Agent 2] Phân tích Nghiệp vụ:
{
  "root_cause": "Nhà mạng xác nhận đã cấp dịch vụ thành công",
  "refund_allowed": false,
  "next_action": "Yêu cầu khách hàng liên hệ Viettel xác nhận",
  ...
}

────────────────────────────────────────────────────────────
[Agent 0] Phản hồi chuẩn ZaloPay:

Chào bạn,

ZaloPay rất tiếc khi bạn chưa nhận được gói dữ liệu sau khi
giao dịch thành công...

Cảm ơn bạn đã tin tưởng và sử dụng dịch vụ ZaloPay!
────────────────────────────────────────────────────────────
```

---

## Tích hợp vào code Python khác

```python
from agent import run_pipeline

result = run_pipeline(
    ticket="KH mua data Viettel thành công nhưng chưa nhận. Mã GD 260611004463951.",
    check_result="Nhà mạng xác nhận gói 1N_TMDT đã được cộng thành công.",
)

if result.success:
    print(result.final_response)
    print("Hoàn tiền:", result.analysis.refund_allowed)
    print("Cần leo thang:", result.analysis.escalate)
else:
    print("Lỗi:", result.error)
```

---

## Cấu trúc thư mục

```
zalopay-agent/
├── CLAUDE.md           # Context cho Claude Code
├── agent.py            # Pipeline chính
├── requirements.txt    # Thư viện Python
├── Dockerfile          # Container image
├── .env.example        # Mẫu biến môi trường
└── README.md           # File này
```

---

## Mở rộng

- **Thêm nghiệp vụ mới:** Chỉnh sửa `AGENT2_SYSTEM` prompt, thêm quy tắc xử lý
- **Thêm loại ticket mới:** Cập nhật ví dụ trong `AGENT1_SYSTEM`
- **Tích hợp API nội bộ:** Gọi API kiểm tra hệ thống trước khi chạy Agent 2, truyền kết quả vào `check_result`
- **Batch processing:** Vòng lặp `run_pipeline()` trên danh sách ticket, lưu kết quả vào JSONL
