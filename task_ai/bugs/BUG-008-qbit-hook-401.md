# BUG-008 — hook заливки книг получал 401 от API LearnOS

**Статус:** fixed (infra, вне репо learnos) · найдено 2026-11-03 · свидетельство: торрент-книга «Радченко 1С:Предприятие 8.3» докачалась, но в библиотеку не попала; агент не видел результата и перебирал адреса qBit вслепую

## Корень

Hook на media-CT (`/opt/media/scripts/learnos-qbit-hook.sh`) POST-ит PDF в
`/api/sources/upload` с `Authorization: Bearer …`. После включения bearer-токена
(R-07, T-049) hook продолжал ходить без него — API отдавал 401, книги терялись
между qBit и библиотекой.

## Чинить

Bearer в запросе hook'а — infra-правка на media-CT, вне репо learnos
(коммит proxmox `067d2bc`). В репо сделан компенсирующий слой (T-053):
`duplicate` на qBit 409/202, действие `import` у torrent_fetch как fallback
hook'а руками.

## Связи

- [T-053](../archive/2026-11-04-T-053-incident-torrent-bookfix.md) — import/auto/409 в torrent-fetch
