from __future__ import annotations

from collections.abc import Iterator

from app.core.llm import invoke_agent_llm, stream_agent_llm
from app.schemas.contracts import AgentDetail


class AgentRunner:
    """Runtime wrapper for a single agent node."""

    def run(self, agent: AgentDetail, resolved_input: dict) -> dict:
        return invoke_agent_llm(agent, resolved_input)

    def stream(self, agent: AgentDetail, resolved_input: dict) -> Iterator[dict]:
        return stream_agent_llm(agent, resolved_input)


agent_runner = AgentRunner()
