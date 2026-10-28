"""Tuning: стадия правки промпта → дифф → применение (override-файл) → сброс; правки builtin-скиллов."""

from __future__ import annotations

import pytest

from app.agent.runtime import resolve_prompt_path
from app.kernel.errors import NotFound, ValidationFailed
from app.kernel.tools.spec import ToolContext


def test_stage_apply_and_reset(rest_app, client, container):
    # текущий промпт быстрого разбора
    current = client.get("/api/tuning/prompts").json()
    assert any(p["agent"] == "quick_reviewer" for p in current)

    staged = client.post("/api/conversations", json={"mode": "tuning", "title": "тюн"}).json()
    # стадируем через сервис (REST-обёртки stage нет — её вызывает инструмент агента)
    card = container.tuning.stage_change(
        "quick_reviewer", "Новый текст промпта. Шути больше.", "больше шуток", staged["uid"]
    )
    assert card["kind"] == "prompt"
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
    with pytest.raises(NotFound):
        container.tuning.stage_change("no_such_agent", "текст", "summary")


def test_propose_skill_change_card_backup_and_rollback(rest_app, client, container):
    """Правка builtin-скилла: карточка с диффом → approve пишет override+бэкап → сброс откатывает."""
    stub = "def main(query='', limit=5, **_):\n    return {'marker': 'override-active', 'query': query}\n"
    card = container.tuning.stage_skill_change("web-search", "run.py", stub, "тестовый override")
    assert card["kind"] == "skill"
    assert card["_card"]["type"] == "prompt_change" and card["_card"]["kind"] == "skill"
    assert card["_card"]["file"] == "run.py"
    assert any(d["op"] == "+" and "override-active" in d["line"] for d in card["diff"])

    r = client.post(f"/api/tuning/changes/{card['change_id']}/approve")
    assert r.status_code == 200, r.text
    data = container.settings.data_dir
    assert "override-active" in (data / "skill-overrides" / "web-search" / "run.py").read_text(
        encoding="utf-8"
    )
    backups = list((data / "prompt_backups" / "skill_web-search").glob("*__run.py"))
    assert backups and "httpx" in backups[0].read_text(encoding="utf-8")  # бэкап исходника

    # скилл живо исполняет override (сеть не зовётся — заглушка)
    assert container.skills.run("web-search", {"query": "тест"})["marker"] == "override-active"
    assert container.tools.has("web-search")  # инструмент на месте после reload

    # откат: override снят, файл скилла снова из кода
    rr = client.post("/api/tuning/skills/web-search/reset")
    assert rr.status_code == 200 and rr.json()["reset"] is True
    assert not (data / "skill-overrides" / "web-search" / "run.py").exists()
    builtin_run = (container.settings.skills_dir / "web-search" / "run.py").resolve()
    assert container.skills.effective_file("web-search", "run.py").resolve() == builtin_run


def test_propose_skill_change_rejections(container):
    """Агентский скилл и неизвестное имя через карточку не проходят; файл только run.py|SKILL.md."""
    container.tools.call(
        "save_skill",
        {
            "skill_name": "mine",
            "skill_md": "---\nname: mine\ndescription: свой скилл\n---\n",
            "run_py": "def main(**_):\n    return {}\n",
        },
        ToolContext(channel="agent", agent_name="root"),
    )
    with pytest.raises(ValidationFailed, match="save_skill"):
        container.tuning.stage_skill_change("mine", "run.py", "x = 1", "свое не трогаем")
    with pytest.raises(NotFound):
        container.tuning.stage_skill_change("no_such_skill", "run.py", "x = 1", "нет такого")
    with pytest.raises(ValidationFailed, match="файл"):
        container.tuning.stage_skill_change("web-search", "helpers.py", "x = 1", "не тот файл")
