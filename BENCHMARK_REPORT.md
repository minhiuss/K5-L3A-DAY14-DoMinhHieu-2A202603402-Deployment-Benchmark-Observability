# Benchmark & Observability Report — Day 14

> Mọi con số lấy từ report JSON trong `reports/` (Part 7 Bước 1) và CSV trong `benchmark-results/` (Bước 2).

**Họ tên:** Đỗ Minh Hiếu
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 Ubuntu (24 logical CPU), Python 3.11.18, Docker Desktop 29.9.3. Load test chạy cùng máy với agent.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Bình thường p95 ≈ 220 ms (mock LLM 120–180 ms + retrieval 20 ms); 500 ms chừa khoảng an toàn ~2× mà người dùng chat vẫn thấy nhanh. Đặt theo p95 vì average che mất request chậm (xem 2.2) |
| Error rate `/ask` | < 2 % | Mock LLM lỗi ngẫu nhiên ~1% (`MOCK_ERROR_RATE=0.01`); 2% = gấp đôi mức nền, vượt là có sự cố thật chứ không phải nhiễu |
| Accuracy trên golden dataset | ≥ 85 % (gate CI), mục tiêu 100 % | 85% là ngưỡng chặn merge trong job CI; bản đã sửa KB đạt 23/23 nên mọi regression đều bị bắt bằng `--baseline` |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

300 request mỗi mức (`reports/load_v2_c{1,10,50,100}.json`).

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.58 | 188.3 | 219.7 | 1694.0 | 0.67% | ✅ PASS |
| 10 | 37.02 | 192.5 | 221.9 | 1706.6 | 1.00% | ✅ PASS |
| 50 | 122.72 | 201.8 | 270.8 | 1701.4 | 1.33% | ✅ PASS |
| 100 | 56.22 | 380.3 | 3332.7 | 3682.1 | 0.33% | ❌ FAIL (p95) |

**Nhận xét:** RPS tăng gần tuyến tính từ 1 → 10 (×8) vì mỗi request chủ yếu là *chờ* (mock LLM `asyncio.sleep`), một event loop chờ song song được nhiều request. Từ 10 → 50 chỉ còn ×3.3 và tới 100 thì **giảm** (56 req/s) trong khi p95 nhảy từ 271 lên 3333 ms: agent chỉ có **1 process uvicorn** (1 event loop, 1 core) cộng với load generator chạy cùng máy, nên ở c=100 request phải xếp hàng trước khi được xử lý — latency tăng vì thời gian chờ trong hàng, không phải vì LLM chậm hơn (p50 LLM vẫn ~190 ms). Nút thắt là CPU của 1 process → cần nhiều worker / nhiều instance (mục 5). p99 ≈ 1700 ms ở mọi mức là do ~3% request bị mock làm chậm thêm 1500 ms (`MOCK_SLOW_RATE=0.03`).

### 2.2 Tail latency

300 request, concurrency 20 (`reports/load_v2_slow_{0,0.03,0.1}.json`).

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 189.0 | 220.3 | 237.2 |
| 0.03 (mặc định) | 246.6 | 234.8 | 1703.9 |
| 0.1 | 386.8 | 1694.2 | 1715.0 |

**Nhận xét:** **p99 nhạy nhất**: chỉ 3% request chậm đã đẩy p99 từ 237 lên 1704 ms (×7), trong khi avg chỉ tăng 189 → 247 ms (+30%) và p95 gần như không đổi (chưa tới 5% request chậm). Lên 10% request chậm thì cả p95 cũng vượt SLO (1694 ms). Average gộp request nhanh và chậm lại rồi chia đều → 1 người chờ 1.7 giây bị "pha loãng" bởi 99 người chờ 0.2 giây, nhìn avg vẫn thấy ổn. SLO đặt theo p95/p99 vì nó nói thẳng "x% người dùng chờ không quá N ms" — đúng trải nghiệm người dùng tệ nhất mà average che mất.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

23 câu trong `eval/golden_dataset.jsonl` (`reports/eval_v1.json`, `eval_v2.json`, `eval_v2_fixed.json`).

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.4 | 109.1 | 114.5 |
| Tổng cost (USD) | 0.000408 | 0.000762 | 0.000798 |
| Cost / câu đúng (USD) | 0.00040815 | 0.00003627 | 0.00003468 |
| Quality gate | FAIL (ngưỡng 80%) | PASS (80%, 0 regression so với v1) | PASS (100%, 0 regression so với v2) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| scaling-03 | `cpu`, `memory`, `custom metrics` | Thêm tài liệu `(["hpa", "kubernetes", "autoscal"], "Kubernetes HPA ... CPU, memory hoặc custom metrics ...")` vào cuối `KNOWLEDGE_BASE` (`develop/utils/mock_llm.py`) |
| security-02 | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu `(["jwt"], "... JWT là token có chữ ký số, mang thông tin user và thời điểm hết hạn ...")` |

