---
name: book-splitter
description: "Ингест PDF-книги: TOC (закладки) → главы в отдельные .md файлы → записи в chapters. Вызывать через process_source(source_id)."
params:
  source_id:
    type: int
    desc: id источника (kind=book) с заполненным local_path
version: 0.1
status: active
---

# book-splitter

PDF → оглавление (pymupdf get_toc) → top-записи закладок → `data/sources/<id>/ch_<idx>.md`
+ строки в chapters (title, path, tokens_est, summary-заглушка, start_page/end_page,
секции level-2 в sections_json). Текст и картинки собираются через `page.get_text("dict")`:
image-блоки рендерятся по bbox (dpi 150) в `data/sources/<id>/images/` и вставляются
в .md главы markdown-ссылками `/api/sources/<uid>/images/…`; декоративные мелкие
(< 40pt) пропускаются. Классификацию записей (глава/мусор/приложение) делает
structure_curator в сервисе library — сплиттер отдаёт все top-записи как есть
(`entries` в результате). Переобработка чистит старые chapters/ и images/.

Нет закладок в PDF → ошибка (эвристика по шрифтам — фаза 1.1).
