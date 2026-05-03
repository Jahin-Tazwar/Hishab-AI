# Single-stage Python slim image for Cloud Run deployment.
FROM python:3.11-slim

WORKDIR /app

# System packages: only what's needed for psycopg / cryptography (none for our deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Cloud Run injects PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

# Use uvicorn directly (no gunicorn — single worker is fine for MVP)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
