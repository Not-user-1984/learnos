# B-012 · Ревью, раунд 1 (2026-11-17) — fix

Проверки: server 524 passed, ruff/format/lint-imports OK; web lint/tsc/build OK.
Регресс-тесты лежат в коммите B-013 (311d44a), а не в d43f578. Принимается, но отчёт должен говорить правду.

## Исправить
1. **major** `web/src/components/courses/course-board.tsx:122` — «Читать» ведёт в `/read` для любого kind, видео и статья дают 404.
   Нужно как в «Сегодня»: book → `/read?ch=`, остальные → `/library/{uid}/{chapter_idx||1}`. Если kind нет в item, взять его из источника.
2. **minor** `server/app/modules/today/service.py:82` — дефолт `kind="book"` при отсутствии поля ведёт в ридер.
   Брать kind из источника; если его нет — ссылка на страницу источника, а не на `/read`.
3. **minor** `web/src/components/chat/chat-view.tsx:310` — `hover:text-rose-500` → токен `destructive` (web/DESIGN.md).
4. Тест на п.1 (функция построения ссылки по kind — общая для Today и course-board, без дублирования).

## Готово, когда
Видео в курсе → «Читать» открывает страницу главы; rose-500 в chat/ нет (`grep -rn "rose-" web/src/components/chat`); проверки зелёные.

# Раунд 2 (2026-11-17) — done
Пункты 1–4 закрыты (общая `web/src/lib/reading-link.ts`, kind из источника, rose → destructive). Проверки: 540 passed, web OK.
Юнит-теста `readingHref` нет — в web нет тест-раннера, покрыто API-тестами kind. Принято.
