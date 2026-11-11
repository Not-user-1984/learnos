"""CLI: migrate | reindex | smoke-llm | seed-demo."""

import argparse
import asyncio
import sys


def main() -> None:
    """Точка входа uv run python -m app.cli."""
    parser = argparse.ArgumentParser(prog="learnos")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="применить миграции Alembic")
    reindex_p = sub.add_parser("reindex", help="пересобрать индекс базы знаний из kb/")
    reindex_p.add_argument(
        "--embeddings", action="store_true", help="векторы тоже (инкрементально по хэшу, B-008)"
    )
    sub.add_parser("smoke-llm", help="живая проверка LLM: ответ, стрим, tool call")
    sub.add_parser("seed-demo", help="демо-данные в текущие LEARNOS_DATA_DIR/LEARNOS_KB_DIR")
    args = parser.parse_args()
    from .bootstrap import build_container

    container = build_container()

    if args.cmd == "migrate":
        from .main import migrate_db

        migrate_db(container)
        print("миграции применены")
    elif args.cmd == "reindex":
        result = container.knowledge.reindex()
        container.search.reindex_blocks()
        container.search.reindex_chapters()
        print(f"reindex: {result}")
        if args.embeddings:
            _reindex_embeddings(container)
    elif args.cmd == "smoke-llm":
        asyncio.run(_smoke_llm(container))
    elif args.cmd == "seed-demo":
        _seed_demo(container)


def _reindex_embeddings(container) -> None:
    """Бэкфилл векторов с прогрессом; повторный запуск досчитывает недостающее (хэш текста)."""
    if not container.search.embed_ready():
        print("embeddings: роль embed не настроена — пропускаю (поиск остаётся на FTS)")
        return
    blocks = container.knowledge.list_blocks(limit=1000)
    done = skipped = 0
    for meta in blocks:
        out = container.search.index_block_embeddings(meta.uid)
        done += 1 if out.get("indexed") else 0
        skipped += 0 if out.get("indexed") else 1
        mark = "✓" if out.get("indexed") else (out.get("reason") or "skip")
        print(f"  блок {done + skipped}/{len(blocks)}: {meta.uid} {mark}")
    chapters_done = 0
    for src in container.library.list_sources():
        src_chapters = 0
        for ch in container.library.list_chapters(src["uid"]):
            part = container.library.read_chapter(src["uid"], ch["idx"], 0, 50000)
            out = container.search.index_chapter_embeddings(src["uid"], ch["idx"], part["text"])
            if out.get("indexed"):
                src_chapters += 1
        chapters_done += src_chapters
        print(f"  источник {src['uid']}: глав проиндексировано {src_chapters}")
    print(f"embeddings: блоков {done} (+{skipped} пропущено), глав {chapters_done}")


async def _smoke_llm(container) -> None:
    """Три проверки LLM: обычный ответ, стрим, вызов инструмента echo."""
    from .llm.types import LLMRequest, Message, ToolSchema

    provider, model, _params = container.llm_router.resolve("chat")
    print(f"провайдер: {provider.name}, модель: {model}")

    resp = await provider.complete(
        model, LLMRequest(messages=(Message(role="user", content="Ответь одним словом: два+2?"),))
    )
    print(f"1) complete: {resp.text!r}")

    text = ""
    async for ev in provider.stream(
        model, LLMRequest(messages=(Message(role="user", content="Посчитай от 1 до 5 через пробел"),))
    ):
        if ev.type == "text":
            text += ev.text
    print(f"2) stream: {text!r}")

    echo = ToolSchema(
        name="echo",
        description="повторить текст",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )
    calls_text = ""
    async for ev in provider.stream(
        model,
        LLMRequest(
            messages=(Message(role="user", content="Вызови инструмент echo с текстом 'привет'"),),
            tools=(echo,),
        ),
    ):
        if ev.type == "tool_call" and ev.tool_call:
            calls_text = f"{ev.tool_call.name}({ev.tool_call.arguments})"
    print(f"3) tool call: {calls_text!r}")
    if "echo" not in calls_text:
        sys.exit(1)


def _seed_demo(container) -> None:
    """10+ блоков в 3 категориях для проверки фильтров (только в тестовые каталоги)."""
    from .modules.knowledge.domain import BlockDraft, Concept

    demo = [
        (
            "Инкапсуляция в Python",
            "programming/python/oop",
            "python",
            "Скрытие внутреннего состояния объекта за методами.",
        ),
        (
            "Миксины в Python",
            "programming/python/oop",
            "python",
            "Переиспользование поведения без наследования.",
        ),
        ("Дескрипторы", "programming/python/oop", "python", "Протокол __get__/__set__ атрибутов."),
        ("Асинхронность в Python", "programming/python", "python", "Event loop, корутины, await."),
        ("Типизация Python", "programming/python", "python", "Аннотации и mypy."),
        ("Поды Kubernetes", "infra/kubernetes", "k8s", "Минимальная единица деплоя."),
        ("Services в Kubernetes", "infra/kubernetes", "k8s", "Стабильный адрес для подов."),
        ("ConfigMaps", "infra/kubernetes", "k8s", "Конфигурация без пересборки образа."),
        ("Ingress", "infra/kubernetes", "k8s", "HTTP-маршрутизация в кластер."),
        ("Омлет", "life/cooking", "кулинария", "Быстрый завтрак из яиц."),
        ("Кофе во френч-прессе", "life/cooking", "кучит", "4 минуты, крупный помол."),
    ]
    for title, category, tag, summary in demo:
        container.knowledge.save_block(
            BlockDraft(
                title=title,
                summary=summary,
                kind="lesson",
                concepts=(Concept(term=title, definition=summary),),
                theses=(f"{title} — важно для практики",),
                tags=(tag,),
                category_suggestion=category,
            ),
            category_status="suggested",
        )
    print(f"создано демо-блоков: {len(demo)}")


if __name__ == "__main__":
    main()
