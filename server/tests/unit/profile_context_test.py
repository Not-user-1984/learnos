"""Блок «Контекст» несёт имя и «о себе» из профиля — смена профиля меняет промпт (BUG-007)."""

import app.modules.profile.infra.tables  # noqa: F401 — регистрирует settings-таблицу до create_all фикстуры


def _context(container) -> str:
    """Блок «Контекст» свободного разговора: только профиль, без источника/сессии."""
    conv = {"activity_id": None, "chapter_idx": None, "mode": "free", "focus_block_uid": None}
    return container.chat._context_block(conv, None)


def test_context_block_carries_name_and_about(container):
    """Имя и «О себе» из профиля доходят до системного промпта."""
    block = _context(container)
    profile = container.profile.get()
    assert f"Имя: {profile.name}" in block
    assert profile.about in block


def test_profile_change_changes_context_block(container):
    """Смена about/name в профиле меняет блок «Контекст» (без LLM)."""
    before = _context(container)
    profile = container.profile.get()
    container.profile.update(
        profile.model_copy(update={"name": "Тест", "about": "Python-разработчик, учу алгоритмы"})
    )
    after = _context(container)
    assert "Имя: Тест" in after
    assert "Python-разработчик" in after
    assert "Имя: Тест" not in before
    assert "Python-разработчик" not in before


def test_person_brief_skips_empty_about(container):
    """Пустое «о себе» не оставляет в брифе висящей строки."""
    container.profile.update(container.profile.get().model_copy(update={"about": "  "}))
    assert "О себе" not in container.profile.person_brief()
