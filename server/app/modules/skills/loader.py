"""Загрузчик drop-in скиллов: SKILL.md (frontmatter) + run.py с функцией main."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, create_model

from ...kernel.tools.spec import ToolContext, ToolSpec

_TYPES = {
    "str": (str, ...),
    "string": (str, ...),
    "int": (int, ...),
    "float": (float, ...),
    "bool": (bool, ...),
}


def _parse_frontmatter(text: str) -> dict:
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md: нет блока frontmatter")
    meta = yaml.safe_load(parts[1]) or {}
    if isinstance(meta.get("params"), str):
        meta["params"] = json.loads(meta["params"])
    return meta


def _load_entry(skill_dir: Path):
    spec = importlib.util.spec_from_file_location(f"skill_{skill_dir.name}", skill_dir / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.main


class SkillLoader:
    """Читает server/skills/<name>/SKILL.md и превращает скилл в ToolSpec."""

    def __init__(self, settings) -> None:
        self._skills_dir = Path(settings.skills_dir)
        self._registry: dict[str, dict[str, Any]] = {}

    def load(self) -> dict[str, dict[str, Any]]:
        """Перечитать скиллы с диска (вызывается на старте)."""
        self._registry.clear()
        for skill_md in sorted(self._skills_dir.glob("*/SKILL.md")):
            meta = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            name = meta.get("name", skill_md.parent.name)
            self._registry[name] = {
                "name": name,
                "description": meta.get("description", ""),
                "params": meta.get("params") or {},
                "entry": _load_entry(skill_md.parent),
            }
        return self._registry

    def info(self) -> list[dict[str, Any]]:
        """Список скиллов с параметрами (для list_skills)."""
        if not self._registry:
            self.load()
        return [
            {"name": s["name"], "description": s["description"], "params": s["params"]}
            for s in self._registry.values()
        ]

    def run(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Выполнить скилл по имени."""
        if not self._registry:
            self.load()
        skill = self._registry.get(name)
        if skill is None:
            return {
                "error": "skill_not_found",
                "message": f"скилл '{name}' не найден",
                "available": sorted(self._registry),
            }
        try:
            result = skill["entry"](**kwargs)
        except TypeError as e:
            return {
                "error": "validation_failed",
                "message": f"неверные аргументы: {e}",
                "params": skill["params"],
            }
        return result if isinstance(result, dict) else {"ok": True, "result": result}

    def tool_specs(self) -> list[ToolSpec]:
        """Спецификации: run_skill + авто-скиллы как отдельные инструменты."""
        if not self._registry:
            self.load()

        def run_skill(args: RunSkillArgs, ctx: ToolContext) -> dict[str, Any]:
            del ctx
            return self.run(args.name, args.kwargs)

        def list_skills(args: _EmptyArgs, ctx: ToolContext) -> list[dict[str, Any]]:
            del ctx
            return self.info()

        specs = [
            ToolSpec(
                name="run_skill",
                module="skills",
                description="Выполнить drop-in скилл. kwargs — аргументы согласно list_skills.",
                args_model=RunSkillArgs,
                handler=run_skill,
                label="Скилл",
            ),
            ToolSpec(
                name="list_skills",
                module="skills",
                description="Доступные drop-in скиллы и их параметры.",
                args_model=_EmptyArgs,
                handler=list_skills,
                label="Список скиллов",
            ),
        ]
        for name, skill in self._registry.items():
            specs.append(self._skill_spec(name, skill))
        return specs

    def _skill_spec(self, name: str, skill: dict[str, Any]) -> ToolSpec:
        fields: dict[str, Any] = {}
        for pname, p in skill["params"].items():
            ann, default = _TYPES.get(str(p.get("type", "str")), (str, ...))
            if p.get("optional"):
                # optional без дефолта получает None: аннотация X | None, чтобы MCP-клиент
                # мог не передавать поле вовсе (иначе null ломает pydantic-валидацию)
                default = p.get("default")
                ann = ann | None
            fields[pname] = (ann, default)
        model = create_model(f"{name}_args", **fields) if fields else _EmptyArgs

        def handler(args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
            del ctx
            # None-параметры не доходят до run.py: скиллы ждут дефолты («»), а не None
            return self.run(name, {k: v for k, v in args.model_dump().items() if v is not None})

        params_brief = ", ".join(
            f"{p}:{p_['type']}" + ("?" if p_.get("optional") else "") for p, p_ in skill["params"].items()
        )
        return ToolSpec(
            name=name,
            module="skills",
            description=f"{skill['description']} Параметры: {params_brief or '—'}",
            args_model=model,
            handler=handler,
            label=f"Скилл {name}",
        )


class RunSkillArgs(BaseModel):
    """Аргументы run_skill."""

    name: str
    kwargs: dict[str, Any] = {}


class _EmptyArgs(BaseModel):
    """Скилл без параметров."""
