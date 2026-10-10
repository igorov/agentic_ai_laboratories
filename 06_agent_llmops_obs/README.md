# 06_agent_llmops_obs

Backend del curso **Agentes de IA** que extiende `05_agent_guardrails` (agente
con tools locales, retrieval en Qdrant, MCP de Neon, skills, hooks y 8 capas de
guardrails) con **LLMOps y observabilidad**: tracing con LangSmith, feedback
humano, prompts versionados con evaluación offline, CI/CD con canary en Cloud
Run, prueba de carga y SLOs.

---

# LLMOps & Observabilidad

```
 Development ──▶ Evaluation ──▶ Staging/Canary ──▶ Production ──▶ Monitoring
 prompts/        evals/          llmops-cd.yml      Cloud Run       LangSmith
 system/v1.md    golden set      smoke + 10%        autoscaling     traces, costo,
                 eval gate (PR)  rollback auto                      online evals, 👍/👎
      ▲                                                                 │
      └──────────────── feedback negativo → golden set ◀────────────────┘
```

| Pieza | Dónde | Documentación |
|---|---|---|
| Tracing (traces, spans, tokens, costo) | `src/services/tracing.py`, `AgentService.chat` | abajo |
| Feedback humano 👍/👎 | `POST /api/feedback`, columnas `is_ok` en `history` | abajo |
| Prompts versionados | `prompts/system/{PROMPT_VERSION}.md` | abajo |
| Evaluación offline (eval gate) | `evals/` | abajo |
| CI/CD (prompt, model e integration CI + canary) | `.github/workflows/llmops-*.yml` | [docs/cicd.md](docs/cicd.md) |
| Prueba de carga | `loadtest/` | [loadtest/README.md](loadtest/README.md) |
| SLOs y error budget | — | [docs/slos.md](docs/slos.md) |
| Online evals y feedback loop | UI de LangSmith | [docs/online_evals.md](docs/online_evals.md) |

## Tracing con LangSmith

Con `LANGSMITH_TRACING=true` y `LANGSMITH_API_KEY`, cada `POST /api/chat`
genera un trace `chat_request` en el proyecto `LANGSMITH_PROJECT`:

```
chat_request (run_id = trace_id de la respuesta)
├── SecretKeysMiddleware.before_agent … LlamaGuardMiddleware.before_agent   # 8 guardrails
├── pre_agent_hook / pre_model_hook
├── model (ChatOpenAI)          ← tokens de entrada/salida y costo
├── tools (retrieve_documents, load_skill, run_sql, …)
├── post_model_hook / post_agent_hook
```

- El `trace_id` se genera **antes** de invocar al agente y se pasa como
  `run_id`: es el mismo en la respuesta de la API, en la tabla `history` y en
  LangSmith.
- Metadata de cada trace: `session_id` (LangSmith agrupa la conversación en
  *Threads*), `user`, `prompt_version`, `model`, `app_version` (revisión de
  Cloud Run) e `is_new_session`.
- **PII**: el cliente de LangSmith usa un *anonymizer* con las REGEX de las
  capas 1 y 5 de los guardrails. Secretos, emails, tarjetas, RUC, celulares y
  DNI salen del servicio como `<SECRET>`, `<EMAIL>`, `<CREDIT_CARD>`, `<RUC>`,
  `<PHONE>` y `<DNI>`, incluso en los mensajes que un guardrail bloqueó.
- Los mensajes de bloqueo de los guardrails llevan `name="guardrail"`: se
  distinguen en el trace y las evals los detectan.

## Feedback humano

```http
POST /api/feedback
{ "trace_id": "…", "is_ok": false, "comment": "El precio no es correcto" }
```

1. Guarda `is_ok`, `feedback_comment` y `feedback_at` en `history` (404 si el
   `trace_id` no existe). La BD es la fuente de verdad.
2. Envía el feedback `user_score` (1 = 👍, 0 = 👎) al trace en LangSmith. Si
   LangSmith falla, solo se registra un warning.

