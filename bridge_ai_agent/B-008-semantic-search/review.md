# B-008 · ревью

## Раунд 1 · 2026-11-12 · вердикт: done

Проверки по всей очереди (HEAD a6cea3b): ruff ✅ · format ✅ · lint-imports 7/7 ✅ · pytest 494 passed ✅ · web lint/tsc/build ✅ · alembic одна голова 0021.

- sqlite-vec + Python-cosine fallback, RRF, jobs-индексация, reindex --embeddings; без роли embed — честная деградация в FTS.
- Хвост (не блокер): роль embed закомментирована — нужно имя модели эмбеддингов z.ai; до включения поиск = FTS.
