---
name: book-splitter
description: "Ингест PDF-книги: TOC (закладки) → главы в отдельные .md файлы → записи в chapters; без закладок — главы-куски по страницам. Вызывать через process_source(source_id)."
params:
  source_id:
    type: int
    desc: id источника (kind=book) с заполненным local_path
  chunk_pages:
    type: int
    optional: true
    default: 50
    desc: размер куска-главы в страницах для PDF без закладок (10..200)
version: 0.2
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

Нет закладок в PDF → главы-куски по страницам (`mode: "pages"`, дефолт 50 стр.,
хвост < 5 стр. входит в предыдущий кусок); куратор структуры в этом режиме
не вызывается. Происхождение глав — в поле `mode` ответа: `toc` | `pages`.
