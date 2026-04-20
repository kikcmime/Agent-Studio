from __future__ import annotations

from app.schemas.contracts import AgentDetail


class AgentRunner:
    """Minimal agent execution wrapper.

    v1 behavior:
    - does not call a real LLM yet
    - returns a normalized payload so the flow runner can be wired end-to-end
    """

    def run(self, agent: AgentDetail, resolved_input: dict) -> dict:
        message = resolved_input.get("user_message") or resolved_input.get("query") or ""
        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "message": f"{agent.name} processed request",
            "echo_input": resolved_input,
            "normalized_task": message[:120],
        }


agent_runner = AgentRunner()

