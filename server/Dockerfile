# Ядро LearnOS: FastAPI + MCP, миграции применяются на старте
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    LEARNOS_DATA_DIR=/data \
    LEARNOS_KB_DIR=/kb \
    LEARNOS_SKILLS_DIR=/app/skills

# пин версии uv (G аудита: latest ломается без предупреждения); прямо в строке —
# классический docker builder не раскрывает ARG в COPY --from (поймал CI-гейт)
COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /usr/local/bin/uv

# ffmpeg + deno: yt-dlp требует JS-runtime для YouTube (PO-токены), иначе субтитры падают на 429
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*
ARG TARGETARCH
RUN case "$TARGETARCH" in \
      arm64) DENO_TRIPLE=aarch64-unknown-linux-gnu ;; \
      *) DENO_TRIPLE=x86_64-unknown-linux-gnu ;; \
    esac \
    && curl -fsSL "https://github.com/denoland/deno/releases/download/v2.9.7/deno-${DENO_TRIPLE}.zip" -o /tmp/deno.zip \
    && unzip -j /tmp/deno.zip deno -d /usr/local/bin \
    && rm /tmp/deno.zip \
    && deno --version | head -1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY skills ./skills
COPY app ./app
# тесты и eval-раннер нужны в образе: CI-гейт деплоя гоняет pytest в свежесобранном
# образе до up; evals запускаются вручную из контейнера на живой модели
COPY tests ./tests
COPY scripts ./scripts

RUN mkdir -p /data /kb
VOLUME ["/data", "/kb"]

EXPOSE 8765
CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
