"""Prueba de carga del backend con Locust.

Cada usuario virtual simula una conversación: envía preguntas de longitud
variable a /api/chat y mantiene su session_id por 3 turnos (el historial
crece, como en producción). Mide latencia total, throughput y errores,
incluidos 429 del proveedor del LLM que el backend traduce en 5xx.

Al terminar, el proceso sale con exit code 1 si se violan los umbrales
(LOADTEST_MAX_FAILURE_RATIO / LOADTEST_P95_MS): así la prueba puede hacer
fallar un pipeline.

Uso:
  locust -f loadtest/locustfile.py --host https://<servicio>.run.app \
    -u 10 -r 2 -t 3m --headless \
    --csv loadtest/reports/run --html loadtest/reports/run.html

⚠️ Cada request llama al LLM real: la prueba tiene costo de OpenAI/Groq.
"""
import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, events, task

QUESTIONS = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
# Mezcla de tipos de pregunta: mayoría cortas/medias, algunas largas y bloqueos.
QUESTION_WEIGHTS = {"short": 4, "medium": 4, "long": 2, "blocked": 1}
TURNS_PER_SESSION = 3

MAX_FAILURE_RATIO = float(os.getenv("LOADTEST_MAX_FAILURE_RATIO", "0.01"))
P95_MS = float(os.getenv("LOADTEST_P95_MS", "8000"))
CHAT_ENDPOINT_NAME = "/api/chat"


def pick_question() -> str:
    kind = random.choices(list(QUESTION_WEIGHTS), weights=list(QUESTION_WEIGHTS.values()))[0]
    return random.choice(QUESTIONS[kind])


class ChatUser(HttpUser):
    # Tiempo de "lectura" entre mensajes de un usuario real.
    wait_time = between(2, 6)

    def on_start(self):
        # Prefijo loadtest- para filtrar estos traces en LangSmith (metadata user).
        self.user_id = f"loadtest-{random.randint(1, 10_000)}"
        self.session_id = None
        self.turns = 0

    @task(10)
    def chat(self):
        payload = {"question": pick_question(), "user": self.user_id}
        if self.session_id:
            payload["session_id"] = self.session_id

        with self.client.post(CHAT_ENDPOINT_NAME, json=payload, name=CHAT_ENDPOINT_NAME,
                              catch_response=True, timeout=120) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            body = response.json()
            if not body.get("answer") or not body.get("trace_id"):
                response.failure("respuesta sin answer o trace_id")
                return
            response.success()

        self.turns += 1
        self.session_id = None if self.turns % TURNS_PER_SESSION == 0 else body["session_id"]

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")


@events.quitting.add_listener
def enforce_thresholds(environment, **kwargs):
    """Umbrales del pipeline: tasa de fallos y p95 de /api/chat."""
    stats = environment.stats
    chat = stats.get(CHAT_ENDPOINT_NAME, "POST")
    p95 = chat.get_response_time_percentile(0.95) if chat.num_requests else 0
    failure_ratio = stats.total.fail_ratio

    print(f"[thresholds] fail_ratio={failure_ratio:.3%} (máx {MAX_FAILURE_RATIO:.1%}) · "
          f"p95 /api/chat={p95:.0f} ms (máx {P95_MS:.0f} ms)")

    if failure_ratio > MAX_FAILURE_RATIO:
        print("[thresholds] FAIL: tasa de fallos por encima del umbral")
        environment.process_exit_code = 1
    elif p95 > P95_MS:
        print("[thresholds] FAIL: p95 de /api/chat por encima del umbral")
        environment.process_exit_code = 1
    else:
        environment.process_exit_code = 0
