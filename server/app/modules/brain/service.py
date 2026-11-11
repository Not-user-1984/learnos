"""Сервис «второго мозга» (B-007): capture за один вызов и контекст по теме за один вызов.

Правило «выученное = только через сессию» сохраняется: всё, что нейронки кладут
через capture, — сырьё (inbox, verified=false); verified-знание рождает сессия-урок.
"""

import hashlib
import re

from ..knowledge.domain import BlockDraft

# тег-хэш для дедупа текста: sha256 нормализованного текста, укороченный
_HASH_TAG_LEN = 23  # "sha256:" + 16 символов


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def text_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(_norm_text(text).encode()).hexdigest()[:16]}"


def _sentences(text: str, budget: int) -> str:
    """Excerpt по предложениям, укладываясь в бюджет символов."""
    out: list[str] = []
    total = 0
    for sentence in re.split(r"(?<=[.!?…])\s+", text.strip()):
        if total + len(sentence) > budget and out:
            break
        out.append(sentence)
        total += len(sentence) + 1
        if total >= budget:
            break
    excerpt = " ".join(out)
    return excerpt[:budget] if excerpt else text[:budget]


class BrainService:
    """Use-cases capture/context/get для внешних нейронок через MCP /mcp/brain."""

    def __init__(self, knowledge, library, search) -> None:
        self._kb = knowledge
        self._lib = library
        self._search = search

    # --- capture: положить за один вызов ---

    def capture(
        self,
        kind: str,
        content: str,
        title: str | None = None,
        topic: str | None = None,
        tags: list[str] | None = None,
        source_agent: str | None = None,
    ) -> dict:
        """Положить материал в LearnOS идемпотентно.

        text → заметка-блок во входящие (verified=false, дедуп по sha256 текста);
        url → источник в библиотеку (YouTube/PDF/web, дедуп по URL) + запуск обработки.
        """
        if kind == "url":
            return self._capture_url(content, title)
        if kind == "text":
            return self._capture_text(content, title, topic, tags or [], source_agent)
        return {"error": "validation_failed", "message": "kind должен быть text|url"}

    def _capture_url(self, url: str, title: str | None) -> dict:
        from ..library.domain import is_youtube_url

        kind = "video" if is_youtube_url(url) else ("book" if url.lower().endswith(".pdf") else "web")
        out = self._lib.add_source(kind, title or url, url=url)
        if not out.get("created", True):
            return {"uid": out["uid"], "kind": "source", "created": False, "status": out["status"]}
        # сразу в обработку: главы/транскрипт появятся фоновым job
        self._lib.process_source(out["uid"])
        return {"uid": out["uid"], "kind": "source", "created": True, "status": "processing"}

    def _capture_text(
        self, text: str, title: str | None, topic: str | None, tags: list[str], source_agent: str | None
    ) -> dict:
        htag = text_hash(text)
        existing = self._kb.list_blocks(tag=htag, limit=1)
        if existing:
            return {"uid": existing[0].uid, "kind": "note", "created": False, "status": "inbox"}
        draft = BlockDraft(
            title=(title or _norm_text(text)[:70] or "Заметка")[:100],
            summary=text[:280],
            kind="note",
            theses=(text[:4000],),
            tags=[*tags, htag, *(["by:" + source_agent] if source_agent else [])][:8],
            category_suggestion=topic,
        )
        block = self._kb.save_block(draft, category_status="inbox", verified=False)
        return {"uid": block.meta.uid, "kind": "note", "created": True, "status": "inbox"}

    # --- context: всё по теме за один вызов ---

    def context(
        self,
        topic: str,
        budget_chars: int = 8000,
        include: list[str] | None = None,
        cursor: int = 0,
    ) -> dict:
        """Компактный контекст по теме: verified-блоки → главы → inbox-заметки.

        Каждый элемент — {uid, type, title, verified, excerpt} с uid для get();
        укладывается в budget_chars, остаток — через next_cursor.
        """
        include = include or ["blocks", "chapters", "inbox"]
        found = self._search.search(topic, scope="all", limit=10)

        items: list[dict] = []
        if "blocks" in include:
            metas = {m.uid: m for m in self._kb.list_blocks(q=topic, limit=10)}
            for hit in found.get("blocks", []):
                meta = metas.get(hit["block_uid"])
                if meta is None:
                    continue
                items.append(
                    {
                        "uid": meta.uid,
                        "type": "block",
                        "title": meta.title,
                        "verified": bool(meta.verified),
                        "category_status": meta.category_status,
                        "excerpt": hit.get("snippet") or meta.summary or "",
                        "_rank": 0 if meta.verified else 2,
                    }
                )
        if "chapters" in include:
            for hit in found.get("chunks", []):
                items.append(
                    {
                        "uid": f"{hit['source_uid']}:{hit['chapter']}",
                        "type": "chapter",
                        "title": hit.get("title", ""),
                        "verified": False,
                        "excerpt": hit.get("snippet", ""),
                        "_rank": 1,
                    }
                )
        if "inbox" in include:
            # inbox не в FTS-индексе: матчим слова темы по заголовку/саммари
            words = [w for w in re.split(r"\W+", topic.lower()) if len(w) >= 3]
            for meta in self._kb.inbox():
                haystack = (meta.title + " " + (meta.summary or "")).lower()
                if words and all(w in haystack for w in words):
                    items.append(
                        {
                            "uid": meta.uid,
                            "type": "inbox",
                            "title": meta.title,
                            "verified": False,
                            "excerpt": meta.summary or "",
                            "_rank": 3,
                        }
                    )
        items.sort(key=lambda i: i.pop("_rank"))

        # бюджет: режем excerpt по предложениям, лишние элементы — за next_cursor
        out: list[dict] = []
        used = 0
        for item in items:
            if used >= budget_chars:
                break
            room = budget_chars - used
            excerpt = _sentences(item["excerpt"], min(600, room))
            out.append({**item, "excerpt": excerpt})
            used += len(excerpt) + len(item["title"]) + 40
        return {
            "topic": topic,
            "items": out[cursor:] or out,
            "truncated": len(out) < len(items) or used >= budget_chars,
            "next_cursor": (cursor + len(out)) if len(out) < len(items) else None,
        }

    # --- get: batch для блоков/глав/источников ---

    def get(self, uids: list[str], max_chars_each: int = 4000) -> dict:
        """Блоки/главы/источники пачкой: uid блока (blk_…), источник (src_…),
        глава — "src_…:N" (uid из context)."""
        results: list[dict] = []
        for uid in uids[:10]:
            try:
                if uid.startswith("blk_"):
                    b = self._kb.get_block(uid)
                    results.append(
                        {
                            "uid": uid,
                            "type": "block",
                            "title": b.meta.title,
                            "content": b.content[:max_chars_each],
                            "truncated": len(b.content) > max_chars_each,
                        }
                    )
                elif ":" in uid and uid.split(":", 1)[0].startswith("src_"):
                    src_uid, _, ch = uid.rpartition(":")
                    part = self._lib.read_chapter(src_uid, int(ch), 0, max_chars_each)
                    results.append(
                        {
                            "uid": uid,
                            "type": "chapter",
                            "title": part.get("title", uid),
                            "content": part.get("text", "")[:max_chars_each],
                            "truncated": bool(part.get("next_offset")),
                        }
                    )
                elif uid.startswith("src_"):
                    src = self._lib.get_source(uid)
                    results.append(
                        {
                            "uid": uid,
                            "type": "source",
                            "title": src["title"],
                            "kind": src["kind"],
                            "summary": src.get("summary") or "",
                            "chapters": [
                                {"idx": c["idx"], "title": c["title"]} for c in src.get("chapters", [])[:40]
                            ],
                        }
                    )
            except Exception:  # noqa: BLE001 — один битый uid не роняет пачку
                results.append({"uid": uid, "error": "not_found"})
        return {"items": results}

    # --- мелкие утилиты мозга ---

    def list_topics(self) -> list[dict]:
        """Дерево категорий с числом блоков."""
        return self._kb.category_tree()

    def inbox(self, limit: int = 20) -> list[dict]:
        """Входящие: сырьё от нейронок и человека, ждёт сессии-проговора."""
        return [
            {
                "uid": m.uid,
                "title": m.title,
                "summary": m.summary,
                "tags": list(m.tags),
                "created_at": m.created,
            }
            for m in self._kb.inbox()[:limit]
        ]

    def promote_hint(self, uid: str) -> dict:
        """Как сделать знание выученным: только сессия-урок, не механический флаг."""
        return {
            "uid": uid,
            "hint": (
                "Блок становится выученным (verified) только через сессию-урок: открой "
                f"/kb/{uid} и запусти сессию, или попроси в чате «сессия по блоку {uid}». "
                "Механического promote нет — проговор важнее флага."
            ),
        }

    def add_source(self, kind: str, title: str, url: str | None = None) -> dict:
        """Источник в библиотеку (дедуп по URL); обработка запускается отдельно process."""
        out = self._lib.add_source(kind, title, url=url)
        return out
