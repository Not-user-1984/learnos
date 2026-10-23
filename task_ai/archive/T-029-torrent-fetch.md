---
id: T-029
title: Скилл torrent-fetch + интеграция закачек в библиотеку
status: done
priority: high
from: спонтанная задача пользователя (2026-10-22)
created: 2026-10-22
closed: 2026-10-22
---

## Что нужно

«Поищи книгу/фильм/музыку» → Prowlarr ищет по трекерам → suggest (список кандидатов,
выбор) или auto (качать лучшего сразу) → qBittorrent качает → книги (категория
learnos-books) при завершении сами падают в библиотеку LearnOS (upload → process,
главы нарезаются).

Этапы:
1. Канонический скилл в `~/my_dev/radmipa-skills` (ветка curator/20261016):
   `skills/torrent-fetch/` — SKILL.md, run.py (CLI search/add/status/books),
   providers/{prowlarr,qbittorrent,libgen}.py, config.example.json. Реальный конфиг
   вне git (~/.config/torrent-fetch/config.json). Креды — с media-CT (Prowlarr
   config.xml, qBit qBittorrent.conf), без печати значений.
2. Вендор-копия в `server/skills/torrent-fetch/` + unit-тесты (MockTransport,
   без сети). Push-hook: qBit `exel_on_torrent_completed` → скрипт на media-CT →
   крупнейший PDF раздачи learnos-books → `/api/sources/upload` → `/process`.
3. (если успеется) Промпт research-режима: подсказка агенту про torrent_fetch.

## Критерии готовности

- [x] Скилл в radmipa-skills запушен в curator/20261016 (fa9fcc9)
- [x] Живые проверки: search книга/не-книга, suggest-таблица, add (libgen + торрент), status
- [x] Вендор-скилл в server/skills + 9 unit-тестов зелёные (799a455)
- [x] Hook на media-CT: завершение раздачи-книги → источник в библиотеке прода
- [x] E2E: add книги с мака → qBit → hook → библиотека прода (src_caeb226b, 21 глава нарезана)
- [x] Деплой (3a16ba9), health ok, доки обновлены

## Заметки

- Prowlarr: http://192.168.0.131:9696 (ключ в /opt/media/config/prowlarr/config.xml)
- qBit: http://192.168.0.131:8080, WebUI API-key qbt_... (qBittorrent.conf) — Bearer-аутентификация
- libgen: живое зеркало libgen.li через socks5://192.168.0.10:1080 (vpn-gw); в vendored-копии выключен
- qBit на add повторной раздачи отвечает 202 — считать дубликатом, не ошибкой
- Внутри контейнера qBit смонтированы /scripts (CT /opt/media/scripts) и /downloads (CT /media/downloads)
- pve.py exec ломает кавычки (fish на proxmox-host): сложные команды — скриптом через push + bash
