from fastapi import APIRouter, HTTPException

from app.schemas.contracts import (
    ErrorPayload,
    ErrorResponse,
    RunCreateRequest,
    RunDetail,
    RunSummary,
    SuccessResponse,
)
from app.services.run_service import run_service

router = APIRouter(tags=["runs"])


@router.post(
    "/flows/{flow_id}/runs",
    response_model=SuccessResponse[RunSummary],
    responses={404: {"model": ErrorResponse}},
)
def create_run(flow_id: str, request: RunCreateRequest) -> SuccessResponse[RunSummary]:
    summary = run_service.create_run(flow_id, request)
    if not summary:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="flow_not_found", message="flow not found").model_dump())
    return SuccessResponse(data=summary)


@router.get(
    "/runs/{run_id}",
    response_model=SuccessResponse[RunDetail],
    responses={404: {"model": ErrorResponse}},
)
def get_run_detail(run_id: str) -> SuccessResponse[RunDetail]:
    run = run_service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="run_not_found", message="run not found").model_dump())
    return SuccessResponse(data=run)

