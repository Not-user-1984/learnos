---
id: T-031
title: Академический поиск v2: OpenAlex + Semantic Scholar + прозрачность провайдеров
status: done   # закрыта 2026-10-24: критерии проверены на проде (см. archive/README.md)
priority: high
from: спонтанная задача пользователя 2026-10-24 («расширь, чтобы я видел все источники у агента — что, где он ищет»)
created: 2026-10-24
---

## Что нужно

Сейчас `academic_search` — только arXiv (`research/providers.py:134` AcademicProvider, `research/service.py:119-121`). Расширить и сделать прозрачным, где агент ищет.

### Э1. Новые академические провайдеры
По образцу существующих (Protocol `SearchProvider.search(query, limit) -> _ok(...)` в `research/providers.py`):
- **OpenAlexProvider** — `https://api.openalex.org/works?search=...` без ключа (наш keyless-стиль). Поля: title, authors, year, doi, url, abstract (reconstruct из abstract_inverted_index), cited_by_count, open_access.
- **SemanticScholarProvider** — `https://api.semanticscholar.org/graph/v1/paper/search?query=...&fields=title,authors,year,abstract,url,openAccessPdf,citationCount` без ключа (терпим 429 → один ретрай с паузой, потом тихий пропуск).
- Оба с таймаутами httpx как у текущих, `provider` = "openalex" / "semantic_scholar".

### Э2. Агрегация в academic()
`research/service.py academic()`: опросить arXiv + OpenAlex + Semantic Scholar (последовательно или concurrently — как проще с текущим _cached; ошибки одного провайдера не роняют остальные). Дедупликация по нормализованному DOI, иначе по нормализованному title. У КАЖДОГО результата — поле `provider`. Итог: `{"query", "count", "results": [...], "providers": {"arxiv": n, "openalex": n, "semantic_scholar": n, "failed": [...]}}`. Кэш как сейчас.

### Э3. Прозрачность «где ищет агент»
- Новый тул MCP/REST `search_providers` (модуль research): отдаёт конфигурацию поиска по категориям с состоянием: web (цепочка tavily→serper→ddg→wikipedia→hn, кто enabled по ключам/настройкам), academic (arxiv/openalex/semantic_scholar, всегда доступны), video (youtube). Поля: категория, провайдеры, enabled, примечание (ключ задан/безключевой).
- Интегрировать в существующую страницу настроек веба «Прокси и поиск» (где /api/connectivity + /check): новый блок «Провайдеры поиска» — таблица по категориям (где агент ищет), без переключателей (только отображение) в этой итерации.
- В результатах `academic_search` агент видит `provider` у каждой статьи (тул-спека описывает это).

### Э4. Директива промпта
В research-директиву (system_extra research-режима, где упоминается torrent_fetch) добавить подсказку: для научных тем звать `academic_search` — теперь ищет по arXiv + OpenAlex + Semantic Scholar, у результатов есть `provider`.

## Критерии готовности
- [ ] `academic_search` по запросу «transformer attention» возвращает смешанные результаты с полем provider (минимум 2 провайдера живые на проде).
- [ ] Один провайдер недоступен (мок/симуляция) — остальные работают, failed отражён в ответе.
- [ ] Тул `search_providers` в MCP и REST отдаёт полный список категорий/провайдеров.
- [ ] Веб: на странице настроек виден блок «Провайдеры поиска» (web/academic/video).
- [ ] Тесты: провайдеры (мок-ответы OpenAlex/S2: парсинг, inverted abstract), дедуп, агрегатор с упавшим провайдером, тул search_providers. Сервер + веб проверки зелёные, деплой, прод-проверка.

## Заметки
- OpenAlex без ключа ~100k/день — для нас бесконечно; S2 без ключа ~1 rps shared-pool — ретрай обязателен.
- Не добавлять ключи S2 в этой итерации (безключевой режим достаточно).
- UI-типы: web/src/lib/types.ts + npm run gen:api при изменении схем REST.