Không sửa `golden_dataset.jsonl`. Kiểm tra không regression: keyword mới (`hpa`, `kubernetes`, `autoscal`, `jwt`) chỉ xuất hiện trong đúng 2 câu này của dataset, và eval cuối báo `Câu bị regression : 0`. Đã chép cùng bản sửa sang `production/utils/mock_llm.py` để stack Docker cũng đạt 100%.

**Quality gate trong CI:** `.github/workflows/eval.yml` chạy trên mỗi pull request: bật agent v2 rồi `python eval/run_eval.py --min-accuracy 0.85`. `run_eval.py` trả exit code 1 khi accuracy < ngưỡng hoặc có regression → step fail → job đỏ → bật *Require status checks* trong branch protection thì PR không merge được. Đã thử: gate 85% trên v2 → `exit=0`, trên v1 → `exit=1`.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** v2 thêm bước retrieval nên prompt dài gấp ~2 lần (57 → 109 token/câu), tổng cost tăng 87% (0.000408 → 0.000762) và p95 chậm hơn ~28 ms (190.5 → 218.6). Nhưng accuracy tăng từ 4% lên 91% nên **cost / câu đúng giảm ~11 lần** (0.000408 → 0.0000363 USD). So "cost / câu" thì v1 trông rẻ hơn, nhưng v1 gần như trả lời sai hết — tiền bỏ ra cho câu sai là tiền mất. "Cost / câu đúng" đo đúng giá trị nhận được, nên v2 là lựa chọn tốt hơn.

---

## 4. Observability stack (production)

Stack chạy bằng `docker compose -p k5-day14-observability up -d --build` trong `06-lab-complete/benchmark-observability/production/`.

> **Sửa 1 lỗi của Dockerfile mẫu:** agent khởi động lại liên tục với `ModuleNotFoundError: No module named 'uvicorn'`. Nguyên nhân: `useradd -d /app` đặt HOME của user `agent` là `/app`, nên Python tìm gói "user site" ở `/app/.local`, trong khi gói được `COPY` vào `/home/agent/.local`. Sửa: thêm `ENV PYTHONUSERBASE=/home/agent/.local`.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — `screenshots/grafana-dashboard.png` (chụp lúc đang chạy thí nghiệm A+B+D: error rate 22.75 %, p95 1.88 s, instances up 2)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (status ERROR, `LLMError`) — `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing** — `screenshots/prometheus-alert-firing.png` (3 alert cùng firing)

**Exercise 7.4 — trả lời** (đo bằng Locust headless 100 users, 3 instance, file `benchmark-results/scale_3_stats.csv`):

1. **p95 và avg:** `POST /ask` avg **241 ms**, p50 190 ms, p95 **240 ms**, p99 **1700 ms**. Avg (241) lớn hơn cả p50 (190) vì ~3 % request bị mock làm chậm ~1.7 s (`MOCK_SLOW_RATE=0.03`) kéo trung bình lên; p95 vẫn thấp vì 3 % < 5 %, chỉ p99 thấy được đuôi chậm. → Một con số avg vừa che mất đuôi chậm, vừa làm request "thường" trông chậm hơn thực tế; phải nhìn phân phối (p50/p95/p99).
2. **Nginx có chia đều không:** có. Trong 2 phút tải với 2 instance: `172.19.0.7` = 3679 request, `172.19.0.8` = 3681 (lệch 0.05 %). Với 3 instance: 2453 / 2404 / 2408. 12 request thử tay: 4 / 4 / 4 (header `X-Served-By`). Round-robin nên đều.
3. **Input tokens/s > output tokens/s:** input = system prompt + **context retrieval** + câu hỏi, còn output chỉ là câu trả lời ngắn. Trace chậm ở 4.3: `input_tokens 72`, `output_tokens 40`. Lưu ý panel Tokens/s là biểu đồ **xếp chồng** (`stacking: normal`): đường vàng trên cùng là input + output, phần xanh (input ≈ 5K/s) mới là input.
4. **`curl -i http://localhost:8080/metrics` → `HTTP/1.1 404 Not Found`.** Nginx có `location = /metrics` trả 404 cho bên ngoài: metrics lộ thông tin nội bộ (route, model, chi phí, số instance). Prometheus không đi qua Nginx mà scrape thẳng `agent:8000/metrics` trong mạng `obs_net`.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | pending sau 21 s → **firing sau 81 s** | Stat **Error rate** (22.75 %), "Requests/s theo status code" (đường 503 tăng) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | pending sau 9 s → **firing sau 129 s** | Stat **Latency p95** (1.88 s), "Latency /ask p50/p95/p99" (p95 vượt đường SLO 1 s), "LLM latency p95 theo model" |
| C | `LLM_MODEL=mock-llm-large` | không chạy | — | — |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`for: 30s`, instance `172.19.0.10:8000`) | pending sau 15 s → **firing sau 45 s** | Stat **Instances up** (3 → 2), "Requests/s theo instance" (mất 1 đường) |
| E | `AGENT_VERSION=v1` | không alert nào (đo ở develop: v1 vẫn trả 200, accuracy 4.3 %) | — | Không panel hạ tầng nào; chỉ thấy qua eval (mục 3) |

