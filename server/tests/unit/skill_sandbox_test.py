"""R-06: песочница агентских скиллов не отдаёт секреты из окружения сервиса.

Цепочка атаки из аудита: web_read (недоверенный текст) → prompt injection →
save_skill → скрипт читает ZAI_API_KEY/TAVILY/SERPER и сливает наружу.
Subprocess теперь получает только allowlist-env и пишет в персональный WORK_DIR.
"""

import os
from pathlib import Path
from types import SimpleNamespace

from app.modules.skills.loader import SkillLoader

SKILL_MD = """\
---
name: envprobe
description: Проверяет изоляцию окружения песочницы.
params: {}
---
"""

RUN_PY = """\
import os


def main(**_):
    env = dict(os.environ)
    leaked = sorted(
        k for k in env
        if ("KEY" in k or "TOKEN" in k or "SECRET" in k) and not k.startswith("LEARNOS_SKILL")
    )
    wd = env["LEARNOS_WRITE_DIR"]
    with open(os.path.join(wd, "probe.txt"), "w", encoding="utf-8") as f:
        f.write("written")
    return {"env_keys": sorted(env), "leaked": leaked, "write_dir": wd}
"""


def _loader(tmp_path: Path) -> SkillLoader:
    skill_dir = tmp_path / "agent-skills" / "root" / "envprobe"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (skill_dir / "run.py").write_text(RUN_PY, encoding="utf-8")
    return SkillLoader(
        SimpleNamespace(skills_dir=tmp_path / "skills", data_dir=tmp_path, skill_exec_timeout=30)
    )


def test_subprocess_sees_no_service_secrets(tmp_path, monkeypatch):
    """Ключи сервиса не попадают в env subprocess-скилла (R-06)."""
    for key in ("ZAI_API_KEY", "ZAI_API_KEY_2", "TAVILY_API_KEY", "SERPER_API_KEY", "LEARNOS_TELEGRAM_TOKEN"):
        monkeypatch.setenv(key, "super-secret-value")
    out = _loader(tmp_path).run("envprobe", {}, caller="root")

    assert out["exit_code"] == 0
    assert out["leaked"] == []
    for key in ("ZAI_API_KEY", "TAVILY_API_KEY", "LEARNOS_TELEGRAM_TOKEN"):
        assert key not in out["env_keys"]
    # рабочего минимума достаточно: интерпретатору нужен PATH
    assert "PATH" in out["env_keys"]
    assert "LEARNOS_SKILL_ARGS" in out["env_keys"]


def test_write_dir_is_per_skill_sandbox(tmp_path):
    """LEARNOS_WRITE_DIR — персональный каталог скилла, а не весь data/ с базой (R-06)."""
    out = _loader(tmp_path).run("envprobe", {}, caller="root")
    assert out["write_dir"] == str(tmp_path / "skill-work" / "root" / "envprobe")
    probe = tmp_path / "skill-work" / "root" / "envprobe" / "probe.txt"
    assert probe.read_text(encoding="utf-8") == "written"
    # learnos.db (даже если существует) не лежит в WORK_DIR скилла
    assert not os.path.exists(os.path.join(out["write_dir"], "learnos.db"))
