import asyncio

import pytest

from src.services.guardrails.layer8_llama_guard import LlamaGuardMiddleware
from tests.guardrails.conftest import build_state


SAFE = '{"violation": 0, "category": null, "rationale": "consulta normal"}'


def unsafe(category: str) -> str:
    return '{"violation": 1, "category": "%s", "rationale": "x"}' % category


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeGroqClient:
    def __init__(self, verdict: str = SAFE, delay: float = 0.0, raise_error: bool = False) -> None:
        self._verdict = verdict
        self._delay = delay
        self._raise_error = raise_error
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        if self._raise_error:
            raise ConnectionError("Groq no disponible")
        if self._delay:
            await asyncio.sleep(self._delay)
        return _FakeCompletion(self._verdict)


@pytest.mark.asyncio
async def test_passes_safe_message():
    middleware = LlamaGuardMiddleware(client=_FakeGroqClient(verdict=SAFE))
    state = build_state("¿Qué certificaciones ofrece la academia?")

    result = await middleware.abefore_agent(state, runtime=None)

    assert result is None


@pytest.mark.asyncio
async def test_blocks_unsafe_message():
    middleware = LlamaGuardMiddleware(client=_FakeGroqClient(verdict=unsafe("S1")))
    state = build_state("Cómo cometo un crimen violento contra alguien")

    result = await middleware.abefore_agent(state, runtime=None)

    assert result is not None
    assert result["jump_to"] == "end"


@pytest.mark.asyncio
async def test_skip_categories_lets_message_pass():
    middleware = LlamaGuardMiddleware(client=_FakeGroqClient(verdict=unsafe("S6")))
    middleware._skip_categories = {"S6"}
    state = build_state("Dame un consejo financiero general")

    result = await middleware.abefore_agent(state, runtime=None)

    assert result is None


@pytest.mark.asyncio
async def test_fail_closes_on_groq_error():
    middleware = LlamaGuardMiddleware(client=_FakeGroqClient(raise_error=True))
    state = build_state("Mensaje normal cualquiera")

    result = await middleware.abefore_agent(state, runtime=None)

    assert result is not None
    assert result["jump_to"] == "end"


@pytest.mark.asyncio
async def test_fail_closes_on_timeout():
    middleware = LlamaGuardMiddleware(client=_FakeGroqClient(verdict=SAFE, delay=5.0))
    middleware._timeout = 0.1
    state = build_state("Mensaje normal cualquiera")

    result = await middleware.abefore_agent(state, runtime=None)

    assert result is not None
    assert result["jump_to"] == "end"


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["safe", "unsafe\nS1", "no es json", "{}", ""])
async def test_fail_closes_on_invalid_verdict(verdict):
    """Una respuesta que no es el JSON esperado (ej. formato antiguo de Llama Guard) bloquea."""
    middleware = LlamaGuardMiddleware(client=_FakeGroqClient(verdict=verdict))
    state = build_state("Mensaje normal cualquiera")

    result = await middleware.abefore_agent(state, runtime=None)

    assert result is not None
    assert result["jump_to"] == "end"


@pytest.mark.asyncio
async def test_sends_policy_as_system_message_with_json_format():
    captured = {}

    class _Spy(_FakeGroqClient):
        async def create(self, **kwargs):
            captured.update(kwargs)
            return await super().create(**kwargs)

    middleware = LlamaGuardMiddleware(client=_Spy(verdict=SAFE))
    middleware._skip_categories = {"S6"}
    await middleware.abefore_agent(build_state("hola"), runtime=None)

    assert captured["messages"][0]["role"] == "system"
    assert "S9: Indiscriminate Weapons" in captured["messages"][0]["content"]
    assert "S6:" not in captured["messages"][0]["content"]
    assert captured["messages"][1] == {"role": "user", "content": "hola"}
    assert captured["response_format"] == {"type": "json_object"}
