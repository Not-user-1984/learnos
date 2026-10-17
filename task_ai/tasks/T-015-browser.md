---
id: T-015
title: Браузер для агентов (третья линия ресерча)
status: idea
priority: medium
from: просьба пользователя + task_ai/reference/hermes-research.md §2
created: 2026-10-17
---

## Что нужно
Инструмент браузера как fallback после search+extract: страница не отдалась / JS-рендер / SPA.
Паттерн Hermes: a11y-tree снапшоты с refs `@eN` (не скриншоты), сессии на задачу,
oversize-снапшоты → truncate-and-store, SSRF до navigate и на каждом редиректе.

## Решить перед стартом
- Backend: Playwright (нужен node/браузер в контейнере сервера — отдельный sidecar-сервис?) против облачных (Browserbase и пр. — по ключу).
- Объём MVP: только `browser_read(url)` (JS-рендер → текст для библиотеки) против полного набора navigate/click/type (интерактив: логины, SPA).
- Куда попадают сессии/куки (приватность), rate-limit на домен.

## Критерии готовности
- [ ] выбран backend, решение зафиксировано в этой задаче
- [ ] `browser_read` доступен агентам как fallback с тем же truncate-and-store
- [ ] интерактивные инструменты (если да) — с approval на опасные действия
- [ ] тесты: SSRF, обрезка снапшота, очистка сессий
