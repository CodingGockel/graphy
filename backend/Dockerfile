# Backend image: FastAPI served by uvicorn.
FROM python:3.12-slim

# Don't write .pyc files; flush stdout/stderr immediately (so container logs work).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY src ./src
COPY healthcheck.py .

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Number of uvicorn workers (override via compose / env).
ENV UVICORN_WORKERS=2

# Container-level *liveness* check (see healthcheck.py): succeed as long as the API
# answers HTTP at all. /api/v1/health itself returns 503 when GraphDB (external,
# VPN-gated) or the LLM is unreachable — that's a readiness concern, not liveness.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "healthcheck.py"]

# No --reload in production. Workers come from $UVICORN_WORKERS.
# --proxy-headers + --forwarded-allow-ips=*: trust X-Forwarded-* from the nginx
# reverse proxy so the app sees the real client IP and https scheme. (Safe here:
# the backend has no published host port, so only the in-network nginx reaches it.)
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS} --proxy-headers --forwarded-allow-ips='*'"]