Cách đo: chạy A + B + D **cùng lúc** để có ≥ 2 alert firing (tải nền Locust 30 users). Đổi biến môi trường bằng `MOCK_ERROR_RATE=0.2 MOCK_SLOW_RATE=0.3 docker compose -p k5-day14-observability up -d --no-deps --scale agent=3 agent`, chờ 15 s rồi `docker pause` agent-3 và bắt đầu đếm giờ (T0). Script hỏi `localhost:9090/api/v1/alerts` mỗi 3 s. Vì A, B đổi trước T0 khoảng 15 s nên thời gian thật của A, B dài hơn số trên ~15 s.

**Phân tích:** thời gian tới firing ≈ thời gian để biểu thức vượt ngưỡng (cửa sổ `rate[1m]` cần vài lần scrape 5 s) **+** `for:`. D nhanh nhất (`up == 0` đúng ngay lần scrape hỏng đầu tiên + 30 s). A ≈ 20 s tích luỹ lỗi + 60 s. B lâu nhất vì `for: 2m`: latency phải xấu liên tục 2 phút mới báo — đánh đổi giữa báo sớm và báo nhầm (một đợt chậm ngắn không đánh thức ai). Trong lúc D, Nginx vẫn trả lời vì `proxy_next_upstream error timeout` chuyển request sang instance còn sống.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đổi sang v1 không làm hệ thống chậm hay lỗi (vẫn 200, latency còn nhanh hơn), chỉ làm câu trả lời **sai** — metric hạ tầng (latency, error rate, saturation) không thấy được. Phát hiện bằng (1) **quality gate trước deploy**: eval golden dataset trong CI (mục 3) chặn ngay bản v1 vì accuracy 4% < 85%; (2) **eval định kỳ sau deploy** (canary / cron chạy `run_eval.py` vào bản production) và alert khi accuracy giảm; (3) theo dõi **tín hiệu chất lượng trong lúc chạy**: tỉ lệ câu trả lời generic, tỉ lệ retrieval rỗng, feedback 👍/👎 của người dùng; (4) metric `agent_info{version=...}` để biết ngay version nào đang chạy.

### 4.3 Debug bằng trace

**Trace chậm** (`screenshots/jaeger-slow-trace.png`, trace chậm nhất trong 1000 trace của 15 phút):

- `trace_id`: `ba454786657b3761aa9a1174f1da20cd`
- Tổng thời gian: **1717.9 ms**
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small` 1692.4 ms** (98.5 %). Các span khác: `agent.run` 1715.1 ms (cha của LLM), `agent.retrieve_context` 22.4 ms. → Chậm do LLM, không do retrieval.
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs --no-log-prefix agent | grep ba454786...`):

```json
{"ts": "2026-11-25T10:20:22.096147+00:00", "level": "INFO", "service": "observable-agent", "instance": "af0530d2afd4", "event": "llm_call", "trace_id": "ba454786657b3761aa9a1174f1da20cd", "span_id": "bc048d9ca3efb321", "request_id": "6809d9e3c264", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 72, "output_tokens": 40, "cost_usd": 3.5e-05, "llm_ms": 1691.9}
{"ts": "2026-11-25T10:20:22.096708+00:00", "level": "INFO", "service": "observable-agent", "instance": "af0530d2afd4", "event": "http_request", "trace_id": "ba454786657b3761aa9a1174f1da20cd", "span_id": "bc048d9ca3efb321", "request_id": "6809d9e3c264", "method": "POST", "route": "/ask", "status": 200, "ms": 1717.1}
```

`llm_ms` 1691.9 trong log khớp span LLM 1692.4 ms trong Jaeger.

**Trace lỗi** (`screenshots/jaeger-error-trace.png`):

