# Lyra Oracle — Qobuz Hi-Fi Acquisition Microservice
# Authenticates with Qobuz API, downloads FLAC/hi-res audio, embeds metadata.
#
# Build:  docker build -t lyra-qobuz docker/qobuz/
# Run:    docker-compose up -d qobuz
#
# Volume mounts:
#   /app/staging  → host staging/ dir (shared with ingest watcher)

FROM python:3.12-slim AS base

LABEL maintainer="Lyra Oracle"
LABEL description="Qobuz hi-fi audio acquisition service"

# Prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY service.py .

# Create staging directory
RUN mkdir -p /app/staging

# Non-root user for security
RUN useradd --create-home --shell /bin/bash lyra && \
    chown -R lyra:lyra /app
USER lyra

EXPOSE 7700

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; r=requests.get('http://localhost:7700/health', timeout=3); r.raise_for_status()" || exit 1

# Uvicorn with 2 workers — Qobuz rate-limits aggressively, more workers
# won't help and will trigger 429s. The /acquire/batch endpoint uses
# a thread pool internally for controlled concurrency.
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "7700", "--workers", "2", "--log-level", "info"]
