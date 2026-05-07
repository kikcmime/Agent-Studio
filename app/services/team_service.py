from app.repositories.factory import get_store
from app.schemas.contracts import TeamCreateRequest, TeamDetail, TeamSummary, TeamUpdateRequest

STUDIO_WRAPPER_MARKER = "__studio_wrapper__"


class TeamService:
    def list_teams(self) -> list[TeamSummary]:
        store = get_store()
        return [TeamSummary(**item.model_dump()) for item in store.list_teams()]

    def get_team(self, team_id: str) -> TeamDetail | None:
        store = get_store()
        return store.get_team(team_id)

    def create_team(self, request: TeamCreateRequest) -> TeamDetail:
        store = get_store()
        return store.create_team(request)

    def update_team(self, team_id: str, request: TeamUpdateRequest) -> TeamDetail | None:
        store = get_store()
        return store.update_team(team_id, request)

    def delete_team(self, team_id: str) -> TeamDetail | None:
        store = get_store()
        team = store.delete_team(team_id)
        if not team:
            return None

        for flow in store.list_flows():
            if flow.description == f"{STUDIO_WRAPPER_MARKER}:team:{team_id}":
                store.delete_flow(flow.id)

        return team


team_service = TeamService()
