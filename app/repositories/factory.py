from app.core.config import settings
from app.repositories.in_memory import InMemoryStore, store


def get_store() -> InMemoryStore:
    if settings.storage_backend == "postgres":
        # PostgreSQL repository wiring will be added in the next phase.
        # For now, fall back to the in-memory implementation to keep the app usable.
        return store
    return store

