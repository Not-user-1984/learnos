"""Настройки приложения. Единственное место чтения переменных окружения."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_DIR = Path(__file__).resolve().parent.parent.parent.parent
SERVER_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Все настройки LearnOS; префикс LEARNOS_, значения по умолчанию — локальный мак."""

    model_config = SettingsConfigDict(
        env_prefix="LEARNOS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_dir: Path = REPO_DIR / "data"
    kb_dir: Path = REPO_DIR / "kb"
    skills_dir: Path = SERVER_DIR / "skills"
    llm_config: Path = SERVER_DIR / "config" / "llm.yaml"
    log_format: str = "text"
    tool_result_max_chars: int = 8000
    context_budget_tokens: int = 24000
    db_echo: bool = False
    # Telegram-мост (модуль messenger): токен бота и чат назначения; прокси — при необходимости
    telegram_token: str = ""  # LEARNOS_TELEGRAM_TOKEN
    telegram_chat_id: str = "490168997"  # личный чат Дмитрия
    telegram_proxy: str = ""  # например socks5://host.docker.internal:7890

    @property
    def db_path(self) -> Path:
        """Путь к файлу SQLite."""
        return self.data_dir / "learnos.db"

    @property
    def db_url(self) -> str:
        """URL подключения для SQLAlchemy."""
        return f"sqlite:///{self.db_path}"


@lru_cache
def get_settings() -> Settings:
    """Синглтон настроек; в тестах пересобирается cache_clear()."""
    return Settings()
