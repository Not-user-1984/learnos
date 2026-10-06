import importlib.util
import json

import yaml

from .paths import SKILLS_DIR

_REGISTRY: dict[str, dict] = {}

_TYPES = {"str": "str", "string": "str", "int": "int", "float": "float", "bool": "bool"}


def _parse_frontmatter(text: str) -> dict:
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md: no frontmatter block")
    meta = yaml.safe_load(parts[1]) or {}
    if isinstance(meta.get("params"), str):
        meta["params"] = json.loads(meta["params"])
    return meta


def _load_entry(skill_dir):
    run_path = skill_dir / "run.py"
    spec = importlib.util.spec_from_file_location(f"skill_{skill_dir.name}", run_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _build_fn(entry, params: dict):
    sig_parts, call_parts = [], []
    for pname, p in params.items():
        t = _TYPES.get(str(p.get("type", "str")), "str")
        if p.get("optional"):
            default = p.get("default")
            sig_parts.append(f"{pname}: {t} = {default!r}")
        else:
            sig_parts.append(f"{pname}: {t}")
        call_parts.append(f"{pname}={pname}")
    src = f"def _tool({', '.join(sig_parts)}):\n    return _entry({', '.join(call_parts)})"
    ns = {"_entry": entry}
    exec(src, ns)
    return ns["_tool"]


def load_skills() -> dict[str, dict]:
    _REGISTRY.clear()
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = meta.get("name", skill_md.parent.name)
        params = meta.get("params") or {}
        entry = _load_entry(skill_md.parent)
        _REGISTRY[name] = {
            "name": name,
            "description": meta.get("description", ""),
            "params": params,
            "entry": entry,
            "fn": _build_fn(entry, params),
            "dir": str(skill_md.parent),
        }
    return _REGISTRY


def run_skill(name: str, kwargs: dict) -> dict:
    skill = _REGISTRY.get(name)
    if not skill:
        return {"error": f"skill '{name}' not found", "available": sorted(_REGISTRY)}
    try:
        return skill["entry"](**kwargs)
    except TypeError as e:
        return {"error": f"bad arguments: {e}", "params": skill["params"]}


def register_mcp_tools(mcp) -> None:
    for name, skill in _REGISTRY.items():
        mcp.add_tool(skill["fn"], name=name, description=skill["description"])


def registry_info() -> list[dict]:
    return [
        {"name": s["name"], "description": s["description"], "params": s["params"]}
        for s in _REGISTRY.values()
    ]
