"""Агент mcp_designer: разбирает ссылку/файл/описание в конфиг внешнего MCP."""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class McpDesignerOut(BaseModel):
    """Выход конструктора MCP-подключений."""

    name: str = Field(max_length=40)
    url: str = Field(max_length=500)
    description: str = Field(default="", max_length=200)
    headers: dict[str, str] = Field(default_factory=dict)
    summary: str = Field(default="", max_length=300)


mcp_designer = AgentSpec(
    name="mcp_designer",
    description="Конструктор MCP-подключений: ссылка/файл/описание → конфиг внешнего сервера.",
    prompt_path=AGENTS_DIR / "mcp_designer" / "prompt.md",
    model_role="chat",
    tools=frozenset(),
    output_model=McpDesignerOut,
)


def valid_mcp_name(name: str) -> bool:
    return bool(NAME_RE.match(name)) and ":" not in name


def register_agents(c) -> None:
    registry: AgentRegistry = c.agent_registry
    registry.register(mcp_designer)
