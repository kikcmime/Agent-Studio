from fastapi import APIRouter, HTTPException

from app.schemas.contracts import (
    AgentCreateRequest,
    AgentDetail,
    AgentSummary,
    AgentUpdateRequest,
    ErrorPayload,
    ErrorResponse,
    SuccessResponse,
)
from app.services.agent_service import agent_service

router = APIRouter(tags=["agents"])


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

