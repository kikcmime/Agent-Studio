from app.repositories.factory import get_store
from app.schemas.contracts import FlowCreateRequest, FlowSummary, FlowUpdateRequest, FlowVersionDetail


class FlowService:
    def list_flows(self) -> list[FlowSummary]:
        store = get_store()
        return [FlowSummary(**item.model_dump(exclude={"definition"})) for item in store.list_flows()]

    def get_flow(self, flow_id: str) -> FlowVersionDetail | None:
        store = get_store()
        return store.get_flow(flow_id)

    def create_flow(self, request: FlowCreateRequest) -> FlowVersionDetail:
        store = get_store()
        return store.create_flow(request)

    def update_flow(self, flow_id: str, request: FlowUpdateRequest) -> FlowVersionDetail | None:
        store = get_store()
        return store.update_flow(flow_id, request)


flow_service = FlowService()
