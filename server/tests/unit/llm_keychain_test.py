"""Цепочка ключей LLM (T-040): сборка пула из api_key_envs, ротация на квоту, cooldown.

Транспорт подменяется фейковым клиентом: поведение зависит от значения ключа,
поэтому тесты видят, каким именно ключом ушёл запрос. Значения ключей — заглушки.
"""

import time
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.kernel.errors import LLMError
from app.llm.providers.openai_compat import OpenAICompatProvider, _map_error
from app.llm.router import LLMConfig, ModelRouter, RoleBinding, _collect_api_keys
from app.llm.types import LLMRequest, Message

_URL = "https://unit.test/v1/chat/completions"


def _req() -> LLMRequest:
    return LLMRequest(messages=(Message(role="user", content="вопрос"),))


# --- заглушки исключений openai ---


def _status_error(cls: type[openai.APIStatusError], status: int, message: str) -> Exception:
    request = httpx.Request("POST", _URL)
    return cls(message, response=httpx.Response(status, request=request), body=None)


def _err_429(message: str = "превышен лимит запросов") -> Exception:
    return _status_error(openai.RateLimitError, 429, message)


def _err_connection() -> Exception:
    return openai.APIConnectionError(request=httpx.Request("POST", _URL))


# --- заглушки ответов ---


def _resp(text: str) -> SimpleNamespace:
    message = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=message)], usage=None)


def _chunk(text: str) -> SimpleNamespace:
    delta = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason="stop", delta=delta)])


class _FakeStream:
    def __init__(self, chunks: list) -> None:
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _ScriptedClient:
    """Фейковый AsyncOpenAI: поведение по значению ключа, счётчик вызовов."""

    def __init__(self, api_key: str, behavior) -> None:
        self.api_key = api_key
        self.calls = 0
        self._behavior = behavior
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls += 1
        action = self._behavior(self.api_key)
        if isinstance(action, Exception):
            raise action
        return _FakeStream(action) if kwargs.get("stream") else action


def _make_provider(keys: list[str], behavior, *, now: dict | None = None, cooldown: float = 600.0):
    """Провайдер на фейковом транспорте; возвращает (провайдер, клиенты по значению ключа)."""
    clock = (lambda: now["t"]) if now is not None else time.monotonic
    provider = OpenAICompatProvider("zai", _URL, list(keys), cooldown_seconds=cooldown, monotonic=clock)
    by_key: dict[str, _ScriptedClient] = {}

    def fake_client(api_key: str | None):
        client = _ScriptedClient(api_key or "not-set", behavior)
        by_key[client.api_key] = client
        return client

    provider._make_client = fake_client
    return provider, by_key


# --- сборка пула из llm.yaml ---


def test_collect_api_keys_order_skip_empty_and_dups(monkeypatch):
    monkeypatch.setenv("K1", "v1")
    monkeypatch.delenv("K2", raising=False)
    monkeypatch.setenv("K3", "v3")
    monkeypatch.setenv("K4", "")
    spec = {"api_key_envs": ["K1", "K2", "K3", "K4", "K1", ""]}
    keys, missing = _collect_api_keys(spec)
    assert keys == ["v1", "v3"]
    assert missing == ["K2", "K4"]


def test_collect_api_keys_fallback_to_single_env(monkeypatch):
    monkeypatch.setenv("K1", "v1")
    keys, missing = _collect_api_keys({"api_key_env": "K1"})
    assert keys == ["v1"] and missing == []
    keys, missing = _collect_api_keys({"api_key_env": None})
    assert keys == [] and missing == []


def _router(spec: dict) -> ModelRouter:
    config = LLMConfig(providers={"zai": spec}, roles={"chat": RoleBinding(provider="zai", model="glm")})
    return ModelRouter(config)


