# Day 14 Lab - Mission Answers

> Môi trường chạy: Windows 11 + WSL2 Ubuntu, Python 3.11.18 (venv `uv`), Docker Desktop 29.9.3, Compose v5.7.0. Ngày chạy: 2026-11-25.
> Mọi output dưới đây là output thật của lệnh đã chạy (token đã che).

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

File `01-localhost-vs-production/develop/app.py`:

1. **Hardcode secret** — dòng 17–18: `OPENAI_API_KEY = "sk-hardcoded-..."`, `DATABASE_URL = "postgresql://admin:password123@..."`. Push lên GitHub là lộ key + mật khẩu DB; muốn đổi key phải sửa code và deploy lại.
2. **Log ra secret** — dòng 34: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`. Log được gửi tới hệ thống log tập trung → ai đọc được log cũng có key. (Khi chạy thấy thật: `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`.)
3. **`print()` thay vì logging có cấu trúc** — dòng 33, 38. Không có level, timestamp, không phải JSON → không lọc / tìm / đếm được trong Loki, Datadog...
4. **Config cố định trong code** — dòng 21–22: `DEBUG = True`, `MAX_TOKENS = 500`. Muốn đổi giữa dev/staging/prod phải sửa code thay vì đổi biến môi trường.
5. **Không có health check** — không có `/health` (khi chạy `curl /health` → `404`). Platform không biết app chết để restart, load balancer không biết instance nào hỏng.
6. **Bind `localhost`** — dòng 51: `host="localhost"`. Trong container chỉ nhận kết nối từ chính container → từ ngoài không gọi được. Phải là `0.0.0.0`.
7. **Port cố định** — dòng 52: `port=8000`. Railway/Render cấp port qua biến `PORT`; app không đọc → platform không route được traffic.
8. **`reload=True`** — dòng 53: chế độ dev theo dõi file, tốn tài nguyên, không dùng cho production.
9. **Không xử lý shutdown** — không có lifespan / SIGTERM: khi platform tắt container, request đang chạy bị cắt ngang.

### Exercise 1.2: Chạy basic version

```text
$ curl -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

$ curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
→ HTTP 422   (bản develop nhận question qua query, không nhận JSON)

$ curl http://localhost:8000/health
{"detail":"Not Found"}  → HTTP 404
```

Log server (thấy secret bị in ra):

```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
```

Nó chạy được, nhưng **không production-ready**: lộ secret, không health check, chỉ nghe localhost.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode (`DEBUG = True`, key trong code) | Env vars qua `config.py` + `.env.example` | Cùng một code/image chạy ở dev, staging, prod chỉ bằng đổi biến; secret không vào git |
| Secret | `OPENAI_API_KEY = "sk-..."` | Đọc từ env, để trống thì dùng mock | Lộ key trên GitHub = mất tiền / mất dữ liệu; key phải đổi được mà không deploy lại |
| Health check | Không có (404) | `GET /health` (liveness) + `GET /ready` (readiness) | Platform tự restart khi app chết; LB ngừng gửi traffic tới instance chưa sẵn sàng |
| Logging | `print()`, in cả secret | JSON (`{"event": "agent_request", "question_length": ...}`), không log secret | Máy parse được → tìm/lọc/alert theo field; không lộ dữ liệu nhạy cảm |
| Shutdown | Đột ngột | Graceful: `lifespan` dọn dẹp sau khi uvicorn xử lý xong request đang chạy | Deploy/scale-down không làm hỏng request của người dùng |
| Host / Port | `localhost:8000` cố định | `0.0.0.0` + `PORT` từ env | Chạy được trong container và trên cloud (port do platform cấp) |
| Reload | `reload=True` luôn | Chỉ khi `DEBUG=true` | Production không cần theo dõi file, tiết kiệm tài nguyên |

Output bản production:

```text
$ curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). ...","model":"gpt-4o-mini"}
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":3.8,"version":"1.0.0","environment":"development",...}  [200]
$ curl http://localhost:8000/ready
{"ready":true}  [200]
```

Khi gửi SIGTERM, log cho thấy tắt êm: `Shutting down → Waiting for application shutdown → Application shutdown complete → Finished server process`.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11` — bản Python đầy đủ (Debian + build tools), rất nặng (~1 GB).
2. **Working directory:** `/app` (`WORKDIR /app`) — mọi lệnh `COPY`, `RUN`, `CMD` sau đó chạy trong thư mục này.
3. **Vì sao COPY requirements.txt trước:** Docker cache từng layer. `requirements.txt` ít đổi, code đổi liên tục. Copy requirements + `pip install` trước → sửa code chỉ làm mất cache của layer `COPY app.py`, layer cài thư viện (chậm nhất) được dùng lại → build lại nhanh hơn nhiều.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh *mặc định*, bị thay khi chạy `docker run image <lệnh khác>`. `ENTRYPOINT` là chương trình *cố định* của container; tham số của `docker run` được nối thêm vào nó. Hay dùng chung: `ENTRYPOINT ["uvicorn"]` + `CMD ["app:app"]`.

