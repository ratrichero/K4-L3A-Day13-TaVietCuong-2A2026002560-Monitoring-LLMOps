# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Tạ Việt Cường
- **MSSV:** 2A2026002560
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/ratrichero/K4-L3A-Day13-TaVietCuong-2A2026002560-Monitoring-LLMOps
- **Commit SHA cuối:** `2a290f618d30002179f6e7ceb8d3eff9951446c8` (commit chứa đầy đủ kết quả + evidence; dòng này được ghi nhận trong commit kế tiếp trên `main`)
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (seed 1311, incident `rag_slow`)
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A2026002560`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata1.png`, `evidence/08-trace-metadata2.png`, `evidence/08-trace-metadata3.png`, `evidence/08-trace-metadata4.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview1.png`, `evidence/11-dashboard-overview2.png`, `evidence/11-dashboard-overview3.png`, `evidence/11-dashboard-overview4.png`, `evidence/11-dashboard-overview5.png`, `evidence/11-dashboard-overview6.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (FAIL — dự kiến) | 100/100 (4/4 PASSED) | CP1: correlation ID + enrichment + PII đã hoàn thiện |
| `validate_dashboard.py` | HỢP LỆ 6/6 panel | HỢP LỆ 6/6 panel | Đạt cả baseline lẫn kết quả cuối |
| `pytest` | 22/22 passed | 25/25 passed | +3 test PII mới (CCCD, thẻ, passport) |
| Số traces hợp lệ | 12 trace root `lab-agent-run` (env=dev) | 94 trace root (env=dev, project cá nhân, trong 24h) | Mọi trace mới đều có child observations (retriever + generation) theo đúng CP2 |
| Số PII leak | 0 | 0 | Log mới chứa `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]` thay vì PII nguyên văn |
| Latency P95 / TTFT P95 | 444 ms / 57 ms | 1129 ms / 50 ms | Snapshot sau CP1 (chưa loại cold-start sau reload); metrics thời incident và sau fix ghi tại §7 |
| Retrieval success rate | 100% (10/10) | 100% (12/12) | Không có lỗi retrieval |

## 3.1 CP0 — Setup và baseline (ghi 2026-09-29)

**Tiêu chí hoàn thành CP0 — đã đạt:**

- `http://127.0.0.1:8000/health` trả `{"ok": true, "tracing_enabled": true, "incidents": {...}}`.
- `data/logs.jsonl` được tạo bởi tiến trình API (47 records tại thời điểm chạy validator baseline).
- Trace mới xuất hiện trong đúng project Langfuse cá nhân `day13-k4-l3a-2A2026002560`:
  12 root trace `lab-agent-run` (env=dev) trong 24h, ví dụ traceId `3e8f351b93fd8f0159e556d10428a395`.
- **Blocker đã gặp:** UI Langfuse Cloud mặc định lọc `Environment = default`, trong khi trace của app
  được gắn `env=dev` (từ `APP_ENV`), nên ban đầu tưởng như "không có trace". Cách xử lý: chuyển filter
  Environment sang `dev`/`All` — trace hiện ra ngay (đã xác minh thêm bằng API v2 observations của Langfuse).

**Kết quả baseline (chạy trước khi sửa TODO CP1):**

| Lệnh | Kết quả |
|---|---|
| `python scripts/load_test.py` | 10/10 request trả HTTP 200 (correlation_id `MISSING` — đúng như dự kiến vì middleware CP1 chưa làm) |
| `python scripts/validate_logs.py` | **30/100** — FAILED: thiếu required fields, chưa có correlation ID propagation, chưa enrichment; PII scrubbing PASS, 0 leak |
| `python scripts/validate_dashboard.py` | **HỢP LỆ: 6/6 panel** |
| `python -m pytest -q` | **22 passed** |

**Snapshot metrics baseline (`/metrics`, traffic=10):**