`GET /api/history/{session_id}` devuelve `is_ok` y `feedback_comment`, así el
frontend (`02_agent_app_feedback`) muestra el voto al recargar.

Para una tabla `history` ya existente, ejecuta los `ALTER TABLE` del final de
`setup/database_history.sql`.

## Prompts versionados

El system prompt vive en `prompts/system/{PROMPT_VERSION}.md` (el contexto de
Neon se inyecta en `{neon_context}`). Para cambiarlo:

1. Crea `prompts/system/v2.md` (no edites `v1.md`: es la baseline).
2. Sube `PROMPT_VERSION` en `.env` y en `deploy/cloudrun.env.yaml`.
3. Abre un PR: el **prompt CI** corre el eval gate con la versión nueva.

## Evaluación offline

```bash
python evals/run_evals.py                       # prompt y modelo del .env
python evals/run_evals.py --prompt-version v2   # probar otro prompt
python evals/run_evals.py --model gpt-4.1-mini  # probar otro modelo
```

- `evals/datasets/golden_set.jsonl`: 26 casos (RAG, bloqueos de guardrails,
  skills y fuera de alcance). Se sincroniza como dataset
  `agent-llmops-obs-golden` en LangSmith.
- Evaluadores (`evals/evaluators.py`):

  | Métrica | Tipo | Qué verifica |
  |---|---|---|
  | `guardrail_behavior` | determinista | Bloquea lo que debe y deja pasar lo legítimo |
  | `tool_selection` | determinista | Llamó a la tool esperada |
  | `correctness` | LLM-as-judge | La respuesta coincide con la referencia |
  | `groundedness` | LLM-as-judge | La respuesta está respaldada por los contextos recuperados |

- `evals/thresholds.yaml`: umbrales del gate. Si alguna métrica queda por
  debajo, el script termina con **exit 1** y el PR queda bloqueado.
- Cada ejecución es un experimento en LangSmith
  (`<prompt>-<modelo>-<commit>`), comparable contra los anteriores.

---

# Guardrails (heredado de `05_agent_guardrails`)

## Guardrails

Cada capa es un `AgentMiddleware` con un hook `before_agent`. Las capas corren
en orden estricto 1 → 8. Si una detecta un problema, devuelve un `AIMessage` con
el mensaje de rechazo y `jump_to: "end"`, de modo que **ni las capas
siguientes ni el LLM se ejecutan**. El rechazo llega al usuario como una
respuesta normal del chat (HTTP 200) y se guarda en el historial.

```
mensaje ─▶ C1 ─▶ C2 ─▶ C3 ─▶ C4 ─▶ C5 ─▶ C6 ─▶ C7 ─▶ C8 ─▶ agente (hooks + LLM + tools)
            │     │     │     │     │     │     │     │
            └─────┴─────┴─────┴──┬──┴─────┴─────┴─────┘
                                 ▼
                     bloqueo (jump_to: "end")
```

| # | Capa                 | Archivo (`src/services/guardrails/`) | Técnica                            | Configuración (`config/guardrails/`) |
|---|----------------------|--------------------------------------|------------------------------------|--------------------------------------|
| 1 | Secret keys          | `layer1_secrets.py`                  | REGEX (API keys, tokens, JWT)      | — (patrones en código)               |
| 2 | Prompt injection     | `layer2_prompt_injection.py`         | REGEX ES/EN por categorías         | `prompt_injection_patterns.yaml`     |
| 3 | Toxicidad            | `layer3_toxicity.py`                 | REGEX; mensaje de contención para autolesión | `toxicity_patterns.yaml`   |
| 4 | Reglas de negocio    | `layer4_custom_regex.py`             | librería `regex` con timeout (anti-ReDoS) | `custom_patterns.yaml`        |
| 5 | PII                  | `layer5_pii.py`                      | Presidio + spaCy (`es_core_news_sm`), con respaldo REGEX local; estrategia `block` / `mask` / `off` por entidad | `pii_strategies.yaml` |
| 6 | URLs / phishing      | `layer6_url_filter.py`               | REGEX (URLs con y sin protocolo, acortadores) | `url_blocklist.yaml`      |
| 7 | Llama Prompt Guard 2 | `layer7_prompt_guard.py`             | Clasificador vía Groq (BENIGN / MALICIOUS) | —                            |
| 8 | gpt-oss-safeguard    | `layer8_llama_guard.py`              | Clasificador vía Groq con política propia (taxonomía S1-S13, respuesta JSON) | `llama_guard_categories.yaml` (`skip_categories`) |

