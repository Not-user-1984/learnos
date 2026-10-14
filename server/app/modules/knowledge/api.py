"""REST базы знаний: /api/kb/* (+алиасы /api/blocks из v1)."""

from fastapi import APIRouter
from pydantic import BaseModel

from .schemas import BlockCard, BlockDetail, CategoryIn, CategoryNode, TagCount, VersionInfo


class RestoreIn(BaseModel):
    """Откат без тела — параметры в пути."""


class SetCategoryBody(BaseModel):
    """Подтверждение категории из UI."""

    path: str | None = None
    confirm: bool = True


def _without_frontmatter(content: str) -> str:
    """Тело блока без YAML-frontmatter (для рендера)."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            return parts[2].lstrip("\n")
    return content


def make_router(svc) -> APIRouter:
    """Роуты базы знаний."""
    r = APIRouter(prefix="/kb", tags=["knowledge"])

    @r.get("/blocks", response_model=list[BlockCard])
    def list_blocks(
        category: str | None = None,
        tag: str | None = None,
        kind: str | None = None,
        source: str | None = None,
        status: str | None = None,
        q: str | None = None,
        sort: str = "created",
        order: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ):
        items = svc.list_blocks(
            category=category,
            tag=tag,
            kind=kind,
            source=source,
            status=status,
            q=q,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )
        return [_card_with_relations(m) for m in items]

    def _card_with_relations(m) -> BlockCard:
        return BlockCard(
            block_uid=m.uid,
            title=m.title,
            kind=m.kind,
            summary=m.summary,
            category_path=m.category_path,
            category_status=m.category_status,
            tags=list(m.tags),
            sources=[_src(s) for s in m.sources],
            weak_spots_count=m.weak_spots_count,
            version=m.version,
            created_at=m.created,
            updated_at=m.updated,
        )

    def _src(s):
        return {"source": s.source, "chapter": s.chapter, "title": s.title}

    @r.get("/blocks/{uid}", response_model=BlockDetail)
    def get_block(uid: str):
        b = svc.get_block(uid)
        return BlockDetail(
            **_card_with_relations(b.meta).model_dump(),
            content=_without_frontmatter(b.content),
            session_uid=b.meta.session_uid,
            conversation_uid=b.meta.conversation_uid,
            activity_uid=b.meta.activity_uid,
            versions_count=b.meta.versions_count,
            links=list(b.meta.links),
            back_links=list(b.meta.back_links),
        )

    @r.get("/blocks/{uid}/raw")
    def raw_block(uid: str):
        from fastapi.responses import Response

        b = svc.get_block(uid)
        return Response(
            content=b.content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{b.meta.path}.md"'},
        )

    @r.get("/blocks/{uid}/versions", response_model=list[VersionInfo])
    def versions(uid: str):
        return [VersionInfo(**v) for v in svc.versions(uid)]

    @r.get("/blocks/{uid}/versions/{version}")
    def get_version(uid: str, version: int):
        return {"block_uid": uid, "version": version, "content": svc.get_version_content(uid, version)}

    @r.post("/blocks/{uid}/restore/{version}")
    def restore(uid: str, version: int):
        b = svc.restore_version(uid, version)
        return {"ok": True, "block_uid": b.meta.uid, "version": b.meta.version}

    @r.post("/blocks/{uid}/category")
    def set_category(uid: str, body: SetCategoryBody):
        b = svc.set_block_category(uid, body.path, body.confirm)
        return {
            "ok": True,
            "block_uid": b.meta.uid,
            "category": b.meta.category_path,
            "status": b.meta.category_status,
        }

    @r.get("/categories", response_model=list[CategoryNode])
    def categories():
        def to_node(d: dict) -> CategoryNode:
            return CategoryNode(
                **{k: v for k, v in d.items() if k != "children"},
                children=[to_node(ch) for ch in d["children"]],
            )

        return [to_node(x) for x in svc.category_tree()]

    @r.post("/categories", response_model=CategoryNode)
    def create_category(body: CategoryIn):
        cat = svc.create_category(body.path, body.title, body.color, body.icon, body.sort)
        return CategoryNode(path=cat.path, title=cat.title, color=cat.color, icon=cat.icon)

    @r.patch("/categories/{path:path}", response_model=CategoryNode)
    def patch_category(path: str, body: CategoryIn):
        cat = svc.update_category(path, title=body.title, color=body.color, icon=body.icon, sort=body.sort)
        return CategoryNode(path=cat.path, title=cat.title, color=cat.color, icon=cat.icon)

    @r.get("/tags", response_model=list[TagCount])
    def tags():
        return [TagCount(tag=t, count=n) for t, n in sorted(svc.tags().items())]

    @r.get("/inbox", response_model=list[BlockCard])
    def inbox():
        return [_card_with_relations(m) for m in svc.inbox()]

    @r.post("/reindex")
    def reindex():
        return svc.reindex()

    return r


def make_alias_router(svc) -> APIRouter:
    """Алиасы v1: /api/blocks и /api/blocks/{uid} → /api/kb/…"""
    r = APIRouter(prefix="/blocks", tags=["knowledge"])

    @r.get("")
    def list_blocks(course_id: int | None = None):
        del course_id
        return [_alias_card(m) for m in svc.list_blocks()]

    @r.get("/{uid}")
    def get_block(uid: str):
        b = svc.get_block(uid)
        return {**_alias_card(b.meta), "content": b.content}

    def _alias_card(m) -> dict:
        return {
            "block_uid": m.uid,
            "kind": m.kind,
            "title": m.title,
            "summary": m.summary,
            "category_path": m.category_path,
            "category_status": m.category_status,
            "tags": list(m.tags),
            "weak_spots_count": m.weak_spots_count,
            "version": m.version,
            "created_at": m.created,
            "updated_at": m.updated,
        }

    return r
