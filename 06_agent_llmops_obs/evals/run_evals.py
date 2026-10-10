"""Evaluación offline del agente contra el golden set (eval gate de CI).

Uso (desde la carpeta 06_agent_llmops_obs):
    python evals/run_evals.py                      # prompt y modelo del .env
    python evals/run_evals.py --model gpt-4.1-mini # model CI: otro modelo
    python evals/run_evals.py --prompt-version v2  # probar un prompt nuevo

Pasos:
  1. Sincroniza el golden set (evals/datasets/golden_set.jsonl) como dataset
     en LangSmith (lo crea si no existe y agrega los ejemplos nuevos).
  2. Ejecuta el agente (guardrails + hooks + LLM + tools locales, sin MCP)
     sobre cada ejemplo con `aevaluate`: cada ejecución queda como un
     experimento comparable en LangSmith.
  3. Calcula el promedio de cada métrica, latencia p95 y tokens promedio.
  4. Compara contra evals/thresholds.yaml y termina con exit 1 si alguna
     métrica no alcanza su umbral.
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
EVALS_DIR = ROOT_DIR / "evals"
GOLDEN_SET = EVALS_DIR / "datasets" / "golden_set.jsonl"
THRESHOLDS = EVALS_DIR / "thresholds.yaml"
DATASET_NAME = "agent-llmops-obs-golden"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eval gate del agente contra el golden set")
    parser.add_argument("--model", help="Modelo a evaluar (sobrescribe OPENAI_MODEL)")
    parser.add_argument("--prompt-version", help="Versión del prompt (sobrescribe PROMPT_VERSION)")
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--output", default=str(EVALS_DIR / "results.json"))
    return parser.parse_args()


# Las variables se fijan ANTES de importar src.*, porque environment.py,
# prompts.py y agent_service.py leen la configuración al importarse.
args = parse_args()
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()
if args.model:
    os.environ["OPENAI_MODEL"] = args.model
if args.prompt_version:
    os.environ["PROMPT_VERSION"] = args.prompt_version

import yaml  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langsmith import Client, aevaluate  # noqa: E402

from evals.evaluators import build_llm_evaluators, guardrail_behavior, tool_selection  # noqa: E402
from src.services.agent_service import AgentService, build_agent  # noqa: E402
from src.services.guardrails.common import GUARDRAIL_MESSAGE_NAME  # noqa: E402
from src.services.tools import get_all_tools  # noqa: E402
from src.utils.environment import OPENAI_MODEL, PROMPT_VERSION  # noqa: E402


def load_golden_set() -> List[Dict[str, Any]]:
    with open(GOLDEN_SET, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sync_dataset(client: Client, examples: List[Dict[str, Any]]) -> None:
    """Crea el dataset en LangSmith si no existe y agrega los ejemplos nuevos."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Golden set del agente de la academia (RAG, guardrails, skills, smalltalk)",
        )

    existing = {ex.inputs.get("question") for ex in client.list_examples(dataset_id=dataset.id)}
    new_examples = [ex for ex in examples if ex["inputs"]["question"] not in existing]
    if new_examples:
        client.create_examples(
            dataset_id=dataset.id,
            inputs=[ex["inputs"] for ex in new_examples],
            outputs=[ex["outputs"] for ex in new_examples],
        )
    print(f"Dataset '{DATASET_NAME}': {len(existing)} existentes, {len(new_examples)} nuevos")


_agent = build_agent(get_all_tools(None))


