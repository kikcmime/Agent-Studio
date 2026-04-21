from app.repositories.factory import get_store
from app.runners.flow_runner import flow_runner
from app.schemas.contracts import RunCreateRequest, RunDetail, RunSummary


class RunService:
    def create_run(self, flow_id: str, request: RunCreateRequest) -> RunSummary | None:
        store = get_store()
        result = flow_runner.run_flow(flow_id, request)
        if result is None:
            return None
        if hasattr(store, "save_run"):
            store.save_run(result)
        else:
            store.runs[result.id] = result
        return RunSummary(
            id=result.id,
            flow_id=result.flow_id,
            flow_version=result.flow_version,
            status=result.status,
            created_at=result.started_at,
        )

    def get_run(self, run_id: str) -> RunDetail | None:
        store = get_store()
        return store.get_run(run_id)


run_service = RunService()
