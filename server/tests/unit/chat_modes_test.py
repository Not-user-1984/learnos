"""Режимы чата: MODES (схемы) и AGENT_BY_MODE (сервис) согласованы."""

from app.modules.chat.schemas import MODES
from app.modules.chat.service import AGENT_BY_MODE


def test_agent_by_mode_covers_all_modes():
    assert set(AGENT_BY_MODE) == set(MODES), "новый режим чата должен получить агента"