async def target(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Ejecuta el agente con la pregunta y devuelve lo que necesitan los evaluadores."""
    started = time.perf_counter()
    response = await _agent.ainvoke({"messages": [HumanMessage(content=inputs["question"])]})
    latency = time.perf_counter() - started

    messages = response.get("messages", [])
    parsed = AgentService._parse_agent_response(response)
    last = messages[-1] if messages else None
    tools = [
        call["name"]
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    ]
    return {
        "answer": parsed["answer"],
        "blocked": getattr(last, "name", None) == GUARDRAIL_MESSAGE_NAME,
        "tools": tools,
        "contexts": AgentService._extract_retrieved_contexts(response),
        "input_tokens": parsed["input_tokens"],
        "output_tokens": parsed["output_tokens"],
        "latency_s": round(latency, 3),
    }


def p95(values: List[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def build_summary(rows: List[Dict[str, Any]], thresholds: Dict[str, float]) -> Dict[str, Any]:
    scores: Dict[str, List[float]] = {}
    for row in rows:
        for key, value in row["scores"].items():
            if value is not None:
                scores.setdefault(key, []).append(value)

    metrics = {}
    for key, threshold in thresholds.items():
        values = scores.get(key, [])
        mean = sum(values) / len(values) if values else None
        metrics[key] = {
            "mean": mean,
            "n": len(values),
            "threshold": threshold,
            "passed": mean is not None and mean >= threshold,
        }

    latencies = [row["outputs"].get("latency_s", 0) for row in rows]
    tokens = [row["outputs"].get("input_tokens", 0) + row["outputs"].get("output_tokens", 0) for row in rows]
    return {
        "model": OPENAI_MODEL,
        "prompt_version": PROMPT_VERSION,
        "examples": len(rows),
        "metrics": metrics,
        "latency_p95_s": round(p95(latencies), 3),
        "avg_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0,
        "passed": all(m["passed"] for m in metrics.values()),
    }


def to_markdown(summary: Dict[str, Any], experiment: str, failures: List[Dict[str, Any]]) -> str:
    status = "✅ PASS" if summary["passed"] else "❌ FAIL"
    lines = [
        f"## Eval gate {status}",
        "",
        f"Experimento `{experiment}` · modelo `{summary['model']}` · prompt `{summary['prompt_version']}` · {summary['examples']} casos",
        "",
        "| Métrica | Promedio | Umbral | n | Estado |",
        "|---|---|---|---|---|",
    ]
    for key, m in summary["metrics"].items():
        mean = "—" if m["mean"] is None else f"{m['mean']:.2f}"
        lines.append(f"| {key} | {mean} | {m['threshold']:.2f} | {m['n']} | {'✅' if m['passed'] else '❌'} |")
    lines += [
        "",
        f"Latencia p95: **{summary['latency_p95_s']} s** · Tokens promedio por caso: **{summary['avg_tokens']}**",
    ]
    if failures:
        lines += ["", "### Casos fallidos", "", "| Pregunta | Métrica | Comentario |", "|---|---|---|"]
        for f in failures:
            lines.append(f"| {f['question'][:70]} | {f['key']} | {(f['comment'] or '')[:120]} |")
    return "\n".join(lines)


async def main() -> int:
    if not os.getenv("LANGSMITH_API_KEY"):
        print("ERROR: falta LANGSMITH_API_KEY", file=sys.stderr)
        return 2

    config = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    thresholds: Dict[str, float] = config["thresholds"]

    client = Client()
    sync_dataset(client, load_golden_set())

    sha = (os.getenv("GITHUB_SHA") or "local")[:7]
    results = await aevaluate(
        target,
        data=DATASET_NAME,
        evaluators=[guardrail_behavior, tool_selection, *build_llm_evaluators(config["judge_model"])],
        experiment_prefix=f"{PROMPT_VERSION}-{OPENAI_MODEL}-{sha}",
        metadata={"model": OPENAI_MODEL, "prompt_version": PROMPT_VERSION, "git_sha": sha},
        max_concurrency=args.max_concurrency,
        client=client,
    )

    rows: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    async for row in results:
        question = row["example"].inputs["question"]
        outputs = (row["run"].outputs or {}) if row["run"] else {}
        scores = {}
        for res in row["evaluation_results"]["results"]:
            scores[res.key] = res.score
            if res.score is not None and res.score < 1:
                failures.append({"question": question, "key": res.key, "comment": res.comment})
        rows.append({"question": question, "outputs": outputs, "scores": scores})

    summary = build_summary(rows, thresholds)
    experiment = results.experiment_name
    markdown = to_markdown(summary, experiment, failures)
    print(markdown)

    Path(args.output).write_text(
        json.dumps({"experiment": experiment, "summary": summary, "failures": failures, "rows": rows},
                   ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
