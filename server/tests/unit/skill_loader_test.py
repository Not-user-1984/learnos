"""Скилл-загрузчик: optional-параметры без default не ломают MCP-вызов и run.py."""

from pathlib import Path
from types import SimpleNamespace

from app.modules.skills.loader import SkillLoader

SKILL_MD = """---
name: opt_skill
description: тестовый скилл с optional-параметрами
params:
  action:
    type: str
    desc: действие
  query:
    type: str
    optional: true
    desc: запрос
  num:
    type: int
    optional: true
    desc: номер
  cat:
    type: str
    optional: true
    default: books
    desc: категория
version: 0.1
---
"""


def _make_loader(tmp_path: Path) -> SkillLoader:
    skill_dir = tmp_path / "opt_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (skill_dir / "run.py").write_text(
        "def main(action='status', query='', num=0, cat='books', **_):\n"
        "    return {'ok': True, 'action': action, 'query': query, 'num': num, 'cat': cat}\n",
        encoding="utf-8",
    )
    loader = SkillLoader(
        SimpleNamespace(skills_dir=tmp_path, data_dir=tmp_path / "data", skill_exec_timeout=30)
    )
    loader.load()
    return loader


def test_optional_params_without_default_validate_empty(tmp_path):
    """MCP передал только обязательное поле: pydantic пропускает, run.py получает дефолты."""
    loader = _make_loader(tmp_path)
    spec = next(s for s in loader.tool_specs() if s.name == "opt_skill")
    args = spec.args_model.model_validate({"action": "search"})  # раньше: null ломал валидацию
    out = spec.handler(args, None)
    assert out["ok"] and out["query"] == "" and out["num"] == 0 and out["cat"] == "books"


def test_optional_param_null_and_default_kept(tmp_path):
    """Явный null от MCP-клиента выкидывается; дефолт из SKILL.md сохраняется."""
    loader = _make_loader(tmp_path)
    spec = next(s for s in loader.tool_specs() if s.name == "opt_skill")
    args = spec.args_model.model_validate({"action": "add", "query": None, "num": 3, "cat": "movies"})
    out = spec.handler(args, None)
    assert out["query"] == "" and out["num"] == 3 and out["cat"] == "movies"


def test_torrent_fetch_model_validates_without_optionals(tmp_path):
    """Реальный torrent_fetch: вызов только с action валиден; None-поля не уходят в run.py."""
    loader = SkillLoader(
        SimpleNamespace(
            skills_dir=Path(__file__).parents[2] / "skills", data_dir=tmp_path, skill_exec_timeout=30
        )
    )
    loader.load()
    spec = next(s for s in loader.tool_specs() if s.name == "torrent_fetch")
    args = spec.args_model.model_validate({"action": "status"})
    payload = {k: v for k, v in args.model_dump().items() if v is not None}
    assert payload["action"] == "status"
    assert payload["cat"] == "books" and payload["limit"] == 20  # дефолты из SKILL.md
    assert not {"query", "title", "num", "magnet"} & payload.keys()  # optional без default → None → выкинуты
