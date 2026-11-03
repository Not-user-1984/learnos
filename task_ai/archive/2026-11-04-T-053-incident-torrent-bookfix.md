---
id: T-053
title: Инцидент 2026-11-03 — torrent-fetch (auto/import/409) и book-splitter без TOC
status: done
priority: high
from: инцидент прода 2026-11-03 22:00–22:10 UTC (аудит ZCode)
created: 2026-11-04
closed: 2026-11-04
---

## Что нужно

Инцидент: агент не смог довести торрент-книгу до библиотеки (нет action=auto,
qBit 409 на повторный add, нет действия import), а PDF «Django-4-Практика
создания» (791 стр., без закладок) валил ингест целиком.

- A1. torrent_fetch main(): action=`auto` — поиск + сразу добавить лучшего.
- A2. qbit add(): 409 = уже добавлен → `duplicate: true`, не ошибка (qBit 5.x).
- A3. qbit torrents(): content_path/save_path в выдаче (для import).
- A4. Действие `import`: завершённая раздача learnos-books/без категории →
  PDF (файл или крупнейший в каталоге ≥100 КБ) → source+job напрямую в БД
  (уровень app.db, без сервисного слоя), идемпотентно по title (existed=true).
- A5. SKILL.md: auto, import, 409=дубликат.
- A6. Тесты: 409-duplicate, поля torrents, маршрутизация auto, import (полный,
  идемпотентность, каталог PDF, отказы).
- B1. book-splitter: PDF без TOC → главы-куски по N страниц (дефолт 50,
  10..200), названия «Страницы 1–50», `mode: toc|pages` в ответе, секций нет,
  куратор структуры не вызывается.
- B2. Хвост куска < 5 стр. — приклеивается к предыдущей главе.
- B3. Тесты: без TOC → куски/mode=pages; с TOC → mode=toc (прежний путь);
  формула кусков на объёме 791 стр. → 16 глав.

## Критерии готовности

- [x] action=auto работает из MCP/агента; add 409 не роняет сценарий
- [x] import идемпотентен, создаёт source(status=chosen)+job(process_source)
- [x] Django-4 (791 стр., без TOC) обрабатывается: ~16 глав
- [x] Тесты зелёные, ruff/format/import-linter чистые
- [x] Прод после деплоя: переобработка src_09a3ec0d, health ok

## Заметки

- Раздача «Радченко 1С 8.3» (hash d47efb28…) на проде уже в библиотеке как
  src_5f3dbec4 (hook успел) — import по ней должен вернуть existed=true.
- Файлы qBit живут на media-CT (192.168.0.131, /downloads внутри контейнера
  qBit) и из CT 132 недоступны: import при недостижимом content_path отвечает
  `file_unreachable` с подсказкой про hook (полный импорт работает, когда путь
  виден — локальная разработка, будущий mount). Идемпотентность проверяется до
  доступа к файлу.
- Куратор структуры пропускается только в mode=pages (gate в
  `LibraryService._run_process`).

## Сделано (2026-11-04)

Коммиты ab6dbca (torrent-fetch: auto/import/409/пути), aade221 (book-splitter
pages-режим + gate куратора), b227a61 (задача/баги). Тесты 417 → 427.

Самопроверка прода (CT 132, деплой 22:44 UTC, health ok):

- Django-4 src_09a3ec0d переобработан: `mode=pages`, 16 глав «Страницы 1–50» …
  «Страницы 751–791» (1..791), lang=ru, source processed.
- torrent_fetch import по hash d47efb28… (Радченко): `{"ok": true, "uid":
  "src_5f3dbec4", "existed": true, "source_status": "processed"}` — идемпотентность
  распознала книгу, залитую hook'ом (title с «.pdf»).
- Вывод инцидента: add 409 больше не роняет сценарий агента; у агента есть
  внятный action=auto и import с объяснимыми ошибками (file_unreachable → hook).
