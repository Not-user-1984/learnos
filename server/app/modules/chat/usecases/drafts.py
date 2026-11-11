"""Драфты блоков из разговора: генерация и превью-стор (B-009)."""

from ....kernel.errors import NotFound
from ..service import _draft_to_plain  # noqa: SF001 — историческое место функции


class DraftUseCases:
    """Перенос из chat/service.py без изменения поведения."""

    def __init__(self, svc) -> None:
        self._svc = svc

    # --- генерация блока из разговора (save_note без draft) ---

    def generate_block_draft(
        self,
        conversation_uid: str | None,
        kind: str,
        title_hint: str | None = None,
        instructions: str | None = None,
    ):
        """Драфт блока из переписки (порт knowledge.generate_from_dialog, B-009)."""

        if not conversation_uid:
            return None
        conv = self.get_conversation(conversation_uid)
        # разбор ассистента — главный материал конспекта: берём щедро, реплики пользователя — короче
        dialog = "\n".join(
            f"{m['role']}: {m['content'][:6000] if m['role'] == 'assistant' else m['content'][:1500]}"
            for m in conv.get("messages", [])
            if m["role"] in {"user", "assistant"}
        )
        if not dialog.strip():
            return None
        extra = [f"kind={kind}"]
        if title_hint:
            extra.append(f"Подсказка заголовка: {title_hint}")
        if instructions:
            extra.append(f"Правки пользователя к драфту (обязательны): {instructions}")
        source_line = self._draft_source_line(conv)
        if source_line:
            extra.append(source_line)
        return self._svc._knowledge.generate_from_dialog(dialog, kind=kind, extra_lines=extra)

    def _draft_source_line(self, conv: dict) -> str:
        """Строка «Источник: … (глава N)» для block_writer — привязка драфта к пройденному."""
        try:
            act = self._svc._learning.get_activity(conv["activity_id"])
            src = self._svc._library.get_source(act["source_id"])
            chapter = conv.get("chapter_idx") or act["cursor_chapter"]
            return f"Источник: {src['title']} ({src['kind']}, uid={src['uid']}), глава {chapter}"
        except (KeyError, NotFound):
            return ""

    # --- превью конспекта: драфт живёт на сервере, апрув идёт по preview_id ---

    def store_draft_preview(self, conversation_uid: str, draft) -> int:
        """Положить превью драфта, вернуть preview_id для save_note."""
        d = draft if isinstance(draft, dict) else _draft_to_plain(draft)
        history = self._svc._previews.setdefault(conversation_uid, [])
        history.append(d)
        return len(history)

    def get_draft_preview(self, conversation_uid: str | None, preview_id: int) -> dict | None:
        """Превью по id (None — не найдено/протухло)."""
        if not conversation_uid:
            return None
        history = self._svc._previews.get(conversation_uid) or []
        return history[preview_id - 1] if 0 < preview_id <= len(history) else None
