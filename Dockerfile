FROM python:3.11-slim

# Security: do not run as root
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/

# Ensure the non-root user owns the workdir
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# reload=False is the default; stated explicitly for clarity
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