| Metric | Giá trị |
|---|---|
| Latency P50 / P95 / P99 | 396 / 444 / 444 ms |
| TTFT P95 | 57 ms |
| Cost | tổng 0.0205 USD (bình quân 0.002 USD/request) |
| Tokens in/out (tổng) | 338 / 1299 |
| Error breakdown | {} (không có lỗi) |
| Quality avg | 0.88 |
| Retrieval success | 100% (10/10) |

> Ghi chú: log validator chưa đạt ở thời điểm này là **dự kiến** — các TODO CP1
> (correlation ID trong `app/middleware.py`, bind metadata trong `app/main.py`,
> bật PII processor trong `app/logging_config.py`) chưa được thực hiện.
> Baseline đã được ghi lại; khi vào CP1 sẽ xóa/đổi tên `data/logs.jsonl` cũ rồi đo lại
> để không tính các dòng log chưa đạt.

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` (app/middleware.py) xóa context cũ (`clear_contextvars`), nhận header `x-request-id` nếu đúng format `req-[0-9a-f]{8}`, không thì sinh `req-<8-hex>` (uuid4). ID được bind vào structlog contextvars, lưu vào `request.state`, và trả lại qua response headers `x-request-id` + `x-response-time-ms`; body JSON response cũng mang `correlation_id`.
- **Các metadata được ghi vào structured log:** `user_id_hash` (SHA-256, 12 ký tự), `session_id`, `feature`, `model`, `env` — bind bằng `bind_contextvars` trong `/chat` (app/main.py) trước log `request_received`, nên mọi log trong request (`request_received`, `response_sent`, `request_failed`) đều đủ enrichment; mỗi request có đúng 1 correlation ID, không rò giữa request.
- **Cách bảo đảm PII được scrub trước khi ghi:** Processor `scrub_event` (app/logging_config.py) đặt **trước** `JsonlFileProcessor` và `JSONRenderer` (tức trước cả ghi file lẫn console). Nó chạy recursive `scrub_text` (app/pii.py) trên mọi giá trị string trong event, kể cả nested trong `payload`/list. Pattern: email, `phone_vn`, `cccd`, `credit_card`, `passport` (P/G + 7 số). Ngoài ra preview message/answer đã qua `summarize_text` ngay tại source. Không dùng regex keyword địa chỉ VN vì false-positive cao với dữ liệu nghiệp vụ (đã cân nhắc, giữ decision này).
- **Cách kiểm chứng kết quả:** `validate_logs.py` = **100/100** (4/4: schema, correlation propagation 10 ID duy nhất, enrichment, PII); log mới hiển thị `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`; response headers chứa đúng `x-request-id` (kể cả khi client truyền `req-deadbeef` → được giữ nguyên); `pytest` 25/25 pass (kèm 3 test PII mới).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** traces được sinh từ chính workload tôi chạy (load_test, prompt_versioning.py) vào project `day13-k4-l3a-2A2026002560`; xác minh bằng Observations API v2 (`/api/public/v2/observations`) bằng keypair cá nhân trong `.env` — mọi observation đều có `environment=dev` và `userId` là hash SHA-256 của user_id tôi gửi.
- **Cấu trúc root/retrieval/generation observations:** root = AGENT `lab-agent-run` (`@observe`); con = RETRIEVER `retrieve-docs` (input query đã scrub PII, output docs) và GENERATION `llm-generate` (model `claude-sonnet-4-5`, input/output đã scrub, `usageDetails` input/output/total, `costDetails` total, prompt link tới `day13-chat`). Đã fix thêm lỗi SDK: `LANGFUSE_TIMEOUT` mặc định 5 bị OTLP exporter hiểu là 5ms nên batch export hay thất bại — đã ép lên 30000ms trong `app/tracing.py`.
- **Cách nối trace với log:** `correlation_id` (do middleware sinh, format `req-<8-hex>`) được ghi vào metadata của cả root span lẫn retriever/generation; log `data/logs.jsonl` cũng chứa cùng `correlation_id` nên tra cứu 2 chiều log ↔ trace được.
- **Prompt name:** `day13-chat` (text prompt, 3 biến `feature`, `docs`, `message`)
- **Version/label baseline:** v1 — labels `[baseline, production]`
- **Version/label candidate:** v2 — labels `[candidate]` (bổ sung dòng "Answer concisely: at most two short sentences.")
- **Trace ID của mỗi version:**
  - baseline (v1): `5b4b063264ebdb10c6951583700fcd67`, `9098afaeec209f585d1f826966ca595e`
  - candidate (v2): `3417f14e6e82fc6b8620019222f87e8e`, `29f98ae599386c44e11b4a2d433250e4`
  - sau promote `production`→v2: `c499eefc8f0b5ab115f30ab1da1d051b`, `929338d67547f6cf5df00acbd2cbcfdd`
  - sau rollback `production`→v1: `ba2a7363ec39cd43b07d1c3f16c27bcc`, `c8db2e91dfc13423cf52fd7985ba30c2`
- **Cách promote và rollback `production`:** script `scripts/prompt_versioning.py` (tự viết): `init` tạo v1/v2 idempotent, `promote` gỡ `production` khỏi v1 và gắn vào v2, `rollback` làm ngược lại; mỗi bước chạy 2 request mẫu qua `LabAgent` với label tương ứng rồi query Observations API v2 in trace ID. Lưu ý kỹ thuật: sau khi `update_prompt` label, read API có thể trả stale trong vài giây — script và evidence đều đợi 3–8s rồi xác nhận lại bằng raw API trước khi chạy trace.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** dashboard contract tại [`config/dashboard.yaml`](../config/dashboard.yaml) gồm 6 panel: latency (P50/P95/P99 + TTFT P95, đơn vị ms), traffic (req/phút), errors (error rate % + breakdown error_type + retrieval success %), cost (USD/phút + tổng), tokens (in/out tổng), quality (mean score 0–1). Mỗi panel có title, unit, time range 60 phút, refresh 30s và threshold line. Nguồn dữ liệu chuẩn là `data/logs.jsonl`; validator đạt 6/6 panel. Runtime dashboard dựng bằng Streamlit tại [`scripts/dashboard.py`](../scripts/dashboard.py) — chạy `.venv/Scripts/python -m streamlit run scripts/dashboard.py` — đọc logs.jsonl, vẽ đủ 6 panel với threshold/SLO line đúng contract (Evidence `11-dashboard-overview.png`).
- **SLO và lý do chọn:** SLO chính `fast_successful_requests` — 99.5% request trong window 28d phải có `latency_ms <= 3000` (symptom-based: đo trải nghiệm người dùng, không đo implementation). Giữ ngưỡng 3000ms của đề vì phù hợp baseline thực đo: P50 ≈ 426ms, P95 ≈ 500–1100ms, P99 ≈ 1359ms — ngưỡng nằm trên P99 nên chỉ bắt sự cố thật (ví dụ `rag_slow` +2.5s đẩy P99 vượt đường 3000ms) chứ không báo động giả ở traffic thường. Guardrails bổ trợ: error rate ≤ 2%, daily cost ≤ 2.5 USD, quality ≥ 0.75, retrieval success ≥ 90%.
- **Cách tính error budget:** budget = (1 − 99.5%) × tổng request hợp lệ trong 28d = 0.5% × N bad events được phép. Ví dụ 10.000 request/28d → tối đa 50 request được chậm hơn 3000ms hoặc fail. Burn rate = bad_events / (0.005 × N); burn rate > 1 nghĩa là tiêu budget nhanh hơn kế hoạch → freeze deploy/mitigation.
- **Ba alert và runbook tương ứng:** tất cả symptom-based, kênh Slack, chi tiết trong [`docs/alerts.md`](../docs/alerts.md):
  1. `high_p95_latency` (warning, 5m): P95 latency > 3000ms — điều tra span retriever vs generation trên trace; mitigation tắt `rag_slow` nếu là incident.
  2. `error_rate_spike` (critical, 3m): error rate > 2% — lọc `request_failed`, kiểm tra `tool_fail`/health; mitigation tắt incident hoặc rollback deploy.
  3. `quality_degradation` (warning, 10m): mean quality < 0.75 — kiểm tra `prompt_version`/`prompt_source` trên trace; mitigation rollback prompt về v1 bằng `scripts/prompt_versioning.py rollback`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, affected_feature `monitoring`, latency_threshold_ms 2000)
- **Khoảng thời gian điều tra:** 2026-09-29 09:47:23 → 09:47:43 UTC (load test `--challenge --concurrency 5` chạy trong window này, 5/5 request đều bị ảnh hưởng)
- **Triệu chứng từ metrics:** `/metrics` sau incident: latency P50 2653ms, P95 = P99 = **2950ms** — vượt ngưỡng 3000ms SLO gần như chạm và vượt `latency_threshold_ms` 2000ms của challenge ở cả P50; TTFT P95 50ms bình thường, error 0%, cost bình thường (avg 0.0021 USD) → triệu chứng thuần latency, không phải lỗi hay cost.
- **Log line và correlation ID liên quan:** 5 log `response_sent` trong `data/logs.jsonl` đều `latency_ms > 2000` và `feature=monitoring`; correlation IDs: `req-8363516a` (2950ms — nặng nhất), `req-5592cab9` (2653ms), `req-bbce184c` (2653ms), `req-27a65c3e` (2652ms), `req-79cd7dc2` (2652ms). TTFT 50ms ổn định cho thấy bottleneck KHÔNG nằm ở LLM.
- **Trace ID và span gây ảnh hưởng:** trace của `req-8363516a`: **`d91ba604d69fc4bfc9907fbda6c2b523`**. Waterfall (Langfuse): root AGENT `lab-agent-run` 4190ms → **RETRIEVER `retrieve-docs` 2508ms** (span gây ảnh hưởng) → GENERATION `llm-generate` 151ms (usage 35/162 tokens, cost 0.0025 USD — bình thường). So sánh cả 5 trace: retriever 2506–2511ms ở tất cả, generation 151–152ms — pattern đồng nhất 100%.
- **Root cause:** retrieval layer chậm ~2.5 giây trên MỌI request (không phải vài request) trong window incident — khớp với trạng thái `rag_slow` được bật qua `/incidents/rag_slow/enable` trước khi chạy workload. Với ngưỡng SLO 3000ms, P99 base ≈ 1359ms chỉ cần cộng thêm ~2.5s retrieval là vượt; `monitoring` là feature chịu ảnh hưởng vì toàn bộ query của challenge thuộc feature này. Đây là sự cố độ trễ của vector store, không phải lỗi LLM hay prompt.
- **Fix action:** (1) tắt incident bằng `POST /incidents/rag_slow/disable` — xác nhận `/health` trả `rag_slow: false` và chạy lại request mẫu latency về baseline (~400ms); (2) trong production thật: timeout + circuit breaker cho vector store để fail-fast thay vì treo 2.5s, và cache kết quả retrieval cho query lặp để giảm phụ thuộc.
- **Preventive measure:** (1) alert `high_p95_latency` đã cấu hình trong `config/alert_rules.yaml` (P95 > 3000ms trong 5 phút) sẽ bắt chính xác pattern này sớm; (2) thêm SLO riêng cho retrieval span (P95 retriever duration < 500ms) quan sát trực tiếp trên Langfuse thay vì chỉ đo end-to-end; (3) rehearsal định kỳ với `inject_incident.py --scenario rag_slow` để kiểm chứng cả alert lẫn runbook `docs/alerts.md#alert-1-high_p95_latency`.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** đặt processor scrub PII `scrub_event` **trước** `JsonlFileProcessor` và `JSONRenderer` trong pipeline structlog, thay vì scrub ở tầng render/console. Lý do: mọi giá trị log (kể cả nested trong `payload`) phải sạch ngay tại thời điểm ghi xuống file — nếu scrub muộn thì PII nguyên văn có thể đã nằm trong file log trước khi bị làm sạch, và log cũ không bao giờ được sửa lại được. Cách đặt này giúp `validate_logs.py` đạt 100/100 với 0 leak; cùng hàm scrub được áp dụng cả cho input/output gởi lên Langfuse trace (§5).
- **Một lỗi/blocker đã gặp:** (1) UI Langfuse Cloud mặc định filter `Environment = default` trong khi trace app gắn `env=dev`, tưởng "không tạo được trace" — phát hiện bằng cách query trực tiếp Observations v2 API rồi đổi filter UI (đã ghi tại §3.1). (2) `LANGFUSE_TIMEOUT` mặc định 5 của SDK bị OTLP exporter hiểu là 5ms nên batch export trace thất bại liên tục — đã ép lên 30000ms trong `app/tracing.py` (§5). (3) `create_prompt` của Langfuse Cloud không idempotent — mỗi call tạo version mới; script `prompt_versioning.py` do đó phải tìm version theo nội dung trước khi tạo (§5).
- **Cách tìm nguyên nhân và xử lý:** theo đúng luồng Metrics → Logs → Traces: `/metrics` cho P50 ≈ 2653ms, P95 = P99 ≈ 2950ms nhưng TTFT bình thường (50ms), error 0%, cost bình thường → triệu chứng thuần latency, bottleneck không nằm ở LLM. Lọc log `response_sent` có `latency_ms > 2000` lấy 5 `correlation_id`; mở 5 trace tương ứng trên Langfuse: RETRIEVER `retrieve-docs` đồng đều 2506–2511ms trong khi GENERATION chỉ ~151ms → root cause là retrieval layer (incident `rag_slow` +2.5s). Xử lý: tắt incident, xác nhận latency về baseline; dài hạn: timeout + circuit breaker cho vector store, cache retrieval (§7).
- **Cách hiểu luồng Metrics → Logs → Traces:** metrics trả lời "chỉ số nào xấu, trong khoảng nào" (triệu chứng + thời gian); logs trả lời "request nào, ai, feature/model gì" khi lọc theo `correlation_id` + thời gian; traces trả lời "component nội bộ nào chậm/lỗi" qua waterfall span. `correlation_id` là chìa khóa nối cả ba lớp để điều tra không bị đứt mạch.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt version/label cho phép gắn kết chất lượng/cost đo được với đúng phiên bản prompt — khi version mới làm giảm chất lượng, rollback label `production` về version ổn định là mitigation tức thì (alert 3 → runbook `scripts/prompt_versioning.py rollback`). Token/cost là guardrail chống chạy ngoài kiểm soát chi phí; SLO + error budget biến câu hỏi "méo đến mức nào là quá" thành con số đo được, và burn rate > 1 là tín hiệu rõ để freeze deploy hoặc mitigation.
- **Điều quan trọng nhất đã học:** PII phải chặn đúng "cạnh" của pipeline logging (trước khi ghi xuống bất cứ đâu) — không thể "dọn sau"; và mỗi tín hiệu observability (metric/log/trace) chỉ có giá trị khi được nối với nhau bằng một correlation ID duy nhất để truy ngược được ba lớp.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** (1) dashboard runtime (Streamlit, `scripts/dashboard.py`) đọc cửa sổ 60 phút từ `data/logs.jsonl`, chưa xây time series database dài hạn; (2) thống kê `/metrics` giữ trong bộ nhớ, mất khi restart API; (3) `config/alert_rules.yaml` là contract hoàn chỉnh nhưng chưa nối với hệ thống cảnh báo thật (Slack webhook/Prometheus) — khi incident chạy thử, runbook trong `docs/alerts.md` được thực thi thủ công.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
