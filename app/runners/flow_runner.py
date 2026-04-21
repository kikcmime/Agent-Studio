from __future__ import annotations

from collections import defaultdict
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
                team_output = {
                    "mode": "team_placeholder",
                    "strategy": node.data.strategy,
                    "member_agent_ids": node.data.member_agent_ids,
                    "message": "Team node execution placeholder. Parallel child execution will be implemented in the orchestrator layer.",
                }
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
                        event_type="team.placeholder.completed",
                        created_at=utcnow(),
                        payload={"node_id": node.id, "member_agent_ids": node.data.member_agent_ids},
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
        branch: bool | None = None,
    ):
        edges = edges_by_source.get(node_id) or []
        if not edges:
            return None

        if branch is not None:
            preferred_handles = ["true", "false"] if branch else ["false", "true"]
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

    def _evaluate_condition(self, node: ConditionNode, runtime_context: dict) -> bool:
        rule = node.data.condition
        actual = self._resolve_context_value(rule.field, runtime_context)
        expected = rule.value

        if rule.operator == "eq":
            return actual == expected
        if rule.operator == "ne":
            return actual != expected
        if rule.operator == "contains":
            return expected in actual if actual is not None else False
        if rule.operator == "gt":
            return actual > expected
        if rule.operator == "gte":
            return actual >= expected
        if rule.operator == "lt":
            return actual < expected
        if rule.operator == "lte":
            return actual <= expected
        if rule.operator == "exists":
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