### Exercise 2.2: Build và run

```text
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run --rm -p 8000:8000 my-agent:develop
$ curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker?"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":4.0,"container":true}   [200]
```

`"container": true` → app biết mình đang chạy trong container. Image develop nặng **1.15 GB** vì base `python:3.11` bản đầy đủ.

### Exercise 2.3: Image size comparison

Đọc `02-docker/production/Dockerfile`:
- **Stage 1 (builder):** `python:3.11-slim` + cài `gcc`, `libpq-dev`, rồi `pip install --user` mọi thư viện vào `/root/.local`.
- **Stage 2 (runtime):** `python:3.11-slim` sạch, chỉ `COPY --from=builder /root/.local`, copy code, tạo user `appuser` (non-root), có `HEALTHCHECK`.
- **Vì sao nhỏ hơn:** image cuối chỉ chứa stage cuối. gcc, header, cache apt/pip nằm lại ở builder và bị bỏ; base `slim` thay cho bản full.

Số đo (`docker images`):
```text
$ docker images | grep my-agent
my-agent:advanced   ac7849fdd769   163MB
my-agent:develop    9b8840105a83   1.15GB
```

- Develop: **1154.3 MB** (1 154 311 927 byte)
- Production: **162.9 MB** (162 882 434 byte)
- Difference: nhỏ hơn **85.9 %** (≈ 7.1 lần) — `1 − 162.9 / 1154.3`

### Exercise 2.4: Docker Compose stack

```text
                  :80
 client ──▶ ┌──────────┐      ┌───────────┐
            │  nginx   │ ───▶ │  agent    │ ──▶ redis:6379  (session, rate limit)
            │ (LB, 10  │      │ (FastAPI, │ ──▶ qdrant:6333 (vector DB cho RAG)
            │  r/s)    │      │  :8000)   │
            └──────────┘      └───────────┘
        tất cả nằm chung network "internal" (bridge); chỉ nginx mở port ra ngoài
```

4 service: `agent` (build từ Dockerfile, không mở port ra ngoài), `redis`, `qdrant`, `nginx` (cổng 80/443). Giao tiếp bằng tên service qua DNS nội bộ của Compose (`redis://redis:6379/0`, `http://qdrant:6333`, `proxy_pass http://agent:8000`). `agent` chỉ khởi động khi redis và qdrant `service_healthy`.

Output test qua Nginx (`docker compose -p k5-day14-docker up -d --build`, 4 service: agent healthy, redis healthy, qdrant healthy, nginx mở cổng 80/443):

```text
$ curl http://localhost/health
{"status":"ok","uptime_seconds":24.2,"version":"2.0.0","timestamp":"2026-11-25T09:58:42.167939"}   [200]

$ curl -i http://localhost/ask -X POST -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

Header `Server: nginx` + 3 header bảo mật → request đi qua Nginx rồi mới tới agent (agent không mở cổng ra ngoài).

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- URL: **https://superb-upliftment-production.up.railway.app** — `/health` 200, `/ready` 200 (Redis nối được), `/ask` không key 401; `check_production_ready.py --public-url` → PASS 12/12 · 44/44
- Screenshot: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`
- Deploy thư mục `06-lab-complete/` (agent Part 6), Redis là service Redis của Railway, `REDIS_URL` + `AGENT_API_KEY` đặt trong Variables.

### Exercise 3.2: So sánh `railway.toml` và `render.yaml`

| | `railway.toml` | `render.yaml` |
|---|---|---|
| Định dạng | TOML, chỉ mô tả **1 service** (thư mục đang deploy) | YAML Blueprint, mô tả **cả hạ tầng** (web + Redis Key Value) trong 1 file |
| Build | `builder = "DOCKERFILE"` | `runtime: docker`, `rootDir: 06-lab-complete` (repo có nhiều thư mục) |
| Health check | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Secret | Không ghi trong file; đặt bằng `railway variables set` / dashboard | Khai báo trong file nhưng không có giá trị: `generateValue: true` (Render tự sinh) hoặc `sync: false` (nhập tay) |
| Redis | Thêm service Redis bằng tay trên dashboard rồi trỏ `REDIS_URL` | `fromService` lấy `connectionString` của service `keyvalue` ngay trong file |
| Deploy | `railway up` đẩy code từ máy (CLI) | Render đọc file từ GitHub, tự deploy khi push |

