import time
from typing import Any

from langchain.agents.middleware import (
    AgentState,
    after_agent,
    after_model,
    before_agent,
    before_model,
)
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime
from typing_extensions import NotRequired

from src.utils.environment import MAX_MODEL_CALLS
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HooksState(AgentState):
    """Estado del agente extendido con los datos que comparten los hooks."""

    started_at: NotRequired[float]
    model_calls: NotRequired[int]
    tools_called: NotRequired[list[str]]


@before_agent(state_schema=HooksState)
def pre_agent_hook(state: HooksState, runtime: Runtime) -> dict[str, Any] | None:
    """Pre-hook de agente: corre 1 vez al inicio de cada invocación."""
    messages = state["messages"]
    question = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )
    logger.info(
        "[pre_agent] pregunta=%r, mensajes de entrada=%d", question, len(messages)
    )
    return {"started_at": time.time(), "model_calls": 0, "tools_called": []}


@before_model(state_schema=HooksState, can_jump_to=["end"])
def pre_model_hook(state: HooksState, runtime: Runtime) -> dict[str, Any] | None:
    """Pre-hook de modelo: corre antes de cada llamada al LLM."""
    model_calls = state.get("model_calls", 0) + 1
    logger.info(
        "[pre_model] llamada #%d al modelo con %d mensaje(s)",
        model_calls,
        len(state["messages"]),
    )

    if model_calls > MAX_MODEL_CALLS:
        logger.warning("[pre_model] límite de %d llamadas alcanzado", MAX_MODEL_CALLS)
        return {
            "messages": [
                AIMessage("No pude completar la solicitud: se alcanzó el límite de pasos.")
            ],
            "jump_to": "end",
        }
    return {"model_calls": model_calls}


@after_model(state_schema=HooksState)
def post_model_hook(state: HooksState, runtime: Runtime) -> dict[str, Any] | None:
    """Post-hook de modelo: corre después de cada respuesta del LLM."""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage):
        return None

    requested = [call["name"] for call in last.tool_calls]
    usage = last.usage_metadata or {}
    logger.info(
        "[post_model] tokens entrada=%s salida=%s, tools pedidas=%s",
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
        requested or "ninguna",
    )
    if requested:
        return {"tools_called": [*state.get("tools_called", []), *requested]}
    return None


@after_agent(state_schema=HooksState)
def post_agent_hook(state: HooksState, runtime: Runtime) -> dict[str, Any] | None:
    """Post-hook de agente: corre 1 vez al terminar la invocación."""
    elapsed = time.time() - state.get("started_at", time.time())
    answer = state["messages"][-1].content if state["messages"] else ""
    logger.info(
        "[post_agent] duración=%.2fs, llamadas al modelo=%d, tools usadas=%s, largo respuesta=%d",
        elapsed,
        state.get("model_calls", 0),
        state.get("tools_called", []),
        len(answer),
    )
    return None


HOOKS = [pre_agent_hook, pre_model_hook, post_model_hook, post_agent_hook]
