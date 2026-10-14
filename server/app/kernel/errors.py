"""Иерархия ошибок приложения. REST маппит их в HTTP, адаптер инструментов — в {"error", "message"}."""


class AppError(Exception):
    """Базовая ошибка: код для машин, сообщение — для человека."""

    code = "app_error"
    http_status = 500

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(AppError):
    """Сущность не найдена."""

    code = "not_found"
    http_status = 404


class Conflict(AppError):
    """Конфликт состояния (например, удаление источника с блоками)."""

    code = "conflict"
    http_status = 409


class InvalidState(AppError):
    """Недопустимый переход или состояние (например, advance вне стейт-машины)."""

    code = "invalid_state"
    http_status = 409


class ValidationFailed(AppError):
    """Некорректные входные данные."""

    code = "validation_failed"
    http_status = 422


class ExternalServiceError(AppError):
    """Внешний сервис (скилл, LLM, сеть) ответил ошибкой."""

    code = "external_service_error"
    http_status = 502


class LLMError(ExternalServiceError):
    """Ошибка LLM-провайдера: not_configured | auth | rate_limit | timeout | bad_request | unavailable."""

    code = "llm_error"
    http_status = 502
