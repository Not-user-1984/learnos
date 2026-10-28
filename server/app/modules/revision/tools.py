"""Инструменты ревизии (T-038): чтение репо, задачи, подготовка веток, проверки."""

from typing import Literal

from pydantic import BaseModel, Field

from ...kernel.tools.spec import ToolContext, ToolSpec


class RepoListArgs(BaseModel):
    """Аргументы листинга дерева."""

    path: str = Field(default="", description="Подкаталог от корня репо (пусто — корень)")


class RepoReadArgs(BaseModel):
    """Аргументы чтения файла."""

    path: str = Field(description="Путь файла от корня репо, например server/app/main.py")
    max_chars: int = Field(default=20000, ge=0, le=100000, description="Лимит символов")


class CreateTaskFileArgs(BaseModel):
    """Аргументы создания задачи."""

    title: str = Field(min_length=3, description="Короткое название (одной строкой)")
    body: str = Field(min_length=10, description="Что нужно: проблема, контекст, ожидание")


class GitFileIn(BaseModel):
    """Файл правки для ветки агента."""

    path: str = Field(description="Путь от корня репо (вне guard-листа)")
    content: str = Field(description="Полное новое содержимое файла")


class GitPrepareChangeArgs(BaseModel):
    """Аргументы подготовки ветки."""

    branch: str = Field(description="Ветка вида agent/<имя> — латиница/цифры/._-")
    files: list[GitFileIn] = Field(min_length=1, description="Файлы правки (полное содержимое)")
    commit_message: str = Field(min_length=3, description="Сообщение коммита: что и почему")


class RunChecksArgs(BaseModel):
    """Аргументы проверок."""

    scope: Literal["server"] = "server"
    branch: str | None = Field(default=None, description="Ветка agent/* — проверки в её worktree")


def revision_tools(c) -> list[ToolSpec]:
    """Инструменты агента-аудитора; guard и бюджет — внутри сервиса."""
    svc = c.revision

    def repo_list(args: RepoListArgs, ctx: ToolContext) -> dict:
        del ctx
        return svc.repo_list(args.path)

    def repo_read(args: RepoReadArgs, ctx: ToolContext) -> dict:
        del ctx
        return svc.repo_read(args.path, args.max_chars)

    def create_task_file(args: CreateTaskFileArgs, ctx: ToolContext) -> dict:
        return svc.create_task_file(args.title, args.body, ctx.agent_name or "")

    def git_prepare_change(args: GitPrepareChangeArgs, ctx: ToolContext) -> dict:
        return svc.git_prepare_change(
            args.branch,
            [f.model_dump() for f in args.files],
            args.commit_message,
            ctx.agent_name or "",
        )

    def run_checks(args: RunChecksArgs, ctx: ToolContext) -> dict:
        del ctx
        return svc.run_checks(args.branch)

    return [
        ToolSpec(
            name="repo_list",
            module="revision",
            description=(
                "Дерево каталогов репозитория LearnOS (без data/, kb/, кэшей). Стартовая точка аудита."
            ),
            args_model=RepoListArgs,
            handler=repo_list,
            label="Дерево репо",
        ),
        ToolSpec(
            name="repo_read",
            module="revision",
            description="Прочитать текстовый файл репозитория (только чтение, лимит 2 МБ).",
            args_model=RepoReadArgs,
            handler=repo_read,
            label=lambda a: f"Читаю {str(a.get('path', '?'))}",
        ),
        ToolSpec(
            name="create_task_file",
            module="revision",
            description=(
                "Создать задачу в task_ai/tasks/ по шаблону проекта (статус idea, следующий "
                "свободный номер). Только создание — существующие файлы не перезаписываются."
            ),
            args_model=CreateTaskFileArgs,
            handler=create_task_file,
            label="Задача из аудита",
        ),
        ToolSpec(
            name="git_prepare_change",
            module="revision",
            description=(
                "Подготовить правку веткой agent/<имя> в git worktree и закоммитить — только "
                "после зелёных проверок (ruff+format+lint-imports+pytest по server); main не "
                "затрагивается, пуша нет, применение — за человеком. Пути из guard-листа "
                "(bootstrap/main/alembic/llm/compose/web/task_ai/deploy/сам модуль revision) "
                "запрещены — для них create_task_file. Не более 3 веток в день."
            ),
            args_model=GitPrepareChangeArgs,
            handler=git_prepare_change,
            label=lambda a: f"Ветка {str(a.get('branch', '?'))}",
        ),
        ToolSpec(
            name="run_checks",
            module="revision",
            description=(
                "Прогнать проверки сервера (ruff, ruff format, lint-imports, pytest) в рабочей "
                "копии или worktree ветки agent/*. Возвращает коды выхода и хвосты логов."
            ),
            args_model=RunChecksArgs,
            handler=run_checks,
            label="Проверки server",
        ),
    ]
