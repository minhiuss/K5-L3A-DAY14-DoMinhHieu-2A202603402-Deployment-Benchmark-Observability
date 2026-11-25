# Deployment Information

## Public URL

https://superb-upliftment-production.up.railway.app

## Platform

Railway (Dockerfile builder, `06-lab-complete/railway.toml`) + Redis service của Railway.
Bản thay thế: Render Blueprint (`06-lab-complete/render.yaml`, web + Key Value).

## Test Commands

Đặt `BASE` là URL public, `AGENT_API_KEY` là key đã đặt trên dashboard (không dán key vào bài):

### Health Check

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200 (Redis kết nối được)
```

### API Test (with authentication)

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả thật (2026-11-25, `BASE=https://superb-upliftment-production.up.railway.app`):

```text
GET  /health            → 200  {"status":"ok","uptime_seconds":35.7,"environment":"production"}
GET  /ready             → 200  {"ready":true}
POST /ask (không key)   → 401  {"detail":"Missing or invalid API key. Send header: X-API-Key: <key>"}
POST /ask (có key)      → 200  {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Log trên Railway (`screenshots/test.png`): `event: startup env: production port: 8080 redis_ok: true`, rồi lần lượt `/health 200`, `/ready 200`, `/ask 401`, `/ask 200` (`cost_usd: 0.00000975`).


`python check_production_ready.py --public-url "$BASE"`:

```text
     ✅ Public URL: GET https://superb-upliftment-production.up.railway.app/health → 200
  Result: 12/12 tiêu chí đạt · 44/44 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

## Environment Variables Set

Đặt trên dashboard Railway (Variables), không có trong code / git:

| Biến | Giá trị |
|---|---|
| `AGENT_API_KEY` | (secret, che) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (tham chiếu service Redis của Railway) |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | không đặt → mặc định `10` trong `app/config.py` |
| `DAILY_BUDGET_USD` | không đặt → mặc định `1.0` trong `app/config.py` |
| `PORT` | Railway tự cấp |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