- **Capas deterministas (1-4, 6):** sin llamadas externas; respuesta instantánea.
- **Capa 5:** todo el procesamiento es local. Si Presidio o el modelo de spaCy
  no están disponibles, usa automáticamente un detector REGEX equivalente
  (DNI, RUC, celular, email, tarjeta). Con `mask`, el texto se enmascara
  y el mensaje continúa por el pipeline (ej. `987654321` → `98*******`).
- **Capas 7 y 8 (fail-close):** si Groq falla o no responde dentro de
  `GROQ_TIMEOUT_SECONDS`, el mensaje **se bloquea**. Nunca se deja pasar por
  un error de conexión.
- **Auditoría:** cada bloqueo se registra en el log JSON con la capa, el motivo
  y el `message_hash` (sha256). El texto del mensaje nunca se registra en
  texto plano.
- Los YAML de `config/guardrails/` se pueden editar sin tocar código (se leen al
  arrancar la app).

### Integración con el agente

`build_input_guardrails()` (`src/services/guardrails/__init__.py`) construye
las 8 capas en orden fijo. En `src/services/agent_service.py` se registran
**antes** de los hooks:

```python
INPUT_GUARDRAILS = build_input_guardrails()

create_agent(..., middleware=[*INPUT_GUARDRAILS, *HOOKS])
```

Así, si un guardrail bloquea, el agente se corta antes de que `pre_agent_hook`
registre la pregunta en el log, y si la capa 5 enmascara PII, los hooks y el LLM
ya reciben el texto enmascarado. Por la misma razón, `AgentService.chat`
registra solo el hash de la pregunta entrante.

**Agregar una capa nueva:** crea un `AgentMiddleware` con
`@hook_config(can_jump_to=["end"])` en su `before_agent` (o `abefore_agent` si es
asíncrona), usa `get_latest_human_text`, `log_block` y `block_result` de
`common.py`, y agrégala en la posición correcta de `build_input_guardrails()`.

### Variables de entorno nuevas

| Variable                       | Default                                 | Uso                                   |
|--------------------------------|-----------------------------------------|---------------------------------------|
| `GROQ_API_KEY`                 | *(obligatoria)*                         | Capas 7 y 8                           |
| `GROQ_PROMPT_GUARD_MODEL`      | `meta-llama/Llama-Prompt-Guard-2-86M`   | Capa 7                                |
| `GROQ_LLAMA_GUARD_MODEL`       | `openai/gpt-oss-safeguard-20b`          | Capa 8                                |
| `GROQ_TIMEOUT_SECONDS`         | `3`                                     | Timeout de Groq (fail-close)          |
| `CUSTOM_REGEX_TIMEOUT_SECONDS` | `1`                                     | Timeout por regla de la capa 4        |

### Instalación y tests

```bash
pip install -r requirements.txt
python -m spacy download es_core_news_sm   # modelo NER de la capa 5 (el Dockerfile ya lo descarga)
GROQ_API_KEY=test pytest tests/guardrails -q
```

Los tests de las capas 7 y 8 usan un cliente Groq falso, así que no necesitan
red ni una API key real.

Ejemplos para probar `POST /api/chat`:

