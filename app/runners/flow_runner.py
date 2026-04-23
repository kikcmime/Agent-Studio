from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.repositories.factory import get_store
from app.runners.agent_runner import agent_runner
from app.schemas.contracts import (
    AgentNode,
    ConditionNode,
    EndNode,
    FlowEdge,
    FlowDefinition,
    RunCreateRequest,
    RunDetail,
    RunEvent,
    RunStatus,
    RunStepResult,
    StartNode,
    StepStatus,
    TeamNode,
)


def utcnow() -> datetime:
    return datetime.utcnow()


class FlowRunner:
    def __init__(self) -> None:
        self.store = get_store()

    def run_flow(self, flow_id: str, request: RunCreateRequest) -> RunDetail | None:
        flow = self.store.get_flow(flow_id)
        if not flow:
            return None

        definition = flow.definition
        node_map = {node.id: node for node in definition.nodes}
        edges_by_source = self._build_edges_by_source(definition.edges)
        current = self._resolve_start_node(definition)
        if current is None:
            return None

        steps: list[RunStepResult] = []
        runtime_context: dict = {"input": request.input, "steps": {}, "retry_counts": {}}
        now = utcnow()
        run_id = f"run_{uuid4().hex[:12]}"
        events: list[RunEvent] = [
            RunEvent(
                id=f"event_{uuid4().hex[:10]}",
                run_id=run_id,
                event_type="run.started",
                created_at=now,
                payload={"flow_id": flow_id, "flow_version": flow.latest_version},
            )
        ]

        step_guard = 0
        while current is not None:
            step_guard += 1
            if step_guard > 200:
                return self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, now, utcnow(), steps, events)

            node = current
            if isinstance(node, StartNode):
                current = self._select_next_node(node.id, edges_by_source, node_map)
                continue
            if isinstance(node, EndNode):
                events.append(
                    RunEvent(
                        id=f"event_{uuid4().hex[:10]}",
                        run_id=run_id,
                        event_type="run.finished",
                        created_at=utcnow(),
                        payload={"end_node_id": node.id},
                    )
                )
                break

            if isinstance(node, AgentNode):
                agent = self.store.get_agent(node.data.agent_binding.agent_id)
                if not agent:
                    failed_at = utcnow()
                    steps.append(
                        RunStepResult(
                            id=f"step_{uuid4().hex[:10]}",
                            node_id=node.id,
                            node_type=node.type,
                            status=StepStatus.FAILED,
                            started_at=now,
                            finished_at=failed_at,
                            input={},
                            output={},
                            error=f"agent {node.data.agent_binding.agent_id} not found",
                        )
                    )
                    retry_target = self._resolve_retry_target(node.id, node.data.max_retry, node.data.on_fail, runtime_context)
                    if retry_target and retry_target in node_map:
                        events.append(
                            RunEvent(
                                id=f"event_{uuid4().hex[:10]}",
                                run_id=run_id,
                                event_type="retry.redirected",
                                created_at=utcnow(),
                                payload={
                                    "failed_node_id": node.id,
                                    "target_node_id": retry_target,
                                    "retry_count": runtime_context["retry_counts"][node.id],
                                    "max_retry": node.data.max_retry,
                                },
                            )
                        )
                        current = node_map.get(retry_target)
                        continue
                    return self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, now, failed_at, steps, events)

                resolved_input = self._resolve_input_mapping(node.data.input_mapping, runtime_context)
                started_at = utcnow()
                events.append(
                    RunEvent(
                        id=f"event_{uuid4().hex[:10]}",
                        run_id=run_id,
                        event_type="step.started",
                        created_at=started_at,
                        payload={"node_id": node.id, "agent_id": agent.id},
                    )
                )
                try:
                    output = agent_runner.run(agent, resolved_input)
                except Exception as exc:
                    failed_at = utcnow()
                    steps.append(
                        RunStepResult(
                            id=f"step_{uuid4().hex[:10]}",
                            node_id=node.id,
                            node_type=node.type,
                            status=StepStatus.FAILED,
                            started_at=started_at,
                            finished_at=failed_at,
                            input=resolved_input,
                            output={},
                            error=str(exc),
                        )
                    )
                    events.append(
                        RunEvent(
                            id=f"event_{uuid4().hex[:10]}",
                            run_id=run_id,
                            event_type="step.failed",
                            created_at=failed_at,
                            payload={"node_id": node.id, "error": str(exc)},
                        )
                    )
                    retry_target = self._resolve_retry_target(node.id, node.data.max_retry, node.data.on_fail, runtime_context)
                    if retry_target:
                        events.append(
                            RunEvent(
                                id=f"event_{uuid4().hex[:10]}",
                                run_id=run_id,
                                event_type="retry.redirected",
                                created_at=utcnow(),
                                payload={
                                    "failed_node_id": node.id,
                                    "target_node_id": retry_target,
                                    "retry_count": runtime_context["retry_counts"][node.id],
                                    "max_retry": node.data.max_retry,
                                },
                            )
                        )
                        retry_node = node_map.get(retry_target)
                        if retry_node:
                            current = retry_node
                            continue

                    return self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, now, failed_at, steps, events)
                finished_at = utcnow()
                output_key = node.data.output_mapping or {node.id: "{{output}}"}
                runtime_context["steps"][node.id] = output
                steps.append(
                    RunStepResult(
                        id=f"step_{uuid4().hex[:10]}",
                        node_id=node.id,
                        node_type=node.type,
                        status=StepStatus.COMPLETED,
                        started_at=started_at,
                        finished_at=finished_at,
                        input=resolved_input,
                        output={"result": output, "mapped_output": output_key},
                    )
                )
                events.append(
                    RunEvent(
                        id=f"event_{uuid4().hex[:10]}",
                        run_id=run_id,
                        event_type="step.completed",
                        created_at=finished_at,
                        payload={"node_id": node.id, "output": output},
                    )
                )
                current = self._select_next_node(node.id, edges_by_source, node_map)
                continue

            if isinstance(node, TeamNode):
                started_at = utcnow()
                resolved_input = self._resolve_input_mapping(node.data.input_mapping, runtime_context)
                team_output = self._run_team_node(node, resolved_input)
                runtime_context["steps"][node.id] = team_output
                steps.append(
                    RunStepResult(
                        id=f"step_{uuid4().hex[:10]}",
                        node_id=node.id,
                        node_type=node.type,
                        status=StepStatus.COMPLETED,
                        started_at=started_at,
                        finished_at=utcnow(),
                        input=resolved_input,
                        output={"result": team_output},
                    )
                )
                events.append(
                    RunEvent(
                        id=f"event_{uuid4().hex[:10]}",
                        run_id=run_id,
                        event_type="team.completed",
                        created_at=utcnow(),
                        payload={"node_id": node.id, "member_agent_ids": team_output.get("member_agent_ids", [])},
                    )
                )
                if node.data.member_agent_ids and node.data.label.lower().startswith("fail"):
                    retry_target = self._resolve_retry_target(node.id, node.data.max_retry, node.data.on_fail, runtime_context)
                    if retry_target:
                        events.append(
                            RunEvent(
                                id=f"event_{uuid4().hex[:10]}",
                                run_id=run_id,
                                event_type="retry.redirected",
                                created_at=utcnow(),
                                payload={
                                    "failed_node_id": node.id,
                                    "target_node_id": retry_target,
                                    "retry_count": runtime_context["retry_counts"][node.id],
                                    "max_retry": node.data.max_retry,
                                },
                            )
                        )
                        retry_node = node_map.get(retry_target)
                        if retry_node:
                            current = retry_node
                            continue
                current = self._select_next_node(node.id, edges_by_source, node_map)
                continue

            if isinstance(node, ConditionNode):
                result = self._evaluate_condition(node, runtime_context)
                runtime_context["steps"][node.id] = {"condition_result": result}
                events.append(
                    RunEvent(
                        id=f"event_{uuid4().hex[:10]}",
                        run_id=run_id,
                        event_type="condition.evaluated",
                        created_at=utcnow(),
                        payload={"node_id": node.id, "result": result},
                    )
                )
                current = self._select_next_node(node.id, edges_by_source, node_map, branch=result)
                continue

            current = self._select_next_node(node.id, edges_by_source, node_map)

        final_output = self._build_final_output(runtime_context, steps)
        events.append(
            RunEvent(
                id=f"event_{uuid4().hex[:10]}",
                run_id=run_id,
                event_type="run.completed",
                created_at=utcnow(),
                payload={"steps_count": len(steps)},
            )
        )
        return RunDetail(
            id=run_id,
            flow_id=flow_id,
            flow_version=flow.latest_version,
            status=RunStatus.COMPLETED,
            input=request.input,
            output=final_output,
            started_at=now,
            finished_at=utcnow(),
            steps=steps,
            events=events,
        )

    def run_flow_stream(self, flow_id: str, request: RunCreateRequest) -> Iterator[tuple[str, dict[str, Any]]]:
        flow = self.store.get_flow(flow_id)
        if not flow:
            yield "run.failed", {"error": "flow not found", "flow_id": flow_id}
            return

        definition = flow.definition
        node_map = {node.id: node for node in definition.nodes}
        edges_by_source = self._build_edges_by_source(definition.edges)
        current = self._resolve_start_node(definition)
        run_id = f"run_{uuid4().hex[:12]}"
        started_at = utcnow()
        steps: list[RunStepResult] = []
        events: list[RunEvent] = [
            RunEvent(
                id=f"event_{uuid4().hex[:10]}",
                run_id=run_id,
                event_type="run.started",
                created_at=started_at,
                payload={"flow_id": flow_id, "flow_version": flow.latest_version},
            )
        ]
        runtime_context: dict = {"input": request.input, "steps": {}, "retry_counts": {}}

        yield "run.started", {"run_id": run_id, "flow_id": flow_id, "status": "running"}

        if current is None:
            failed = self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, started_at, utcnow(), steps, events)
            self._save_stream_run(failed)
            yield "run.completed", failed.model_dump(mode="json")
            return

        step_guard = 0
        while current is not None:
            step_guard += 1
            if step_guard > 200:
                failed = self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, started_at, utcnow(), steps, events)
                self._save_stream_run(failed)
                yield "run.completed", failed.model_dump(mode="json")
                return

            node = current
            if isinstance(node, StartNode):
                current = self._select_next_node(node.id, edges_by_source, node_map)
                continue

            if isinstance(node, EndNode):
                finished_at = utcnow()
                events.append(
                    RunEvent(
                        id=f"event_{uuid4().hex[:10]}",
                        run_id=run_id,
                        event_type="run.finished",
                        created_at=finished_at,
                        payload={"end_node_id": node.id},
                    )
                )
                output = self._build_final_output(runtime_context, steps)
                detail = RunDetail(
                    id=run_id,
                    flow_id=flow_id,
                    flow_version=flow.latest_version,
                    status=RunStatus.COMPLETED,
                    input=request.input,
                    output=output,
                    started_at=started_at,
                    finished_at=finished_at,
                    steps=steps,
                    events=events,
                )
                self._save_stream_run(detail)
                yield "run.completed", detail.model_dump(mode="json")
                return

            if isinstance(node, AgentNode):
                agent = self.store.get_agent(node.data.agent_binding.agent_id)
                resolved_input = self._resolve_input_mapping(node.data.input_mapping, runtime_context)
                step_started_at = utcnow()
                yield "step.started", {"run_id": run_id, "node_id": node.id, "agent_id": node.data.agent_binding.agent_id}

                if not agent:
                    failed_at = utcnow()
                    error = f"agent {node.data.agent_binding.agent_id} not found"
                    steps.append(
                        RunStepResult(
                            id=f"step_{uuid4().hex[:10]}",
                            node_id=node.id,
                            node_type=node.type,
                            status=StepStatus.FAILED,
                            started_at=step_started_at,
                            finished_at=failed_at,
                            input=resolved_input,
                            output={},
                            error=error,
                        )
                    )
                    yield "step.failed", {"run_id": run_id, "node_id": node.id, "error": error}
                    failed = self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, started_at, failed_at, steps, events)
                    self._save_stream_run(failed)
                    yield "run.completed", failed.model_dump(mode="json")
                    return

                output: dict[str, Any] | None = None
                try:
                    for item in agent_runner.stream(agent, resolved_input):
                        if item.get("type") == "delta":
                            yield "token.delta", {"run_id": run_id, "node_id": node.id, "delta": item.get("delta", "")}
                        elif item.get("type") == "completed":
                            output = item.get("output") or {}
                except Exception as exc:
                    failed_at = utcnow()
                    steps.append(
                        RunStepResult(
                            id=f"step_{uuid4().hex[:10]}",
                            node_id=node.id,
                            node_type=node.type,
                            status=StepStatus.FAILED,
                            started_at=step_started_at,
                            finished_at=failed_at,
                            input=resolved_input,
                            output={},
                            error=str(exc),
                        )
                    )
                    yield "step.failed", {"run_id": run_id, "node_id": node.id, "error": str(exc)}
                    failed = self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, started_at, failed_at, steps, events)
                    self._save_stream_run(failed)
                    yield "run.completed", failed.model_dump(mode="json")
                    return

                output = output or {"message": ""}
                finished_at = utcnow()
                runtime_context["steps"][node.id] = output
                steps.append(
                    RunStepResult(
                        id=f"step_{uuid4().hex[:10]}",
                        node_id=node.id,
                        node_type=node.type,
                        status=StepStatus.COMPLETED,
                        started_at=step_started_at,
                        finished_at=finished_at,
                        input=resolved_input,
                        output={"result": output, "mapped_output": node.data.output_mapping or {node.id: "{{output}}"}},
                    )
                )
                yield "step.completed", {"run_id": run_id, "node_id": node.id, "output": output}
                current = self._select_next_node(node.id, edges_by_source, node_map)
                continue

            if isinstance(node, TeamNode):
                step_started_at = utcnow()
                resolved_input = self._resolve_input_mapping(node.data.input_mapping, runtime_context)
                team_output = self._empty_team_output(node)
                member_agent_ids = team_output["member_agent_ids"]
                member_results: list[dict[str, Any]] = []

                for index, member_agent_id in enumerate(member_agent_ids):
                    agent = self.store.get_agent(member_agent_id)
                    if not agent:
                        member_results.append(
                            {
                                "agent_id": member_agent_id,
                                "agent_name": member_agent_id,
                                "status": "failed",
                                "message": f"Agent {member_agent_id} not found.",
                            }
                        )
                        continue

                    yield "team.member.started", {
                        "run_id": run_id,
                        "node_id": node.id,
                        "agent_id": member_agent_id,
                        "agent_name": agent.name,
                    }

                    if len(member_agent_ids) > 1:
                        prefix = f"{agent.name}:\n"
                        if index > 0:
                            prefix = f"\n\n{prefix}"
                        yield "token.delta", {"run_id": run_id, "node_id": node.id, "delta": prefix}

                    member_output: dict[str, Any] | None = None
                    try:
                        for item in agent_runner.stream(agent, resolved_input):
                            if item.get("type") == "delta":
                                yield "token.delta", {"run_id": run_id, "node_id": node.id, "delta": item.get("delta", "")}
                            elif item.get("type") == "completed":
                                member_output = item.get("output") or {}
                    except Exception as exc:
                        member_output = {
                            "agent_id": member_agent_id,
                            "agent_name": agent.name,
                            "message": f"执行失败：{exc}",
                            "error": str(exc),
                        }

                    member_output = member_output or {
                        "agent_id": member_agent_id,
                        "agent_name": agent.name,
                        "message": "",
                    }
                    member_results.append(
                        {
                            "agent_id": member_agent_id,
                            "agent_name": agent.name,
                            "status": "failed" if member_output.get("error") else "completed",
                            "output": member_output,
                            "message": member_output.get("message", ""),
                        }
                    )
                    yield "team.member.completed", {
                        "run_id": run_id,
                        "node_id": node.id,
                        "agent_id": member_agent_id,
                        "status": member_results[-1]["status"],
                    }

                team_output = self._build_team_output(node, member_results)
                step_finished_at = utcnow()
                runtime_context["steps"][node.id] = team_output
                steps.append(
                    RunStepResult(
                        id=f"step_{uuid4().hex[:10]}",
                        node_id=node.id,
                        node_type=node.type,
                        status=StepStatus.COMPLETED,
                        started_at=step_started_at,
                        finished_at=step_finished_at,
                        input=resolved_input,
                        output={"result": team_output},
                    )
                )
                yield "team.completed", {"run_id": run_id, "node_id": node.id, "output": team_output}
                current = self._select_next_node(node.id, edges_by_source, node_map)
                continue

            current = self._select_next_node(node.id, edges_by_source, node_map)

        output = self._build_final_output(runtime_context, steps)
        detail = RunDetail(
            id=run_id,
            flow_id=flow_id,
            flow_version=flow.latest_version,
            status=RunStatus.COMPLETED,
            input=request.input,
            output=output,
            started_at=started_at,
            finished_at=utcnow(),
            steps=steps,
            events=events,
        )
        self._save_stream_run(detail)
        yield "run.completed", detail.model_dump(mode="json")

    def _save_stream_run(self, detail: RunDetail) -> None:
        if hasattr(self.store, "save_run"):
            self.store.save_run(detail)
        else:
            self.store.runs[detail.id] = detail

    def _resolve_team_member_ids(self, node: TeamNode) -> list[str]:
        if node.data.member_agent_ids:
            return node.data.member_agent_ids

        if node.data.team_id and hasattr(self.store, "get_team"):
            team = self.store.get_team(node.data.team_id)
            if team:
                return team.member_agent_ids

        return []

    def _empty_team_output(self, node: TeamNode) -> dict[str, Any]:
        return {
            "mode": "team",
            "strategy": node.data.strategy,
            "team_id": node.data.team_id,
            "member_agent_ids": self._resolve_team_member_ids(node),
            "member_results": [],
            "message": "",
        }

    def _build_team_output(self, node: TeamNode, member_results: list[dict[str, Any]]) -> dict[str, Any]:
        messages: list[str] = []
        for result in member_results:
            agent_name = result.get("agent_name") or result.get("agent_id") or "Agent"
            message = result.get("message") or ""
            if message:
                messages.append(f"{agent_name}: {message}")

        if not messages and member_results:
            messages.append("Team 已执行完成，但成员 Agent 没有返回文本结果。")
        if not member_results:
            messages.append("Team 没有绑定可执行的成员 Agent。")

        return {
            "mode": "team",
            "strategy": node.data.strategy,
            "team_id": node.data.team_id,
            "member_agent_ids": self._resolve_team_member_ids(node),
            "member_results": member_results,
            "message": "\n\n".join(messages),
        }

    def _run_team_node(self, node: TeamNode, resolved_input: dict[str, Any]) -> dict[str, Any]:
        member_results: list[dict[str, Any]] = []

        for member_agent_id in self._resolve_team_member_ids(node):
            agent = self.store.get_agent(member_agent_id)
            if not agent:
                member_results.append(
                    {
                        "agent_id": member_agent_id,
                        "agent_name": member_agent_id,
                        "status": "failed",
                        "message": f"Agent {member_agent_id} not found.",
                    }
                )
                continue

            try:
                output = agent_runner.run(agent, resolved_input)
                member_results.append(
                    {
                        "agent_id": member_agent_id,
                        "agent_name": agent.name,
                        "status": "completed",
                        "output": output,
                        "message": output.get("message", ""),
                    }
                )
            except Exception as exc:
                member_results.append(
                    {
                        "agent_id": member_agent_id,
                        "agent_name": agent.name,
                        "status": "failed",
                        "message": f"执行失败：{exc}",
                        "error": str(exc),
                    }
                )

        return self._build_team_output(node, member_results)

    def _build_edges_by_source(self, edges: list[FlowEdge]) -> dict[str, list[FlowEdge]]:
        edges_by_source: dict[str, list[FlowEdge]] = defaultdict(list)
        for edge in edges:
            edges_by_source[edge.source].append(edge)
        return edges_by_source

    def _resolve_retry_target(
        self,
        node_id: str,
        max_retry: int,
        on_fail: str | None,
        runtime_context: dict,
    ) -> str | None:
        if not on_fail or max_retry <= 0:
            return None

        retry_counts = runtime_context.setdefault("retry_counts", {})
        current_count = retry_counts.get(node_id, 0)

        if current_count >= max_retry:
            return None

        retry_counts[node_id] = current_count + 1
        return on_fail

    def _build_failed_run(
        self,
        run_id: str,
        flow_id: str,
        flow_version: int,
        request_input: dict,
        started_at: datetime,
        finished_at: datetime,
        steps: list[RunStepResult],
        events: list[RunEvent],
    ) -> RunDetail:
        events.append(
            RunEvent(
                id=f"event_{uuid4().hex[:10]}",
                run_id=run_id,
                event_type="run.failed",
                created_at=finished_at,
                payload={"reason": "retry_exhausted_or_no_failure_route"},
            )
        )
        return RunDetail(
            id=run_id,
            flow_id=flow_id,
            flow_version=flow_version,
            status=RunStatus.FAILED,
            input=request_input,
            output={},
            started_at=started_at,
            finished_at=finished_at,
            steps=steps,
            events=events,
        )

    def _resolve_start_node(self, definition: FlowDefinition):
        explicit_start = next((node for node in definition.nodes if isinstance(node, StartNode)), None)
        if explicit_start:
            return explicit_start

        targets = set()
        for edge in definition.edges:
            targets.add(edge.target)

        start_nodes = [node for node in definition.nodes if node.id not in targets]
        if not start_nodes:
            return definition.nodes[0] if definition.nodes else None
        return start_nodes[0]

    def _select_next_node(
        self,
        node_id: str,
        edges_by_source: dict[str, list[FlowEdge]],
        node_map: dict[str, Any],
        branch: str | None = None,
    ):
        edges = edges_by_source.get(node_id) or []
        if not edges:
            return None

        # 如果有分支ID，优先匹配分支
        if branch is not None:
            # 先尝试匹配 branch_id
            for edge in edges:
                edge_branch = edge.data.get("branch") if edge.data else None
                if edge_branch == branch:
                    return node_map.get(edge.target)
            # 兼容旧逻辑：匹配 true/false
            preferred_handles = ["true", "false"] if branch in ("true", True) else ["false", "true"]
            for handle in preferred_handles:
                for edge in edges:
                    edge_handle = (edge.source_handle or edge.data.get("branch") or "").lower()
                    if edge_handle == handle:
                        return node_map.get(edge.target)

        return node_map.get(edges[0].target)

    def _resolve_input_mapping(self, mapping: dict, runtime_context: dict) -> dict:
        if not mapping:
            return dict(runtime_context.get("input") or {})

        resolved: dict = {}
        for key, value in mapping.items():
            if isinstance(value, str) and value.startswith("{{input.") and value.endswith("}}"):
                field = value.removeprefix("{{input.").removesuffix("}}")
                resolved[key] = runtime_context.get("input", {}).get(field)
            elif isinstance(value, str) and value.startswith("{{steps.") and value.endswith("}}"):
                path = value.removeprefix("{{steps.").removesuffix("}}").split(".")
                current = runtime_context.get("steps", {})
                for part in path:
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        current = None
                        break
                resolved[key] = current
            else:
                resolved[key] = value
        source_input = runtime_context.get("input", {})
        for passthrough_key in ("messages", "session_id"):
            if passthrough_key in source_input and passthrough_key not in resolved:
                resolved[passthrough_key] = source_input[passthrough_key]
        return resolved

    def _resolve_context_value(self, expression: str, runtime_context: dict):
        if expression.startswith("input."):
            field = expression.removeprefix("input.")
            return runtime_context.get("input", {}).get(field)
        if expression.startswith("steps."):
            path = expression.removeprefix("steps.").split(".")
            current = runtime_context.get("steps", {})
            for part in path:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None
            return current
        return runtime_context.get(expression)

    def _evaluate_condition(self, node: ConditionNode, runtime_context: dict) -> str:
        """评估条件节点，返回匹配的分支ID"""
        data = node.data
        condition_type = data.condition_type or "simple"

        # 获取输入值
        input_value = self._resolve_context_value(
            data.input_source.replace("{{", "").replace("}}", ""),
            runtime_context
        )

        # 简单条件（兼容旧版本）
        if condition_type == "simple" and data.condition:
            rule = data.condition
            actual = self._resolve_context_value(rule.field, runtime_context)
            expected = rule.value
            matched = self._match_simple_condition(actual, expected, rule.operator)
            return "true" if matched else "false"

        # 表达式条件
        if condition_type == "expression" and data.expression:
            # 简单表达式求值（替换变量后比较）
            expr = data.expression
            # 替换 {{xxx}} 变量
            import re
            def replace_var(m):
                var_path = m.group(1).strip()
                return str(self._resolve_context_value(var_path, runtime_context) or "")
            expr = re.sub(r'\{\{([^}]+)\}\}', replace_var, expr)
            try:
                # 安全求值：只支持基本比较
                matched = eval(expr, {"__builtins__": {}}, {})
                return "true" if matched else "false"
            except:
                return data.default_branch_id or "false"

        # LLM 分类
        if condition_type == "llm_classify" and data.llm_config:
            config = data.llm_config
            # 简化实现：返回第一个匹配的类别（实际应调用 LLM）
            categories = config.categories or []
            for branch in data.branches:
                if branch.condition_value in categories:
                    return branch.id
            return data.default_branch_id or (data.branches[0].id if data.branches else "false")

        # 正则匹配
        if condition_type == "regex" and data.regex_patterns:
            import re
            text = str(input_value or "")
            for pattern_obj in data.regex_patterns:
                try:
                    if re.search(pattern_obj.pattern, text):
                        return pattern_obj.branch_id
                except re.error:
                    continue
            return data.default_branch_id or "false"

        # JSON Schema 校验
        if condition_type == "json_schema" and data.json_schema:
            # 简化实现：只检查必需字段是否存在
            schema = data.json_schema
            required = schema.get("required", [])
            if isinstance(input_value, dict):
                missing = [f for f in required if f not in input_value]
                return "valid" if not missing else "invalid"
            return "invalid"

        # 默认走第一个分支
        return data.default_branch_id or (data.branches[0].id if data.branches else "true")

    def _match_simple_condition(self, actual, expected, operator: str) -> bool:
        """简单条件匹配"""
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "contains":
            return expected in actual if actual is not None else False
        if operator == "gt":
            return actual > expected if actual is not None else False
        if operator == "gte":
            return actual >= expected if actual is not None else False
        if operator == "lt":
            return actual < expected if actual is not None else False
        if operator == "lte":
            return actual <= expected if actual is not None else False
        if operator == "exists":
            return actual is not None
        return False

    def _build_final_output(self, runtime_context: dict, steps: list[RunStepResult]) -> dict:
        if steps:
            last = steps[-1]
            return {
                "final_text": last.output.get("result", {}).get("message", ""),
                "last_step_node_id": last.node_id,
                "steps_count": len(steps),
                "step_outputs": runtime_context.get("steps", {}),
            }
        return {"final_text": "", "steps_count": 0}


flow_runner = FlowRunner()
