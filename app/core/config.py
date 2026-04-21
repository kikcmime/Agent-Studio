from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


def load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "dev")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "memory")
    postgres_dsn: str | None = os.getenv("POSTGRES_DSN")
    default_llm_provider: str = os.getenv("DEFAULT_LLM_PROVIDER", "openai-compatible")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_default_model: str | None = os.getenv("OPENAI_DEFAULT_MODEL")

    openai_compatible_base_url: str | None = os.getenv("OPENAI_COMPATIBLE_BASE_URL")
    openai_compatible_api_key: str | None = os.getenv("OPENAI_COMPATIBLE_API_KEY")
    openai_compatible_default_model: str | None = os.getenv("OPENAI_COMPATIBLE_DEFAULT_MODEL")
    cors_allow_origins: list[str] = [
        item.strip()
        for item in os.getenv(
            "CORS_ALLOW_ORIGINS",
            "http://127.0.0.1:4000,http://localhost:4000",
        ).split(",")
        if item.strip()
    ]


settings = Settings()
