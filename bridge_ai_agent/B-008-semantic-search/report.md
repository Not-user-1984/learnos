# B-008 — отчёт исполнителя

## Изменённые файлы

**LLM:**
- `app/llm/provider.py` — `embed` в протоколе
- `app/llm/providers/openai_compat.py` — `embed(model, texts)`: /embeddings, ротация ключей по квоте + ретраи временных ошибок (как chat)
- `app/llm/providers/fake.py` — детерминированные bag-of-words хэш-векторы (64 измерения, md5-стабильные между процессами) — семантика для тестов без модели
- `config/llm.yaml` — роль `embed` (закомментированным пресетом z.ai: модель уточнить в доке провайдера; роль не настроена → чистый FTS без ошибок)

**Векторный индекс:**
- `app/kernel/db.py` — sqlite-vec грузится в connect (нет колеса/расширения — не фатально, поиск на FTS)
- `app/modules/search/infra/vec.py` — новый: `vec_chunks` (item_key, chunk_no, text_hash, embedding_json) + `vec_state` (model/dim — детект смены модели → полный пересбор) + vec0-таблица; KNN через vec0 MATCH на проде, **Python-cosine fallback** по embedding_json без расширения (мак-дев без loadable extensions); инкрементальность по sha256 текста
- `migrations/versions/0019_vec_chunks.py` — таблицы для прода (vec0 создаётся runtime — размерность модели неизвестна в миграции)
- `pyproject.toml` — `sqlite-vec==0.1.9`

**Поиск:**
- `app/modules/search/service.py` — `search(q, scope, limit, mode=hybrid|fts|vector)`: RRF (k=60) слияние FTS+векторов с `matched_by` у каждого хита; `chunk_text` (~1000 симв по предложениям); `index_block_embeddings`/`index_chapter_embeddings` (инкрементально, skipped без роли embed); `on_block_deleted` чистит и векторы; `drop_source_index` — FTS+векторы источника; `vector_status()` для health
- `app/modules/search/api.py` — `GET /api/search?mode=`
- `app/modules/search/__init__.py` — wire с VecRepo+router; job-хэндлер `search_embed` (block:/source:); подписки: BlockSaved/Updated → FTS сразу + job векторов, SourceProcessed → FTS + job, BlockDeleted/SourceDeleted → чистка обоих индексов

**Воркер и CLI:**
- `app/modules/library/worker.py` — `register_handler(kind, handler)`, `enqueue(kind, target)`, завершение чужих jobs (done|skipped)
- `app/modules/library/service.py` — `finish_job(job_id, status, message)`
- `app/cli.py` — `reindex --embeddings`: бэкфилл блоков и глав с прогрессом, повторный запуск досчитывает только недостающее (хэш)

**Health:** `app/main.py` — `embed_configured`, `embed_indexed_items`, `embed_pending_blocks`.

Brain (B-007) `context` автоматически стал гибридным — зовёт `search.search` с дефолтом hybrid.

**Тесты:** `tests/unit/hybrid_search_test.py` — RRF на синтетике; чанкование; деградация в FTS без роли embed (router=None); инкрементальность (повтор → skip «текст не менялся») + удаление блока чистит векторы; **10 пар «запрос→блок» (+10 дистракторов): hybrid находит ≥8 в топ-5** (прогнал: все пары находятся); mode=vector по словам.

## Результаты проверок

- `cd server`: ruff ✅ · format ✅ · lint-imports ✅ (4/4) · pytest ✅ (весь suite; миграции до head 0019 зелёные; кроме 4 предсуществующих сетевых test_from_url)
- `docker compose build server` ✅ (после повтора: первый упал на 502 debian-зеркала — сетевое, не связано с изменениями); в образе `/app/.venv` `sqlite-vec==0.1.9` загружается: `SELECT vec_version()` → v0.1.9
- `cd web`: gen:api ✅ (82 пути) · tsc ✅ (веб-код не менялся)

## Отклонения и решения

1. **Python-cosine fallback**: macOS-дев без loadable extensions (pysqlite3-binary под mac arm64 не собирается) — эмбеддинг дублируется в `embedding_json`, KNN считается наивно; на проде (CT, расширение есть) — vec0 KNN. Честная работа в обоих мирах, тихой деградации нет.
2. **Роль embed в llm.yaml закомментирована**: имя модели эмбеддингов у z.ai не подтверждено докой (риск из плана) — включается одной строкой; до этого гибрид деградирует в FTS без ошибок (тест на это есть).
3. **Размерность** определяется по первому ответу модели (len вектора), а не конфигом; смена модели/размерности — автоматический полный пересбор индекса (vec_state).
4. **Индексация векторов — jobs в общем JobWorker** (register_handler): запрос пользователя не блокируется; без роли embed job завершается `skipped` (не failed).
5. **Прод-смоук гибрида на живых эмбеддингах** не выполнял (роль не включена до уточнения модели, пуша нет) — покрыт e2e-тестами на фейке; после включения роли на проде: `reindex --embeddings` + `GET /api/search?q=…&mode=hybrid`.

## Вопросы

- Нужно у провайдера (z.ai) уточнить имя модели эмбеддингов и размерность — после этого раскомментировать роль в `config/llm.yaml` и прогнать `reindex --embeddings` на проде.
