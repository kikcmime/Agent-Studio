from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.contracts import (
    AgentRunCreateRequest,
    AgentCreateRequest,
    AgentDetail,
    AgentSummary,
    AgentUpdateRequest,
    ErrorPayload,
    ErrorResponse,
    SuccessResponse,
)
from app.runners.agent_runner import agent_runner
from app.services.agent_service import agent_service

router = APIRouter(tags=["agents"])


def encode_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.get(
    "/agents",
    response_model=SuccessResponse[list[AgentSummary]],
    responses={404: {"model": ErrorResponse}},
)
def list_agents() -> SuccessResponse[list[AgentSummary]]:
    items = agent_service.list_agents()
    return SuccessResponse(data=items, meta={"total": len(items)})


@router.post(
    "/agents",
    response_model=SuccessResponse[AgentDetail],
    responses={400: {"model": ErrorResponse}},
)
def create_agent(request: AgentCreateRequest) -> SuccessResponse[AgentDetail]:
    return SuccessResponse(data=agent_service.create_agent(request))


@router.get(
    "/agents/{agent_id}",
    response_model=SuccessResponse[AgentDetail],
    responses={404: {"model": ErrorResponse}},
)
def get_agent(agent_id: str) -> SuccessResponse[AgentDetail]:
    agent = agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="agent_not_found", message="agent not found").model_dump())
    return SuccessResponse(data=agent)


@router.put(
    "/agents/{agent_id}",
    response_model=SuccessResponse[AgentDetail],
    responses={404: {"model": ErrorResponse}},
)
def update_agent(agent_id: str, request: AgentUpdateRequest) -> SuccessResponse[AgentDetail]:
    agent = agent_service.update_agent(agent_id, request)
    if not agent:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="agent_not_found", message="agent not found").model_dump())
    return SuccessResponse(data=agent)


@router.post(
    "/agents/{agent_id}/runs/stream",
    responses={404: {"model": ErrorResponse}},
)
def stream_agent_run(agent_id: str, request: AgentRunCreateRequest) -> StreamingResponse:
    agent = agent_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="agent_not_found", message="agent not found").model_dump())

    def event_stream():
        run_id = f"agent_run_{uuid4().hex[:12]}"
        yield encode_sse("run.started", {"run_id": run_id, "agent_id": agent_id, "status": "running"})
        yield encode_sse("step.started", {"run_id": run_id, "node_id": agent_id, "node_type": "agent"})

        try:
            output = agent_runner.run(agent, request.input)
        except Exception as exc:
            yield encode_sse("step.failed", {"run_id": run_id, "agent_id": agent_id, "error": str(exc)})
            yield encode_sse("run.failed", {"run_id": run_id, "status": "failed", "error": str(exc)})
            return

        yield encode_sse(
            "step.completed",
            {"run_id": run_id, "node_id": agent_id, "node_type": "agent", "status": "completed", "output": output},
        )
        yield encode_sse(
            "run.completed",
            {"run_id": run_id, "agent_id": agent_id, "status": "completed", "output": output},
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
