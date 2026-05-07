from app.repositories.factory import get_store
from app.schemas.contracts import AgentCreateRequest, AgentDetail, AgentSummary, AgentUpdateRequest

STUDIO_WRAPPER_MARKER = "__studio_wrapper__"


class AgentService:
    def list_agents(self) -> list[AgentSummary]:
        store = get_store()
        return [AgentSummary(**item.model_dump()) for item in store.list_agents()]

    def get_agent(self, agent_id: str) -> AgentDetail | None:
        store = get_store()
        return store.get_agent(agent_id)

    def create_agent(self, request: AgentCreateRequest) -> AgentDetail:
        store = get_store()
        return store.create_agent(request)

    def update_agent(self, agent_id: str, request: AgentUpdateRequest) -> AgentDetail | None:
        store = get_store()
        return store.update_agent(agent_id, request)

    def delete_agent(self, agent_id: str) -> AgentDetail | None:
        store = get_store()
        agent = store.delete_agent(agent_id)
        if not agent:
            return None

        for flow in store.list_flows():
            if flow.description == f"{STUDIO_WRAPPER_MARKER}:agent:{agent_id}":
                store.delete_flow(flow.id)

        return agent


agent_service = AgentService()
