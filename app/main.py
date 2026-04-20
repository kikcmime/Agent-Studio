from fastapi import FastAPI

from app.api.agent_routes import router as agent_router
from app.api.flow_routes import router as flow_router
from app.api.run_routes import router as run_router

app = FastAPI(title="Agent Studio API", version="0.3.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(agent_router, prefix="/api/v1")
app.include_router(flow_router, prefix="/api/v1")
app.include_router(run_router, prefix="/api/v1")

