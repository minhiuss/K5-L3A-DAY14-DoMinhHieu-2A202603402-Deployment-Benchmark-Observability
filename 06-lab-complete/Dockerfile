# ============================================================
# Production Dockerfile — multi-stage (tiêu chí 1)
#   Stage 1 "builder": có pip, cài dependencies vào /install
#   Stage 2 "runtime": chỉ copy /install + code → image nhỏ, không có cache pip
# ============================================================

# ── Stage 1: builder ──
FROM python:3.11-slim AS builder
WORKDIR /build
# requirements.txt TRƯỚC code: code đổi mà requirements không đổi → Docker dùng lại layer cache, khỏi cài lại
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ──
FROM python:3.11-slim AS runtime
# User non-root: app bị chiếm quyền thì kẻ tấn công cũng không có root trong container
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=app:app app/ ./app/
COPY --chown=app:app utils/ ./utils/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
USER app
EXPOSE 8000

# Docker tự gọi /health mỗi 30s; fail 3 lần → container "unhealthy"
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8000'), timeout=3)" || exit 1

# `exec` thay shell bằng uvicorn → uvicorn là PID 1, nhận SIGTERM trực tiếp khi `docker stop`
# ${PORT:-8000}: Railway/Render cấp PORT; không có thì dùng 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
