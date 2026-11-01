"""R-14: чужой Jinja-синтаксис в промпте (Helm/docker --format) не роняет агента."""

from pydantic import BaseModel

from app.agent.runtime import safe_render, validate_prompt
from app.agent.spec import AgentContext, AgentSpec
from app.kernel.tools.registry import ToolRegistry
from tests.agent.test_subagents import ListRecorder


class _Args(BaseModel):
    pass


def test_helm_template_in_prompt_does_not_crash_render():
    """{{ .Values.x }} (Helm) — UndefinedError раньше, теперь текст живёт как есть."""
    text = "Разверни чарт:\n```yaml\nreplicas: {{ .Values.replicaCount }}\n```"
    out = safe_render(text, {"profile": "mac"})
    assert ".Values.replicaCount" in out  # контент сохранён


def test_docker_format_in_prompt_survives():
    text = "docker ps --format '{{.Names}} {{.Status}}'"
    out = safe_render(text, {})
    assert "{{.Names}}" in out


def test_fallback_substitutes_known_variables():
    """Фолбэк точечно подставляет известные переменные, остальной jinja не трогает."""
    text = "профиль: {{ profile }}\nшаблон: {{ .Values.x }}"
    out = safe_render(text, {"profile": "mac + pve"})
    assert "профиль: mac + pve" in out
    assert "{{ .Values.x }}" in out


def test_normal_render_unchanged():
    assert safe_render("Привет, {{ name }}!", {"name": "Дима"}) == "Привет, Дима!"


def test_validate_prompt_warns_on_broken_syntax():
    """Битый Jinja — предупреждение (сохраняется, рендер уйдёт фолбэком)."""
    warning = validate_prompt("текст {% if x } незакрытый тег")
    assert warning and "Jinja" in warning


def test_validate_prompt_clean_text_no_warning():
    assert validate_prompt("чистый текст промпта") is None


def test_validate_prompt_foreign_syntax_warns_but_not_blocks():
    """Helm-синтаксис — предупреждение, не блокировка (фолбэк его спасает)."""
    warning = validate_prompt("{{ some_var }} и {{ .Values }}")
    assert warning  # знаем о фолбэке, но агент работать будет


def test_custom_agent_prompt_rendered_via_safe_path(tmp_path):
    """Кастомный агент с Docker-шаблоном в промпте проходит полный ран (R-14)."""
    import asyncio

    from app.agent.registry import AgentRegistry
    from app.agent.runtime import AgentRuntime
    from app.llm.providers.fake import FakeLLMProvider, FakeTurn
    from app.llm.router import LLMConfig, ModelRouter
    from app.llm.types import Message

    registry = AgentRegistry()
    registry.register(
        AgentSpec(
            name="devops_helper",
            description="тест",
            prompt_text="Смотри вывод docker ps --format '{{.Names}}' и объясняй.",
            tools=frozenset(),
            max_steps=4,
        )
    )
    fake = FakeLLMProvider()
    fake.queue(FakeTurn(text="готово"))
    runtime = AgentRuntime(
        ModelRouter(LLMConfig(providers={}, roles={}), force_provider=fake),
        ToolRegistry(),
        ListRecorder(),
    )

    async def run() -> list:
        return [
            ev
            async for ev in runtime.run(
                registry.get("devops_helper"), AgentContext(), [Message(role="user", content="го")]
            )
        ]

    events = asyncio.run(run())
    assert events[-1].type == "final"
