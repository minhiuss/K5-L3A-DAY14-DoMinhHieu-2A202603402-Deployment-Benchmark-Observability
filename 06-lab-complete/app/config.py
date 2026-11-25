"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Mỗi field dưới đây đọc một biến môi trường bằng os.getenv(TÊN, mặc_định).
  • Có biến → dùng giá trị của biến (vd Railway/Render/script chấm đặt).
  • Không có → dùng mặc định an toàn cho local (không bao giờ là secret thật).
Danh sách biến đầy đủ: xem .env.example.
"""
import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


@dataclass
class Settings:
    # default_factory → đọc env lúc tạo Settings() (lúc app khởi động), không phải lúc định nghĩa class
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    # Secret: mặc định rỗng → thiếu AGENT_API_KEY thì mọi request /ask đều bị 401 (an toàn)
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=lambda: _env_float("DAILY_BUDGET_USD", 1.0))
    monthly_budget_usd: float = field(default_factory=lambda: _env_float("MONTHLY_BUDGET_USD", 10.0))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


settings = Settings()
