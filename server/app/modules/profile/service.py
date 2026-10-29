"""Сервис профиля: чтение и запись settings.profile."""

import json

from sqlalchemy import select

from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import NotFound
from .schemas import DEFAULT_PROFILE, Profile


class ProfileService:
    """Use-cases профиля; дефолт создаётся при первом чтении."""

    def __init__(self, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    def get(self) -> Profile:
        """Текущий профиль (создаёт дефолт, если ещё нет)."""
        from .infra.tables import settings_table

        with self._uow() as uow:
            row = uow.session.execute(select(settings_table).where(settings_table.c.key == "profile")).first()
            if row is None:
                uow.session.execute(
                    settings_table.insert().values(
                        key="profile", value_json=DEFAULT_PROFILE.model_dump_json()
                    )
                )
                return DEFAULT_PROFILE
            return Profile.model_validate(json.loads(row.value_json))

    def update(self, profile: Profile) -> Profile:
        """Сохранить профиль целиком."""
        from .infra.tables import settings_table

        with self._uow() as uow:
            existing = uow.session.execute(
                select(settings_table).where(settings_table.c.key == "profile")
            ).first()
            values = {"key": "profile", "value_json": profile.model_dump_json()}
            if existing is None:
                uow.session.execute(settings_table.insert().values(**values))
            else:
                uow.session.execute(
                    settings_table.update()
                    .where(settings_table.c.key == "profile")
                    .values(value_json=values["value_json"])
                )
            return profile

    def person_brief(self) -> str:
        """Кто учится: имя и «о себе» — для обращения и подбора примеров в промптах."""
        p = self.get()
        lines = [f"Имя: {p.name}"]
        if p.about.strip():
            lines.append(f"О себе: {p.about.strip()}")
        return "\n".join(lines)

    def machines_brief(self) -> str:
        """Компактное описание машин для промптов агентов."""
        profile = self.get()
        lines = [
            f"- {m.name} ({m.kind}, id={m.id}): {m.specs}; инструменты: {', '.join(m.tools) or '—'}"
            + (f"; заметки: {m.notes}" if m.notes else "")
            for m in profile.machines
        ]
        return "\n".join(lines) or "(машин нет)"

    def learning_brief(self) -> str:
        """Компактные предпочтения для промптов."""
        p = self.get().learning
        practice = "да" if p.practice_default else "нет"
        return (
            f"сессия {p.session_minutes} мин; понятий {p.theory_concepts}; "
            f"вопросов на понятие {p.questions_per_concept}; "
            f"практика={practice}; стиль: {p.explain_style}"
        )

    def ensure_machine(self, machine_id: str) -> None:
        """Проверить, что машина с таким id есть в профиле."""
        profile = self.get()
        if not any(m.id == machine_id for m in profile.machines):
            raise NotFound(f"машина '{machine_id}' не найдена в профиле")
