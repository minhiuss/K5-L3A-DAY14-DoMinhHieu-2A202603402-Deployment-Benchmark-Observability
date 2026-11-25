"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)

Cách làm — sliding window bằng Redis sorted set (ZSET):
  key   = "ratelimit:<hash của API key>"
  member = mã duy nhất của 1 request, score = thời điểm request (giây)
  1. ZREMRANGEBYSCORE: xoá request cũ hơn 60 giây
  2. ZCARD: đếm request còn lại trong cửa sổ 60 giây
  3. đủ giới hạn → 429; chưa đủ → ZADD request này
  4. EXPIRE: key tự xoá khi không ai gọi nữa (khỏi rác Redis)
"""
import hashlib
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    # Không lưu API key thô vào Redis — chỉ lưu 16 ký tự đầu của mã băm sha256
    bucket = "ratelimit:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    now = time.time()
    limit = settings.rate_limit_per_minute

    r.zremrangebyscore(bucket, 0, now - WINDOW_SECONDS)          # 1
    count = r.zcard(bucket)                                       # 2
    if count >= limit:                                            # 3
        oldest = r.zrange(bucket, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
        raise HTTPException(
            status_code=429,
            detail={"error": "Rate limit exceeded", "limit": limit, "window_seconds": WINDOW_SECONDS},
            headers={"Retry-After": str(retry_after)},
        )
    r.zadd(bucket, {f"{now}-{uuid.uuid4().hex[:8]}": now})
    r.expire(bucket, WINDOW_SECONDS + 1)                          # 4
