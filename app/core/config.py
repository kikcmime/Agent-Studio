from __future__ import annotations

import os

from pydantic import BaseModel


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "dev")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "memory")
    postgres_dsn: str | None = os.getenv("POSTGRES_DSN")


settings = Settings()
