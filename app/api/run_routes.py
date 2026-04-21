from __future__ import annotations

import json
from collections.abc import Iterable

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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


def encode_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def stream_run_detail(run: RunDetail) -> Iterable[str]:
    yield encode_sse("run.started", {"run_id": run.id, "flow_id": run.flow_id, "status": "running"})

    for event in run.events:
        yield encode_sse(event.event_type, event.model_dump(mode="json"))

    for step in run.steps:
        yield encode_sse(
            "step.completed" if step.status == "completed" else f"step.{step.status}",
            step.model_dump(mode="json"),
        )

    yield encode_sse("run.completed", run.model_dump(mode="json"))


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


@router.post(
    "/flows/{flow_id}/runs/stream",
    responses={404: {"model": ErrorResponse}},
)
def stream_flow_run(flow_id: str, request: RunCreateRequest) -> StreamingResponse:
    summary = run_service.create_run(flow_id, request.model_copy(update={"stream": True}))
    if not summary:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="flow_not_found", message="flow not found").model_dump())

    run = run_service.get_run(summary.id)
    if not run:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="run_not_found", message="run not found").model_dump())

    return StreamingResponse(stream_run_detail(run), media_type="text/event-stream")


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
