# ZaloPay CSKH Multi-Agent Pipeline

## Tổng quan

Hệ thống AI đa tác nhân xử lý ticket chăm sóc khách hàng ZaloPay theo pipeline 3 bước tuần tự.

## Kiến trúc Pipeline

```
Ticket đầu vào + Kết quả kiểm tra
        ↓
  [Agent 1] Phân loại Ticket      → JSON: category, sub_category, merchant, transaction_id
        ↓
  [Agent 2] Phân tích Nghiệp vụ   → JSON: root_cause, refund_allowed, next_action
        ↓
  [Agent 0] Soạn thảo & Chuẩn hóa → Phản hồi chuẩn ZaloPay gửi khách hàng
```

## Các Agent

### Agent 1 — Classifier (Phân loại Ticket)
- **Input:** Nội dung ticket thô từ khách hàng
- **Output:** JSON có các trường: `category`, `sub_category`, `merchant`, `transaction_id`, `phone_number`, `amount`, `customer_request`
- **Quy tắc:** Chỉ trả về JSON, không thêm văn bản giải thích

### Agent 2 — Resolver (Phân tích Nghiệp vụ)
- **Input:** JSON từ Agent 1 + kết quả kiểm tra hệ thống
- **Output:** JSON có các trường: `root_cause`, `refund_allowed`, `next_action`, `customer_responsibility`, `escalate`
- **Quy tắc:** Không suy diễn ngoài thông tin được cung cấp; nếu đối tác xác nhận thành công thì `refund_allowed = false`

### Agent 0 — Responder (Soạn thảo & Chuẩn hóa Văn phong)
- **Input:** JSON từ Agent 1 + JSON từ Agent 2
- **Output:** Phản hồi chuẩn ZaloPay hoàn chỉnh
- **Quy tắc bắt buộc:**
  - Bắt đầu bằng "Chào bạn,"
  - Không dùng tiếng Anh
  - Luôn dùng thương hiệu "ZaloPay"
  - Không dùng từ tiêu cực: "không biết", "không phải trách nhiệm của ZaloPay", "khách hàng nhập sai"
  - Thêm lời xin lỗi khi khách đang khiếu nại
  - Kết thúc bằng lời cảm ơn của ZaloPay

## Cấu trúc thư mục

```
zalopay-agent/
├── CLAUDE.md           # File này — context cho Claude Code
├── agent.py            # Pipeline chính
├── requirements.txt    # Thư viện Python
├── Dockerfile          # Container image
├── README.md           # Hướng dẫn sử dụng
└── .env.example        # Mẫu biến môi trường
```

## Biến môi trường

| Biến | Mô tả | Bắt buộc |
|------|-------|----------|
| `ANTHROPIC_API_KEY` | API key của Anthropic | ✅ |
| `MODEL` | Model Claude sử dụng (mặc định: claude-sonnet-4-6) | ❌ |
| `MAX_TOKENS` | Số token tối đa mỗi lần gọi (mặc định: 1000) | ❌ |
| `LOG_LEVEL` | Mức log: DEBUG / INFO / WARNING (mặc định: INFO) | ❌ |

## Lưu ý khi phát triển

- Mỗi agent là một hàm độc lập, có thể test riêng lẻ
- Agent 1 và Agent 2 trả về JSON — luôn dùng `safe_parse_json()` để parse
- Nếu JSON parse thất bại, pipeline raise `AgentParseError` và dừng
- Toàn bộ output mỗi bước được log ở mức DEBUG để dễ debug
