# Ядро LearnOS: FastAPI + MCP, миграции применяются на старте
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    LEARNOS_DATA_DIR=/data \
    LEARNOS_KB_DIR=/kb \
    LEARNOS_SKILLS_DIR=/app/skills

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# yt-dlp нужен скиллу youtube-to-summary
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && curl -fsSL https://yt-dlp.org/downloads/latest/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY skills ./skills
COPY app ./app

RUN mkdir -p /data /kb
VOLUME ["/data", "/kb"]

EXPOSE 8765
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
