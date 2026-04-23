from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_routes import router as agent_router
from app.api.flow_routes import router as flow_router
from app.api.run_routes import router as run_router
from app.api.team_routes import router as team_router
from app.core.config import settings

app = FastAPI(title="Agent Studio API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(agent_router, prefix="/api/v1")
app.include_router(team_router, prefix="/api/v1")
app.include_router(flow_router, prefix="/api/v1")
app.include_router(run_router, prefix="/api/v1")