def test_resolve_builds_provider_from_key_pool(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "k1")
    monkeypatch.delenv("ZAI_API_KEY_2", raising=False)
    monkeypatch.setenv("ZAI_API_KEY_3", "k3")
    spec = {
        "type": "openai_compat",
        "base_url": _URL,
        "api_key_envs": ["ZAI_API_KEY", "ZAI_API_KEY_2", "ZAI_API_KEY_3"],
    }
    provider, model, params = _router(spec).resolve("chat")
    assert model == "glm"
    assert params == {}  # params роли не заданы — пустые
    assert provider._api_keys == ["k1", "k3"]


def test_resolve_raises_when_whole_chain_missing(monkeypatch):
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY_2", raising=False)
    spec = {"type": "openai_compat", "base_url": _URL, "api_key_envs": ["ZAI_API_KEY", "ZAI_API_KEY_2"]}
    with pytest.raises(LLMError, match="ZAI_API_KEY, ZAI_API_KEY_2") as excinfo:
        _router(spec).resolve("chat")
    assert excinfo.value.code == "not_configured"


def test_status_counts_keys_in_pool(monkeypatch):
    monkeypatch.setenv("K1", "v1")
    monkeypatch.delenv("K2", raising=False)
    chain = {"type": "openai_compat", "base_url": _URL, "api_key_envs": ["K1", "K2"]}
    st = _router(chain).status()
    assert st["configured"] is True and st["keys"] == 1

    monkeypatch.delenv("K1", raising=False)
    st = _router(chain).status()
    assert st["configured"] is False and st["keys"] == 0
    assert "K1" in st["reason"] and "K2" in st["reason"]

    keyless = _router({"type": "openai_compat", "base_url": _URL, "api_key_env": None}).status()
    assert keyless["configured"] is True and keyless["keys"] == 0


# --- ротация ключей в провайдере ---


async def test_complete_rotates_on_rate_limit_and_sticks():
    behavior = lambda key: _err_429() if key == "k1" else _resp("со второго ключа")  # noqa: E731
    provider, by_key = _make_provider(["k1", "k2"], behavior)

    r = await provider.complete("glm", _req())
    assert r.text == "со второго ключа"
    assert by_key["k1"].calls == 1 and by_key["k2"].calls == 1
    assert provider._sticky == 1

    # sticky: следующий запрос идёт сразу рабочим ключом, первый не трогаем
    r2 = await provider.complete("glm", _req())
    assert r2.text == "со второго ключа"
    assert by_key["k1"].calls == 1 and by_key["k2"].calls == 2


async def test_key_returns_to_service_after_cooldown():
    now = {"t": 1000.0}
    behavior = {"fn": lambda key: _err_429() if key == "k1" else _resp("ok2")}
    provider, by_key = _make_provider(["k1", "k2"], lambda key: behavior["fn"](key), now=now)

    assert (await provider.complete("glm", _req())).text == "ok2"

    # рабочий ключ упёрся в квоту, а первый уже отстоял cooldown — возвращается
    behavior["fn"] = lambda key: _err_429() if key == "k2" else _resp("ok1")
    now["t"] += 601.0
    r = await provider.complete("glm", _req())
    assert r.text == "ok1"
    assert by_key["k1"].calls == 2


async def test_all_keys_in_cooldown_raises_clear_error():
    provider, _ = _make_provider(["k1", "k2"], lambda key: _err_429(), now={"t": 0.0})
    with pytest.raises(LLMError) as excinfo:
        await provider.complete("glm", _req())
    assert excinfo.value.code == "rate_limit"
    assert "cooldown" in excinfo.value.message and "мин" in excinfo.value.message
    assert set(provider._cooldown_until) == {0, 1}


async def test_single_key_contract():
    behavior = {"fn": lambda key: _resp("ок")}
    provider, by_key = _make_provider(["k1"], lambda key: behavior["fn"](key))

    assert (await provider.complete("glm", _req())).text == "ок"

    # один ключ: квота сразу даёт понятную ошибку без бессмысленного ретрая
    behavior["fn"] = lambda key: _err_429()
    with pytest.raises(LLMError, match="cooldown"):
        await provider.complete("glm", _req())
    assert by_key["k1"].calls == 2


