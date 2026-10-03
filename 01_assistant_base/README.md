# assistant_base_01

Backend base del curso **Agentes de IA**: un esqueleto limpio y por capas sobre
el que se construye, paso a paso, un asistente conversacional con IA. Es el
punto de partida (el más sencillo) de la serie de backends del repositorio.

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
