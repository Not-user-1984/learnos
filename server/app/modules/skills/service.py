"""Свои скиллы агентов: сохранение (save_skill) и горячая перезагрузка реестров (T-037)."""

import logging
import re

from ...agent.registry import AgentRegistry
from ...kernel.errors import Conflict, ValidationFailed
from ...kernel.tools.registry import DuplicateTool, ToolRegistry
from .loader import SkillLoader, _parse_frontmatter

log = logging.getLogger("learnos.skills")

SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")  # дефис — как у builtin (web-search)


class SkillsService:
    """save_skill пишет скилл в data/agent-skills/<owner>/<name>/ и живо обновляет реестры."""

    def __init__(self, settings, loader: SkillLoader, tools: ToolRegistry, agents: AgentRegistry) -> None:
        self._settings = settings
        self.loader = loader  # публичен: tuning применяет override builtin-скиллов и дергает reload
        self._tools = tools
        self._agents = agents

    def save_skill(self, owner: str, skill_name: str, skill_md: str, run_py: str) -> dict:
        """Создать/обновить СВОЙ скилл агента; после записи скилл сразу доступен как инструмент."""
        if not owner:
            raise ValidationFailed("скилл сохраняет агент — владелец определяется вызывающим")
        self._validate(owner, skill_name, skill_md, run_py)
        skill_dir = self.loader.agent_skill_dir(owner, skill_name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
        (skill_dir / "run.py").write_text(run_py, encoding="utf-8")
        self.reload()
        return {
            "ok": True,
            "skill": skill_name,
            "owner": owner,
            "message": f"скилл '{skill_name}' сохранён и уже доступен как инструмент",
        }

    def reload(self) -> None:
        """Пере-скан скиллов и синхронизация реестров инструментов и агентов — без рестарта."""
        for name in {"run_skill", "list_skills"} | self.loader.names():
            self._tools.unregister(name)
        self.loader.load()
        for spec in self.loader.tool_specs():
            try:
                self._tools.register(spec)
            except DuplicateTool as e:
                log.warning("скилл %s не зарегистрирован как инструмент: %s", spec.name, e.message)
        for agent in self._agents.all():
            extra = self.loader.names_owned_by(agent.name)
            if agent.name == "root":
                extra |= self.loader.agent_skill_names()  # каталог root видит скиллы всех агентов
            if extra:
                self._agents.extend_tools(agent.name, extra)

    def _validate(self, owner: str, skill_name: str, skill_md: str, run_py: str) -> None:
        if not skill_name or not SKILL_NAME_RE.match(skill_name):
            raise ValidationFailed("имя скилла: латиница/цифры/_, начинается с буквы, до 40 символов")
        if not skill_md.strip():
            raise ValidationFailed("SKILL.md пуст")
        if not run_py.strip():
            raise ValidationFailed("run.py пуст")
        try:
            meta = _parse_frontmatter(skill_md)
        except Exception as e:  # noqa: BLE001 — ошибка разбора уходит агенту как есть
            raise ValidationFailed(f"SKILL.md: {e}") from e
        if meta.get("name", skill_name) != skill_name:
            raise ValidationFailed(f"name в frontmatter должен совпадать с именем скилла '{skill_name}'")
        if skill_name in self.loader.builtin_names():
            raise Conflict(
                f"имя '{skill_name}' занято builtin-скиллом — его правят через propose_change(kind='skill')"
            )
        owners = self.loader.owners_of(skill_name)
        if others := owners - {owner}:
            raise Conflict(f"скилл '{skill_name}' уже есть у агента {', '.join(sorted(others))}")
        if not owners and self._tools.has(skill_name):  # новый скилл не должен красть имя инструмента
            raise Conflict(f"имя '{skill_name}' уже занято инструментом")
