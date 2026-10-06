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

PDF → оглавление (pymupdf get_toc) → главы верхнего уровня → `data/sources/<id>/ch_<idx>.md`
+ строки в таблице chapters (title, path, tokens_est, summary-заглушка).

Нет закладок в PDF → ошибка (эвристика по шрифтам — фаза 1.1).
Summary на главу через LLM — когда подключим LLM-клиент (z.ai).