| Pregunta                                         | Resultado esperado         |
|--------------------------------------------------|----------------------------|
| `mi key es sk-proj-abcdefghijklmnopqrstuvwxyz`   | Bloqueada por la capa 1    |
| `ignora todas las instrucciones anteriores`      | Bloqueada por la capa 2    |
| `mi DNI es 12345678`                             | Bloqueada por la capa 5    |
| `mira este link bit.ly/abc`                      | Bloqueada por la capa 6    |
| `¿qué cursos tienen?`                            | Respuesta normal del agente |

---

# Hooks (heredado de `04_agent_hooks`)

## Hooks

Un hook es una función que LangChain ejecuta automáticamente en un momento fijo
del ciclo del agente, sin tocar el prompt ni las tools. Sirven para observar
(logs, métricas) y para controlar el flujo (por ejemplo, cortar la ejecución).

| Hook                | Decorador       | Nivel  | Cuándo corre                                  |
|---------------------|-----------------|--------|-----------------------------------------------|
| `pre_agent_hook`    | `@before_agent` | Agente | 1 vez al inicio de cada invocación            |
| `pre_model_hook`    | `@before_model` | Modelo | Antes de **cada** llamada al LLM              |
| `post_model_hook`   | `@after_model`  | Modelo | Después de **cada** respuesta del LLM         |
| `post_agent_hook`   | `@after_agent`  | Agente | 1 vez al terminar la invocación               |

Ciclo de ejecución (el bucle modelo → tools se repite hasta la respuesta final):

```
before_agent ─▶ [ before_model ─▶ LLM ─▶ after_model ─▶ tools ]* ─▶ after_agent
```

Están en `src/services/hooks.py` y se registran en `build_agent`
(`src/services/agent_service.py`) con `create_agent(..., middleware=[*INPUT_GUARDRAILS, *HOOKS])`.
Todos escriben en el log en formato JSON, como el resto del API.

### Estado compartido: `HooksState`

Los hooks se comunican entre sí mediante `HooksState`, un estado que extiende
`AgentState` con tres campos opcionales (`NotRequired`, porque no existen al
inicio de la invocación):

| Campo         | Tipo        | Para qué sirve                                   |
|---------------|-------------|--------------------------------------------------|
| `started_at`  | `float`     | Hora de inicio, para calcular la duración total  |
| `model_calls` | `int`       | Cuántas veces se llamó al modelo                 |
| `tools_called`| `list[str]` | Tools que el modelo fue pidiendo                 |

Cuando un hook devuelve un diccionario, sus claves se mezclan con el estado; si
devuelve `None`, no cambia nada.

### `pre_agent_hook` (`@before_agent`)

Corre **una vez** al inicio de cada invocación.

- Busca el último `HumanMessage` (la pregunta actual) y registra la pregunta y
  cuántos mensajes llegaron, incluido el historial.
- Inicializa el estado: `started_at = time.time()`, `model_calls = 0` y
  `tools_called = []`. Es importante porque los demás hooks leen esos campos;
  sin esto, el contador no arrancaría en cero en cada invocación.

### `pre_model_hook` (`@before_model(can_jump_to=["end"])`)

Corre **antes de cada llamada al LLM**. Si la pregunta usa una tool, corre dos
veces.

1. Calcula `model_calls + 1` y lo registra junto con el número de mensajes que
   se enviarán al modelo.
2. Si el valor supera `MAX_MODEL_CALLS` (variable de entorno, 10 por defecto),
   devuelve:
   - un `AIMessage` con "No pude completar la solicitud: se alcanzó el límite de
     pasos", y
   - `jump_to: "end"`, que salta al final sin llamar al modelo.
3. Si no lo supera, guarda el nuevo `model_calls` en el estado.

`can_jump_to=["end"]` declara que este hook puede cortar la ejecución; sin esa
declaración, LangChain no acepta el `jump_to`. Sirve para que un bucle de tools
no se descontrole y consuma tokens sin fin (control de flujo básico, no
seguridad).

### `post_model_hook` (`@after_model`)

Corre **después de cada respuesta del LLM**, antes de ejecutar las tools que
haya pedido.

- Toma el último mensaje del estado, que es la respuesta del modelo
  (`AIMessage`).
