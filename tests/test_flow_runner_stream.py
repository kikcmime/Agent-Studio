from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ["STORAGE_BACKEND"] = "memory"

from app.repositories.in_memory import InMemoryStore
from app.runners.agent_runner import agent_runner
from app.runners.flow_runner import FlowRunner
from app.schemas.contracts import AgentNode, RunCreateRequest, RunStatus


class FlowRunnerStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryStore()
        self.runner = FlowRunner()
        self.runner.store = self.store

    def _set_demo_agent_id(self, agent_id: str) -> None:
        flow = self.store.get_flow("flow_demo")
        assert flow is not None

        updated_flow = flow.model_copy(deep=True)
        for node in updated_flow.definition.nodes:
            if isinstance(node, AgentNode):
                node.data.agent_binding.agent_id = agent_id

        self.store.flows[updated_flow.id] = updated_flow

    def test_stream_run_emits_expected_success_sequence(self) -> None:
        with patch.object(
            agent_runner,
            "stream",
            return_value=iter(
                [
                    {"type": "delta", "delta": "Hel"},
                    {"type": "delta", "delta": "lo"},
                    {
                        "type": "completed",
                        "output": {
                            "message": "Hello",
                            "status": "success",
                        },
                    },
                ]
            ),
        ):
            events = list(
                self.runner.run_flow_stream(
                    "flow_demo",
                    RunCreateRequest(input={"user_message": "hello"}),
                )
            )

        self.assertEqual(
            [event for event, _ in events],
            ["run.started", "step.started", "token.delta", "token.delta", "step.completed", "run.completed"],
        )
        completed = events[-1][1]
        self.assertEqual(completed["status"], RunStatus.COMPLETED)
        self.assertEqual(completed["output"]["final_text"], "Hello")
        self.assertEqual(completed["steps"][-1]["status"], "completed")

    def test_stream_run_emits_failure_completion_when_agent_is_missing(self) -> None:
        self._set_demo_agent_id("agent_missing")

        events = list(
            self.runner.run_flow_stream(
                "flow_demo",
                RunCreateRequest(input={"user_message": "hello"}),
            )
        )

        self.assertEqual(
            [event for event, _ in events],
            ["run.started", "step.started", "step.failed", "run.completed"],
        )
        completed = events[-1][1]
        self.assertEqual(completed["status"], RunStatus.FAILED)
        self.assertTrue(completed["output"]["failed"])
        self.assertEqual(completed["events"][-1]["event_type"], "run.failed")

    def test_stream_run_does_not_emit_control_tag_fragments_as_token_deltas(self) -> None:
        with patch.object(
            agent_runner,
            "stream",
            return_value=iter(
                [
                    {"type": "delta", "delta": "任务完成"},
                    {"type": "delta", "delta": '<agent_studio_control>{"flow_status":"success"}'},
                    {"type": "delta", "delta": "</agent_studio_control>"},
                    {
                        "type": "completed",
                        "output": {
                            "message": "任务完成",
                            "status": "success",
                            "control": {"flow_status": "success"},
                        },
                    },
                ]
            ),
        ):
            events = list(
                self.runner.run_flow_stream(
                    "flow_demo",
                    RunCreateRequest(input={"user_message": "hello"}),
                )
            )

        token_deltas = [payload["delta"] for event, payload in events if event == "token.delta"]
        self.assertEqual(token_deltas, ["任务完成"])


if __name__ == "__main__":
    unittest.main()
