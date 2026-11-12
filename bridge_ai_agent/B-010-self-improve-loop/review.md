# B-010 · ревью

## Раунд 1 · 2026-11-12 · вердикт: done

Проверки по всей очереди (HEAD a6cea3b): ruff ✅ · format ✅ · lint-imports 7/7 ✅ · pytest 494 passed ✅ · web lint/tsc/build ✅ · alembic одна голова 0021.

- Планировщик (cron, лок, catch-up), repo_scout → create_task_file, /proposals (accept = push+PR, только agent/* по regex), review_digest; расписания по умолчанию выключены.
- Minor: push `git push origin agent/x` без refs/heads/ — при теге с тем же именем неоднозначно; наличие gh и прав на push на CT не проверено — проверить при первом accept.
