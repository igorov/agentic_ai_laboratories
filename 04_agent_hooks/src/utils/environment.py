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
