"""Реестр агентов приложения по имени; заполняется модулями в wire()."""

from .spec import AgentSpec


class AgentRegistry:
    """Все AgentSpec приложения; дубликат builtin-имени — ошибка старта.

    Кастомные агенты (из UI) регистрируются поверх через upsert_custom и
    снимаются remove_custom — без рестарта процесса.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}
        self._builtin: set[str] = set()

    def register(self, spec: AgentSpec) -> None:
        if spec.name in self._agents:
            raise ValueError(f"агент '{spec.name}' уже зарегистрирован")
        self._agents[spec.name] = spec
        self._builtin.add(spec.name)

    def upsert_custom(self, spec: AgentSpec) -> None:
        """Добавить/обновить кастомного агента (имя не должно конфликтовать с builtin)."""
        if spec.name in self._builtin:
            raise ValueError(f"имя '{spec.name}' занято встроенным агентом")
        self._agents[spec.name] = spec

    def remove_custom(self, name: str) -> None:
        """Снять кастомного агента; builtin удалить нельзя."""
        if name in self._builtin:
            raise ValueError(f"встроенный агент '{name}' удалить нельзя")
        self._agents.pop(name, None)

    def is_builtin(self, name: str) -> bool:
        return name in self._builtin

    def get(self, name: str) -> AgentSpec:
        spec = self._agents.get(name)
        if spec is None:
            raise KeyError(f"агент '{name}' не найден")
        return spec

    def all(self) -> list[AgentSpec]:
        return list(self._agents.values())
