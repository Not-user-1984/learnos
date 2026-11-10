---
id: T-057
title: Роли и провайдеры LLM из UI (этап 10-B)
status: idea
priority: medium
from: ТЗ этап 10-B ([stages/10-settings-and-cloud.md](../stages/10-settings-and-cloud.md), части A и B) / BB-003, BB-004
created: 2026-11-10
---

## Что нужно

Полный этап 10-B: управление ролями и провайдерами LLM из веб-интерфейса без правки
`llm.yaml` и рестартов. Сейчас (после T-056) конфигурация — только файл
`server/config/llm.yaml` + env-ключи, просмотр — блок «LLM» в настройках и
`GET /api/llm/status` (read-only).

Опора на сделанное в T-056 (BB-003/004/005):

- per-role `params` уже прокидываются: RoleBinding.params → `resolve()` →
  `LLMRequest.extra_params` → wire-запрос (адаптер openai_compat нормализует
  `thinking`-шорткат, дропает параметр после bad_request без зацикливания);
- `ModelRouter.detailed_status()` — роли/провайдеры/цепочки ключей (без значений);
- `OpenAICompatProvider.keychain_status()/reset_cooldown()`;
- тул `llm_status` (root-агент, `reset_cooldown: true`);
- пресеты провайдеров (OpenRouter/OpenAI/DeepSeek) закомментированы в llm.yaml.

По ТЗ 10-B нужно добавить:

1. **Часть A — SecretStore** (`kernel/secrets.py`): `EncryptedSecretStore`
   (таблица secrets, Fernet, мастер-ключ `LEARNOS_MASTER_KEY`), приоритет env > store,
   API без значений (`{name, is_set, last4, source}`), маскировка в логах.
2. **Рабочая конфигурация в БД**: `llm_providers(...)` + `llm_roles(role, provider,
   model, params_json)`; llm.yaml — seed. `ModelRouter` перечитывает по событию
   `LLMConfigChanged` без рестарта.
3. **UI-редактор**: карточки провайдеров (ключ ••••last4, «Проверить»), таблица ролей
   (провайдер/модель/params, кнопка проверки коротким запросом); база — текущий блок
   «LLM» в настройках (`web/src/components/settings/llm-settings.tsx`).
4. **Hot reload**: смена роли подхватывается живыми агентами (проверка по agent_runs).
5. Опционально роли `stt`/`embed` из ТЗ — по мере появления потребителей.

## Критерии готовности

- [ ] секрет из UI не находится grep'ом по БД/логам/ответам API
- [ ] в UI добавлен второй провайдер (например OpenRouter), роль `fast` переключена на
      него — summary глав идут через него без рестарта (видно в `agent_runs`)
- [ ] тесты: шифрование/приоритет env/маскировка, перечитывание конфига роутером

## Заметки

—
