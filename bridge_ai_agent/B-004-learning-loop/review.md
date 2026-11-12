# B-004 · ревью

## Раунд 1 · 2026-11-12 · вердикт: done

Проверки по всей очереди (HEAD a6cea3b): ruff ✅ · format ✅ · lint-imports 7/7 ✅ · pytest 494 passed ✅ · web lint/tsc/build ✅ · alembic одна голова 0021.

- События SessionStarted/SessionFinished/ChapterRead, статусы items, review_item назавтра, block_sources урока; контракт «learning не зависит от courses/review».
- Решение «закрывать главу во всех курсах» и course_item_id без FK — принято.
