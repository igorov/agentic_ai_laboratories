# 04_agent_hooks

Backend del curso **Agentes de IA** que extiende `03_agent_skills` (agente con
tools locales, retrieval en Qdrant, MCP de Neon y skills) con **hooks**: código
propio que se ejecuta en puntos concretos del ciclo del agente, usando el
*middleware* de LangChain.

---

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
(`src/services/agent_service.py`) con `create_agent(..., middleware=HOOKS)`.
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

### 2. Controllers — `src/controllers/`
Orquestan cada caso de uso: validan la entrada, **instancian el repositorio y
el servicio concretos** (inyección de dependencias manual) y traducen los
errores a respuestas HTTP (`HTTPException` 422 / 500).

- `chat_controller.py` → `handle_chat(...)`
- `history_controller.py` → `handle_get_history(...)`, `handle_get_sessions_by_user(...)`

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
```

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
docker build -t assistant-base-01 .
docker run --name assistant-base-01 -p 8080:8080 --env-file .env assistant-base-01
```

---

## Despliegue en GCP Cloud Run

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
assistant_base_01/
├── Dockerfile
├── requirements.txt
├── .env.example
├── notebooks/            # laboratorios por sesión (Jupyter)
├── scripts/              # despliegue a Cloud Run (sh / ps1 / bat)
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
