"""Генерация блоков агентами (B-009: вынесено из service без изменения поведения).

Хранение (файлы+индекс) — KnowledgeService; превращение диалога/транскрипта
в BlockDraft агентами — здесь.
"""

import json
import logging
from dataclasses import replace

from ....agent.spec import AgentContext
from ....kernel.asyncio_bridge import run_coro_sync
from ....kernel.errors import NotFound
from ..domain import BlockDraft, normalize_category_path
from ..domain import writer_out_to_draft as _writer_out  # noqa: E402


def writer_out_to_draft(out, kind: str) -> BlockDraft:
    """Ответ block_writer (pydantic) → BlockDraft."""
    return _writer_out(out, kind=kind)


class GenerationUseCases:
    """block_writer / categorizer / runbook_writer поверх сервиса знаний."""

    def __init__(self, svc) -> None:
        self._svc = svc  # публичные методы: list_blocks/list_categories/create_category

    def generate_from_dialog(
        self, dialog: str, kind: str = "note", extra_lines: list[str] | None = None
    ) -> BlockDraft:
        """Драфт блока из переписки разговора (порт для chat, B-009)."""
        if self._svc._runtime is None:  # noqa: SLF001 — use-case своего модуля
            raise NotFound("агентный рантайм недоступен")
        from ..agents import block_writer

        existing = self._svc.list_blocks(limit=50)
        existing_brief = "\n".join(f"- {m.uid}: {m.title}" for m in existing) or "(пусто)"
        cats = "\n".join(f"- {c.path}" for c in self._svc.list_categories()) or "(пусто)"
        extra = ("\n\n" + "\n".join(extra_lines)) if extra_lines else ""
        system_extra = (
            f"Существующие блоки (links — только эти uid):\n{existing_brief}\n\nДерево категорий:\n{cats}"
            + extra
        )
        ctx = AgentContext(system_extra=system_extra)
        out = run_coro_sync(self._svc._runtime.run_structured(block_writer, ctx, dialog))  # noqa: SLF001
        return self.categorize_draft(writer_out_to_draft(out, kind=kind))

    def generate_from_transcript(self, session: dict) -> BlockDraft:
        """Собрать BlockDraft из транскрипта сессии (block_writer + categorizer)."""
        if self._svc._runtime is None:  # noqa: SLF001
            raise NotFound("агентный рантайм недоступен")
        from ..agents import block_writer

        transcript = session.get("transcript") or []
        dialog = "\n".join(
            f"[{e['state']}/{e['event']}] {json.dumps(e.get('payload') or {}, ensure_ascii=False)}"
            for e in transcript
        )
        existing = self._svc.list_blocks(limit=50)
        existing_brief = "\n".join(f"- {m.uid}: {m.title}" for m in existing) or "(пусто)"
        cats = "\n".join(f"- {c.path}" for c in self._svc.list_categories()) or "(пусто)"
        profile_brief = self._profile_brief()
        extra = (
            f"Существующие блоки (links — только эти uid):\n{existing_brief}\n\nДерево категорий:\n{cats}"
            + (f"\n\n{profile_brief}" if profile_brief else "")
        )
        ctx = AgentContext(system_extra=extra)
        out = run_coro_sync(
            self._svc._runtime.run_structured(block_writer, ctx, f"Транскрипт сессии:\n{dialog}")  # noqa: SLF001
        )
        return self.categorize_draft(writer_out_to_draft(out, kind=session.get("block_kind", "lesson")))

    def categorize_draft(self, draft: BlockDraft) -> BlockDraft:
        """Проставить драфту category_suggestion через categorizer (не критично при падении)."""
        if self._svc._runtime is None:  # noqa: SLF001
            return draft
        from ..agents import categorizer

        log = logging.getLogger("learnos.knowledge")
        cats = "\n".join(f"- {c.path}" for c in self._svc.list_categories()) or "(пусто)"
        try:
            cat_ctx = AgentContext(system_extra=f"Дерево:\n{cats}")
            cat_out = run_coro_sync(
                self._svc._runtime.run_structured(  # noqa: SLF001
                    categorizer, cat_ctx, f"Блок: {draft.title}\n{draft.summary}"
                )
            )
            path = cat_out.path
            # R-31: новый корень дереву не создаём — только подкатегории существующих
            normalized = normalize_category_path(path)
            roots = {c.path.split("/")[0] for c in self._svc.list_categories()}
            if normalized.split("/")[0] not in roots:
                log.info("categorizer предложил новый корень %s — оставляем без категории", path)
                return draft
            if getattr(cat_out, "new_category_title", None):
                self._svc.create_category(path, cat_out.new_category_title)
            return replace(draft, category_suggestion=path)
        except Exception:  # noqa: BLE001 — категория не критична
            log.info("categorizer не сработал, категория не проставлена")
            return draft

    def generate_runbook(self, session: dict, lesson_uid: str) -> BlockDraft:
        """Собрать runbook-драфт из practice_log транскрипта (runbook_writer)."""
        if self._svc._runtime is None:  # noqa: SLF001
            raise NotFound("агентный рантайм недоступен")
        from ..agents import runbook_writer

        transcript = session.get("transcript") or []
        dialog = "\n".join(
            f"[{e['state']}/{e['event']}] {json.dumps(e.get('payload') or {}, ensure_ascii=False)}"
            for e in transcript
        )
        ctx = AgentContext(system_extra=f"Связанный урок: {lesson_uid}\nПрофиль:\n{self._profile_brief()}")
        out = run_coro_sync(
            self._svc._runtime.run_structured(runbook_writer, ctx, f"Транскрипт сессии:\n{dialog}")  # noqa: SLF001
        )
        return replace(writer_out_to_draft(out, kind="runbook"), links=(lesson_uid,))

    def _profile_brief(self) -> str:
        try:
            profile = self._svc._profile  # noqa: SLF001
            return f"Профиль пользователя:\n{profile.machines_brief()}\n{profile.learning_brief()}"
        except Exception:  # noqa: BLE001
            return ""
