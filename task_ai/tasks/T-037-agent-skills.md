---
id: T-037
title: Скриптовая песочница: агентские скиллы в data/agent-skills
status: review   # ждёт ревью ZCode (ветка t-034-orchestrator)
priority: high
from: T-034 (этап C)
created: 2026-10-28
---

## Что нужно

Главная фишка Harness: каждый агент может создавать и править **свои** скрипты
под задачу (парсеры, обработчики) и выполнять их. Работаем в ветке
`t-034-orchestrator` (см. T-034).

1. **Директория агентских скиллов** `data/agent-skills/<agent>/<skill>/`:
   `SKILL.md` (frontmatter: name, description, params) + `run.py` (`main(**kwargs)`).
   Обобщить `SkillLoader` (`modules/skills/loader.py`): помимо `server/skills/`
   (builtin) сканирует `data/agent-skills/`; владелец = имя агента из пути;
   скилл регистрируется как инструмент владельцу (и root-агенту — каталог).
   Имена не конфликтуют с builtin (DuplicateTool уже ловит).
2. **Исполнение run.py — subprocess с изоляцией**: отдельный процесс
   (`sys.executable`), таймаут (например 120 с), cwd = `data/agent-skills/<agent>/`,
   запись — только внутри `data/` (передавать разрешённые пути переменными
   окружения/аргументами; run.py — договорённость «пиши только в свои пути»,
   контейнер уже изолирует прод); stdout/stderr/код выхода — в результат
   инструмента (обрезка как у ToolRegistry).
3. **Инструменты создания/правки** (для root и владельца):
   - `save_skill(skill_name, skill_md, run_py, ...)` — создать/обновить **свой**
     скилл (только свой агент, только `data/agent-skills/<self>/`);
   - правка builtin-скилла и чужих скиллов — запрещена на уровне инструмента
     (внятная ошибка, предложение пойти через `propose_change`).
4. **`propose_change`** — обобщение `propose_prompt_change` (tuning): типы
   `prompt | skill | script`; карточка с диффом, применение — кнопкой человека,
   бэкап + откат по паттерну `data/prompt_backups`. Builtin-промпты и builtin-скиллы
   правятся только так; свои скиллы — свободно.
5. **Горячая перезагрузка**: после save_skill скилл сразу доступен (пере-скан
   loader'а) — без рестарта сервиса.

## Критерии готовности

- [x] Интеграционный тест: агент создаёт скилл (save_skill) → вызывает его
      (run_skill) → скрипт пишет файл в свою область → результат в инструменте;
      повторный вызов после правки скрипта видит новую версию.
- [x] Тест: скрипт с таймаутом-сном убивается, агент получает ошибку, сервер жив.
- [x] Тест: попытка сохранить скилл вне своей директории / править builtin —
      отвергается.
- [x] `propose_change` для builtin-скилла создаёт карточку; применение пишет
      бэкап, откат работает.
- [x] Проверки зелёные; коммиты в ветке; после готовности — «ждёт ревью ZCode».

## Заметки

- Безопасность прод-изоляцией: сервис в Docker на CT, `data/` — volume;
  subprocess наследует права процесса, но договорённость путей + таймаут +
  контейнер дают достаточный уровень для персональной системы.
- run.py может ходить в сеть (парсеры) — это фича, не баг; лимит — таймаут.

## Заметки реализации (2026-10-28, ждёт ревью ZCode)

**Что/где:**

- `server/app/modules/skills/loader.py` — SkillLoader сканирует builtin
  (`server/skills`, in-process, override из `data/skill-overrides/<name>/`) и
  агентские (`data/agent-skills/<agent>/<skill>/`, subprocess: `sys.executable -c`
  раннер, cwd = каталог скилла, `LEARNOS_SKILL_ARGS`/`LEARNOS_SKILL_RESULT`/
  `LEARNOS_WRITE_DIR`, таймаут `settings.skill_exec_timeout` (120 с, читается
  при каждом запуске), stdout/stderr/exit_code в результате с обрезкой).
  Владение: run_skill и прямой инструмент пускают только владельца и root.
- `server/app/modules/skills/service.py` + `tools.py` — SkillsService.save_skill
  (валидация имени/frontmatter/конфликтов: builtin и занятые имена — Conflict с
  подсказкой про propose_change) + reload(): живой рескан и синхронизация
  ToolRegistry и AgentRegistry. Инструмент `save_skill` (только agent-канал,
  владелец = ctx.agent_name).
- `server/app/agent/registry.py` — `extend_tools` (горячее расширение набора
  инструментов агента); `runtime.py` — live-spec на каждом шаге: скилл,
  сохранённый в текущем запуске, сразу виден и вызываем (покрыто SSE-тестом).
- `server/app/modules/tuning/` — `propose_change(kind: prompt|skill, target,
  file, ...)`; prompt_changes + колонки kind/file (миграция 0010); применение
  скилл-правки: бэкап `data/prompt_backups/skill_<name>/` + override
  `data/skill-overrides/` + живой reload; откат — `POST /api/tuning/skills/{name}/reset`.
  Карточка переиспользует тип `prompt_change` (+kind/file): минимальная правка
  `web/src/components/chat/cards.tsx` и `types.ts` (заголовок «Правка скилла»).
- Промпты: root — раздел «Свои скиллы»; prompt_tuner переведён на propose_change
  (propose_prompt_change сохранён как MCP-стабильный псевдоним).
- Тесты: `tests/unit/agent_skills_test.py`, `tests/api/test_agent_skills.py`
  (lifecycle, таймаут, отказы, ownership, SSE-подхват в том же ответе),
  `tests/api/test_tuning.py` (карточка+бэкап+откат, отказы для агентских скиллов).

**Осознанные решения:**

- Конфликт имени агентского скилла с builtin/инструментом при СКАНЕ диска не
  роняет старт (warning + пропуск) — иначе битый каталог в data блокировал бы
  весь сервис; при save_skill конфликт даёт внятную ошибку заранее.
- Builtin-скиллы исполняются in-process как раньше (доверенный код продукта);
  subprocess-песочница — только для агентских.
- Свой скилл агент правит свободно повторным save_skill (владелец совпадает);
  чужой скилл с тем же именем — Conflict.
- Кастомные агенты получают свои скиллы при регистрации (TuningService) и при
  любом reload; правки builtin-скиллов — только карточкой.
- Дока (README/ARCHITECTURE) — после мерджа и деплоя, по воркфлоу эпика.

**Коммиты:** `cec5b70` (код + тесты) и `1941f15` (статус задачи); ветка `t-034-orchestrator`, запушена.
