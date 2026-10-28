"""Сервис tuning: реестр промптов агентов, стадия правок, применение, откат, кастомные агенты."""

import difflib
import json
from dataclasses import dataclass
from pathlib import Path

from ...agent.runtime import resolve_prompt_path
from ...kernel.clock import SystemClock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import Conflict, NotFound, ValidationFailed
from .infra.tables import custom_agents, prompt_changes

SERVER_ROOT = Path(__file__).resolve().parents[3]  # server/

# файлы builtin-скилла, правимые карточкой (канонический список — в modules/skills/loader)
_SKILL_FILES = ("run.py", "SKILL.md")


@dataclass(frozen=True, slots=True)
class AgentPrompt:
    """Промпт агента: имя, описание, файл, есть ли override."""

    agent: str
    description: str
    module: str
    path: str  # относительный путь от app/
    has_override: bool
    size: int
    custom: bool = False
    tools: list[str] | None = None


class TuningService:
    """Use-cases настройки: список промптов, черновик правки (дифф), применение, откат, кастомные агенты."""

    def __init__(
        self, uow: UnitOfWorkFactory, settings, agent_registry, runtime=None, tools=None, skills=None
    ) -> None:
        self._uow = uow
        self._settings = settings
        self._registry = agent_registry
        self._runtime = runtime
        self._tools = tools
        self._skills = skills  # SkillsService: propose_change(kind="skill") и живой reload
        self._clock = SystemClock()

    # --- реестр ---

    def list_prompts(self) -> list[AgentPrompt]:
        """Промпты всех агентов приложения (реестр — источник имён)."""
        out = []
        for spec in self._registry.all():
            if spec.prompt_text is not None:
                out.append(
                    AgentPrompt(
                        agent=spec.name,
                        description=spec.description,
                        module="custom",
                        path="(кастомный агент)",
                        has_override=False,
                        size=len(spec.prompt_text.encode("utf-8")),
                        custom=True,
                        tools=sorted(spec.tools),
                    )
                )
                continue
            default_path = spec.prompt_path
            actual = resolve_prompt_path(default_path)
            rel = str(default_path.relative_to(SERVER_ROOT))
            out.append(
                AgentPrompt(
                    agent=spec.name,
                    description=spec.description,
                    module=rel.split("/")[2] if "/modules/" in f"/{rel}" else "?",
                    path=rel,
                    has_override=actual != default_path,
                    size=actual.stat().st_size if actual.exists() else 0,
                    tools=sorted(spec.tools),
                )
            )
        return sorted(out, key=lambda p: p.agent)

    def read_prompt(self, agent_name: str) -> dict:
        """Текущий промпт агента (с учётом override) + инструменты и признак кастомного."""
        try:
            spec = self._registry.get(agent_name)
        except KeyError as e:
            raise NotFound(f"агент '{agent_name}' не найден") from e
        if spec.prompt_text is not None:
            return {
                "agent": spec.name,
                "description": spec.description,
                "path": "(кастомный агент)",
                "content": spec.prompt_text,
                "has_override": False,
                "custom": True,
                "tools": sorted(spec.tools),
            }
        actual = resolve_prompt_path(spec.prompt_path)
        if not actual.exists():
            raise NotFound(f"файл промпта не найден: {actual}")
        return {
            "agent": spec.name,
            "description": spec.description,
            "path": str(spec.prompt_path.relative_to(SERVER_ROOT)),
            "content": actual.read_text(encoding="utf-8"),
            "has_override": actual != spec.prompt_path,
            "custom": False,
            "tools": sorted(spec.tools),
        }

    # --- стадия правок ---

    def stage_change(
        self, agent_name: str, new_content: str, summary: str, conversation_uid: str | None = None
    ) -> dict:
        """Черновик правки промпта: сохранить старый/новый текст, вернуть карточку с диффом."""
        if not new_content.strip():
            raise ValidationFailed("новый промпт пуст")
        current = self.read_prompt(agent_name)
        return self._insert_change(
            agent_name,
            current["content"],
            new_content,
            summary or "правка промпта",
            conversation_uid,
            kind="prompt",
        )

    def stage_skill_change(
        self,
        skill_name: str,
        file: str,
        new_content: str,
        summary: str,
        conversation_uid: str | None = None,
    ) -> dict:
        """Черновик правки builtin-скилла (run.py | SKILL.md) — применяется только карточкой."""
        if self._skills is None:
            raise NotFound("модуль скиллов недоступен")
        if file not in _SKILL_FILES:
            raise ValidationFailed(f"файл скилла: {' или '.join(_SKILL_FILES)}")
        kind = self._skills.loader.kind_of(skill_name)
        if kind == "agent":
            raise ValidationFailed(f"скилл '{skill_name}' агентский — его правит владелец через save_skill")
        if kind != "builtin":
            raise NotFound(f"builtin-скилл '{skill_name}' не найден")
        current = self._skills.loader.effective_file(skill_name, file).read_text(encoding="utf-8")
        return self._insert_change(
            skill_name,
            current,
            new_content,
            summary or f"правка {file}",
            conversation_uid,
            kind="skill",
            file=file,
        )

    def _insert_change(
        self,
        target: str,
        old_content: str,
        new_content: str,
        summary: str,
        conversation_uid: str | None,
        *,
        kind: str,
        file: str | None = None,
    ) -> dict:
        """Общая стадия правки (prompt | skill): строка в БД + карточка с диффом."""
        if not new_content.strip():
            raise ValidationFailed("новое содержимое пусто")
        diff = _diff_lines(old_content, new_content)
        card = {
            "type": "prompt_change",
            "kind": kind,
            "change_id": 0,
            "agent": target,
            "summary": summary,
            "diff": diff,
            "status": "pending",
        }
        if file:
            card["file"] = file
        with self._uow() as uow:
            change_id = int(
                uow.session.execute(
                    prompt_changes.insert().values(
                        agent=target,
                        summary=summary,
                        old_content=old_content,
                        new_content=new_content,
                        status="pending",
                        kind=kind,
                        file=file,
                        conversation_uid=conversation_uid,
                        created_at=now_iso(self._clock),
                    )
                ).inserted_primary_key[0]
            )
        card["change_id"] = change_id
        return {
            "change_id": change_id,
            "kind": kind,
            "agent": target,
            "summary": summary,
            "diff": diff,
            "_card": card,
        }

    def apply_change(self, change_id: int) -> dict:
        """Применить: промпт — override в data/prompts/; скилл — override в data/skill-overrides/."""
        with self._uow() as uow:
            row = uow.session.execute(prompt_changes.select().where(prompt_changes.c.id == change_id)).first()
            if row is None:
                raise NotFound(f"правка {change_id} не найдена")
            if row.status != "pending":
                raise ValidationFailed(f"правка уже {row.status}")
            if row.kind == "skill":
                out = self._apply_skill_change(row)
            else:
                out = self._apply_prompt_change(uow, row)
            uow.session.execute(
                prompt_changes.update().where(prompt_changes.c.id == change_id).values(status="applied")
            )
        return out

    def _apply_prompt_change(self, uow, row) -> dict:
        """Применение правки промпта: override-файл + бэкап; промпт живёт сразу."""
        spec = self._registry.get(row.agent)
        if spec.prompt_text is not None:
            # кастомный агент: правка пишется в БД, реестр обновляется сразу
            self._write_custom_prompt(uow, row.agent, row.new_content)
            return {"ok": True, "change_id": row.id, "agent": row.agent, "override": "(кастомный агент)"}
        default_path = spec.prompt_path
        backup_dir = self._settings.data_dir / "prompt_backups" / row.agent
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / f"{now_iso(self._clock).replace(':', '')}.md").write_text(
            row.old_content, encoding="utf-8"
        )
        override = self._override_path(default_path)
        override.parent.mkdir(parents=True, exist_ok=True)
        override.write_text(row.new_content, encoding="utf-8")
        return {"ok": True, "change_id": row.id, "agent": row.agent, "override": str(override)}

    def _apply_skill_change(self, row) -> dict:
        """Применение правки builtin-скилла: бэкап + override + живая перезагрузка скиллов."""
        if self._skills is None:
            raise NotFound("модуль скиллов недоступен")
        backup_dir = self._settings.data_dir / "prompt_backups" / f"skill_{row.agent}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / f"{now_iso(self._clock).replace(':', '')}__{row.file}").write_text(
            row.old_content, encoding="utf-8"
        )
        override = self._settings.data_dir / "skill-overrides" / row.agent / row.file
        override.parent.mkdir(parents=True, exist_ok=True)
        override.write_text(row.new_content, encoding="utf-8")
        self._skills.reload()
        return {
            "ok": True,
            "change_id": row.id,
            "skill": row.agent,
            "file": row.file,
            "override": str(override),
        }

    def reject_change(self, change_id: int) -> dict:
        """Отклонить черновик."""
        with self._uow() as uow:
            row = uow.session.execute(prompt_changes.select().where(prompt_changes.c.id == change_id)).first()
            if row is None:
                raise NotFound(f"правка {change_id} не найдена")
            uow.session.execute(
                prompt_changes.update().where(prompt_changes.c.id == change_id).values(status="rejected")
            )
        return {"ok": True, "change_id": change_id}

    def reset_prompt(self, agent_name: str) -> dict:
        """Сбросить override — вернуть промпт из кода."""
        spec = self._registry.get(agent_name)
        if spec.prompt_text is not None:
            raise ValidationFailed("у кастомного агента нет заводского промпта — правь через чат настройки")
        override = self._override_path(spec.prompt_path)
        if override.exists():
            backup_dir = self._settings.data_dir / "prompt_backups" / agent_name
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / f"reset-{now_iso(self._clock).replace(':', '')}.md").write_text(
                override.read_text(encoding="utf-8"), encoding="utf-8"
            )
            override.unlink()
        return {"ok": True, "agent": agent_name}

    def reset_skill(self, skill_name: str) -> dict:
        """Сбросить override builtin-скилла — файлы из кода; перед снятием бэкап."""
        if self._skills is None:
            raise NotFound("модуль скиллов недоступен")
        if self._skills.loader.kind_of(skill_name) != "builtin":
            raise NotFound(f"builtin-скилл '{skill_name}' не найден")
        override_dir = self._settings.data_dir / "skill-overrides" / skill_name
        if not override_dir.is_dir():
            return {"ok": True, "skill": skill_name, "reset": False, "message": "override не был применён"}
        backup_dir = self._settings.data_dir / "prompt_backups" / f"skill_{skill_name}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(override_dir.iterdir()):
            if f.name not in _SKILL_FILES:
                continue
            (backup_dir / f"reset-{now_iso(self._clock).replace(':', '')}__{f.name}").write_text(
                f.read_text(encoding="utf-8"), encoding="utf-8"
            )
            f.unlink()
        self._skills.reload()
        return {"ok": True, "skill": skill_name, "reset": True}

    def changes(self, status: str | None = None) -> list[dict]:
        """История правок."""
        with self._uow() as uow:
            stmt = prompt_changes.select().order_by(prompt_changes.c.id.desc()).limit(50)
            if status:
                stmt = stmt.where(prompt_changes.c.status == status)
            rows = uow.session.execute(stmt).all()
        return [
            {
                "change_id": r.id,
                "agent": r.agent,
                "summary": r.summary,
                "status": r.status,
                "kind": r.kind,
                "file": r.file,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    def _override_path(self, default_path: Path) -> Path:
        marker = "/modules/"
        rel = str(default_path).split(marker, 1)[1]
        return self._settings.data_dir / "prompts" / rel

    # --- кастомные агенты (конструктор из UI) ---

    def tools_catalog(self) -> list[dict]:
        """Каталог инструментов, доступных агентам (для конструктора и чекбоксов)."""
        if self._tools is None:
            return []
        return [
            {"name": t.name, "description": t.description, "module": t.module}
            for t in self._tools.filter(channel="agent")
        ]

    def custom_agents(self) -> list[dict]:
        """Кастомные агенты (реестр — источник правды, БД — хранилище)."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "tools": sorted(s.tools),
                "model_role": s.model_role,
            }
            for s in self._registry.all()
            if s.prompt_text is not None
        ]

    def draft_custom_agent(self, brief: str) -> dict:
        """Драфт нового агента из пожелания пользователя (agent_designer)."""
        if not brief.strip():
            raise ValidationFailed("опиши, что должен делать агент")
        if self._runtime is None:
            raise NotFound("LLM не настроен — конструктор недоступен")
        from ...agent.spec import AgentContext
        from ...kernel.asyncio_bridge import run_coro_sync
        from .agents import agent_designer

        catalog_text = "\n".join(
            f"- {t['name']} ({t['module']}): {t['description']}" for t in self.tools_catalog()
        )
        user_prompt = f"Пожелание пользователя:\n{brief}\n\nКаталог инструментов:\n{catalog_text or '(нет)'}"
        out = run_coro_sync(self._runtime.run_structured(agent_designer, AgentContext(), user_prompt))
        name = out.name.strip().lower().replace(" ", "_").replace("-", "_")
        tools = self._sanitize_tools(out.tools)
        return {
            "name": name,
            "description": out.description.strip(),
            "prompt": out.prompt.strip(),
            "tools": tools,
            "summary": out.summary.strip(),
            "available_tools": self.tools_catalog(),
        }

    def create_custom_agent(
        self, name: str, description: str, prompt: str, tools: list[str], model_role: str = "chat"
    ) -> dict:
        """Создать кастомного агента: БД + живая регистрация в реестре."""
        from .agents import valid_agent_name

        name = (name or "").strip()
        if not valid_agent_name(name):
            raise ValidationFailed("имя: латиница/цифры/_, начинается с буквы, до 40 символов")
        if self._registry.is_builtin(name) or self._get_custom_row(name) is not None:
            raise Conflict(f"имя агента '{name}' уже занято")
        if not description.strip():
            raise ValidationFailed("нужно описание агента")
        if len(prompt.strip()) < 40:
            raise ValidationFailed("промпт слишком короткий")
        tools = self._sanitize_tools(tools, strict=True)
        now = now_iso(self._clock)
        with self._uow() as uow:
            uow.session.execute(
                custom_agents.insert().values(
                    name=name,
                    description=description.strip(),
                    prompt=prompt.strip(),
                    tools_json=json.dumps(tools, ensure_ascii=False),
                    model_role=model_role,
                    created_at=now,
                    updated_at=now,
                )
            )
        self._register_custom(name, description.strip(), prompt.strip(), tools, model_role)
        return {"ok": True, "agent": name, "mode": f"agent:{name}"}

    def update_custom_agent(
        self,
        name: str,
        description: str | None = None,
        prompt: str | None = None,
        tools: list[str] | None = None,
    ) -> dict:
        """Обновить кастомного агента (БД + реестр)."""
        row = self._get_custom_row(name)
        if row is None:
            raise NotFound(f"кастомный агент '{name}' не найден")
        description = (description if description is not None else row["description"]).strip()
        prompt = (prompt if prompt is not None else row["prompt"]).strip()
        if len(prompt) < 40:
            raise ValidationFailed("промпт слишком короткий")
        current_tools = json.loads(row["tools_json"]) if tools is None else tools
        tools_list = self._sanitize_tools(current_tools, strict=True)
        with self._uow() as uow:
            uow.session.execute(
                custom_agents.update()
                .where(custom_agents.c.name == name)
                .values(
                    description=description,
                    prompt=prompt,
                    tools_json=json.dumps(tools_list, ensure_ascii=False),
                    updated_at=now_iso(self._clock),
                )
            )
        self._register_custom(name, description, prompt, tools_list, row["model_role"])
        return {"ok": True, "agent": name}

    def delete_custom_agent(self, name: str) -> dict:
        """Удалить кастомного агента (встроенных удалить нельзя)."""
        if self._registry.is_builtin(name):
            raise Conflict(f"встроенный агент '{name}' удалить нельзя")
        row = self._get_custom_row(name)
        if row is None:
            raise NotFound(f"кастомный агент '{name}' не найден")
        with self._uow() as uow:
            uow.session.execute(custom_agents.delete().where(custom_agents.c.name == name))
        self._registry.remove_custom(name)
        return {"ok": True, "deleted": name}

    def load_custom_agents(self) -> int:
        """Загрузить кастомных агентов из БД в реестр (после миграций; до таблиц — тихо 0)."""
        try:
            with self._uow() as uow:
                rows = uow.session.execute(custom_agents.select()).all()
        except Exception:  # noqa: BLE001 — таблицы ещё нет (первый старт до миграций)
            return 0
        for r in rows:
            self._register_custom(
                r.name, r.description, r.prompt, json.loads(r.tools_json or "[]"), r.model_role
            )
        return len(rows)

    # --- внутреннее ---

    def _get_custom_row(self, name: str) -> dict | None:
        with self._uow() as uow:
            row = uow.session.execute(custom_agents.select().where(custom_agents.c.name == name)).first()
        return row._mapping if row is not None else None  # noqa: SLF001

    def _register_custom(
        self, name: str, description: str, prompt: str, tools: list[str], model_role: str
    ) -> None:
        from ...agent.spec import AgentSpec

        own_skills = self._skills.loader.names_owned_by(name) if self._skills else set()
        self._registry.upsert_custom(
            AgentSpec(
                name=name,
                description=description,
                prompt_text=prompt,
                tools=frozenset(tools) | own_skills,  # скиллы агента видны сразу
                model_role=model_role or "chat",
                max_steps=24,
            )
        )

    def _write_custom_prompt(self, uow, name: str, prompt: str) -> None:
        """Применение правки промпта кастомного агента (внутри uow стадии)."""
        uow.session.execute(
            custom_agents.update()
            .where(custom_agents.c.name == name)
            .values(prompt=prompt, updated_at=now_iso(self._clock))
        )
        row = uow.session.execute(custom_agents.select().where(custom_agents.c.name == name)).first()
        if row is not None:
            self._register_custom(
                row.name, row.description, prompt, json.loads(row.tools_json or "[]"), row.model_role
            )

    def _sanitize_tools(self, tools: list[str], strict: bool = False) -> list[str]:
        """Оставить только существующие инструменты; strict — ругаться на неизвестные."""
        if self._tools is None:
            return []
        known = {t.name for t in self._tools.filter(channel="agent")}
        picked, unknown = [], []
        for t in tools or []:
            (picked if t in known else unknown).append(t)
        if strict and unknown:
            raise ValidationFailed(f"неизвестные инструменты: {', '.join(sorted(set(unknown)))}")
        return sorted(set(picked))


def _diff_lines(old: str, new: str, context: int = 2) -> list[dict]:
    """Унифицированный дифф в компактном виде для карточки чата."""
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=context))
    out = []
    for line in diff[2:]:  # пропускаем ---/+++
        if line.startswith("@@"):
            out.append({"op": "@", "line": line})
        elif line.startswith("+"):
            out.append({"op": "+", "line": line[1:]})
        elif line.startswith("-"):
            out.append({"op": "-", "line": line[1:]})
        elif line.startswith(" "):
            out.append({"op": " ", "line": line[1:]})
    return out[:80]  # карточку не раздуваем