- Registra los tokens de entrada y salida de esa llamada (`usage_metadata`) y
  los nombres de las tools que pidió (`tool_calls`).
- Si pidió tools, las agrega a `tools_called`; si no, devuelve `None` y no toca
  el estado.

Con una pregunta que usa una tool, corre dos veces: la primera registra que el
modelo pidió la tool y la segunda que ya no pidió ninguna (dio la respuesta
final).

### `post_agent_hook` (`@after_agent`)

Corre **una vez** cuando el agente termina, con el estado final. Registra un
resumen de toda la invocación: duración (a partir de `started_at`), llamadas al
modelo, tools usadas y largo de la respuesta final. Solo observa, por eso
devuelve `None`. También corre cuando `pre_model_hook` cortó la ejecución, así
que el resumen aparece siempre.

### Orden de ejecución

```
pre_agent → pre_model → LLM → post_model → tools → pre_model → LLM → post_model → post_agent
```

Con varios middleware en la lista, los `before_*` corren en el orden de la
lista y los `after_*` en orden inverso.

> Estos hooks son de observabilidad y control de flujo básico; no son un
> esquema de seguridad.

**Agregar un hook nuevo:** define una función con el decorador correspondiente
y agrégala a la lista `HOOKS`.

---

# Skills (heredado de `03_agent_skills`)

## Skills

Una skill es un conjunto de instrucciones especializadas que el agente no
recibe en el system prompt, sino que carga solo cuando las necesita. Así el
contexto inicial se mantiene pequeño aunque existan muchas skills.

Están definidas en `src/services/skills.py`:

```python
class Skill(TypedDict):
    name: str         # identificador único
    description: str  # 1-2 frases, lo que ve el agente al listar
    content: str      # instrucciones completas (markdown)
```

El agente las usa con dos tools:

| Tool                     | Qué hace                                            |
|--------------------------|-----------------------------------------------------|
| `list_skills()`          | Devuelve el nombre y la descripción de cada skill.  |
| `load_skill(skill_name)` | Devuelve el contenido completo de una skill.        |

Skills incluidas:

- `ficha_matricula`: datos, validaciones y plantilla para matricular a un
  alumno en un programa.
- `solicitud_certificado`: requisitos, datos y plantilla para pedir un
  certificado de aprobación o una constancia de estudios.

Flujo: el usuario pide un trámite → el agente llama a `list_skills` → elige la
skill y llama a `load_skill` → sigue sus instrucciones (incluido usar
`retrieve_documents` para validar el programa) → devuelve la ficha o
solicitud para que el usuario la confirme.

> El historial que se reenvía al agente solo guarda preguntas y respuestas,
> no los resultados de las tools. Por eso el system prompt le pide volver a
> cargar la skill en cada turno de un trámite en curso.

**Agregar una skill nueva:** agrega un diccionario `Skill` a la lista `SKILLS`.
No hace falta tocar las tools ni el prompt.

---

## ¿Qué hace este backend?

Un servicio HTTP (API REST) que expone un asistente/agente de IA capaz de:

- Recibir preguntas de un usuario y devolver una respuesta.
- Persistir cada interacción (pregunta, respuesta, tokens, contexto) en una
  base de datos PostgreSQL.
- Consultar el historial de una conversación y listar las sesiones de un
  usuario.

El proyecto está pensado como un **esqueleto limpio y por capas** sobre el que
en cada sesión se va agregando la lógica del agente (LLM, recuperación de
contexto con Qdrant, etc.).

---

## Stack tecnológico

| Componente        | Tecnología                          |
|-------------------|-------------------------------------|
| Lenguaje          | Python 3.11                         |
| Framework web     | FastAPI                             |
| Servidor ASGI     | Uvicorn                             |
| ORM               | SQLAlchemy 2.x                      |
| Base de datos     | PostgreSQL (Neon)                   |
| Validación        | Pydantic 2.x                        |
| Config / entorno  | python-decouple                     |
| Logging           | python-json-logger (logs en JSON)   |
| LLM / Vector DB   | OpenAI · Qdrant *(se integra durante el curso)* |
| Despliegue        | Docker + GCP Cloud Run              |
| Observabilidad    | LangSmith (tracing, feedback, evals)  |
| CI/CD             | GitHub Actions (WIF → Cloud Run)    |
| Carga             | Locust                              |

