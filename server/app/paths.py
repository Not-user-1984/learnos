"""Совместимость путей для скиллов (server/skills/*/run.py)."""

from .kernel.config import get_settings

_settings = get_settings()

DATA_DIR = _settings.data_dir
DB_PATH = _settings.db_path
KB_DIR = _settings.kb_dir

DATA_DIR.mkdir(parents=True, exist_ok=True)
KB_DIR.mkdir(parents=True, exist_ok=True)
