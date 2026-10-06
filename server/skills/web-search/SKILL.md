---
name: web-search
description: "Веб-поиск (прототип, DuckDuckGo). Возвращает топ результатов (title, url). Использовать для research_sources."
params:
  query:
    type: str
    desc: поисковый запрос
  limit:
    type: int
    optional: true
    default: 5
    desc: сколько результатов вернуть
version: 0.1
status: active
---

# web-search

Прототип поискового скилла: DuckDuckGo HTML → топ ссылок.
Позже: fallback-цепочка движков (Яндекс/Google/DDG/Bing), как в radmipa web-search.
