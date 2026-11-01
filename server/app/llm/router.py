"""Фабрика провайдеров и маршрутизатор ролей моделей из llm.yaml."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..kernel.errors import LLMError
from .provider import LLMProvider
from .providers.fake import FakeLLMProvider
from .providers.openai_compat import OpenAICompatProvider
from .types import ProviderCapabilities


@dataclass(frozen=True, slots=True)
class RoleBinding:
    """Привязка роли к провайдеру и модели."""

    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Разобранный llm.yaml: провайдеры и роли."""

    providers: dict[str, dict[str, Any]]
    roles: dict[str, RoleBinding]

    @classmethod
    def load(cls, path: Path) -> "LLMConfig":
        """Прочитать конфиг; при отсутствии — пустой (LLM выключен)."""
        if not path.exists():
            return cls(providers={}, roles={})
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        roles = {
            name: RoleBinding(provider=b["provider"], model=b["model"])
            for name, b in (raw.get("roles") or {}).items()
        }
        return cls(providers=raw.get("providers") or {}, roles=roles)


def _collect_api_keys(spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Пул ключей провайдера: значения env из api_key_envs (пустые пропущены, дубли сняты,
    порядок сохранён); fallback — одиночный api_key_env. Возвращает (ключи, отсутствующие env)."""
    env_names: list[str] = []
    for name in spec.get("api_key_envs") or []:
        if name and name not in env_names:
            env_names.append(name)
    if not env_names and spec.get("api_key_env"):
        env_names = [spec["api_key_env"]]
    keys: list[str] = []
    missing: list[str] = []
    for name in env_names:
        value = os.environ.get(name)
        if value:
            keys.append(value)
        else:
            missing.append(name)
    return keys, missing


class ModelRouter:
    """Выдаёт провайдера и модель по роли; провайдеры создаются лениво и переиспользуются."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        force_provider: LLMProvider | None = None,
        key_cooldown_seconds: float = 600.0,
    ) -> None:
        self._config = config
        self._providers: dict[str, LLMProvider] = {}
        self._force = force_provider
        self._key_cooldown_seconds = key_cooldown_seconds

    def resolve(self, role: str) -> tuple[LLMProvider, str]:
        """Роль → (провайдер, модель). LLMError(not_configured), если роли/ключа нет."""
        if self._force is not None:
            return self._force, "fake-model"
        binding = self._config.roles.get(role)
        if binding is None:
            raise LLMError(f"роль '{role}' не настроена в llm.yaml", code="not_configured")
        spec = self._config.providers.get(binding.provider)
        if spec is None or not spec.get("enabled", True):
            raise LLMError(f"провайдер '{binding.provider}' не настроен или выключен", code="not_configured")
        return self._get_provider(binding.provider, spec), binding.model

    def _get_provider(self, name: str, spec: dict[str, Any]) -> LLMProvider:
        if name not in self._providers:
            keys, missing = _collect_api_keys(spec)
            if missing and not keys:
                raise LLMError(
                    f"нет ни одного ключа из {', '.join(missing)} — LLM недоступен", code="not_configured"
                )
            caps = ProviderCapabilities(**(spec.get("capabilities") or {}))
            ptype = spec.get("type", "openai_compat")
            if ptype == "fake":
                self._providers[name] = FakeLLMProvider()
            else:
                self._providers[name] = OpenAICompatProvider(
                    name, spec["base_url"], keys, caps, cooldown_seconds=self._key_cooldown_seconds
                )
        return self._providers[name]

    def status(self) -> dict[str, Any]:
        """Сводка для /api/health: все роли (R-23), не только chat.

        Раньше молчаливые поломки fast/structured не были видны: блоки не
        генерировались, а health показывал зелёный.
        """
        roles_out: dict[str, dict[str, Any]] = {}
        reasons: list[str] = []
        first_ok: dict[str, Any] | None = None
        for role, binding in self._config.roles.items():
            spec = self._config.providers.get(binding.provider) or {}
            keys, missing = _collect_api_keys(spec)
            # keyless-провайдер (api_key_env не задан) — легален без ключей (R-23)
            keyless = not (spec.get("api_key_envs") or spec.get("api_key_env"))
            ok = bool(spec.get("enabled", True)) and (bool(keys) or keyless)
            entry = {
                "provider": binding.provider,
                "model": binding.model,
                "keys": len(keys),
                "configured": ok,
            }
            if not ok:
                if not spec.get("enabled", True):
                    entry["reason"] = "провайдер выключен"
                elif missing:
                    entry["reason"] = f"нет ключей ({', '.join(missing)})"
                else:
                    entry["reason"] = "провайдер не настроен"
                reasons.append(f"{role}: {entry['reason']}")
            elif first_ok is None:
                first_ok = entry
            roles_out[role] = entry
        overall = bool(roles_out) and not reasons  # ролей нет вовсе — LLM не настроен
        head = first_ok or {"provider": None, "model": None, "keys": 0}
        return {
            "configured": overall,
            "provider": head["provider"],
            "model": head["model"],
            "keys": head["keys"],
            "reason": None if overall else "; ".join(reasons),
            "roles": roles_out,
        }
