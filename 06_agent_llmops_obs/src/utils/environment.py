from decouple import config

# Nivel de logs
LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")

# Acceso a la BD
DATABASE_URL: str = config("DATABASE_URL", default="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres")

# OpenAI
OPENAI_API_KEY: str = config("OPENAI_API_KEY")
OPENAI_MODEL: str = config("OPENAI_MODEL", default="gpt-4o-mini")

# Qdrant
QDRANT_URL: str = config("QDRANT_URL")
QDRANT_KEY: str = config("QDRANT_KEY")
QDRANT_COLLECTION_NAME: str = config("QDRANT_COLLECTION_NAME")

# Neon
NEON_API_KEY: str = config("NEON_API_KEY", default=None)
NEON_PROJECT_ID: str = config("NEON_PROJECT_ID", default=None)

HISTORY_LIMIT: int = config("HISTORY_LIMIT", default=10, cast=int)

# Hooks: máximo de llamadas al modelo por invocación del agente
MAX_MODEL_CALLS: int = config("MAX_MODEL_CALLS", default=10, cast=int)

# Guardrails — Capas 7 y 8, servidas vía Groq API
GROQ_API_KEY: str = config("GROQ_API_KEY")
GROQ_PROMPT_GUARD_MODEL: str = config(
    "GROQ_PROMPT_GUARD_MODEL", default="meta-llama/Llama-Prompt-Guard-2-86M"
)
GROQ_LLAMA_GUARD_MODEL: str = config(
    "GROQ_LLAMA_GUARD_MODEL", default="openai/gpt-oss-safeguard-20b"
)
GROQ_TIMEOUT_SECONDS: float = config("GROQ_TIMEOUT_SECONDS", default=3, cast=float)

# Guardrails — Capa 4 (timeout anti-ReDoS por regla, en segundos)
CUSTOM_REGEX_TIMEOUT_SECONDS: float = config("CUSTOM_REGEX_TIMEOUT_SECONDS", default=1, cast=float)

# Prompts versionados: archivo prompts/system/{PROMPT_VERSION}.md
PROMPT_VERSION: str = config("PROMPT_VERSION", default="v1")

# LangSmith (tracing + feedback). El SDK lee LANGSMITH_* desde os.environ.
LANGSMITH_TRACING: bool = config("LANGSMITH_TRACING", default=False, cast=bool)
LANGSMITH_API_KEY: str = config("LANGSMITH_API_KEY", default=None)
LANGSMITH_PROJECT: str = config("LANGSMITH_PROJECT", default="agent-llmops-obs")

# Versión desplegada: Cloud Run expone K_REVISION en cada revisión.
APP_VERSION: str = config("K_REVISION", default="local")
