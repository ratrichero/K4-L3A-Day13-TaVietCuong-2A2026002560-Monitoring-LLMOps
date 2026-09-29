# Runbook Alert — day13-l3a-monitoring-llmops-lab

Mỗi alert ở đây tương ứng một rule trong [`../config/alert_rules.yaml`](../config/alert_rules.yaml).
Tất cả đều **symptom-based**: báo động khi người dùng cảm nhận triệu chứng (chậm, lỗi, chất lượng giảm),
không trigger theo tên implementation nội bộ.

Luồng điều tra chung cho mọi alert: **Metrics → Logs → Traces**:
1. Dashboard xác nhận triệu chứng + khoảng thời gian.
2. Lọc `data/logs.jsonl` trong khoảng đó, lấy `correlation_id` bất thường.
3. Mở trace có cùng `correlation_id` trên Langfuse, so sánh span (retriever vs generation).

## Alert 1 — high_p95_latency

- Tên: `high_p95_latency`
- Severity: warning
- Duration: 5 phút liên tiếp
- Kênh thông báo: Slack
- SLI/SLO liên quan: `fast_successful_requests` (SLO chính, ngưỡng 3000ms)
- Điều kiện và thời gian duy trì: `percentile(response_sent.latency_ms, 95) > 3000` trong 5 phút
- Ảnh hưởng tới người dùng: 5% request trở lên chậm hơn 3 giây; trải nghiệm chat thấy rõ độ trễ
- Ba bước kiểm tra đầu tiên:
  1. Xem panel **Latency** — xác nhận P95 (không phải chỉ P50) vượt ngưỡng và ghi khoảng thời gian.
  2. Lọc `data/logs.jsonl` theo `latency_ms > 3000`, lấy 1–2 `correlation_id`.
  3. Mở trace theo `correlation_id` đó: so sánh `retrieve-docs` vs `llm-generate` — span nào chiếm phần tăng.
- Mitigation tạm thời:
  - Nếu `retrieve-docs` chậm (≈2.5s) → nghi `rag_slow`: tắt incident bằng
    `python scripts/inject_incident.py --scenario rag_slow --disable`; tạm giảm concurrency.
  - Nếu `llm-generate` chậm → kiểm tra incidents `cost_spike`, cân nhắc fallback model/timeout.
  - Nếu chỉ cold-start (P50 bình thường, vài request đầu sau reload chậm) → không mitigation, ghi nhận và đợi.
- Owner: ta.viet.cuong (K4-L3A)

## Alert 2 — error_rate_spike

- Tên: `error_rate_spike`
- Severity: critical
- Duration: 3 phút liên tiếp
- Kênh thông báo: Slack
- SLI/SLO liên quan: guardrail `error_rate_pct_max: 2`; burn budget của SLO chính
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100 > 2` trong 3 phút
- Ảnh hưởng tới người dùng: hơn 2% request trả HTTP 500, người dùng không nhận được câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Panel **Errors** — xác nhận error rate và breakdown `error_type` (thường thấy `RuntimeError`).
  2. Lọc log `event == "request_failed"`, đọc `detail` + `tool_name`, lấy `correlation_id`.
  3. Mở trace: nếu generation/retriever ở level `ERROR` với "Vector store timeout" → đúng `tool_fail`.
- Mitigation tạm thời:
  - Tắt incident: `python scripts/inject_incident.py --scenario tool_fail --disable`.
  - Nếu lỗi ngoài incident thật: kiểm tra API server còn sống (`/health`), roll back deploy gần nhất.
- Owner: ta.viet.cuong (K4-L3A)

## Alert 3 — quality_degradation

- Tên: `quality_degradation`
- Severity: warning
- Duration: 10 phút liên tiếp
- Kênh thông báo: Slack
- SLI/SLO liên quan: guardrail `quality_score_avg_min: 0.75`
- Điều kiện và thời gian duy trì: `mean(response_sent.quality_score) < 0.75` trong 10 phút
- Ảnh hưởng tới người dùng: câu trả lời ngắn/off-topic hoặc lộ marker `[REDACTED...]` — chất lượng nội dung giảm
- Ba bước kiểm tra đầu tiên:
  1. Panel **Quality** — xác nhận mean giảm đúng khoảng thời gian nào.
  2. Lọc log `quality_score < 0.75`, đọc `answer_preview` — thấy pattern chung chưa.
  3. Mở trace theo `correlation_id`: kiểm tra `prompt_name/prompt_version` và metadata `prompt_source`
     — câu trả lời xấu sau khi đổi label → nghi phiên bản prompt mới (ví dụ v2 rút gọn quá mức).
- Mitigation tạm thời:
  - Rollback prompt về version ổn định: `python scripts/prompt_versioning.py rollback`
    (đưa `production` về v1); xác nhận bằng 1 request mẫu.
  - Nếu nguyên nhân là retrieval trả docs sai → tắt `rag_slow` nếu đang bật và kiểm tra corpus.
- Owner: ta.viet.cuong (K4-L3A)
