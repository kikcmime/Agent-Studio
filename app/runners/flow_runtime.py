from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import re
from typing import Any
from uuid import uuid4

from app.core.llm import invoke_text_classification
from app.runners.agent_runner import agent_runner
from app.schemas.contracts import ConditionNode, FlowDefinition, FlowEdge, RunDetail, RunEvent, RunStatus, RunStepResult, StartNode, StepStatus, TeamNode


def save_stream_run(store: Any, detail: RunDetail) -> None:
    if hasattr(store, "save_run"):
        store.save_run(detail)
    else:
        store.runs[detail.id] = detail


def resolve_team_member_ids(store: Any, node: TeamNode) -> list[str]:
    if node.data.member_agent_ids:
        return node.data.member_agent_ids

    if node.data.team_id and hasattr(store, "get_team"):
        team = store.get_team(node.data.team_id)
        if team:
            return team.member_agent_ids

    return []


def empty_team_output(store: Any, node: TeamNode) -> dict[str, Any]:
    return {
        "mode": "team",
        "strategy": node.data.strategy,
        "team_id": node.data.team_id,
        "member_agent_ids": resolve_team_member_ids(store, node),
        "member_results": [],
        "message": "",
    }


def build_team_output(store: Any, node: TeamNode, member_results: list[dict[str, Any]]) -> dict[str, Any]:
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
        "member_agent_ids": resolve_team_member_ids(store, node),
        "member_results": member_results,
        "message": "\n\n".join(messages),
    }


