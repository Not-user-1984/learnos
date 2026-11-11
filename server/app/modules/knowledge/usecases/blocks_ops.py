"""Операции над блоками поверх CRUD (B-009): откат версий и пересборка индекса."""

from ..domain import Block, BlockMeta, extract_links, parse_markdown
from ..domain import dict_of_meta as _dict_of


class BlocksOpsUseCases:
    """Откат к версии и reindex из kb/ (перенос из service без изменения поведения)."""

    def __init__(self, svc) -> None:
        self._svc = svc

    def restore_version(self, uid: str, version: int, reason: str = "откат") -> Block:
        """Откат к версии: текущий контент сохраняется как версия, файл перезаписывается старым."""
        from ....kernel.clock import now_iso
        from ..events import BlockUpdated

        svc = self._svc
        now = now_iso(svc._clock)  # noqa: SLF001
        with svc._uow() as uow:  # noqa: SLF001
            block = svc._blocks.get(uow.session, uid)  # noqa: SLF001
            old_content = svc._versions.get_version(uow.session, uid, version)  # noqa: SLF001
            current_content = svc._files.read(block.meta.path)  # noqa: SLF001
            svc._versions.add_version(  # noqa: SLF001
                uow.session,
                uid,
                block.meta.version,
                current_content,
                f"перед откатом к v{version}",
                None,
                now,
            )
            svc._files.write_raw(block.meta.path, old_content)  # noqa: SLF001
            meta_raw, _ = parse_markdown(old_content)
            restored = BlockMeta(
                **{
                    **_dict_of(block.meta),
                    "title": meta_raw.get("title", block.meta.title),
                    "kind": meta_raw.get("kind", block.meta.kind),
                    "summary": meta_raw.get("summary") or "",
                    "tags": tuple(meta_raw.get("tags") or ()),
                    "version": block.meta.version + 1,
                    "updated": now,
                }
            )
            svc._blocks.update_row(uow.session, restored)  # noqa: SLF001
            uow.emit(BlockUpdated(block_uid=uid, version=restored.version, reason=reason))
            return Block(meta=restored, content=old_content)

    def reindex(self) -> dict:
        """Пересобрать индекс знаний из kb/ (после ручной правки MD)."""
        import logging

        from ....kernel.errors import NotFound

        log = logging.getLogger("learnos.knowledge")
        svc = self._svc
        created, updated = 0, 0
        with svc._uow() as uow:  # noqa: SLF001
            known = set(svc._blocks.uids(uow.session))  # noqa: SLF001
            for stem in svc._files.list_stems():  # noqa: SLF001
                try:
                    meta = svc._files.read_meta(stem)  # noqa: SLF001
                except (NotFound, ValueError) as e:
                    log.warning("reindex: пропуск %s: %s", stem, e)
                    continue
                meta = BlockMeta(
                    **{
                        **_dict_of(meta),
                        "path": stem,
                        "links": extract_links(svc._files.read(stem).split("---", 2)[-1]),  # noqa: SLF001
                    }
                )
                if meta.uid in known:
                    svc._blocks.update_row(uow.session, meta)  # noqa: SLF001
                    updated += 1
                else:
                    svc._blocks.save(uow.session, meta)  # noqa: SLF001
                    created += 1
        return {"ok": True, "created": created, "updated": updated}
