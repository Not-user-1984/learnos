"""Песочница агентских скиллов: скан data/agent-skills, subprocess-исполнение, override builtin."""

import time
from pathlib import Path
from types import SimpleNamespace

from app.modules.skills.loader import SkillLoader

SERVER_SKILLS = Path(__file__).parents[2] / "skills"

SKILL_MD = """---
name: {name}
description: тестовый агентский скилл
params:
  name:
    type: str
    optional: true
    default: мир
    desc: кого приветствовать
version: 0.1
---
"""

RUN_PY = """\
import os


def main(name="мир", **_):
    out = os.path.join(os.environ["LEARNOS_WRITE_DIR"], "greet.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(name)
    print("пишу файл")
    return {"ok": True, "greeting": f"Привет, {name}!", "wrote": out}
"""


def _make_settings(tmp_path: Path, timeout: int = 30) -> SimpleNamespace:
    return SimpleNamespace(skills_dir=SERVER_SKILLS, data_dir=tmp_path, skill_exec_timeout=timeout)


def _put_agent_skill(tmp_path: Path, owner: str, name: str, run_py: str | None = None) -> None:
    skill_dir = tmp_path / "agent-skills" / owner / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MD.format(name=name), encoding="utf-8")
    (skill_dir / "run.py").write_text(run_py or RUN_PY, encoding="utf-8")


def test_agent_skill_scanned_with_owner(tmp_path):
    """Скилл из data/agent-skills/<agent>/<skill>/ находится, владелец — из пути, инструмент строится."""
    _put_agent_skill(tmp_path, "repo_scout", "hello")
    loader = SkillLoader(_make_settings(tmp_path))
    loader.load()
    assert loader.kind_of("hello") == "agent"
    assert loader.owners_of("hello") == {"repo_scout"}
    assert loader.names_owned_by("repo_scout") == {"hello"}
    assert "hello" in {s.name for s in loader.tool_specs()}


def test_agent_skill_runs_subprocess_and_writes_to_allowed_dir(tmp_path):
    """run.py исполняется subprocess'ом: результат main() + stdout + код выхода; файл — в data/."""
    _put_agent_skill(tmp_path, "root", "hello")
    loader = SkillLoader(_make_settings(tmp_path))
    out = loader.run("hello", {"name": "Дмитрий"}, caller="root")
    assert out["ok"] is True
    assert out["greeting"] == "Привет, Дмитрий!"
    assert out["exit_code"] == 0
    assert "пишу файл" in out["stdout"]
    # песочница R-06: запись только в персональный WORK_DIR, не в корень data/
    assert (tmp_path / "skill-work" / "root" / "hello" / "greet.txt").read_text(encoding="utf-8") == "Дмитрий"


def test_agent_skill_timeout_kills_process(tmp_path):
    """Скрипт со сном убивается по таймауту; ошибка возвращается, процесс не висит."""
    _put_agent_skill(
        tmp_path,
        "root",
        "sleeper",
        "import time\n\n\ndef main(**_):\n    time.sleep(30)\n    return {'ok': True}\n",
    )
    started = time.monotonic()
    out = SkillLoader(_make_settings(tmp_path, timeout=2)).run("sleeper", {}, caller="root")
    assert out["error"] == "skill_timeout"
    assert "2 с" in out["message"]
    assert time.monotonic() - started < 15  # процесс убит, а не ждал 30 с


def test_agent_skill_denied_for_stranger(tmp_path):
    """Агентский скилл вызывает только владелец и root; чужой и MCP — отказ."""
    _put_agent_skill(tmp_path, "repo_scout", "hello")
    loader = SkillLoader(_make_settings(tmp_path))
    denied = loader.run("hello", {}, caller="free_chat")
    assert denied["error"] == "not_allowed"
    assert loader.run("hello", {}, caller=None)["error"] == "not_allowed"  # канал MCP
    assert loader.run("hello", {}, caller="repo_scout")["ok"] is True
    assert loader.run("hello", {}, caller="root")["ok"] is True


def test_builtin_override_resolved_from_data(tmp_path):
    """Override builtin-скилла из data/skill-overrides подхватывается без правки кода."""
    override_dir = tmp_path / "skill-overrides" / "web-search"
    override_dir.mkdir(parents=True)
    (override_dir / "run.py").write_text(
        "def main(query='', limit=5, **_):\n    return {'marker': 'override-active', 'query': query}\n",
        encoding="utf-8",
    )
    loader = SkillLoader(_make_settings(tmp_path))
    loader.load()
    assert loader.run("web-search", {"query": "тест"})["marker"] == "override-active"
    # путь builtin из кода по-прежнему доступен (для диффа и бэкапа)
    assert loader.builtin_file("web-search", "run.py").parent == SERVER_SKILLS / "web-search"


def test_agent_skill_name_conflict_skipped_with_warning(tmp_path):
    """Конфликт имени агентского скилла с builtin не роняет старт — скилл пропускается."""
    _put_agent_skill(tmp_path, "root", "web-search")
    loader = SkillLoader(_make_settings(tmp_path))
    loader.load()
    assert loader.kind_of("web-search") == "builtin"  # builtin выигрывает
    assert loader.names_owned_by("root") == set()
