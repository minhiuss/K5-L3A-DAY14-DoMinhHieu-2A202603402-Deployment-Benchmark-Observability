# Deployment Information

> ⏳ Bản nháp — điền URL và ảnh sau khi deploy (CP6). Không ghi API key thật vào file này.

## Public URL

https://<điền-sau>.up.railway.app

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

Kết quả thật: ⏳

```text

```

`python check_production_ready.py --public-url "$BASE"`: ⏳

## Environment Variables Set

Đặt trên dashboard Railway (Variables), không có trong code / git:

| Biến | Giá trị |
|---|---|
| `AGENT_API_KEY` | (secret, che) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` (tham chiếu service Redis của Railway) |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `PORT` | Railway tự cấp |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
