from decouple import config

LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")

DATABASE_URL: str = config("DATABASE_URL", default="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres")

