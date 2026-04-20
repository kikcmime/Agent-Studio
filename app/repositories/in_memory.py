from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.schemas.contracts import (
    AgentBinding,
    AgentCreateRequest,
    AgentDetail,
    AgentNode,
    AgentNodeData,
    AgentSourceType,
    AgentUpdateRequest,
    EndNode,
    EndNodeData,
    FlowCreateRequest,
    FlowDefinition,
    FlowEdge,
    FlowStatus,
    FlowVersionDetail,
    Position,
    RunCreateRequest,
    RunDetail,
    RunEvent,
    RunStatus,
    RunStepResult,
    RunSummary,
    StartNode,
    StartNodeData,
    StepStatus,
)


def utcnow() -> datetime:
    return datetime.utcnow()


class InMemoryStore:
    def __init__(self) -> None:
        self.agents: dict[str, AgentDetail] = {}
        self.flows: dict[str, FlowVersionDetail] = {}
        self.runs: dict[str, RunDetail] = {}
        self._seed()

    def _seed(self) -> None:
        agent = AgentDetail(
            id="agent_demo",
            name="Triage Agent",
            description="Seed agent for frontend integration",
            source_type=AgentSourceType.USER_DEFINED,
            owner_user_id="demo_user",
            role="Classify and normalize user requests",
            system_prompt="You are a triage agent.",
            instructions="Return normalized task information as JSON.",
            model_config={"provider": "openai-compatible", "model": "gpt-4.1-mini"},
            input_schema={"type": "object", "properties": {"user_message": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"task_type": {"type": "string"}}},
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        definition = FlowDefinition(
            nodes=[
                StartNode(
                    id="node_start",
                    type="start",
                    position=Position(x=120, y=180),
                    data=StartNodeData(label="Start"),
                ),
                AgentNode(
                    id="node_agent_1",
                    type="agent",
                    position=Position(x=360, y=180),
                    data=AgentNodeData(
                        label="Triage Agent",
                        agent_binding=AgentBinding(agent_id=agent.id),
                        input_mapping={"user_message": "{{input.user_message}}"},
                        output_mapping={"triage": "{{output}}"},
                    ),
                ),
                EndNode(
                    id="node_end",
                    type="end",
                    position=Position(x=620, y=180),
                    data=EndNodeData(label="End"),
                ),
            ],
            edges=[
                FlowEdge(id="edge_demo_01", source="node_start", target="node_agent_1"),
                FlowEdge(id="edge_demo_02", source="node_agent_1", target="node_end"),
            ],
        )
        flow = FlowVersionDetail(
            id="flow_demo",
            name="Demo Flow",
            description="Seed response for frontend integration",
            owner_user_id="demo_user",
            status=FlowStatus.DRAFT,
            latest_version=1,
            definition=definition,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self.agents[agent.id] = agent
        self.flows[flow.id] = flow

    def list_agents(self) -> list[AgentDetail]:
        return list(self.agents.values())

    def get_agent(self, agent_id: str) -> AgentDetail | None:
        return self.agents.get(agent_id)

    def create_agent(self, request: AgentCreateRequest) -> AgentDetail:
        now = utcnow()
        agent = AgentDetail(
            id=f"agent_{uuid4().hex[:12]}",
            version=1,
            created_at=now,
            updated_at=now,
            **request.model_dump(),
        )
        self.agents[agent.id] = agent
        return agent

    def update_agent(self, agent_id: str, request: AgentUpdateRequest) -> AgentDetail | None:
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        updated = agent.model_copy(
            update={**request.model_dump(exclude_none=True), "updated_at": utcnow(), "version": agent.version + 1}
        )
        self.agents[agent_id] = updated
        return updated

    def list_flows(self) -> list[FlowVersionDetail]:
        return list(self.flows.values())

    def get_flow(self, flow_id: str) -> FlowVersionDetail | None:
        return self.flows.get(flow_id)

    def create_flow(self, request: FlowCreateRequest) -> FlowVersionDetail:
        now = utcnow()
        flow = FlowVersionDetail(
            id=f"flow_{uuid4().hex[:12]}",
            status=FlowStatus.DRAFT,
            latest_version=1,
            created_at=now,
            updated_at=now,
            name=request.name,
            description=request.description,
            owner_user_id=request.owner_user_id,
            workspace_id=request.workspace_id,
            definition=request.definition,
        )
        self.flows[flow.id] = flow
        return flow

    def get_run(self, run_id: str) -> RunDetail | None:
        return self.runs.get(run_id)

    def create_run(self, flow_id: str, request: RunCreateRequest) -> RunSummary | None:
        flow = self.flows.get(flow_id)
        if not flow:
            return None
        run_id = f"run_{uuid4().hex[:12]}"
        now = utcnow()
        detail = RunDetail(
            id=run_id,
            flow_id=flow_id,
            flow_version=flow.latest_version,
            status=RunStatus.QUEUED,
            input=request.input,
            output={},
            steps=[
                RunStepResult(
                    id=f"step_{uuid4().hex[:10]}",
                    node_id="node_agent_1",
                    node_type="agent",
                    status=StepStatus.PENDING,
                    input=request.input,
                    output={},
                )
            ],
            events=[
                RunEvent(
                    id=f"event_{uuid4().hex[:10]}",
                    run_id=run_id,
                    event_type="run.queued",
                    created_at=now,
                    payload={"flow_id": flow_id},
                )
            ],
        )
        self.runs[run_id] = detail
        return RunSummary(
            id=run_id,
            flow_id=flow_id,
            flow_version=flow.latest_version,
            status=RunStatus.QUEUED,
            created_at=now,
        )


store = InMemoryStore()
