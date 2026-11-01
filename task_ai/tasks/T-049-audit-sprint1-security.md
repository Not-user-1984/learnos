---
id: T-049
title: "Аудит 2026-11-01, спринт 1: безопасность (R-05, R-06, R-07, R-08)"
status: active
priority: high
from: внешний аудит [task_ai/reference/audit-2026-11-01.md](../reference/audit-2026-11-01.md), спринт 1
created: 2026-11-01
---

## Что нужно

Закрыть векторы атаки из аудита:

- **R-05 Субагент теряет карточки**: `_collect_subagent` игнорирует события `card` — карточки
  `git_change`/`prompt_change`/`note_draft`/`chapter_review` субагента не доходят до UI
  (ветка создана, а человеку не показана и не может быть одобрена). Фикс: собирать cards,
  возвращать `_cards: [...]` из run_agent, рантайм родителя эмитит card-события на каждую.
- **R-06 Песочница скиллов не изолирует**: subprocess наследует весь env (ZAI_API_KEY*,
  TAVILY/SERPER, токены), `LEARNOS_WRITE_DIR` = весь data_dir (включая learnos.db), `/repo:ro`
  открывает `.env` прода. Цепочка: web_read (недоверенный текст) → prompt injection → save_skill
  → чтение ключей и слив наружу. Фикс: env-whitelist для subprocess, WORK_DIR =
  `data/skill-work/<owner>/<skill>`, маскировка `.env`/`data` в /repo в compose, rlimit памяти.
- **R-07 Нет авторизации + CORS \***: любой в LAN и любая открытая веб-страница (DNS-rebinding)
  дергает /api и /mcp: удаление данных, connectivity-прокси, approve правок, run_checks (DoS).
  Фикс: опциональный bearer `LEARNOS_API_TOKEN` (middleware, 401 без токена; /api/health открыт),
  CORS из `LEARNOS_CORS_ORIGINS`; Next-прокси и серверные компоненты веба добавляют токен
  на сервере (браузер не видит); на проде токен включить и настроить.
- **R-08 SSRF обходится**: `research/service.py::_fetch` (web_read, extract_chapters) без
  проверки URL + `follow_redirects=True`; `POST /sources` kind=web → `_run_web` → `_fetch` мимо
  `_assert_public_http_url`. Фикс: единый `safe_fetch`/`assert_public_url` в kernel — резолв
  DNS один раз, проверка всех A/AAAA на приватность, ручной обход редиректов с проверкой
  каждого hop; использовать в research._fetch, library from_url/_run_web/_probe_pdf.

## Критерии готовности

- [ ] Тест: root → run_agent(специалист с карточкой) → в результате `_cards` содержит карточку,
      в SSE родителя есть card-событие
- [ ] Тест: агентский скилл не видит переменных окружения с ключами (ZAI_API_KEY → None),
      WORK_DIR указывает в skill-work/<owner>/<skill>
- [ ] На проде /repo/.env и /repo/data недоступны (маскировка в docker-compose)
- [ ] Тест: с заданным LEARNOS_API_TOKEN запрос без токена → 401 (кроме /api/health),
      с неверным → 401, с верным → 200
- [ ] Веб работает с включённым токеном (Next-прокси и SSR добавляют заголовок)
- [ ] Тест: web_read на http://127.0.0.1:8765, http://192.168.0.105:8006, metadata-адрес,
      редирект с публичного на приватный → отказ; на публичный URL → успех
- [ ] Прод CT 132 с включённым токеном: health ок, чат/библиотека работают, факт настройки
      зафиксирован (где лежит токен)

## Заметки

- Токен на прод: сгенерировать, положить в `/opt/learnos/.env` (server+web), `sec set` на маке
  для MCP-клиентов; в отчёте пользователю — как прописать в MCP-подключениях (Authorization: Bearer).
- «save_skill по подтверждению» и разделение lethal trifecta (агент с web_read без save_skill) —
  отдельное решение, вынесено в T-050 (архитектура прав).
- `/mcp` без опасных модулей по умолчанию — не делаем (токен закрывает доступ), отмечено в T-050.
