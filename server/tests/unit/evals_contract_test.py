"""T-050 Э6: eval-сценарии валидны — yaml/поля/агенты/инструменты (ломается в CI)."""

from pathlib import Path

from scripts.run_evals import load_scenarios

EVALS = Path(__file__).resolve().parent.parent / "evals"
KNOWN_FIELDS = {"name", "agent", "user", "system_extra", "expect"}
EXPECT_FIELDS = {"tools_any", "tools_none", "cards_any", "text_contains", "text_not_contains"}


def test_scenarios_exist():
    assert len(list(EVALS.glob("*.yaml"))) >= 6, "меньше шести eval-сценариев — каркас пуст"


def test_scenario_fields_and_types(container):
    registry = container.agent_registry
    all_tools = {t.name for t in container.tools.all()}
    for scenario in load_scenarios():
        name = scenario.get("name", "?")
        assert set(scenario) <= KNOWN_FIELDS, f"{name}: неизвестные поля {set(scenario) - KNOWN_FIELDS}"
        assert scenario.get("name") and scenario.get("agent") and scenario.get("user"), f"{name}: пустые поля"
        # агент существует и это чат-агент (не structured-работник)
        spec = registry.get(scenario["agent"])
        assert spec.prompt_path is not None, f"{name}: агент {scenario['agent']} без промпта"
        # ожидания — известные инструменты
        exp = scenario.get("expect") or {}
        assert set(exp) <= EXPECT_FIELDS, f"{name}: неизвестные expect {set(exp) - EXPECT_FIELDS}"
        for key in ("tools_any", "tools_none"):
            unknown = set(exp.get(key) or []) - all_tools
            assert not unknown, f"{name}: {key} упоминает несуществующие {unknown}"
        for key in ("text_contains", "text_not_contains"):
            assert isinstance(exp.get(key, []), list), f"{name}: {key} не список"


def test_names_unique():
    names = [s["name"] for s in load_scenarios()]
    assert len(names) == len(set(names)), "имена сценариев дублируются"


def test_runner_importable():
    """Раннер живой модели не падает на импорте и видит сценарии."""
    assert load_scenarios(), "load_scenarios ничего не нашёл"
