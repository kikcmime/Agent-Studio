from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.contracts import (
    ErrorPayload,
    ErrorResponse,
    SuccessResponse,
    TeamCreateRequest,
    TeamDetail,
    TeamSummary,
    TeamUpdateRequest,
)
from app.services.team_service import team_service

router = APIRouter(tags=["teams"])


@router.get(
    "/teams",
    response_model=SuccessResponse[list[TeamSummary]],
    responses={404: {"model": ErrorResponse}},
)
def list_teams() -> SuccessResponse[list[TeamSummary]]:
    items = team_service.list_teams()
    return SuccessResponse(data=items, meta={"total": len(items)})


@router.post(
    "/teams",
    response_model=SuccessResponse[TeamDetail],
    responses={400: {"model": ErrorResponse}},
)
def create_team(request: TeamCreateRequest) -> SuccessResponse[TeamDetail]:
    return SuccessResponse(data=team_service.create_team(request))


@router.get(
    "/teams/{team_id}",
    response_model=SuccessResponse[TeamDetail],
    responses={404: {"model": ErrorResponse}},
)
def get_team(team_id: str) -> SuccessResponse[TeamDetail]:
    team = team_service.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="team_not_found", message="team not found").model_dump())
    return SuccessResponse(data=team)


@router.put(
    "/teams/{team_id}",
    response_model=SuccessResponse[TeamDetail],
    responses={404: {"model": ErrorResponse}},
)
def update_team(team_id: str, request: TeamUpdateRequest) -> SuccessResponse[TeamDetail]:
    team = team_service.update_team(team_id, request)
    if not team:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="team_not_found", message="team not found").model_dump())
    return SuccessResponse(data=team)
