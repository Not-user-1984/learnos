"""Домен библиотеки: виды источников, статусы обработки, правила."""

SourceKind = str  # book | video | web


class SourceRules:
    """Правила жизни источника."""

    @staticmethod
    def can_process(status: str) -> bool:
        """Обработку можно запускать из found/chosen/failed; повторную из processed — только с force."""
        return status in {"found", "chosen", "failed"}

    @staticmethod
    def normalize_kind(kind: str) -> str:
        """Привести kind к известному."""
        k = kind.strip().lower()
        if k in {"pdf", "книга", "book"}:
            return "book"
        if k in {"youtube", "video", "видео"}:
            return "video"
        if k in {"article", "web", "статья"}:
            return "web"
        raise ValueError(f"неизвестный вид источника: {kind}")
