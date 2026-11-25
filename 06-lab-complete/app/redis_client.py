"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Yêu cầu:
  • Đọc REDIS_URL từ config
  • App vẫn phải KHỞI ĐỘNG ĐƯỢC khi Redis chưa sẵn sàng (đừng ping Redis lúc import)
  • redis_healthy() dùng cho GET /ready: Redis không kết nối được → False
"""
import redis

from app.config import settings

# from_url chỉ tạo "pool" kết nối, CHƯA kết nối thật → import không bao giờ lỗi khi Redis chết.
# Timeout ngắn: Redis chết thì /ready trả 503 sau ~1s thay vì treo.
r = redis.from_url(
    settings.redis_url,
    decode_responses=True,       # trả str thay vì bytes
    socket_connect_timeout=1,
    socket_timeout=1,
)


def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except redis.RedisError:     # ConnectionError, TimeoutError... đều là con của RedisError
        return False