---

## Arquitectura por capas

El backend sigue una **arquitectura en capas** con inyección de dependencias,
lo que separa responsabilidades y facilita las pruebas:

```
HTTP  ──▶  Routes  ──▶  Controllers  ──▶  Services  ──▶  Repositories  ──▶  DB
                            │                │                │
                           DTOs            DTOs         Models (ORM)
```

Cada petición fluye de arriba hacia abajo; cada capa solo conoce a la
inmediatamente inferior a través de una abstracción.

### 1. Routes — `src/routes/router.py`
Define los endpoints HTTP y delega en los controllers. Inyecta la sesión de
base de datos (`Depends(get_db)`) y declara los modelos de request/response.

Endpoints expuestos:

| Método | Ruta                       | Descripción                                  |
|--------|----------------------------|----------------------------------------------|
| `POST` | `/api/chat`                | Envía una pregunta y obtiene la respuesta.   |
| `GET`  | `/api/history/{session_id}`| Devuelve el historial de una sesión.         |
| `GET`  | `/api/sessions/{user}`     | Lista las sesiones de un usuario.            |
| `POST` | `/api/feedback`            | Registra 👍/👎 de una respuesta (BD + LangSmith). |
| `GET`  | `/health`                  | Estado, versión del prompt, modelo y revisión. |

### 2. Controllers — `src/controllers/`
Orquestan cada caso de uso: validan la entrada, **instancian el repositorio y
el servicio concretos** (inyección de dependencias manual) y traducen los
errores a respuestas HTTP (`HTTPException` 422 / 500).

- `chat_controller.py` → `handle_chat(...)`
- `history_controller.py` → `handle_get_history(...)`, `handle_get_sessions_by_user(...)`
- `feedback_controller.py` → `handle_feedback(...)`

### 3. Services — `src/services/`
Contienen la **lógica de negocio**. Reciben un repositorio por constructor y no
saben nada de HTTP ni de SQLAlchemy.

- `AgentService` — corazón del asistente. Genera la respuesta del agente
  (hoy devuelve un texto fijo; **aquí se integra el LLM durante el curso**),
  crea/gestiona el `session_id` y guarda la interacción vía el repositorio.
- `HistoryService` — consultas del historial: por sesión, por `trace_id` y
  las sesiones de un usuario.

### 4. Repositories — `src/repositories/`
Abstraen el acceso a datos siguiendo el patrón **Repository** (interfaz +
implementación):

- `history_repository.py` — clase abstracta `HistoryRepository` (contrato con
  `save`, `get_by_trace_id`, `get_by_session_id`, `get_all_by_session_id`,
  `get_sessions_by_user`).
- `impl/history_repository_impl.py` — `HistoryRepositoryImpl`, la
  implementación con SQLAlchemy. Convierte entre DTO ↔ modelo ORM
  (`_to_dto` / `_to_model`).
- `models/history.py` — modelo ORM `History` (tabla `history`).
- `__init__.py` — configura el `engine`, `SessionLocal` y el proveedor de
  sesión `get_db()`.

### 5. DTOs — `src/dto/`
Objetos de transferencia validados con Pydantic, para no exponer los modelos
ORM directamente:

- `api_entities.py` — contratos de la API: `ChatRequest`, `ChatResponse`,
  `HistoryItem`, `UserSessionsResponse`.
- `history_dto.py` — `HistoryDTO`, usado entre servicios y repositorios.

### 6. Utils — `src/utils/`
- `environment.py` — carga y centraliza las variables de entorno.
- `logger.py` — logger con salida en formato JSON.

---

## Modelo de datos (`history`)

