"""Telegram Bot API: отправка сообщений и файлов, при необходимости через прокси.

Прокси не обязателен: сначала прямое соединение, при сетевой ошибке — повтор через
LEARNOS_TELEGRAM_PROXY (например socks5://host.docker.internal:7890).
"""

import re
from pathlib import Path

import httpx

from ...kernel.errors import ExternalServiceError

API = "https://api.telegram.org"
MAX_MESSAGE = 3800  # запас до лимита Telegram 4096


class TelegramBotGateway:
    """Реализация TelegramGateway на Bot API; токен и чат из настроек."""

    def __init__(self, settings) -> None:
        self._token = settings.telegram_token
        self._chat_id = settings.telegram_chat_id
        self._proxy = settings.telegram_proxy or None
        self._route: str | None = None  # "" = прямое соединение, url = прокси

    @property
    def configured(self) -> bool:
        return bool(self._token)

    async def send_message(self, text: str, chat_id: str | None = None) -> int:
        return await self._call(
            "sendMessage",
            {
                "chat_id": chat_id or self._chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )

    async def send_document(self, path: str, caption: str = "", chat_id: str | None = None) -> int:
        file = Path(path)
        if not file.exists():
            raise ExternalServiceError(f"файл не найден: {path}")
        return await self._call(
            "sendDocument",
            {"chat_id": chat_id or self._chat_id, "caption": caption[:1000], "parse_mode": "HTML"},
            files={"document": (file.name, file.read_bytes())},
        )

    async def _call(self, method: str, data: dict, files: dict | None = None) -> int:
        if not self._token:
            raise ExternalServiceError(
                "Telegram не настроен: задай LEARNOS_TELEGRAM_TOKEN", code="not_configured"
            )
        url = f"{API}/bot{self._token}/{method}"
        # маршрут: сперва запомненный рабочий, иначе прямой (быстрый connect-таймаут) → прокси
        routes: list[str | None] = [self._route] if self._route is not None else [None, self._proxy]
        last_error: Exception | None = None
        for proxy in routes:
            try:
                timeout = httpx.Timeout(60, connect=8)
                # "" означает «прямой маршрут» — для httpx это None (Proxy("") бросает ValueError)
                async with httpx.AsyncClient(proxy=proxy or None, timeout=timeout) as client:
                    resp = await client.post(url, data=data, files=files)
                    body = resp.json()
                if resp.status_code == 200 and body.get("ok"):
                    self._route = proxy or ""
                    return int(body["result"]["message_id"])
                raise ExternalServiceError(f"Telegram {method}: {body.get('description', resp.status_code)}")
            except httpx.HTTPError as e:  # сеть: пробуем следующий маршрут (прокси)
                last_error = e
                continue
        raise ExternalServiceError(f"Telegram недоступен (включая прокси): {last_error}")


def chunk_for_telegram(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    """Разбить текст на куски <= limit по границам абзацев (для чтения в Telegram)."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(para) <= limit:
            current = para
        else:
            # сверхдлинный абзац — режем по предложениям
            current = ""
            for sentence in _split_sentences(para):
                cand = f"{current} {sentence}".strip()
                if len(cand) > limit and current:
                    chunks.append(current)
                    current = sentence
                else:
                    current = cand
    if current:
        chunks.append(current)
    return chunks


def _split_sentences(paragraph: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", paragraph)
    return parts or [paragraph]
