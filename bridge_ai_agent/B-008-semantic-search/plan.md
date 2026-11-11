# B-008 · Гибридный поиск FTS + векторы (раскрытие T-007)

Цель: поиск и `context` (B-007) находят по смыслу, а не только по словам («как не потерять данные при сбое» →
блок про WAL). Работает без внешнего векторного сервиса: SQLite + sqlite-vec.
Зависит от: B-007 (`context` переключается на гибрид). Закрывает `task_ai/tasks/T-007-semantic-search.md`.

## Готово, когда
- [ ] Роль `embed` в `server/config/llm.yaml` (модель эмбеддингов провайдера, OpenAI-совместимый `/embeddings`);
      нет ключа / роль не настроена → поиск работает на чистом FTS, без ошибок.
- [ ] Эмбеддинги блоков и чанков глав в sqlite-vec; обновляются по событиям `BlockSaved/BlockUpdated/
      BlockDeleted/SourceProcessed/SourceDeleted` (подписки в search, как FTS сейчас).
- [ ] `search(q, mode=hybrid|fts|vector)`, по умолчанию hybrid = RRF-слияние FTS и векторных результатов.
- [ ] CLI `uv run python -m app.cli reindex --embeddings` — бэкфилл с батчами и прогрессом, повторный запуск
      досчитывает только недостающее (хэш текста).
- [ ] Набор из ≥10 пар «запрос → ожидаемый блок» в тестовой фикстуре: hybrid находит ≥8 в топ-5 (на фейковых
      детерминированных эмбеддингах в unit-тестах; на проде — ручной смоук и запись результата в report.md).

## Контекст в коде
- `server/app/modules/search/` — FTS5, подписки `search/__init__.py:31-35`.
- `server/app/llm/` — роли/ключи, адаптер `llm/providers/openai_compat.py` (добавить `embed(texts) -> list[list[float]]`).
- `server/config/llm.yaml` — роли и `api_key_envs`.

## Изменения
1. llm: метод `embed` в адаптере + роль `embed` (батчи до N текстов, ретрай по цепочке ключей как у chat).
2. search/infra: таблица `vec_items(item_type, item_id, chunk_no, text_hash, embedding)` через sqlite-vec
   (зависимость `sqlite-vec` в `pyproject.toml`, загрузка расширения при открытии соединения; в Docker-образе
   проверить, что колесо ставится под платформу CT).
3. search/service: индексация (чанки ≤1000 симв.), запрос, RRF (k=60), фильтры scope как у FTS.
4. Индексация асинхронно: в подписчике ставить задачу в существующий JobWorker (`library/worker.py`), не блокировать
   запрос пользователя; при недоступном embed — job помечается skipped, FTS остаётся.
5. `GET /api/health` / `llm_status`: показывать роль embed и число неиндексированных элементов.

## Тесты
- RRF на синтетике; деградация в FTS без роли embed; инкрементальный reindex по хэшу; удаление блока удаляет векторы.

## Проверки
- `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
- `docker compose build` (sqlite-vec в образе)

## Риски
- Модель эмбеддингов у z.ai: уточнить имя и размерность в документации провайдера; размерность хранить в конфиге,
  при смене модели — полный reindex (детектировать по `model` в метаданных таблицы).
- Объём: книги дают тысячи чанков — бэкфилл батчами, учитывать квоту ключей.
