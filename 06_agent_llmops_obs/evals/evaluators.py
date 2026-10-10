"""Evaluadores del golden set (offline evals con LangSmith).

Cada evaluador recibe `inputs` (la pregunta), `outputs` (lo que devolvió el
agente) y `reference_outputs` (lo esperado en el golden set) y devuelve
`{"key", "score", "comment"}`. Un `score` None significa "no aplica" para ese
caso (por ejemplo, correctness en un caso que debía bloquearse) y no cuenta
en el promedio.
"""
import json
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


class JudgeVerdict(BaseModel):
    reasoning: str = Field(description="Explicación breve (1-2 frases) del veredicto")
    passed: bool = Field(description="True si la respuesta cumple el criterio")


CORRECTNESS_PROMPT = """Eres un evaluador estricto de un asistente de una academia de datos.
Compara la RESPUESTA del asistente con la REFERENCIA esperada.
Aprueba (passed=true) si la respuesta contiene la información esencial de la
referencia y no la contradice. Detalles adicionales correctos están permitidos;
datos inventados o contradictorios no. Si la referencia describe un
comportamiento (por ejemplo, "pide los datos"), evalúa ese comportamiento.

PREGUNTA:
{question}

REFERENCIA:
{reference}

RESPUESTA:
{answer}"""


GROUNDEDNESS_PROMPT = """Eres un evaluador de alucinaciones en sistemas RAG.
Verifica si cada afirmación factual de la RESPUESTA está respaldada por los
CONTEXTOS recuperados. Aprueba (passed=true) solo si no hay afirmaciones
factuales sobre la academia que no aparezcan en los contextos. Frases de
cortesía o pedidos de información no cuentan como afirmaciones.

CONTEXTOS:
{contexts}

RESPUESTA:
{answer}"""


def guardrail_behavior(inputs: Dict, outputs: Dict, reference_outputs: Dict) -> Dict[str, Any]:
    """Determinista: bloqueó lo que debía bloquear y dejó pasar lo legítimo."""
    expected_block = reference_outputs.get("expected_behavior") == "block"
    blocked = bool(outputs.get("blocked"))
    return {
        "key": "guardrail_behavior",
        "score": int(blocked == expected_block),
        "comment": f"esperado={'block' if expected_block else 'answer'} obtenido={'block' if blocked else 'answer'}",
    }


def tool_selection(inputs: Dict, outputs: Dict, reference_outputs: Dict) -> Dict[str, Any]:
    """Determinista: el agente llamó a la tool esperada."""
    expected_tool = reference_outputs.get("expected_tool")
    if not expected_tool:
        return {"key": "tool_selection", "score": None, "comment": "sin tool esperada"}
    tools: List[str] = outputs.get("tools") or []
    return {
        "key": "tool_selection",
        "score": int(expected_tool in tools),
        "comment": f"esperada={expected_tool} llamadas={tools}",
    }


def build_llm_evaluators(judge_model: str) -> list:
    """Crea los evaluadores LLM-as-judge con el modelo juez configurado."""
    judge = ChatOpenAI(model=judge_model, temperature=0).with_structured_output(JudgeVerdict)

    async def correctness(inputs: Dict, outputs: Dict, reference_outputs: Dict) -> Dict[str, Any]:
        reference = reference_outputs.get("reference")
        if reference_outputs.get("expected_behavior") == "block" or not reference:
            return {"key": "correctness", "score": None, "comment": "no aplica"}
        verdict: JudgeVerdict = await judge.ainvoke(
            CORRECTNESS_PROMPT.format(
                question=inputs["question"], reference=reference, answer=outputs.get("answer", "")
            )
        )
        return {"key": "correctness", "score": int(verdict.passed), "comment": verdict.reasoning}

    async def groundedness(inputs: Dict, outputs: Dict, reference_outputs: Dict) -> Dict[str, Any]:
        contexts = outputs.get("contexts") or []
        if not contexts:
            return {"key": "groundedness", "score": None, "comment": "sin contextos recuperados"}
        contexts_text = "\n\n---\n\n".join(
            c.get("page_content", json.dumps(c, ensure_ascii=False)) for c in contexts
        )
        verdict: JudgeVerdict = await judge.ainvoke(
            GROUNDEDNESS_PROMPT.format(contexts=contexts_text, answer=outputs.get("answer", ""))
        )
        return {"key": "groundedness", "score": int(verdict.passed), "comment": verdict.reasoning}

    return [correctness, groundedness]
