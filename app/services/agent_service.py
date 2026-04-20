from app.repositories.factory import get_store
from app.schemas.contracts import AgentCreateRequest, AgentDetail, AgentSummary, AgentUpdateRequest


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


agent_service = AgentService()
