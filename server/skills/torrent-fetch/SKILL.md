---
name: torrent_fetch
description: "Поиск и загрузка книг/фильмов/музыки через Prowlarr (агрегатор трекеров) + qBittorrent. Режим suggest: таблица кандидатов → выбор номера; режим auto: лучший по сидам качается сразу. Книги качаются с категорией learnos-books и при завершении автоматически попадают в библиотеку LearnOS. Триггеры: «поищи книгу», «скачай фильм», «найди раздачу», «что с закачкой»."
version: 0.1
status: active
created: 2026-10-22
params:
  action:
    type: str
    desc: "search (поиск+кандидаты), add (добавить по номеру/hash/magnet), status (список торрентов), books (поиск книг)"
  query:
    type: str
    optional: true
    desc: поисковый запрос (для search/books)
  title:
    type: str
    optional: true
    desc: alias запроса для books
  num:
    type: int
    optional: true
    desc: номер кандидата из последнего поиска (для add)
  cat:
    type: str
    optional: true
    default: books
    desc: "категория: books | movies | music | tv"
  auto:
    type: bool
    optional: true
    default: false
    desc: не спрашивать, качать лучшего сразу
  magnet:
    type: str
    optional: true
    desc: magnet-ссылка или info-hash (для add напрямую)
  limit:
    type: int
    optional: true
    default: 20
    desc: сколько кандидатов показывать
---

# torrent-fetch (vendored): «поищи книгу/фильм» → Prowlarr → qBittorrent → библиотека

Копия канонического скилла `radmipa-skills/skills/torrent-fetch` (живые правки —
там; сюда переносится целиком). Скачивание книг идёт через qBit с категорией
`learnos-books`: по завершении раздачи hook на media-CT заливает PDF в
`/api/sources/upload` и запускает нарезку глав.

## Вызовы (MCP: run_skill / torrent_fetch)

```
search  {query: "Пелевин", cat: "books"}                  → candidates + table, потом add {num: N}
search  {query: "Dune 2021", cat: "movies", auto: true}   → качает лучшего сразу
books   {query: "Fluent Python"}                          → то же для книг
add     {num: 3} | {magnet: "magnet:?..."}                → qBit
status  {}                                                → раздачи с прогрессом
```

## Конфиг

Вне git: `data/torrent-fetch.json` (каталог данных LearnOS; на проде — volume
/data). Цепочка поиска: env `TORRENT_FETCH_CONFIG` → `config.json` рядом со
скиллом → `{LEARNOS_DATA_DIR}/torrent-fetch.json` → `~/.config/torrent-fetch/config.json`.
Образец с плейсхолдерами — `config.example.json`.

- Prowlarr/qBit: URL-ы media-CT и api-ключи (Prowlarr ApiKey; qBit — WebUI
  API-key `qbt_...`, либо username/password).
- libgen на сервере выключен (`libgen.enabled=false`): файл libgen попадает в
  контейнер, а не в библиотеку; основной путь книг — торрент + hook.
- Кэш последнего поиска (`last_search.json`) живёт рядом с конфигом.

## Логика выбора (auto)

Книги — максимум сидов; категория `learnos-books`. Прочее — лучший по сидам,
без категории.

## Куда смотреть при проблемах

| Симптом | Причина |
|---|---|
| prowlarr 401 | сменился ApiKey — перечитать config.xml Prowlarr на media-CT |
| qbit 403 | Bearer-ключ отозван — перечитать qBittorrent.conf |
| книга скачалась, в библиотеке нет | лог hook: /var/log/learnos-qbit-hook.log на media-CT |
