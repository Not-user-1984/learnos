"""Структурные логи: JSON в проде, читаемый текст локально."""

import json
import logging
import sys
from typing import Any

_CONFIGURED = False


def setup_logging(fmt: str = "text") -> None:
    """Настроить корневой логгер один раз за процесс."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger("learnos")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _CONFIGURED = True


class _JsonFormatter(logging.Formatter):
    """Минимальный JSON-форматтер без внешних зависимостей."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("module", "use_case", "conversation_uid", "duration_ms", "agent"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
