"""Скриптовая песочница агентов: save_skill → вызов → правка, отказы, живой подхват в чате (T-037)."""

from app.kernel.tools.spec import ToolContext
from app.llm.providers.fake import FakeLLMProvider, FakeTurn
from app.llm.types import ToolCall
from tests.api.test_sse import parse_sse

SKILL_MD = """---
name: {name}
description: тестовый скилл приветствия
params:
  name:
    type: str
    optional: true
    default: мир
    desc: кого приветствовать
version: 0.1
---
"""

RUN_PY = """\
import os


def main(name="мир", **_):
    out = os.path.join(os.environ["LEARNOS_WRITE_DIR"], "greet.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(name)
    print("пишу файл")
    return {"ok": True, "greeting": f"Привет, {name}!", "wrote": out}
"""

RUN_PY_V2 = "def main(name='мир', **_):\n    return {'ok': True, 'greeting': f'Салют, {name}!'}\n"


def _agent(name: str) -> ToolContext:
    return ToolContext(channel="agent", agent_name=name)


def _save(container, owner: str, name: str, run_py: str = RUN_PY, skill_md: str | None = None) -> dict:
    return container.tools.call(
        "save_skill",
        {"skill_name": name, "skill_md": (skill_md or SKILL_MD).format(name=name), "run_py": run_py},
        _agent(owner),
    )


def test_save_run_and_hot_edit_lifecycle(container):
    """Агент сохраняет скилл → вызывает новым инструментом → правит → видит новую версию."""
    out = _save(container, "root", "greeter")
    assert out["ok"], out
    assert container.tools.has("greeter")  # инструмент зарегистрирован живьём
    assert "greeter" in container.agent_registry.get("root").tools  # и выдан владельцу

    result = container.tools.call("greeter", {"name": "Дмитрий"}, _agent("root"))
    assert result["ok"] is True
    assert result["greeting"] == "Привет, Дмитрий!"
    assert "пишу файл" in result["stdout"]
    assert (container.settings.data_dir / "greet.txt").read_text(encoding="utf-8") == "Дмитрий"

    # правка скрипта подхватывается повторным save_skill — без рестарта
    edited = _save(container, "root", "greeter", run_py=RUN_PY_V2)
    assert edited["ok"], edited
    again = container.tools.call("greeter", {"name": "Дмитрий"}, _agent("root"))
    assert again["greeting"] == "Салют, Дмитрий!"
    assert "wrote" not in again  # новый код, не кэш

    # файлы на диске в рантайм-области агента
    skill_dir = container.settings.data_dir / "agent-skills" / "root" / "greeter"
    assert (skill_dir / "run.py").read_text(encoding="utf-8") == RUN_PY_V2


def test_timeout_skill_killed_server_alive(container):
    """Скрипт с вечным сном убивается таймаутом; реестр инструментов продолжает работать."""
    sleeper = "import time\n\n\ndef main(**_):\n    time.sleep(30)\n    return {'ok': True}\n"
    assert _save(container, "root", "sleeper", run_py=sleeper)["ok"]
    container.settings.skill_exec_timeout = 2  # живая настройка, читается при каждом запуске

    result = container.tools.call("sleeper", {}, _agent("root"))
    assert result["error"] == "skill_timeout"

    alive = container.tools.call("list_skills", {}, ToolContext(channel="mcp"))  # сервер жив
    assert "sleeper" in {s["name"] for s in alive}


def test_save_rejections(container):
    """Отказы: builtin-имя, занятый инструмент, чужой скилл, кривой name/frontmatter, MCP-канал."""
    cases = [
        # (skill_name, run_py, name в frontmatter (None — как skill_name), ожидаемый error-код)
        ("web-search", RUN_PY, None, "conflict"),  # builtin
        ("search", RUN_PY, None, "conflict"),  # существующий инструмент
        ("Bad-Name", RUN_PY, None, "validation_failed"),
        ("greeter_x", RUN_PY, "other_name", "validation_failed"),  # frontmatter name не совпал
        ("greeter_e", "   ", None, "validation_failed"),  # пустой run.py
    ]
    for skill_name, run_py, md_name, code in cases:
        out = container.tools.call(
            "save_skill",
            {
                "skill_name": skill_name,
                "skill_md": SKILL_MD.format(name=md_name or skill_name),
                "run_py": run_py,
            },
            _agent("root"),
        )
        assert out.get("error") == code, (skill_name, out)

    # из MCP (без агента) сохранять нельзя
    mcp = container.tools.call(
        "save_skill",
        {"skill_name": "greeter_m", "skill_md": SKILL_MD, "run_py": RUN_PY},
        ToolContext(channel="mcp"),
    )
    assert mcp["error"] == "validation_failed"

    # скилл другого агента с тем же именем — конфликт
    assert _save(container, "repo_scout", "shared")["ok"]
    clash = _save(container, "free_chat", "shared")
    assert clash["error"] == "conflict"
    assert "repo_scout" in clash["message"]


def test_skill_ownership_enforced(container):
    """Чужой агентский скилл не вызывается ни инструментом, ни run_skill; root может всё."""
    assert _save(container, "repo_scout", "parser")["ok"]

    stranger = container.tools.call("parser", {}, _agent("free_chat"))
    assert stranger["error"] == "not_allowed"
    via_run_skill = container.tools.call("run_skill", {"name": "parser", "kwargs": {}}, _agent("free_chat"))
    assert via_run_skill["error"] == "not_allowed"

    assert container.tools.call("parser", {}, _agent("repo_scout"))["ok"] is True
    assert container.tools.call("parser", {}, _agent("root"))["ok"] is True
    # скилл выдан только владельцу и root, не всем агентам
    assert "parser" in container.agent_registry.get("repo_scout").tools
    assert "parser" in container.agent_registry.get("root").tools
    assert "parser" not in container.agent_registry.get("free_chat").tools


def test_root_saves_and_calls_skill_in_same_chat(client, fake_llm, container):
    """SSE: root сохраняет скилл и вызывает его в том же ответе — живой подхват инструмента."""
    fake_llm.queue(
        FakeTurn(
            tool_calls=[
                FakeLLMProvider.call(
                    "save_skill",
                    skill_name="greeter",
                    skill_md=SKILL_MD.format(name="greeter"),
                    run_py=RUN_PY,
                )
            ]
        ),
        FakeTurn(tool_calls=[ToolCall(id="call_greeter", name="greeter", arguments={"name": "Дмитрий"})]),
        FakeTurn(text="Скилл готов и проверен."),
        FakeTurn(text="скилл в деле"),
    )
    conv = client.post("/api/conversations", json={}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "сделай мне приветчик"}
    ) as resp:
        raw = "".join(resp.iter_text())

    events = parse_sse(raw)
    assert [name for name, _ in events][-1] == "done"
    ends = {d["name"]: d for name, d in events if name == "tool_end"}
    assert ends["save_skill"]["ok"] is True
    assert ends["greeter"]["ok"] is True  # не unknown_tool — hot reload сработал внутри запуска
    assert (container.settings.data_dir / "greet.txt").exists()
