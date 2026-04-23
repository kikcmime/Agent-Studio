from fastapi import APIRouter, HTTPException

from app.schemas.contracts import (
    ErrorPayload,
    ErrorResponse,
    FlowCreateRequest,
    FlowDefinition,
    FlowSummary,
    FlowUpdateRequest,
    FlowVersionDetail,
    SuccessResponse,
)
from app.services.flow_service import flow_service

router = APIRouter(tags=["flows"])


@router.get(
    "/flows",
    response_model=SuccessResponse[list[FlowSummary]],
    responses={404: {"model": ErrorResponse}},
)
def list_flows() -> SuccessResponse[list[FlowSummary]]:
    items = flow_service.list_flows()
    return SuccessResponse(data=items, meta={"total": len(items)})


@router.post(
    "/flows",
    response_model=SuccessResponse[FlowVersionDetail],
    responses={400: {"model": ErrorResponse}},
)
def create_flow(request: FlowCreateRequest) -> SuccessResponse[FlowVersionDetail]:
    return SuccessResponse(data=flow_service.create_flow(request))


@router.put(
    "/flows/{flow_id}",
    response_model=SuccessResponse[FlowVersionDetail],
    responses={404: {"model": ErrorResponse}},
)
def update_flow(flow_id: str, request: FlowUpdateRequest) -> SuccessResponse[FlowVersionDetail]:
    flow = flow_service.update_flow(flow_id, request)
    if not flow:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="flow_not_found", message="flow not found").model_dump())
    return SuccessResponse(data=flow)


@router.get(
    "/flows/{flow_id}",
    response_model=SuccessResponse[FlowVersionDetail],
    responses={404: {"model": ErrorResponse}},
)
def get_flow(flow_id: str) -> SuccessResponse[FlowVersionDetail]:
    flow = flow_service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="flow_not_found", message="flow not found").model_dump())
    return SuccessResponse(data=flow)


@router.get(
    "/flows/{flow_id}/versions/latest",
    response_model=SuccessResponse[FlowDefinition],
    responses={404: {"model": ErrorResponse}},
)
def get_latest_flow_version(flow_id: str) -> SuccessResponse[FlowDefinition]:
    flow = flow_service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=ErrorPayload(code="flow_not_found", message="flow not found").model_dump())
    return SuccessResponse(data=flow.definition, meta={"flow_id": flow_id, "version": flow.latest_version})
