# ZaloPay AI Agents — Nhóm 9 | GreenNode Claw-a-thon 2026

Hai AI Agent hỗ trợ nghiệp vụ ZaloPay, triển khai trên GreenNode AgentBase + Vercel.

🔗 **Live Demo:** https://nhom9-saocungduoc.vercel.app  
🎬 **Video Demo:** https://youtu.be/uo89MfomhA0

---

## Project 1 — ZaloPay CSKH AI Agent

Agent tự động xử lý ticket chăm sóc khách hàng ZaloPay: phân loại, phân tích nghiệp vụ và soạn phản hồi chuẩn trong **1 lần gọi LLM duy nhất**.

**Demo:** https://nhom9-saocungduoc.vercel.app/demo.html

### Tính năng
- Phân loại ticket theo category (TELCO / BANKING / WALLET / TOPUP / PAYMENT)
- Phân tích root cause, xác định refund_allowed, escalate
- Soạn phản hồi đúng văn phong ZaloPay ("Chào bạn, Zalopay xin lỗi...")
- Xử lý hàng loạt từ file Excel (parallel processing)
- Tự động đánh dấu `needs_human_review` khi confidence thấp

### Kiến trúc
```
Input: ticket + check_result
        ↓
  [Single LLM Call — minimax/minimax-m2.5]
        ↓
Output: classification + analysis + final_response
```

### API Endpoint
```
POST https://nhom9-saocungduoc.vercel.app/api/pipeline
Content-Type: application/json

{
  "ticket": "KH mua data Viettel thành công nhưng chưa nhận.",
  "check_result": "Nhà mạng xác nhận đã cấp dịch vụ."
}
```

### Response
```json
{
  "success": true,
  "classification": { "category": "TELCO", "confidence": "high" },
  "analysis": { "root_cause": "...", "refund_allowed": false, "escalate": false },
  "final_response": "Chào bạn,\nZalopay xin lỗi...",
  "needs_human_review": false
}
```

---

## Project 2 — ZaloPay Jira Ticket Analyzer

Agent phân tích hàng loạt ticket Jira từ file export CSV/Excel, gợi ý xử lý cho CS và xuất báo cáo.

**Demo:** https://nhom9-saocungduoc.vercel.app/jira_demo.html

### Tính năng
- Upload file Jira export (.xlsx / .csv) trực tiếp trên trình duyệt
- Phân tích song song tất cả ticket (parallel batch processing)
- Gợi ý xử lý cụ thể cho CS dựa trên root cause + SLA
- Xuất kết quả ra **Excel** (8 cột: Issue Key, Loại vấn đề, Vấn đề khách hàng, Root Cause, SLA, Ưu tiên, Escalate, Gợi ý)
- Xuất **Dashboard HTML** với biểu đồ phân tích và bộ lọc tương tác

### API Endpoint
```
POST https://nhom9-saocungduoc.vercel.app/api/analyze
Content-Type: application/json

{
  "text": "=== TICKET: ISSUE-41046 ===\nSummary: ...\nRoot Cause Type: External Factors"
}
```

### Response
```json
{
  "success": true,
  "tickets": [
    {
      "key": "ISSUE-41046",
      "suggestion": "Thông báo KH hoàn tiền đã về tài khoản đối tác...",
      "sla_status": "OK",
      "priority_action": false,
      "escalate_to": ""
    }
  ]
}
```

---

## Cấu trúc repo

```
├── agent.py              # CSKH Agent pipeline
├── main.py               # HTTP server — Project 1 (AgentBase)
├── jira_agent.py         # Jira Analyzer pipeline
├── jira_main.py          # HTTP server — Project 2 (AgentBase)
├── demo.html             # UI demo Project 1
├── jira_demo.html        # UI demo Project 2
├── api/
│   ├── pipeline.js       # Vercel proxy → AgentBase CSKH
│   └── analyze.js        # Vercel proxy → AgentBase Jira
├── Dockerfile            # Container Project 1
├── Dockerfile.jira       # Container Project 2
├── requirements.txt      # Python deps Project 1
├── requirements_jira.txt # Python deps Project 2
└── CLAUDE.md             # Agent context & rules
```

## Biến môi trường

| Biến | Mô tả |
|------|-------|
| `LLM_API_KEY` | API key VNG MaaS (bắt buộc) |
| `LLM_BASE_URL` | `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` |
| `LLM_MODEL` | `minimax/minimax-m2.5` |
