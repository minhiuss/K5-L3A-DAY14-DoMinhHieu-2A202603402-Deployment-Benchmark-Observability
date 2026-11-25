"""
Production AI Agent — Part 6 Final Project

Chạy:   uvicorn app.main:app --workers 2      (từ thư mục 06-lab-complete/)
Chấm:   python check_production_ready.py

Luồng của POST /ask:
  verify_api_key (401) → check_rate_limit (429) → check_budget (402) → LLM → record_cost
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


# ── Tiêu chí 10: structured logging ─────────────────────────────────────
class JsonFormatter(logging.Formatter):
    """Biến mỗi bản ghi log thành 1 dòng JSON: {"ts", "lvl", "event", ...các field thêm}."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))      # field thêm truyền qua extra={"fields": {...}}
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(entry, ensure_ascii=False)


logger = logging.getLogger("agent")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
logger.handlers = [_handler]
logger.setLevel(settings.log_level)
logger.propagate = False        # không đẩy lên root logger → không bị in lần 2 theo format khác


def log(event: str, level: int = logging.INFO, **fields):
    logger.log(level, event, extra={"fields": fields})


# ── Tiêu chí 11: graceful shutdown ──────────────────────────────────────
# Uvicorn tự bắt SIGTERM: ngừng nhận request mới, chờ request đang chạy xong,
# rồi chạy phần sau `yield` bên dưới và thoát với exit code 0.
# → KHÔNG tự đăng ký signal.signal(SIGTERM, ...) để khỏi đè handler của uvicorn.
STATE = {"ready": False, "started_at": time.time(), "in_flight": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: KHÔNG bắt buộc Redis phải sống (container phải chạy được khi chưa có Redis)
    STATE["ready"] = True
    log("startup", env=settings.environment, port=settings.port, redis_ok=redis_healthy())
    yield
    # Shutdown: uvicorn chỉ tới đây SAU KHI request đang chạy đã xong
    STATE["ready"] = False
    log("shutdown", in_flight=STATE["in_flight"])
    r.close()


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Mỗi request → 1 dòng log JSON có path, status, thời gian xử lý (ms)."""
    start = time.perf_counter()
    STATE["in_flight"] += 1
    try:
        response = await call_next(request)
    finally:
        STATE["in_flight"] -= 1
    log("request", method=request.method, path=request.url.path,
        status=response.status_code, ms=round((time.perf_counter() - start) * 1000, 1))
    return response


# ── Xử lý lỗi: trả JSON rõ ràng, không lộ stack trace ──────────────────
@app.exception_handler(redis.RedisError)
async def redis_error_handler(request: Request, exc: redis.RedisError):
    log("redis_error", logging.ERROR, path=request.url.path, error=type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Storage temporarily unavailable"})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log("unhandled_error", logging.ERROR, path=request.url.path, error=type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=100)


def _tokens(text: str) -> int:
    """Ước lượng số token (~4 ký tự / token) vì mock LLM không trả usage."""
    return max(1, len(text) // 4)


# ── Tiêu chí 4: liveness ────────────────────────────────────────────────
@app.get("/health")
def health():
    """Process còn sống → 200. KHÔNG gọi Redis ở đây: Redis chết không có nghĩa là app chết."""
    return {"status": "ok", "uptime_seconds": round(time.time() - STATE["started_at"], 1),
            "environment": settings.environment}


# ── Tiêu chí 5: readiness ───────────────────────────────────────────────
@app.get("/ready")
def ready():
    """Sẵn sàng phục vụ? Cần Redis (rate limit + cost guard). Không có → 503 để LB ngừng gửi traffic."""
    if not STATE["ready"]:
        raise HTTPException(status_code=503, detail="Shutting down")
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis not reachable")
    return {"ready": True}


# ── Tiêu chí 6, 7, 8: /ask được bảo vệ ─────────────────────────────────
@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):   # 401 nếu thiếu / sai key
    check_rate_limit(api_key)                                         # 429 nếu quá RATE_LIMIT_PER_MINUTE
    check_budget()                                                    # 402 nếu hết budget
    answer = llm_ask(body.question)
    cost = record_cost(_tokens(body.question), _tokens(answer))
    log("ask", user_id=body.user_id, q_len=len(body.question), cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}
