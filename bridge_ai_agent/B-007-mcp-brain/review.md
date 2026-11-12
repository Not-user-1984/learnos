# B-007 · ревью

## Раунд 1 · 2026-11-12 · вердикт: done

Проверки по всей очереди (HEAD a6cea3b): ruff ✅ · format ✅ · lint-imports 7/7 ✅ · pytest 494 passed ✅ · web lint/tsc/build ✅ · alembic одна голова 0021.

- /mcp/brain, capture/context/get идемпотентны; save_note из внешнего MCP → inbox (ctx.channel=='mcp' по умолчанию в mcp_adapter), из веб-агента — confirmed как раньше.
- Принято: имена search_kb/add_source_kb (уникальность реестра). Прод-смоук tools/list — после деплоя.
