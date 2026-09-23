FROM python:3.11-slim

# Security: do not run as root
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app
ENV DATABASE_PATH=/app/data/otp_service.db

# Install dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/

# The named SQLite volume inherits this directory's ownership on first mount.
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)"

# reload=False is the default; stated explicitly for clarity
# Only the internal gateway reaches this container; honor its HTTPS forwarding.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--no-access-log"]