Vì sao khác: Railway hướng tới deploy nhanh từ CLI, cấu hình ít, phần còn lại ở dashboard. Render dùng "infrastructure as code": cả stack nằm trong git, tái tạo được bằng một Blueprint.

### Exercise 3.3: Cloud Run CI/CD (đọc `cloudbuild.yaml`, `service.yaml`)

Pipeline Cloud Build chạy 4 bước nối tiếp nhau (`waitFor`):
1. **test** — trong `python:3.11-slim`, cài requirements + pytest, chạy `pytest tests/`; fail thì dừng cả pipeline.
2. **build** — `docker build` image tag `$COMMIT_SHA` và `latest`, dùng `--cache-from latest` cho nhanh.
3. **push** — đẩy cả 2 tag lên Container Registry `gcr.io/$PROJECT_ID/ai-agent`.
4. **deploy** — `gcloud run deploy` image theo đúng commit, region `asia-southeast1`, 1–10 instance, 512Mi/1 CPU, secret `OPENAI_API_KEY` lấy từ Secret Manager.

`service.yaml` mô tả cùng service theo kiểu Knative: `minScale 1` (tránh cold start), `maxScale 10`, `containerConcurrency 80`, `livenessProbe /health`, `startupProbe /ready`, secret qua `secretKeyRef`.

## Part 4: API Security

### Exercise 4.1-4.3: Test results

**4.1 — API key (bản develop, `AGENT_API_KEY=secret-key-123 python app.py`):**

```text
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). ..."}
```

Ghi chú: bản develop Part 4 nhận **JSON body** (gửi query `?question=` thì lỗi 500 vì `request.json()` không parse được body rỗng). Bản develop trả 403 cho key sai; Part 6 của mình trả 401 cho cả thiếu lẫn sai key theo yêu cầu.

**4.2 — JWT (bản production, tài khoản `student` / `demo123`):**

```text
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
{"access_token":"<TOKEN đã che>","token_type":"bearer","expires_in_minutes":60,...}

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"question":"What is JWT?"}'
HTTP/1.1 200 OK
{"question":"What is JWT?","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":2.1e-05}}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"hi"}'
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

**4.3 — Rate limit (cùng token, 12 request liên tiếp):**

```text
$ for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"question\":\"test $i\"}"; done
req  1..9 -> 200
req 10    -> 429
req 11    -> 429
req 12    -> 429

$ curl -i ... (request tiếp theo)
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

9 lần 200 + 1 lần ở bài 4.2 = 10 request/phút → request thứ 11 bị 429.

### Exercise 4.4: Cost guard implementation

Bản mẫu `04-api-gateway/production/cost_guard.py`:
- Mỗi user có `UsageRecord` theo ngày (input/output tokens, số request). Chi phí = `input_tokens/1000 × 0.00015 + output_tokens/1000 × 0.0006` (giá gpt-4o-mini).
- `check_budget(user_id)` gọi **trước** khi gọi LLM: tổng toàn hệ thống ≥ $10/ngày → **503**; user ≥ $1/ngày → **402 Payment Required**; ≥ 80% thì log cảnh báo.
- `record_usage(...)` gọi **sau** khi LLM trả lời để cộng token/chi phí.
- Hạn chế: lưu trong RAM (`dict`) → restart là mất, nhiều instance mỗi cái đếm riêng.

Cách mình làm ở Part 6 (`06-lab-complete/app/cost_guard.py`): cùng công thức giá, nhưng tổng chi phí nằm trong **Redis** (`cost:day:YYYY-MM-DD`, `cost:month:YYYY-MM`) bằng `INCRBYFLOAT` (cộng nguyên tử, nhiều worker cộng cùng lúc không mất số), có `EXPIRE` để tự xoá. Vượt `DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD` → 402. Rate limit bảo vệ **tốc độ** (chống spam/DoS), cost guard bảo vệ **tiền** (một user hỏi chậm nhưng prompt rất dài vẫn có thể đốt budget) → cần cả hai.

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

**5.1 Health checks** (`05-scaling-reliability/develop/app.py`):

```text
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":3.3,...,"checks":{"memory":{"status":"ok","used_percent":6.2}}}
$ curl http://localhost:8000/ready
{"ready":true,"in_flight_requests":1}
```