async def test_network_error_keeps_key_no_rotation(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.llm.providers.openai_compat.asyncio.sleep", no_sleep)
    provider, by_key = _make_provider(["k1", "k2"], lambda key: _err_connection())

    with pytest.raises(LLMError) as excinfo:
        await provider.complete("glm", _req())
    assert excinfo.value.code == "unavailable"
    # ретрай тем же ключом, второй не тронут, cooldown пуст
    assert set(by_key) == {"k1"} and by_key["k1"].calls == 2
    assert provider._cooldown_until == {} and provider._sticky == 0


async def test_stream_rotates_on_rate_limit():
    behavior = lambda key: _err_429() if key == "k1" else [_chunk("поток со второго")]  # noqa: E731
    provider, by_key = _make_provider(["k1", "k2"], behavior)

    events = [e async for e in provider.stream("glm", _req())]
    assert "".join(e.text for e in events if e.type == "text") == "поток со второго"
    assert events[-1].type == "finish" and events[-1].finish_reason == "stop"
    assert by_key["k1"].calls == 1 and by_key["k2"].calls == 1


# --- классификация ошибок на ротацию ---


def test_map_error_rotation_classes():
    assert _map_error(_status_error(openai.PermissionDeniedError, 403, "доступ запрещён")).code == "auth"
    assert _map_error(_status_error(openai.AuthenticationError, 401, "bad key")).code == "auth"
    assert _map_error(_err_429()).code == "rate_limit"
    quota_402 = _status_error(openai.APIStatusError, 402, "Insufficient quota for this key")
    assert _map_error(quota_402).code == "rate_limit"
    quota_ru = _status_error(openai.APIStatusError, 400, "Превышен лимит запросов к API")
    assert _map_error(quota_ru).code == "rate_limit"
    assert _map_error(_status_error(openai.APIStatusError, 500, "boom")).code == "unavailable"
    assert _map_error(_err_connection()).code == "unavailable"


# --- params роли в wire-запросе (BB-003) ---


def _err_bad_request(message: str = "Invalid parameter: thinking") -> Exception:
    return _status_error(openai.BadRequestError, 400, message)


def test_to_wire_sends_extra_params_only_when_configured():
    provider = OpenAICompatProvider("zai", _URL, ["k1"])

    payload, extra = provider._to_wire(_req())
    assert extra == {} and "thinking" not in payload  # без params роли — чистый запрос

    req = LLMRequest(
        messages=(Message(role="user", content="вопрос"),),
        extra_params={"thinking": {"type": "disabled"}, "max_tokens": 128},
    )
    payload, extra = provider._to_wire(req)
    # extra-параметры идут отдельно: SDK не принимает чужие kwargs, они уедут в extra_body
    assert extra == {"thinking": {"type": "disabled"}, "max_tokens": 128}
    assert "thinking" not in payload and "max_tokens" not in payload


def test_to_wire_normalizes_thinking_shortcut_and_respects_request_fields():
    provider = OpenAICompatProvider("zai", _URL, ["k1"])
    req = LLMRequest(
        messages=(Message(role="user", content="вопрос"),),
        temperature=0.2,
        max_tokens=64,
        extra_params={"thinking": "disabled", "temperature": 0.9, "max_tokens": 999, "messages": []},
    )
    payload, extra = provider._to_wire(req)
    # шорткат 'disabled' → объект по спецификации GLM; явные поля запроса не дублируются,
    # служебные ключи wire не пробрасываются
    assert extra == {"thinking": {"type": "disabled"}}
    assert payload["temperature"] == 0.2 and payload["max_tokens"] == 64
    assert isinstance(payload["messages"][0], dict) and payload["messages"][0]["role"] == "user"


async def test_bad_request_on_extra_param_dropped_without_loop(monkeypatch):
    """bad_request на extra-параметр: дроп, один немедленный ретрай, дальше не шлём."""

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.llm.providers.openai_compat.asyncio.sleep", no_sleep)
    provider, by_key = _make_provider(["k1"], lambda key: _err_bad_request())
    req = LLMRequest(
        messages=(Message(role="user", content="вопрос"),),
        extra_params={"thinking": "disabled"},
    )

    # с thinking → bad_request → дроп и ретрай сразу → снова bad_request (плавающий 1214)
    # → обычный ретрай → bad_request → raise. Максимум 3 вызова, без зацикливания.
    with pytest.raises(LLMError) as excinfo:
        await provider.complete("glm", req)
    assert excinfo.value.code == "bad_request"
    assert by_key["k1"].calls == 3
    # параметр отвергнут: последующие запросы собираются без него
    payload, extra = provider._to_wire(req)
    assert extra == {} and "thinking" not in payload


async def test_bad_request_extra_drop_then_success():
    """Провайдер отверг thinking, но без него отвечает — запрос спасён, параметр снят."""
    calls = {"n": 0}

    def flip(_key):
        calls["n"] += 1
        return _resp("ок без thinking") if calls["n"] >= 2 else _err_bad_request()

    provider, by_key = _make_provider(["k1"], flip)
    req = LLMRequest(
        messages=(Message(role="user", content="вопрос"),),
        extra_params={"thinking": "disabled"},
    )

    r = await provider.complete("glm", req)
    assert r.text == "ок без thinking"
    assert by_key["k1"].calls == 2
    assert "thinking" in provider._unsupported_extra


async def test_stream_bad_request_on_extra_param_dropped():
    calls = {"n": 0}

    def flip(_key):
        calls["n"] += 1
        return [_chunk("поток без thinking")] if calls["n"] >= 2 else _err_bad_request()

    provider, by_key = _make_provider(["k1"], flip)
    req = LLMRequest(
        messages=(Message(role="user", content="вопрос"),),
        extra_params={"thinking": "disabled"},
    )
    events = [e async for e in provider.stream("glm", req)]
    assert "".join(e.text for e in events if e.type == "text") == "поток без thinking"
    assert by_key["k1"].calls == 2  # отказ → дроп → успех


# --- статус цепочки ключей (BB-004/BB-005) ---


def test_keychain_status_states_and_cooldown_left():
    now = {"t": 1000.0}
    provider, _ = _make_provider(["k1", "k2", "k3"], lambda key: _resp("ок"), now=now)
    provider._cooldown_key(2)  # третий ключ в cooldown на 600 с
    now["t"] += 100.0

    st = provider.keychain_status()
    assert st["keys_total"] == 3 and st["sticky"] == 1  # ключи считаем с 1
    states = {k["index"]: k for k in st["keys"]}
    assert states[1]["state"] == "active"  # sticky
    assert states[2]["state"] == "ready"
    assert states[3]["state"] == "cooldown" and 495 <= states[3]["cooldown_seconds"] <= 500


async def test_reset_cooldown_returns_keys_to_service():
    now = {"t": 1000.0}
    behavior = {"fn": lambda key: _err_429()}
    provider, _ = _make_provider(["k1", "k2"], lambda key: behavior["fn"](key), now=now)
    with pytest.raises(LLMError):
        await provider.complete("glm", _req())
    # оба ключа в cooldown — статус это видит
    states = {k["index"]: k for k in provider.keychain_status()["keys"]}
    assert all(k["state"] == "cooldown" for k in states.values())

    assert provider.reset_cooldown() == 2
    assert provider._cooldown_until == {}
    behavior["fn"] = lambda key: _resp("в строю")
    assert (await provider.complete("glm", _req())).text == "в строю"


def test_detailed_status_roles_params_and_providers(monkeypatch):
    monkeypatch.setenv("K1", "v1")
    config = LLMConfig(
        providers={"zai": {"type": "openai_compat", "base_url": _URL, "api_key_envs": ["K1"]}},
        roles={
            "chat": RoleBinding(provider="zai", model="glm-5.3"),
            "fast": RoleBinding(
                provider="zai", model="glm-5.3-flash", params={"thinking": {"type": "disabled"}}
            ),
        },
    )
    router = ModelRouter(config)
    st = router.detailed_status()
    assert st["configured"] is True
    assert st["roles"]["fast"]["params"] == {"thinking": {"type": "disabled"}}
    assert st["roles"]["chat"]["params"] == {}
    prov = st["providers"]["zai"]
    assert prov["keys_total"] == 1 and prov["enabled"] is True and "reason" not in prov
    # провайдер ещё не создан — живой цепочки нет, но конфигурация видна
    assert "keychain" not in prov

    # после resolve появляется живая цепочка с sticky
    router.resolve("chat")
    st = router.detailed_status()
    assert st["providers"]["zai"]["keychain"]["keys_total"] == 1
    assert st["providers"]["zai"]["keychain"]["sticky"] == 1


def test_detailed_status_reports_disabled_provider_reason(monkeypatch):
    monkeypatch.delenv("K1", raising=False)
    config = LLMConfig(
        providers={
            "zai": {"type": "openai_compat", "base_url": _URL, "api_key_envs": ["K1"], "enabled": False}
        },
        roles={"chat": RoleBinding(provider="zai", model="glm")},
    )
    st = ModelRouter(config).detailed_status()
    assert st["configured"] is False
    assert st["providers"]["zai"]["reason"] == "провайдер выключен"


# --- прокси провайдера (B-011): OpenAI блокирует регион прода, embed ходит через socks5 ---


class _FakeSDK:
    """Заглушка openai.AsyncOpenAI: запоминает kwargs конструктора."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_make_client_without_proxy_is_direct(monkeypatch):
    monkeypatch.setattr("app.llm.providers.openai_compat.openai.AsyncOpenAI", _FakeSDK)
    provider = OpenAICompatProvider("zai", _URL, ["k1"])
    client = provider._make_client("k1")
    assert "http_client" not in client.kwargs


def test_make_client_with_proxy_passes_httpx_client(monkeypatch):
    monkeypatch.setattr("app.llm.providers.openai_compat.openai.AsyncOpenAI", _FakeSDK)
    provider = OpenAICompatProvider("openai", _URL, ["k1"], proxy_from=lambda: "socks5://xray:1080")
    client = provider._make_client("k1")
    hc = client.kwargs.get("http_client")
    assert isinstance(hc, httpx.AsyncClient)


async def test_ensure_client_rebuilds_when_proxy_changes(monkeypatch):
    monkeypatch.setattr("app.llm.providers.openai_compat.openai.AsyncOpenAI", _FakeSDK)
    current = {"proxy": "socks5://xray:1080"}
    provider = OpenAICompatProvider("openai", _URL, ["k1"], proxy_from=lambda: current["proxy"])
    first = provider._ensure_client(0)
    same = provider._ensure_client(0)
    assert first is same  # прокси не менялся — клиент переиспользуется
    current["proxy"] = ""  # прокси сняли в UI — следующий запрос напрямую
    rebuilt = provider._ensure_client(0)
    assert rebuilt is not first
    assert "http_client" not in rebuilt.kwargs


def test_router_wires_proxy_from_use_proxy_flag(monkeypatch):
    monkeypatch.setenv("K1", "key1")
    config = LLMConfig(
        providers={
            "zai": {"type": "openai_compat", "base_url": _URL, "api_key_envs": ["K1"]},
            "openai": {
                "type": "openai_compat",
                "base_url": _URL,
                "api_key_envs": ["K1"],
                "use_proxy": True,
            },
        },
        roles={
            "chat": RoleBinding(provider="zai", model="glm"),
            "embed": RoleBinding(provider="openai", model="text-embedding-3-small"),
        },
    )
    router = ModelRouter(config)
    prov_zai, _, _ = router.resolve("chat")
    prov_oai, _, _ = router.resolve("embed")
    assert prov_zai._proxy_from is None
    assert prov_oai._proxy_from is not None
