from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.core.llm import _strip_control_markup_progressively
from app.repositories.factory import get_store
from app.runners.agent_runner import agent_runner
from app.runners import flow_runtime
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
        runtime_context: dict = {"input": request.input, "steps": {}, "retry_counts": {}, "flow_id": flow_id}
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
                            output=self._build_failed_output(request.input, steps),
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
                resolved_input = self._inject_round_context(node.id, resolved_input, runtime_context)
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
                            output=self._build_failed_output(request.input, steps),
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
                if self._output_requests_retry(output):
                    retry_target = self._resolve_retry_target(node.id, node.data.max_retry, node.data.on_fail, runtime_context)
                    if retry_target and retry_target in node_map:
                        steps.append(
                            RunStepResult(
                                id=f"step_{uuid4().hex[:10]}",
                                node_id=node.id,
                                node_type=node.type,
                                status=StepStatus.FAILED,
                                started_at=started_at,
                                finished_at=finished_at,
                                input=resolved_input,
                                output={"result": output, "mapped_output": output_key},
                                error="agent requested retry",
                            )
                        )
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

                    return self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, now, finished_at, steps, events)
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
                resolved_input = self._inject_round_context(node.id, resolved_input, runtime_context)
                team_output = self._run_team_node(node, resolved_input, runtime_context)
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
        runtime_context: dict = {"input": request.input, "steps": {}, "retry_counts": {}, "flow_id": flow_id}

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
                resolved_input = self._inject_round_context(node.id, resolved_input, runtime_context)
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
                streamed_text = ""
                visible_text = ""
                try:
                    for item in agent_runner.stream(agent, resolved_input):
                        if item.get("type") == "delta":
                            streamed_text += str(item.get("delta", ""))
                            next_visible_text = _strip_control_markup_progressively(streamed_text)
                            if len(next_visible_text) > len(visible_text):
                                delta = next_visible_text[len(visible_text) :]
                                visible_text = next_visible_text
                                if delta:
                                    yield "token.delta", {"run_id": run_id, "node_id": node.id, "delta": delta}
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
                if self._output_requests_retry(output):
                    retry_target = self._resolve_retry_target(node.id, node.data.max_retry, node.data.on_fail, runtime_context)
                    if retry_target and retry_target in node_map:
                        steps.append(
                            RunStepResult(
                                id=f"step_{uuid4().hex[:10]}",
                                node_id=node.id,
                                node_type=node.type,
                                status=StepStatus.FAILED,
                                started_at=step_started_at,
                                finished_at=finished_at,
                                input=resolved_input,
                                output={"result": output, "mapped_output": node.data.output_mapping or {node.id: "{{output}}"}},
                                error="agent requested retry",
                            )
                        )
                        yield "step.failed", {"run_id": run_id, "node_id": node.id, "error": "agent requested retry", "output": output}
                        yield "retry.redirected", {
                            "run_id": run_id,
                            "failed_node_id": node.id,
                            "target_node_id": retry_target,
                            "retry_count": runtime_context["retry_counts"][node.id],
                            "max_retry": node.data.max_retry,
                        }
                        current = node_map.get(retry_target)
                        continue

                    failed = self._build_failed_run(run_id, flow_id, flow.latest_version, request.input, started_at, finished_at, steps, events)
                    self._save_stream_run(failed)
                    yield "run.completed", failed.model_dump(mode="json")
                    return
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
                resolved_input = self._inject_round_context(node.id, resolved_input, runtime_context)
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
                    member_input = self._inject_team_member_context(node.id, agent.name, resolved_input, runtime_context)
                    member_streamed_text = ""
                    member_visible_text = ""
                    try:
                        for item in agent_runner.stream(agent, member_input):
                            if item.get("type") == "delta":
                                member_streamed_text += str(item.get("delta", ""))
                                next_visible_text = _strip_control_markup_progressively(member_streamed_text)
                                if len(next_visible_text) > len(member_visible_text):
                                    delta = next_visible_text[len(member_visible_text) :]
                                    member_visible_text = next_visible_text
                                    if delta:
                                        yield "token.delta", {"run_id": run_id, "node_id": node.id, "delta": delta}
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

            if isinstance(node, ConditionNode):
                result = self._evaluate_condition(node, runtime_context)
                runtime_context["steps"][node.id] = {"condition_result": result}
                yield "condition.evaluated", {"run_id": run_id, "node_id": node.id, "result": result}
                current = self._select_next_node(node.id, edges_by_source, node_map, branch=result)
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
        flow_runtime.save_stream_run(self.store, detail)

    def _resolve_team_member_ids(self, node: TeamNode) -> list[str]:
        return flow_runtime.resolve_team_member_ids(self.store, node)

    def _empty_team_output(self, node: TeamNode) -> dict[str, Any]:
        return flow_runtime.empty_team_output(self.store, node)

    def _build_team_output(self, node: TeamNode, member_results: list[dict[str, Any]]) -> dict[str, Any]:
        return flow_runtime.build_team_output(self.store, node, member_results)

    def _run_team_node(self, node: TeamNode, resolved_input: dict[str, Any], runtime_context: dict) -> dict[str, Any]:
        return flow_runtime.run_team_node(self.store, node, resolved_input, runtime_context)

    def _build_edges_by_source(self, edges: list[FlowEdge]) -> dict[str, list[FlowEdge]]:
        return flow_runtime.build_edges_by_source(edges)

    def _resolve_retry_target(
        self,
        node_id: str,
        max_retry: int,
        on_fail: str | None,
        runtime_context: dict,
    ) -> str | None:
        return flow_runtime.resolve_retry_target(node_id, max_retry, on_fail, runtime_context)

    def _output_requests_retry(self, output: dict[str, Any]) -> bool:
        control = output.get("control") if isinstance(output.get("control"), dict) else {}
        status = str(
            control.get("status")
            or control.get("flow_status")
            or output.get("status")
            or output.get("flow_status")
            or ""
        ).strip().lower()
        if status in {"fail", "failed", "retry"}:
            return True

        message = str(output.get("message") or output.get("final_text") or "").lower()
        retry_markers = ("flow_status: fail", "flow_status：fail", "flow_status=fail")
        return any(marker in message for marker in retry_markers)

    def _current_round(self, runtime_context: dict) -> int:
        return flow_runtime.current_round(runtime_context)

    def _inject_round_context(self, node_id: str, resolved_input: dict, runtime_context: dict) -> dict:
        return flow_runtime.inject_round_context(node_id, resolved_input, runtime_context)

    def _inject_team_member_context(self, node_id: str, agent_name: str, resolved_input: dict, runtime_context: dict) -> dict:
        return flow_runtime.inject_team_member_context(node_id, agent_name, resolved_input, runtime_context)

    def _build_failed_output(self, request_input: dict, steps: list[RunStepResult]) -> dict[str, Any]:
        return flow_runtime.build_failed_output(request_input, steps)

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
        return flow_runtime.build_failed_run(
            run_id, flow_id, flow_version, request_input, started_at, finished_at, steps, events
        )

    def _resolve_failed_reason(self, steps: list[RunStepResult]) -> str:
        return flow_runtime.resolve_failed_reason(steps)

    def _extract_rps_choice(self, value: Any) -> str:
        return flow_runtime.extract_rps_choice(value)

    def _extract_rps_result(self, value: Any) -> str:
        return flow_runtime.extract_rps_result(value)

    def _extract_flow_status(self, value: Any) -> str:
        return flow_runtime.extract_flow_status(value)

    def _build_round_summary(self, steps: list[RunStepResult]) -> list[dict[str, Any]]:
        return flow_runtime.build_round_summary(steps)

    def _format_round_table(self, rounds: list[dict[str, Any]]) -> str:
        return flow_runtime.format_round_table(rounds)

    def _resolve_start_node(self, definition: FlowDefinition):
        return flow_runtime.resolve_start_node(definition)

    def _select_next_node(
        self,
        node_id: str,
        edges_by_source: dict[str, list[FlowEdge]],
        node_map: dict[str, Any],
        branch: str | None = None,
    ):
        return flow_runtime.select_next_node(node_id, edges_by_source, node_map, branch)

    def _resolve_input_mapping(self, mapping: dict, runtime_context: dict) -> dict:
        return flow_runtime.resolve_input_mapping(mapping, runtime_context)

    def _resolve_context_value(self, expression: str, runtime_context: dict):
        return flow_runtime.resolve_context_value(expression, runtime_context)

    def _evaluate_condition(self, node: ConditionNode, runtime_context: dict) -> str:
        return flow_runtime.evaluate_condition(node, runtime_context)

    def _match_simple_condition(self, actual, expected, operator: str) -> bool:
        return flow_runtime.match_simple_condition(actual, expected, operator)

    def _build_final_output(self, runtime_context: dict, steps: list[RunStepResult]) -> dict:
        return flow_runtime.build_final_output(runtime_context, steps)


flow_runner = FlowRunner()
