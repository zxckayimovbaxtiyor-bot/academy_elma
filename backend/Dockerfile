# One image for the API and the worker (different commands in docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg/ffprobe for the HLS transcodes done by the worker.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
# Test tools are included so the suite can also be run on the offline server.
RUN pip install -r requirements-dev.txt

COPY . .
RUN useradd --system --uid 10001 --home-dir /app academy \
 && mkdir -p /data/media \
 && chown academy /data/media
USER academy

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-4} --proxy-headers --forwarded-allow-ips='*'"]
