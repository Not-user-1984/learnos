"""Сервис tuning: реестр промптов агентов, стадия правок, применение и откат."""

import difflib
from dataclasses import dataclass
from pathlib import Path

from ...agent.runtime import resolve_prompt_path
from ...kernel.clock import SystemClock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import NotFound, ValidationFailed
from .infra.tables import prompt_changes

AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent  # app/modules


@dataclass(frozen=True, slots=True)
class AgentPrompt:
    """Промпт агента: имя, описание, файл, есть ли override."""

    agent: str
    description: str
    module: str
    path: str  # относительный путь от app/
    has_override: bool
    size: int


class TuningService:
    """Use-cases настройки: список промптов, черновик правки (дифф), применение, откат."""

    def __init__(self, uow: UnitOfWorkFactory, settings, agent_registry) -> None:
        self._uow = uow
        self._settings = settings
        self._registry = agent_registry
        self._clock = SystemClock()

    # --- реестр ---

    def list_prompts(self) -> list[AgentPrompt]:
        """Промпты всех агентов приложения (реестр — источник имён)."""
        out = []
        for spec in self._registry.all():
            default_path = spec.prompt_path
            actual = resolve_prompt_path(default_path)
            rel = str(default_path.relative_to(AGENTS_ROOT.parent.parent))
            out.append(
                AgentPrompt(
                    agent=spec.name,
                    description=spec.description,
                    module=rel.split("/")[2] if "/modules/" in f"/{rel}" else "?",
                    path=rel,
                    has_override=actual != default_path,
                    size=actual.stat().st_size if actual.exists() else 0,
                )
            )
        return sorted(out, key=lambda p: p.agent)

    def read_prompt(self, agent_name: str) -> dict:
        """Текущий промпт агента (с учётом override) + признак override."""
        try:
            spec = self._registry.get(agent_name)
        except KeyError as e:
            raise NotFound(f"агент '{agent_name}' не найден") from e
        actual = resolve_prompt_path(spec.prompt_path)
        if not actual.exists():
            raise NotFound(f"файл промпта не найден: {actual}")
        return {
            "agent": spec.name,
            "description": spec.description,
            "path": str(spec.prompt_path.relative_to(AGENTS_ROOT.parent.parent)),
            "content": actual.read_text(encoding="utf-8"),
            "has_override": actual != spec.prompt_path,
        }

    # --- стадия правок ---

    def stage_change(
        self, agent_name: str, new_content: str, summary: str, conversation_uid: str | None = None
    ) -> dict:
        """Черновик правки: сохранить старый/новый текст, вернуть карточку с диффом."""
        if not new_content.strip():
            raise ValidationFailed("новый промпт пуст")
        current = self.read_prompt(agent_name)
        with self._uow() as uow:
            change_id = int(
                uow.session.execute(
                    prompt_changes.insert().values(
                        agent=agent_name,
                        summary=summary or "правка промпта",
                        old_content=current["content"],
                        new_content=new_content,
                        status="pending",
                        conversation_uid=conversation_uid,
                        created_at=now_iso(self._clock),
                    )
                ).inserted_primary_key[0]
            )
        return {
            "change_id": change_id,
            "agent": agent_name,
            "summary": summary,
            "diff": _diff_lines(current["content"], new_content),
            "_card": {
                "type": "prompt_change",
                "change_id": change_id,
                "agent": agent_name,
                "summary": summary or "правка промпта",
                "diff": _diff_lines(current["content"], new_content),
                "status": "pending",
            },
        }

    def apply_change(self, change_id: int) -> dict:
        """Применить: override-файл в data/prompts/ + бэкап; промпт живёт сразу."""
        with self._uow() as uow:
            row = uow.session.execute(prompt_changes.select().where(prompt_changes.c.id == change_id)).first()
            if row is None:
                raise NotFound(f"правка {change_id} не найдена")
            if row.status != "pending":
                raise ValidationFailed(f"правка уже {row.status}")
            spec = self._registry.get(row.agent)
            default_path = spec.prompt_path
            backup_dir = self._settings.data_dir / "prompt_backups" / row.agent
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / f"{now_iso(self._clock).replace(':', '')}.md").write_text(
                row.old_content, encoding="utf-8"
            )
            override = self._override_path(default_path)
            override.parent.mkdir(parents=True, exist_ok=True)
            override.write_text(row.new_content, encoding="utf-8")
            uow.session.execute(
                prompt_changes.update().where(prompt_changes.c.id == change_id).values(status="applied")
            )
        return {"ok": True, "change_id": change_id, "agent": row.agent, "override": str(override)}

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
        override = self._override_path(spec.prompt_path)
        if override.exists():
            backup_dir = self._settings.data_dir / "prompt_backups" / agent_name
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / f"reset-{now_iso(self._clock).replace(':', '')}.md").write_text(
                override.read_text(encoding="utf-8"), encoding="utf-8"
            )
            override.unlink()
        return {"ok": True, "agent": agent_name}

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
                "created_at": r.created_at,
            }
            for r in rows
        ]

    def _override_path(self, default_path: Path) -> Path:
        marker = "/modules/"
        rel = str(default_path).split(marker, 1)[1]
        return self._settings.data_dir / "prompts" / rel


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
