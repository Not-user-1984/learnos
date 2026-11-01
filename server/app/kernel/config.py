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
    # LLM: cooldown ключа цепочки после ошибки квоты/авторизации, секунды (T-040)
    llm_key_cooldown: int = 600
    # Telegram-мост (модуль messenger): токен бота и чат назначения; прокси — при необходимости
    telegram_token: str = ""  # LEARNOS_TELEGRAM_TOKEN
    telegram_chat_id: str = "490168997"  # личный чат Дмитрия
    telegram_proxy: str = ""  # например socks5://host.docker.internal:7890
    # Песочница агентских скиллов (T-037): subprocess-таймаут run.py в секундах
    skill_exec_timeout: int = 120
    # Ревизия кода агентом-аудитором (T-038): корень git-репо (на проде — рабочая копия
    # deploy'я); пусто — инструменты ревизии отвечают «не настроено»
    repo_root: str = ""
    # Дневной бюджет подготовленных агентом веток agent/* (ступень 2 ревизии)
    git_branch_budget: int = 3
    # Ресёрч (модуль research): провайдер поиска и прокси для внешних запросов
    search_provider: str = "chain"  # цепочка [платный по ключу → ddg → wikipedia → hn]; см. T-019
    web_proxy: str = ""  # например socks5://192.168.0.10:1080 (vpn-gw) — если регион блокирует
    allow_private_url_fetch: bool = (
        False  # from-url: разрешить внутренние адреса (LAN) — по умолчанию SSRF-защита
    )
    # Auth (R-07): bearer-токен для /api и /mcp; пусто — проверка выключена
    # (личный сервис в LAN). Задан — все запросы, кроме /api/health, требуют
    # Authorization: Bearer <токен>. Веб-прокси Next добавляет его на сервере.
    api_token: str = ""
    # CORS: список origin через запятую; пусто — «*» (как раньше)
    cors_origins: str = ""
    yt_proxy: str = ""  # прокси yt-dlp (YouTube); из настроек связи (UI) или env LEARNOS_YT_PROXY

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
