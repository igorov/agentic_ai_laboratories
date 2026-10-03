from decouple import config

# Nivel de logs
LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")

# Acceso a la BD
DATABASE_URL: str = config("DATABASE_URL", default="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres")

# OpenAI
OPENAI_API_KEY: str = config("OPENAI_API_KEY")

# Qdrant
QDRANT_URL: str = config("QDRANT_URL")
QDRANT_KEY: str = config("QDRANT_KEY")
QDRANT_COLLECTION_NAME: str = config("QDRANT_COLLECTION_NAME")