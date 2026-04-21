from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

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
    ModelConfig,
    Position,
    RetryPolicy,
    RunDetail,
    RunEvent,
    RunStepResult,
    StartNode,
    StartNodeData,
)


def utcnow() -> datetime:
    return datetime.utcnow()


def normalize_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[str]:
    return value if isinstance(value, list) else []


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = normalize_dsn(dsn)
        self.init_schema()
        self.seed_if_empty()

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def init_schema(self) -> None:
        schema_path = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
        with self.connect() as conn:
            conn.execute(schema_path.read_text())

    def seed_if_empty(self) -> None:
        with self.connect() as conn:
            row = conn.execute("select count(*) as total from agents").fetchone()
            if row and row["total"]:
                return

        agent = AgentDetail(
            id="agent_demo",
            name="Triage Agent",
            description="Seed agent for frontend integration",
            source_type=AgentSourceType.USER_DEFINED,
            owner_user_id="demo_user",
            role="Classify and normalize user requests",
            system_prompt="You are a triage agent.",
            instructions="Return normalized task information as JSON.",
            llm_config=ModelConfig(provider="openai-compatible", model="gpt-4.1-mini", temperature=0.2),
            tool_ids=["tool_search"],
            skill_ids=["skill_triage"],
            knowledge_ids=["kb_support"],
            input_schema={"type": "object", "properties": {"user_message": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"task_type": {"type": "string"}}},
            retry_policy=RetryPolicy(),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self._insert_agent(agent)

        definition = FlowDefinition(
            nodes=[
                StartNode(id="node_start", type="start", position=Position(x=120, y=180), data=StartNodeData(label="Start")),
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
                EndNode(id="node_end", type="end", position=Position(x=620, y=180), data=EndNodeData(label="End")),
            ],
            edges=[
                FlowEdge(id="edge_demo_01", source="node_start", target="node_agent_1"),
                FlowEdge(id="edge_demo_02", source="node_agent_1", target="node_end"),
            ],
        )
        self.create_flow(
            FlowCreateRequest(
                name="Demo Flow",
                description="Seed response for frontend integration",
                owner_user_id="demo_user",
                definition=definition,
            ),
            flow_id="flow_demo",
        )

    def _row_to_agent(self, row: dict[str, Any]) -> AgentDetail:
        return AgentDetail(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            source_type=row["source_type"],
            owner_user_id=row["owner_user_id"],
            workspace_id=row["workspace_id"],
            role=row["role"],
            status=row["status"],
            stream=row["stream"],
            debug=row["debug"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            system_prompt=row["system_prompt"],
            instructions=row["instructions"],
            llm_config=ModelConfig(
                provider=row["model_provider"],
                model=row["model_name"],
                temperature=as_dict(row["model_config_json"]).get("temperature"),
                extra=as_dict(row["model_config_json"]).get("extra", {}),
            ),
            tool_ids=as_list(row["tool_ids_json"]),
            skill_ids=as_list(row["skill_ids_json"]),
            knowledge_ids=as_list(row["knowledge_ids_json"]),
            input_schema=as_dict(row["input_schema_json"]),
            output_schema=as_dict(row["output_schema_json"]),
            timeout_seconds=row["timeout_seconds"],
            retry_policy=RetryPolicy(**as_dict(row["retry_policy_json"])),
            version=row["version"],
        )

    def _insert_agent(self, agent: AgentDetail) -> AgentDetail:
        config = {
            "temperature": agent.llm_config.temperature,
            "extra": agent.llm_config.extra,
        }
        with self.connect() as conn:
            conn.execute(
                """
                insert into agents (
                  id, name, description, source_type, owner_user_id, workspace_id, role,
                  system_prompt, instructions, model_provider, model_name, model_config_json,
                  input_schema_json, output_schema_json, tool_ids_json, skill_ids_json,
                  knowledge_ids_json, timeout_seconds, retry_policy_json, version, status,
                  stream, debug, created_at, updated_at
                ) values (
                  %(id)s, %(name)s, %(description)s, %(source_type)s, %(owner_user_id)s, %(workspace_id)s, %(role)s,
                  %(system_prompt)s, %(instructions)s, %(model_provider)s, %(model_name)s, %(model_config_json)s,
                  %(input_schema_json)s, %(output_schema_json)s, %(tool_ids_json)s, %(skill_ids_json)s,
                  %(knowledge_ids_json)s, %(timeout_seconds)s, %(retry_policy_json)s, %(version)s, %(status)s,
                  %(stream)s, %(debug)s, %(created_at)s, %(updated_at)s
                )
                on conflict (id) do nothing
                """,
                {
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "source_type": agent.source_type.value,
                    "owner_user_id": agent.owner_user_id,
                    "workspace_id": agent.workspace_id,
                    "role": agent.role,
                    "system_prompt": agent.system_prompt,
                    "instructions": agent.instructions,
                    "model_provider": agent.llm_config.provider,
                    "model_name": agent.llm_config.model,
                    "model_config_json": to_json(config),
                    "input_schema_json": to_json(agent.input_schema),
                    "output_schema_json": to_json(agent.output_schema),
                    "tool_ids_json": to_json(agent.tool_ids),
                    "skill_ids_json": to_json(agent.skill_ids),
                    "knowledge_ids_json": to_json(agent.knowledge_ids),
                    "timeout_seconds": agent.timeout_seconds,
                    "retry_policy_json": to_json(agent.retry_policy.model_dump()),
                    "version": agent.version,
                    "status": agent.status,
                    "stream": agent.stream,
                    "debug": agent.debug,
                    "created_at": agent.created_at,
                    "updated_at": agent.updated_at,
                },
            )
        return agent

    def list_agents(self) -> list[AgentDetail]:
        with self.connect() as conn:
            rows = conn.execute("select * from agents order by updated_at desc").fetchall()
        return [self._row_to_agent(row) for row in rows]

    def get_agent(self, agent_id: str) -> AgentDetail | None:
        with self.connect() as conn:
            row = conn.execute("select * from agents where id = %s", (agent_id,)).fetchone()
        return self._row_to_agent(row) if row else None

    def create_agent(self, request: AgentCreateRequest) -> AgentDetail:
        now = utcnow()
        agent = AgentDetail(
            id=f"agent_{uuid4().hex[:12]}",
            version=1,
            created_at=now,
            updated_at=now,
            **request.model_dump(),
        )
        return self._insert_agent(agent)

    def update_agent(self, agent_id: str, request: AgentUpdateRequest) -> AgentDetail | None:
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        updated = agent.model_copy(update={**request.model_dump(exclude_none=True), "updated_at": utcnow(), "version": agent.version + 1})
        config = {"temperature": updated.llm_config.temperature, "extra": updated.llm_config.extra}
        with self.connect() as conn:
            conn.execute(
                """
                update agents set
                  name=%(name)s, description=%(description)s, role=%(role)s,
                  system_prompt=%(system_prompt)s, instructions=%(instructions)s,
                  model_provider=%(model_provider)s, model_name=%(model_name)s, model_config_json=%(model_config_json)s,
                  input_schema_json=%(input_schema_json)s, output_schema_json=%(output_schema_json)s,
                  tool_ids_json=%(tool_ids_json)s, skill_ids_json=%(skill_ids_json)s, knowledge_ids_json=%(knowledge_ids_json)s,
                  timeout_seconds=%(timeout_seconds)s, retry_policy_json=%(retry_policy_json)s, version=%(version)s,
                  status=%(status)s, stream=%(stream)s, debug=%(debug)s, updated_at=%(updated_at)s
                where id=%(id)s
                """,
                {
                    "id": updated.id,
                    "name": updated.name,
                    "description": updated.description,
                    "role": updated.role,
                    "system_prompt": updated.system_prompt,
                    "instructions": updated.instructions,
                    "model_provider": updated.llm_config.provider,
                    "model_name": updated.llm_config.model,
                    "model_config_json": to_json(config),
                    "input_schema_json": to_json(updated.input_schema),
                    "output_schema_json": to_json(updated.output_schema),
                    "tool_ids_json": to_json(updated.tool_ids),
                    "skill_ids_json": to_json(updated.skill_ids),
                    "knowledge_ids_json": to_json(updated.knowledge_ids),
                    "timeout_seconds": updated.timeout_seconds,
                    "retry_policy_json": to_json(updated.retry_policy.model_dump()),
                    "version": updated.version,
                    "status": updated.status,
                    "stream": updated.stream,
                    "debug": updated.debug,
                    "updated_at": updated.updated_at,
                },
            )
        return updated

    def _row_to_flow(self, row: dict[str, Any]) -> FlowVersionDetail:
        return FlowVersionDetail(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            owner_user_id=row["owner_user_id"],
            workspace_id=row["workspace_id"],
            status=row["status"],
            latest_version=row["latest_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            definition=FlowDefinition(**row["definition_json"]),
        )

    def list_flows(self) -> list[FlowVersionDetail]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select f.*, fv.definition_json
                from flows f
                join flow_versions fv on fv.flow_id = f.id and fv.version = f.latest_version
                order by f.updated_at desc
                """
            ).fetchall()
        return [self._row_to_flow(row) for row in rows]

    def get_flow(self, flow_id: str) -> FlowVersionDetail | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select f.*, fv.definition_json
                from flows f
                join flow_versions fv on fv.flow_id = f.id and fv.version = f.latest_version
                where f.id = %s
                """,
                (flow_id,),
            ).fetchone()
        return self._row_to_flow(row) if row else None

    def create_flow(self, request: FlowCreateRequest, flow_id: str | None = None) -> FlowVersionDetail:
        now = utcnow()
        flow = FlowVersionDetail(
            id=flow_id or f"flow_{uuid4().hex[:12]}",
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
        version_id = f"flow_version_{uuid4().hex[:12]}"
        with self.connect() as conn:
            conn.execute(
                """
                insert into flows (id, name, description, owner_user_id, workspace_id, status, latest_version, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (id) do nothing
                """,
                (
                    flow.id,
                    flow.name,
                    flow.description,
                    flow.owner_user_id,
                    flow.workspace_id,
                    flow.status.value,
                    flow.latest_version,
                    flow.created_at,
                    flow.updated_at,
                ),
            )
            conn.execute(
                """
                insert into flow_versions (id, flow_id, version, status, definition_json, created_at)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (flow_id, version) do nothing
                """,
                (version_id, flow.id, 1, flow.status.value, to_json(flow.definition.model_dump(mode="json")), now),
            )
        return flow

    def get_run(self, run_id: str) -> RunDetail | None:
        with self.connect() as conn:
            run = conn.execute(
                """
                select r.*, fv.version as flow_version
                from runs r
                join flow_versions fv on fv.id = r.flow_version_id
                where r.id = %s
                """,
                (run_id,),
            ).fetchone()
            if not run:
                return None
            steps = conn.execute("select * from run_steps where run_id = %s order by step_index asc", (run_id,)).fetchall()
            events = conn.execute("select * from run_events where run_id = %s order by created_at asc", (run_id,)).fetchall()

        return RunDetail(
            id=run["id"],
            flow_id=run["flow_id"],
            flow_version=run.get("flow_version") or 1,
            status=run["status"],
            input=as_dict(run["input_json"]),
            output=as_dict(run["output_json"]),
            started_at=run["started_at"],
            finished_at=run["finished_at"],
            steps=[
                RunStepResult(
                    id=step["id"],
                    node_id=step["node_id"],
                    node_type=step["node_type"],
                    status=step["status"],
                    started_at=step["started_at"],
                    finished_at=step["finished_at"],
                    input=as_dict(step["input_json"]),
                    output=as_dict(step["output_json"]),
                    error=step["error_message"],
                )
                for step in steps
            ],
            events=[
                RunEvent(
                    id=event["id"],
                    run_id=event["run_id"],
                    event_type=event["event_type"],
                    created_at=event["created_at"],
                    payload=as_dict(event["event_payload"]),
                )
                for event in events
            ],
        )

    def save_run(self, run: RunDetail) -> None:
        with self.connect() as conn:
            version_row = conn.execute(
                "select id from flow_versions where flow_id = %s and version = %s",
                (run.flow_id, run.flow_version),
            ).fetchone()
            if not version_row:
                return
            conn.execute(
                """
                insert into runs (
                  id, flow_id, flow_version_id, status, input_json, output_json,
                  started_at, finished_at, created_at, updated_at
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (id) do nothing
                """,
                (
                    run.id,
                    run.flow_id,
                    version_row["id"],
                    run.status.value if hasattr(run.status, "value") else run.status,
                    to_json(run.input),
                    to_json(run.output),
                    run.started_at,
                    run.finished_at,
                    run.started_at or utcnow(),
                    run.finished_at or utcnow(),
                ),
            )
            for index, step in enumerate(run.steps):
                conn.execute(
                    """
                    insert into run_steps (
                      id, run_id, node_id, node_type, step_index, status, input_json,
                      output_json, error_message, started_at, finished_at, created_at, updated_at
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (id) do nothing
                    """,
                    (
                        step.id,
                        run.id,
                        step.node_id,
                        step.node_type,
                        index,
                        step.status.value if hasattr(step.status, "value") else step.status,
                        to_json(step.input),
                        to_json(step.output),
                        step.error,
                        step.started_at,
                        step.finished_at,
                        step.started_at or utcnow(),
                        step.finished_at or utcnow(),
                    ),
                )
            for event in run.events:
                conn.execute(
                    """
                    insert into run_events (id, run_id, event_type, event_payload, created_at)
                    values (%s, %s, %s, %s, %s)
                    on conflict (id) do nothing
                    """,
                    (event.id, run.id, event.event_type, to_json(event.payload), event.created_at or utcnow()),
                )