- `/health` (**liveness**): "process còn sống không?" Fail → platform **restart** container. Không được phụ thuộc Redis/DB, nếu không Redis chết một lúc là mọi instance bị restart vô ích.
- `/ready` (**readiness**): "nhận traffic được chưa?" Fail (503) → load balancer **ngừng gửi request** tới instance đó nhưng không restart (đang khởi động, đang tắt, mất Redis).

**5.2 Graceful shutdown** — gửi 1 request rồi `kill -TERM` ngay:

```text
{"answer":"Đây là câu trả lời từ AI agent (mock). ..."} [HTTP 200]   ← request đang chạy vẫn xong
process còn sống? không
INFO: Shutting down
INFO: Waiting for application shutdown.
INFO 🔄 Graceful shutdown initiated...
INFO ✅ Shutdown complete
INFO: Finished server process
```

Uvicorn nhận SIGTERM → ngừng nhận kết nối mới → chờ request đang chạy xong → chạy phần shutdown của `lifespan` → thoát exit code 0.

**5.3 Stateless design:** state trong RAM (`dict` session) chỉ có ở 1 process. Khi chạy 3 instance sau Nginx, request 1 của user A vào instance-1, request 2 có thể vào instance-2 → không thấy history → bug. Cách sửa: lưu session/history ở **Redis** (`session:<id>` với TTL), mọi instance đọc cùng một chỗ, instance nào chết cũng không mất dữ liệu.

**5.4 Load balancing:** `docker compose -p k5-day14-scaling up -d --build --scale agent=3` → 3 agent `healthy` + redis + nginx (cổng 8080). Nginx dùng `upstream` round-robin: mỗi request đi tới instance kế tiếp.

**5.5 Test stateless** (`python test_stateless.py`, 5 câu cùng 1 session):

```text
Request 1: [instance-ae3fd4]   Q: What is Docker?
Request 2: [instance-73574c]   Q: Why do we need containers?
Request 3: [instance-026ce1]   Q: What is Kubernetes?
Request 4: [instance-ae3fd4]   Q: How does load balancing work?
Request 5: [instance-73574c]   Q: What is Redis used for?
Instances used: {'instance-73574c', 'instance-026ce1', 'instance-ae3fd4'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

5 request rơi vào 3 instance theo vòng (ae3fd4 → 73574c → 026ce1 → lặp lại) nhưng history vẫn đủ **10 tin** (5 user + 5 assistant) → state nằm ở Redis, không nằm trong RAM của instance nào.

## Part 6: Final Project — output `check_production_ready.py`

Chạy đầy đủ trong WSL (có Docker): `python check_production_ready.py` — build image 16 s, image **160 MB**, SIGTERM → exit 0, `docker stop` 0.6 s exit 0.

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

## AI Logs

| Lần | Hỏi / nhờ gì | Nhận được gì | Mình tự sửa / kiểm tra thế nào |
|---|---|---|---|
| 1 | Claude Code (Opus): clone repo, đọc đề, lập checklist + file lệnh | Checklist CP0–CP8, file Commands | Tự làm CP0: đổi tên repo, tạo venv 3.11 trong WSL, kiểm `posix 3.11.18` |
| 2 | Claude Code: chạy ví dụ Part 1, 4, 5 và ghi output | Output thật của curl / log server dán ở trên | Đọc lại từng output, đối chiếu với code mẫu (dòng code ở 1.1) |
| 3 | Claude Code: viết code Part 6 (`app/*.py`, Dockerfile, compose, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) | Code có comment giải thích từng bước | Chạy `check_production_ready.py --static-only` và `--skip-docker`; đọc và giải thích được từng file (xem ghi chú ôn tập) |
| 4 | Claude Code: chạy Part 7 Bước 1, sửa `KNOWLEDGE_BASE`, viết job CI | 10 file JSON trong `reports/`, 2 tài liệu KB mới, `.github/workflows/eval.yml` | Số trong `BENCHMARK_REPORT.md` copy từ output JSON; eval cuối 23/23, không regression; thử gate: v2 exit 0, v1 exit 1 |
| 5 | Claude Code: chạy Part 2, 5.4–5.5, grader đầy đủ, Part 7 Bước 2 (Locust, Jaeger, alert, ảnh) | Output thật, CSV Locust, 4 ảnh trong `screenshots/` | Phát hiện và sửa 2 lỗi: (1) Dockerfile `production/` thiếu `PYTHONUSERBASE` → agent crash `No module named 'uvicorn'`; (2) `docker compose run locust` tự đưa agent về `replicas: 2` → chạy lại với `--no-deps`, kiểm số instance bằng Prometheus `count(up{job="agent"}==1)` trước mỗi lần đo |