Cada interacción se guarda en la tabla `history`:

| Campo                | Tipo        | Notas                          |
|----------------------|-------------|--------------------------------|
| `trace_id`           | UUID (PK)   | Identificador único de la interacción |
| `session_id`         | UUID        | Agrupa las interacciones de una conversación |
| `question`           | Text        | Pregunta del usuario           |
| `answer`             | Text        | Respuesta del agente           |
| `user`               | String      | Identificador del usuario      |
| `input_tokens`       | Integer     | Tokens de entrada (opcional)   |
| `output_tokens`      | Integer     | Tokens de salida (opcional)    |
| `retrieved_contexts` | Text        | Contexto recuperado (RAG)      |
| `created_at`         | DateTime    | Fecha/hora de la interacción   |
| `is_ok`              | Boolean     | Feedback: true 👍, false 👎, null sin voto |
| `feedback_comment`   | Text        | Comentario opcional del feedback |
| `feedback_at`        | DateTime    | Fecha/hora del último feedback |

---

## Variables de entorno

Copia `.env.example` a `.env` y complétalo:

```env
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql://user:password@host:5432/dbname
OPENAI_API_KEY=
QDRANT_URL=
QDRANT_KEY=
QDRANT_COLLECTION_NAME=
GROQ_API_KEY=

# LLMOps
PROMPT_VERSION=v1
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=agent-llmops-obs
```

La lista completa está en `.env.example`.

---

## Ejecución local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y completa los valores
python -m src.main
```

El servicio queda disponible en `http://localhost:8080`
(documentación interactiva en `http://localhost:8080/docs`).

### Con Docker

```bash
docker build -t agent-llmops-obs .
docker run --name agent-llmops-obs -p 8080:8080 --env-file .env agent-llmops-obs
```

---

## Despliegue en GCP Cloud Run

El despliegue a producción lo hace el **CD con GitHub Actions** (canary +
rollback): ver [docs/cicd.md](docs/cicd.md). Los scripts manuales siguen
disponibles para pruebas.

En `scripts/` hay scripts que automatizan todo el flujo (construir imagen →
push al Artifact Registry → deploy en Cloud Run, leyendo las variables del
`.env`):

- `deploy.sh` — Linux / macOS
- `deploy.ps1` — Windows (PowerShell, **recomendado**)
- `deploy.bat` — Windows (CMD, alternativa)

Antes de ejecutar, edita las variables al inicio del script
(`REGION`, `REPOSITORY`, `SERVICE`, `PROJECT_ID`) y asegúrate de tener
`gcloud` autenticado y Docker en ejecución.

```bash
# Linux / macOS
cd scripts
./deploy.sh
```

```powershell
# Windows
cd scripts
powershell -ExecutionPolicy Bypass -File .\deploy.ps1
```

---

## Estructura del proyecto

```
06_agent_llmops_obs/
├── Dockerfile
├── requirements.txt
├── .env.example
├── config/guardrails/    # configuración versionada de los guardrails
├── deploy/               # cloudrun.env.yaml (variables no secretas de Cloud Run)
├── docs/                 # cicd.md, slos.md, online_evals.md
├── evals/                # golden set, evaluadores, umbrales y run_evals.py
├── loadtest/             # prueba de carga con Locust
├── notebooks/            # laboratorios por sesión (Jupyter)
├── prompts/system/       # system prompt versionado (v1.md, …)
├── scripts/              # deploy manual, setup de GCP para CI/CD, smoke test
├── tests/                # pytest (guardrails, feedback, prompts, tracing)
└── src/
    ├── main.py           # arranque de la app FastAPI
    ├── routes/           # definición de endpoints
    ├── controllers/      # orquestación de casos de uso
    ├── services/         # lógica de negocio (agente e historial)
    ├── repositories/     # acceso a datos (Repository + ORM)
    ├── dto/              # objetos de transferencia (Pydantic)
    ├── docs/             # openapi.yaml
    └── utils/            # entorno y logging
```
