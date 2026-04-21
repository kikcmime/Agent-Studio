from app.core.config import settings
from app.repositories.in_memory import InMemoryStore, store
from app.repositories.postgres import PostgresStore


postgres_store: PostgresStore | None = None


def get_store() -> InMemoryStore | PostgresStore:
    global postgres_store

    if settings.storage_backend == "postgres":
        if not settings.postgres_dsn:
            raise RuntimeError("POSTGRES_DSN is required when STORAGE_BACKEND=postgres")
        if postgres_store is None:
            postgres_store = PostgresStore(settings.postgres_dsn)
        return postgres_store
    return store