- `trace_id`: `6c67a614d36492a70fae6784680a4fe9`, tổng **127.2 ms**, HTTP 503
- Span `chat mock-llm-small` 96.3 ms status ERROR: `LLMError: Upstream LLM error: 503 Service Unavailable (mock)`, `error.type = upstream_unavailable`; lỗi lan lên `agent.run` và `POST /ask`.

```json
{"ts": "2026-11-25T10:20:00.605177+00:00", "level": "INFO", "service": "observable-agent", "instance": "fa4a0d2b095d", "event": "llm_error", "trace_id": "6c67a614d36492a70fae6784680a4fe9", "span_id": "76392ee7cba54086", "request_id": "d6e3935a7770", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-25T10:20:00.606088+00:00", "level": "INFO", "service": "observable-agent", "instance": "fa4a0d2b095d", "event": "http_request", "trace_id": "6c67a614d36492a70fae6784680a4fe9", "span_id": "76392ee7cba54086", "request_id": "d6e3935a7770", "method": "POST", "route": "/ask", "status": 503, "ms": 125.2}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Lệnh: `docker compose -p k5-day14-observability run --rm --no-deps locust -f /mnt/locust/locustfile.py --host http://nginx --headless -u 100 -r 10 -t 2m --csv /mnt/results/scale_N`. Số lấy từ dòng `Aggregated` (mọi request) và `POST /ask` trong `benchmark-results/scale_1_stats.csv`, `scale_3_stats.csv`. Trước mỗi lần đo đã kiểm `count(up{job="agent"}==1)` trong Prometheus = 1 / 3.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.64 | 190 | 310 (`/ask` 330) | 1700 | 68 / 7803 (0.87 %) |
| 3 | 65.77 | 190 | 230 (`/ask` 240) | 1700 | 87 / 7817 (1.11 %) |

**Giải thích kết quả:**

- **RPS gần như bằng nhau (65.6 vs 65.8) vì giới hạn nằm ở phía Locust, không ở server.** Mỗi user chờ `between(0.5, 2)` s (trung bình 1.25 s) + ~0.22 s chờ trả lời → 1 user gửi ≈ 0.68 req/s → 100 user ≈ **68 req/s tối đa**. Server cả 1 lẫn 3 instance đều phục vụ kịp mức đó, nên thêm instance không tăng RPS. Muốn thấy RPS tăng phải đẩy thêm user hoặc giảm `wait_time`.
- **Khác biệt nằm ở tail latency:** 1 instance (giới hạn `cpus: 0.5`) đã gần bão hoà → p95 `/ask` 330 ms, `/health` p95 38 ms (phải xếp hàng sau request `/ask`). 3 instance → p95 `/ask` 240 ms, `/health` p95 6 ms. Thêm instance chưa tăng throughput nhưng giảm xếp hàng → p95 tốt hơn ~27 %.
- **p99 = 1700 ms ở cả hai** vì ~3 % request bị mock làm chậm cố định ~1.7 s (`MOCK_SLOW_RATE=0.03`): đuôi do LLM, scale ngang không chữa được.
- **Failures ~1 %** đều là `503` từ `MOCK_ERROR_RATE=0.01` (file `scale_*_failures.csv`), không phải do quá tải.
- **Bẫy khi đo:** `docker compose run locust` (không `--no-deps`) tự khởi động lại các service phụ thuộc theo file compose → agent quay về `deploy.replicas: 2`, xoá mất `--scale`. Lần đo đầu cả "1" và "3" instance thực ra đều chạy 2 → đã bỏ, đo lại với `--no-deps`.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Average nói dối về tail latency: 3% request chậm làm p99 tăng ×7 mà avg chỉ +30% → SLO phải đặt theo p95/p99.
  2. Throughput không tăng mãi theo concurrency: 1 process có giới hạn, quá ngưỡng (c=100) thì RPS giảm và p95 tăng ×12 do xếp hàng → load test phải tìm được điểm gãy này trước khi người dùng thật tìm ra.
  3. Hệ thống "khoẻ" về hạ tầng vẫn có thể trả lời sai (v1): cần eval chất lượng + quality gate bên cạnh metric, và so sánh bằng "cost / câu đúng" chứ không phải "cost / câu".
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

  Metric `agent_question_length_chars` (đã thêm ở Exercise 7.1) để thấy prompt bất thường; alert **cost burn rate** (chi phí/giờ vượt x lần mức thường, trước khi chạm `DAILY_BUDGET_USD`); tỉ lệ 429 / 402 (người dùng bị chặn); tỉ lệ retrieval không tìm được tài liệu (dấu hiệu KB thiếu); alert khi accuracy của eval định kỳ giảm so với baseline.
