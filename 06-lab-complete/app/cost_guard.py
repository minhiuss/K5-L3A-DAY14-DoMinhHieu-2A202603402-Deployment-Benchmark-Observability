"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402

Cách làm: 2 bộ đếm (số thực) trong Redis
  cost:day:2026-11-25  → tổng USD hôm nay   (tự xoá sau 2 ngày)
  cost:month:2026-11   → tổng USD tháng này (tự xoá sau 32 ngày)
Lưu trong Redis (không phải biến Python) → mọi worker / instance cùng thấy một tổng.
"""
import time

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _keys() -> tuple[str, str]:
    return "cost:day:" + time.strftime("%Y-%m-%d"), "cost:month:" + time.strftime("%Y-%m")


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    day_key, month_key = _keys()
    spent_day = float(r.get(day_key) or 0)       # chưa có key → None → 0
    spent_month = float(r.get(month_key) or 0)
    if spent_day >= settings.daily_budget_usd or spent_month >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,                     # 402 Payment Required
            detail={
                "error": "Budget exceeded",
                "spent_today_usd": round(spent_day, 6),
                "daily_budget_usd": settings.daily_budget_usd,
                "spent_month_usd": round(spent_month, 6),
                "monthly_budget_usd": settings.monthly_budget_usd,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = input_tokens / 1000 * PRICE_INPUT_PER_1K + output_tokens / 1000 * PRICE_OUTPUT_PER_1K
    day_key, month_key = _keys()
    pipe = r.pipeline()                          # gửi 4 lệnh trong 1 lượt mạng
    pipe.incrbyfloat(day_key, cost)              # INCRBYFLOAT: cộng nguyên tử, 2 worker cộng cùng lúc không mất số
    pipe.expire(day_key, 2 * 24 * 3600)
    pipe.incrbyfloat(month_key, cost)
    pipe.expire(month_key, 32 * 24 * 3600)
    pipe.execute()
    return cost