def run_team_node(store: Any, node: TeamNode, resolved_input: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    member_results: list[dict[str, Any]] = []

    for member_agent_id in resolve_team_member_ids(store, node):
        agent = store.get_agent(member_agent_id)
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
            member_input = inject_team_member_context(node.id, agent.name, resolved_input, runtime_context)
            output = agent_runner.run(agent, member_input)
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

    return build_team_output(store, node, member_results)


def build_edges_by_source(edges: list[FlowEdge]) -> dict[str, list[FlowEdge]]:
    edges_by_source: dict[str, list[FlowEdge]] = defaultdict(list)
    for edge in edges:
        edges_by_source[edge.source].append(edge)
    return edges_by_source


def resolve_retry_target(node_id: str, max_retry: int, on_fail: str | None, runtime_context: dict[str, Any]) -> str | None:
    if not on_fail or max_retry <= 0:
        return None

    retry_counts = runtime_context.setdefault("retry_counts", {})
    current_count = retry_counts.get(node_id, 0)

    if current_count >= max_retry:
        return None

    retry_counts[node_id] = current_count + 1
    return on_fail


def current_round(runtime_context: dict[str, Any]) -> int:
    retry_counts = runtime_context.get("retry_counts") or {}
    numeric_counts = [int(value or 0) for value in retry_counts.values()]
    return max([0, *numeric_counts]) + 1


def inject_round_context(node_id: str, resolved_input: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    if runtime_context.get("flow_id") != "flow_rps_team":
        return resolved_input

    enriched = dict(resolved_input)
    round_number = current_round(runtime_context)
    round_label = f"第{round_number}轮"
    enriched.setdefault("current_round", round_number)
    enriched.setdefault("round_label", round_label)

    user_message = str(enriched.get("user_message") or "").strip()
    if node_id == "rps_host":
        enriched["user_message"] = f"{user_message}\n当前轮次：{round_label}。请只输出：{round_label}开始。".strip()
    elif user_message and round_label not in user_message:
        enriched["user_message"] = f"{user_message}\n当前轮次：{round_label}。"
    return enriched


def inject_team_member_context(node_id: str, agent_name: str, resolved_input: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    if runtime_context.get("flow_id") != "flow_rps_team" or node_id != "rps_players":
        return resolved_input

    enriched = dict(resolved_input)
    round_number = current_round(runtime_context)
    round_label = f"第{round_number}轮"
    base_message = str(enriched.get("user_message") or "").strip()
    if round_number > 1:
        extra = f"当前轮次：{round_label}。\n你是{agent_name}。\n这是平局重开轮次，请只输出一个选择，并尽量避免与其他玩家完全一样。"
    else:
        extra = f"当前轮次：{round_label}。\n你是{agent_name}。请只输出一个选择。"
    enriched["user_message"] = f"{base_message}\n{extra}".strip()
    enriched["current_round"] = round_number
    enriched["round_label"] = round_label
    return enriched


def extract_rps_choice(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    match = re.search(r"(剪刀|石头|布)", value)
    return match.group(1) if match else ""


def extract_rps_result(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    match = re.search(r"结果\s*[=:：]\s*([^\n]+)", value)
    if match:
        return match.group(1).strip()
    if "平局" in value:
        return "平局"
    return ""


def extract_flow_status(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    match = re.search(r"flow_status\s*[:=：]\s*(success|fail|failed|retry)", value, flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def build_round_summary(steps: list[RunStepResult]) -> list[dict[str, Any]]:
    rounds: list[dict[str, Any]] = []

    for step in steps:
        result = step.output.get("result", {}) if isinstance(step.output, dict) else {}
        if step.node_type == "team" and isinstance(result, dict) and result.get("mode") == "team":
            row = {"round": len(rounds) + 1, "A": "", "B": "", "C": "", "result": "", "status": ""}
            found_rps_member = False
            for member in result.get("member_results", []):
                if not isinstance(member, dict):
                    continue
                agent_name = str(member.get("agent_name") or "")
                message = member.get("message") or member.get("output", {}).get("message") or ""
                choice = extract_rps_choice(message)
                if "玩家 A" in agent_name or "玩家A" in agent_name:
                    row["A"] = choice
                    found_rps_member = True
                elif "玩家 B" in agent_name or "玩家B" in agent_name:
                    row["B"] = choice
                    found_rps_member = True
                elif "玩家 C" in agent_name or "玩家C" in agent_name:
                    row["C"] = choice
                    found_rps_member = True
            if found_rps_member:
                rounds.append(row)
            continue

        if not rounds or step.node_type != "agent" or not isinstance(result, dict):
            continue

        message = result.get("message", "")
        parsed_result = extract_rps_result(message)
        parsed_status = extract_flow_status(message)
        if parsed_result:
            rounds[-1]["result"] = parsed_result
        if parsed_status:
            rounds[-1]["status"] = parsed_status

    return rounds


def format_round_table(rounds: list[dict[str, Any]]) -> str:
    header = "| 轮次 | A | B | C | 结果 |\n| --- | --- | --- | --- | --- |"
    rows = [
        f"| 第{row['round']}轮 | {row['A'] or '-'} | {row['B'] or '-'} | {row['C'] or '-'} | {row['result'] or '-'} |"
        for row in rounds
    ]
    return "\n".join([header, *rows])


def build_failed_output(request_input: dict[str, Any], steps: list[RunStepResult]) -> dict[str, Any]:
    rounds = build_round_summary(steps)
    if rounds:
        final_round = rounds[-1]
        summary = f"共进行了 {len(rounds)} 轮；仍未分出胜负，已达到最大重试次数。最后一轮结果：{final_round.get('result') or '未判定'}。"
        return {
            "final_text": f"{summary}\n\n{format_round_table(rounds)}",
            "summary": summary,
            "rounds": rounds,
            "steps_count": len(steps),
            "step_outputs": {step.node_id: step.output for step in steps},
            "failed": True,
        }

    last_message = ""
    if steps:
        last_step = steps[-1]
        if isinstance(last_step.output, dict):
            last_result = last_step.output.get("result") or {}
            if isinstance(last_result, dict):
                last_message = str(last_result.get("message") or "")

    summary = last_message or "执行失败，已达到最大重试次数。"
    return {
        "final_text": summary,
        "summary": summary,
        "steps_count": len(steps),
        "step_outputs": {step.node_id: step.output for step in steps},
        "failed": True,
    }


def resolve_failed_reason(steps: list[RunStepResult]) -> str:
    if not steps:
        return "no_steps_executed"

    last_step = steps[-1]
    if last_step.error:
        normalized = last_step.error.lower()
        if "not found" in normalized:
            return "dependency_not_found"
        if "retry" in normalized:
            return "retry_exhausted"
        return "step_execution_failed"

    if last_step.status == StepStatus.FAILED:
        return "step_failed"
    return "retry_exhausted_or_no_failure_route"


def build_failed_run(
    run_id: str,
    flow_id: str,
    flow_version: int,
    request_input: dict[str, Any],
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
            payload={
                "reason": resolve_failed_reason(steps),
                "failed_step_count": len([step for step in steps if step.status == StepStatus.FAILED]),
            },
        )
    )
    return RunDetail(
        id=run_id,
        flow_id=flow_id,
        flow_version=flow_version,
        status=RunStatus.FAILED,
        input=request_input,
        output=build_failed_output(request_input, steps),
        started_at=started_at,
        finished_at=finished_at,
        steps=steps,
        events=events,
    )


def resolve_start_node(definition: FlowDefinition):
    explicit_start = next((node for node in definition.nodes if isinstance(node, StartNode)), None)
    if explicit_start:
        return explicit_start

    targets = {edge.target for edge in definition.edges}
    start_nodes = [node for node in definition.nodes if node.id not in targets]
    if not start_nodes:
        return definition.nodes[0] if definition.nodes else None
    return start_nodes[0]


def select_next_node(node_id: str, edges_by_source: dict[str, list[FlowEdge]], node_map: dict[str, Any], branch: str | None = None):
    edges = edges_by_source.get(node_id) or []
    if not edges:
        return None

    if branch is not None:
        for edge in edges:
            edge_branch = edge.data.get("branch") if edge.data else None
            if edge_branch == branch:
                return node_map.get(edge.target)

        preferred_handles = ["true", "false"] if branch in ("true", True) else ["false", "true"]
        for handle in preferred_handles:
            for edge in edges:
                edge_handle = (edge.source_handle or edge.data.get("branch") or "").lower()
                if edge_handle == handle:
                    return node_map.get(edge.target)

    return node_map.get(edges[0].target)


def resolve_input_mapping(mapping: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
    if not mapping:
        return dict(runtime_context.get("input") or {})

    resolved: dict[str, Any] = {}
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


def resolve_context_value(expression: str, runtime_context: dict[str, Any]):
    if expression.startswith("input."):
        return runtime_context.get("input", {}).get(expression.removeprefix("input."))
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


def match_simple_condition(actual: Any, expected: Any, operator: str) -> bool:
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


def evaluate_condition(node: ConditionNode, runtime_context: dict[str, Any]) -> str:
    data = node.data
    condition_type = data.condition_type or "simple"
    input_value = resolve_context_value(data.input_source.replace("{{", "").replace("}}", ""), runtime_context)

    if condition_type == "simple" and data.condition:
        rule = data.condition
        actual = resolve_context_value(rule.field, runtime_context)
        return "true" if match_simple_condition(actual, rule.value, rule.operator) else "false"

    if condition_type == "expression" and data.expression:
        expr = re.sub(
            r"\{\{([^}]+)\}\}",
            lambda match: str(resolve_context_value(match.group(1).strip(), runtime_context) or ""),
            data.expression,
        )
        try:
            matched = eval(expr, {"__builtins__": {}}, {})
            return "true" if matched else "false"
        except Exception:
            return data.default_branch_id or "false"

    if condition_type == "llm_classify" and data.llm_config:
        config = data.llm_config
        categories = [branch.condition_value for branch in data.branches if branch.condition_value]
        if categories:
            result = invoke_text_classification(
                text=str(input_value or ""),
                categories=categories,
                prompt=config.prompt,
                model=config.model,
                temperature=0,
            )
            runtime_context.setdefault("condition_results", {})[node.id] = result
            matched_category = result.get("category")
            if matched_category:
                for branch in data.branches:
                    if branch.condition_value == matched_category:
                        return branch.id
        return data.default_branch_id or (data.branches[0].id if data.branches else "false")

    if condition_type == "regex" and data.regex_patterns:
        text = str(input_value or "")
        for pattern_obj in data.regex_patterns:
            try:
                if re.search(pattern_obj.pattern, text):
                    return pattern_obj.branch_id
            except re.error:
                continue
        return data.default_branch_id or "false"

    if condition_type == "json_schema" and data.json_schema:
        required = data.json_schema.get("required", [])
        if isinstance(input_value, dict):
            missing = [field for field in required if field not in input_value]
            return "valid" if not missing else "invalid"
        return "invalid"

    return data.default_branch_id or (data.branches[0].id if data.branches else "true")


def build_final_output(runtime_context: dict[str, Any], steps: list[RunStepResult]) -> dict[str, Any]:
    if not steps:
        return {"final_text": "", "steps_count": 0}

    last = steps[-1]
    last_result = last.output.get("result", {}) if isinstance(last.output, dict) else {}
    last_message = last_result.get("message", "") if isinstance(last_result, dict) else ""
    rounds = build_round_summary(steps) if runtime_context.get("flow_id") == "flow_rps_team" else []
    user_message = str(runtime_context.get("input", {}).get("user_message") or "")

    if rounds:
        all_ties = all((row.get("result") or "") == "平局" for row in rounds)
        final_round = rounds[-1]
        if "平局" in user_message:
            answer = f"是，{len(rounds)} 轮全部平局。" if all_ties else f"不是，第{final_round['round']}轮已经分出结果：{final_round.get('result') or '非平局'}。"
        else:
            answer = f"共进行了 {len(rounds)} 轮；最终结果：{final_round.get('result') or '未判定'}。"

        return {
            "final_text": f"{answer}\n\n{format_round_table(rounds)}",
            "summary": answer,
            "rounds": rounds,
            "last_step_node_id": last.node_id,
            "steps_count": len(steps),
            "step_outputs": runtime_context.get("steps", {}),
        }

    return {
        "final_text": last_message,
        "summary": (
            str(last_result.get("result") or "").strip()
            if isinstance(last_result, dict) and last_result.get("result")
            else last_message.split("\n", 1)[0].strip()
        ),
        "last_step_node_id": last.node_id,
        "steps_count": len(steps),
        "step_outputs": runtime_context.get("steps", {}),
    }
