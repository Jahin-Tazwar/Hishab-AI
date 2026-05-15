# Single-stage Python slim image for Render deployment.
#
# Build-time notes:
#   * No `build-essential` apt layer — every dep in requirements.txt
#     (pandas, pydantic-core, supabase, etc.) ships prebuilt wheels for
#     manylinux_2_17_x86_64, which is what python:3.11-slim (Debian
#     bookworm) consumes. Skipping `build-essential` saves ~200 MB of
#     apt download + ~30-60 s on cold builds.
#   * If you add a dep that needs to compile C/Rust, restore the apt
#     install — but try to find a wheel-shipping version first.
#
# Layer-cache discipline: requirements.txt is COPY'd and pip-installed
# BEFORE the application code, so editing app/ doesn't invalidate the
# pip layer. Bumping a version in requirements.txt rebuilds the deps.

FROM python:3.11-slim

# python-magic needs libmagic1 at runtime (used by ingestion MIME detection).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer when requirements.txt unchanged)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Render injects PORT env var; default to 8080 for parity with Cloud Run.
ENV PORT=8080
EXPOSE 8080

# Use uvicorn directly (no gunicorn — single worker is fine for MVP)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
