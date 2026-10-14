"""Реестр агентов приложения по имени; заполняется модулями в wire()."""

from .spec import AgentSpec


class AgentRegistry:
    """Все AgentSpec приложения; дубликат имени — ошибка старта."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> None:
        if spec.name in self._agents:
            raise ValueError(f"агент '{spec.name}' уже зарегистрирован")
        self._agents[spec.name] = spec

    def get(self, name: str) -> AgentSpec:
        spec = self._agents.get(name)
        if spec is None:
            raise KeyError(f"агент '{name}' не найден")
        return spec

    def all(self) -> list[AgentSpec]:
        return list(self._agents.values())
