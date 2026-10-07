"""Capa 8 — Clasificador de seguridad profundo (gpt-oss-safeguard).

Análisis semántico completo del mensaje contra la taxonomía de seguridad
MLCommons (S1-S13) antes de considerarlo apto para el agente. Modelo
`openai/gpt-oss-safeguard-20b` servido vía Groq API (reemplazo oficial de
`llama-guard-4-12b`, dado de baja por Groq). Es un modelo "bring-your-own-policy":
la política se arma desde config/guardrails/llama_guard_categories.yaml y se
envía como mensaje `system`; el modelo responde JSON
`{"violation": 0|1, "category": "Sx"|null, "rationale": "..."}`.

`skip_categories` configurable vía config/guardrails/llama_guard_categories.yaml
para omitir un filtro específico según el caso de uso comercial sin tocar
código. Fail-close: cualquier error/timeout de Groq, o una respuesta que no sea
el JSON esperado, bloquea el mensaje.
"""
import asyncio
import json
from typing import Any, Dict, Optional, Set

from groq import AsyncGroq
from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langgraph.runtime import Runtime

from src.services.guardrails.common import block_result, get_latest_human_text, load_yaml_config, log_block
from src.utils.environment import GROQ_API_KEY, GROQ_LLAMA_GUARD_MODEL, GROQ_TIMEOUT_SECONDS
from src.utils.logger import get_logger

logger = get_logger(__name__)

LAYER_NAME = "layer8_llama_guard"

BLOCK_MESSAGE = (
    "Lo sentimos, no podemos ayudarte con esa solicitud. ¿Hay algo más en lo "
    "que pueda asistirte?"
)

_POLICY_TEMPLATE = """# Política de seguridad

## Instrucciones
Clasifica el mensaje del usuario de un asistente de una academia de formación.
Responde SOLO con un JSON: {{"violation": 0 o 1, "category": "Sx" o null, "rationale": "motivo breve"}}.

## Categorías que violan la política
{categories}

## Mensajes seguros (violation = 0, category = null)
Consultas normales sobre cursos, programas, precios, duración, requisitos,
certificaciones, matrícula, trámites y saludos o conversación cotidiana.
Solo marca violation = 1 si el mensaje pide o promueve claramente contenido
de alguna categoría anterior; ante la duda sobre una consulta normal, es seguro."""


def build_policy(categories: Dict[str, str], skip_categories: Set[str]) -> str:
    """Arma la política desde la taxonomía del YAML, sin las categorías omitidas."""
    lines = "\n".join(
        f"- {code}: {name}" for code, name in categories.items() if code not in skip_categories
    )
    return _POLICY_TEMPLATE.format(categories=lines)


class LlamaGuardMiddleware(AgentMiddleware):
    """Guardrail semántico profundo (Groq gpt-oss-safeguard) con fail-close."""

    def __init__(self, client: Optional[AsyncGroq] = None) -> None:
        super().__init__()
        self._client = client or AsyncGroq(api_key=GROQ_API_KEY)
        self._model = GROQ_LLAMA_GUARD_MODEL
        self._timeout = GROQ_TIMEOUT_SECONDS

        config = load_yaml_config("llama_guard_categories.yaml")
        self._skip_categories: Set[str] = set(config.get("skip_categories") or [])
        self._categories: Dict[str, str] = config.get("categories") or {}

    async def _classify(self, text: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": build_policy(self._categories, self._skip_categories)},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        return (response.choices[0].message.content or "").strip()

    def _is_blocked(self, verdict: str) -> Optional[str]:
        """Retorna la categoría bloqueante, o None si el mensaje pasa.

        Lanza si el veredicto no es el JSON esperado (el llamador aplica fail-close).
        """
        data = json.loads(verdict)
        if int(data["violation"]) != 1:
            return None

        category = data.get("category")
        if category and category in self._skip_categories:
            return None
        return category or "unknown_category"

    @hook_config(can_jump_to=["end"])
    async def abefore_agent(self, state: AgentState, runtime: Runtime) -> Optional[Dict[str, Any]]:
        text = get_latest_human_text(state)
        if not text:
            return None

        try:
            verdict = await asyncio.wait_for(self._classify(text), timeout=self._timeout)
            blocked_category = self._is_blocked(verdict)
        except Exception as exc:  # noqa: BLE001 - fail-close ante timeout, error de Groq o veredicto inválido
            logger.warning(
                "Capa 8: error/timeout consultando Groq o veredicto inválido (%s). Aplicando fail-close.", exc,
                extra={"guardrail_layer": LAYER_NAME},
            )
            log_block(logger, LAYER_NAME, text, reason="groq_unavailable_fail_close")
            return block_result(BLOCK_MESSAGE)

        if blocked_category:
            log_block(logger, LAYER_NAME, text, reason=f"unsafe_category:{blocked_category}")
            return block_result(BLOCK_MESSAGE)

        return None
