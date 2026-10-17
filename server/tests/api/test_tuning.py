"""Tuning: стадия правки промпта → дифф → применение (override-файл) → сброс."""

from __future__ import annotations

from app.agent.runtime import resolve_prompt_path


def test_stage_apply_and_reset(rest_app, client, container):
    # текущий промпт быстрого разбора
    current = client.get("/api/tuning/prompts").json()
    assert any(p["agent"] == "quick_reviewer" for p in current)

    staged = client.post("/api/conversations", json={"mode": "tuning", "title": "тюн"}).json()
    # стадируем через сервис (REST-обёртки stage нет — её вызывает инструмент агента)
    card = container.tuning.stage_change(
        "quick_reviewer", "Новый текст промпта. Шути больше.", "больше шуток", staged["uid"]
    )
    assert card["diff"], "дифф не пуст"
    assert any(d["op"] == "+" and "Шути" in d["line"] for d in card["diff"])
    change_id = card["change_id"]

    # применение: пишет override и меняет резолв промпта
    r = client.post(f"/api/tuning/changes/{change_id}/approve")
    assert r.status_code == 200, r.text
    default_path = container.agent_registry.get("quick_reviewer").prompt_path
    assert "Шути больше" in resolve_prompt_path(default_path).read_text(encoding="utf-8")

    # сброс возвращает промпт из кода
    rr = client.post("/api/tuning/prompts/quick_reviewer/reset")
    assert rr.status_code == 200
    assert "Шути больше" not in resolve_prompt_path(default_path).read_text(encoding="utf-8")


def test_reject_change(rest_app, client, container):
    card = container.tuning.stage_change("free_chat", "мимо", "тест отклонения")
    r = client.post(f"/api/tuning/changes/{card['change_id']}/reject")
    assert r.status_code == 200
    changes = client.get("/api/tuning/changes?status=rejected").json()
    assert any(c["change_id"] == card["change_id"] for c in changes)


def test_unknown_agent_rejected(container):
    import pytest

    from app.kernel.errors import NotFound

    with pytest.raises(NotFound):
        container.tuning.stage_change("no_such_agent", "текст", "summary")
