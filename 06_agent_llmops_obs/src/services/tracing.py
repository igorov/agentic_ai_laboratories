"""Observabilidad con LangSmith: tracing del agente y feedback de usuarios.

LangChain/LangGraph trazan automáticamente cada nodo del agente (guardrails,
hooks, llamadas al LLM con tokens y costo, tools). Aquí se crea un único
`Client` de LangSmith con un *anonymizer*: antes de enviar inputs/outputs de
cada span, se enmascaran secretos y PII con las mismas REGEX de las capas 1 y 5
de los guardrails. Así, incluso un mensaje que un guardrail bloqueó (y que el
span raíz sí registra) no expone credenciales ni datos personales en el trace.
"""
import re
from functools import lru_cache
from typing import List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tracers import LangChainTracer
from langsmith import Client
from langsmith.anonymizer import create_anonymizer

from src.services.guardrails.layer1_secrets import SECRET_PATTERNS
from src.services.guardrails.layer5_pii import (
    CREDIT_CARD_REGEX,
    DNI_PE_REGEX,
    EMAIL_REGEX,
    PHONE_PE_REGEX,
    RUC_PE_REGEX,
)
from src.utils.environment import LANGSMITH_API_KEY, LANGSMITH_PROJECT, LANGSMITH_TRACING
from src.utils.logger import get_logger

logger = get_logger(__name__)

# El orden importa: primero los patrones más específicos/largos (secretos,
# email, tarjeta, RUC de 11 dígitos) y al final el DNI (8 dígitos), para que
# no "muerda" pedazos de números más largos.
ANONYMIZER_RULES = [
    *({"pattern": pattern, "replace": "<SECRET>"} for pattern in SECRET_PATTERNS),
    {"pattern": re.compile(EMAIL_REGEX), "replace": "<EMAIL>"},
    {"pattern": re.compile(CREDIT_CARD_REGEX), "replace": "<CREDIT_CARD>"},
    {"pattern": re.compile(RUC_PE_REGEX), "replace": "<RUC>"},
    {"pattern": re.compile(PHONE_PE_REGEX), "replace": "<PHONE>"},
    {"pattern": re.compile(DNI_PE_REGEX), "replace": "<DNI>"},
]

anonymize = create_anonymizer(ANONYMIZER_RULES)


def tracing_enabled() -> bool:
    return bool(LANGSMITH_TRACING and LANGSMITH_API_KEY)


@lru_cache(maxsize=1)
def get_langsmith_client() -> Optional[Client]:
    """Cliente único de LangSmith (tracing + feedback). None si no hay API key."""
    if not LANGSMITH_API_KEY:
        return None
    return Client(api_key=LANGSMITH_API_KEY, anonymizer=anonymize)


def get_tracing_callbacks() -> List[BaseCallbackHandler]:
    """Tracer de LangSmith para pasar en `config["callbacks"]` del agente.

    Al pasar un `LangChainTracer` explícito, LangChain no agrega el tracer por
    defecto (el que crea con LANGSMITH_TRACING=true), así que todo el trace sale
    por el cliente con anonymizer.
    """
    if not tracing_enabled():
        return []
    return [LangChainTracer(client=get_langsmith_client(), project_name=LANGSMITH_PROJECT)]
