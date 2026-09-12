from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ["STORAGE_BACKEND"] = "memory"

from app.repositories.in_memory import InMemoryStore
from app.runners.agent_runner import agent_runner
from app.runners.flow_runner import FlowRunner
from app.schemas.contracts import AgentNode, RunCreateRequest, RunStatus, StepStatus


class FlowRunnerFailureTests(unittest.TestCase):
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

    def test_run_flow_fails_cleanly_when_agent_is_missing(self) -> None:
        self._set_demo_agent_id("agent_missing")

        result = self.runner.run_flow(
            "flow_demo",
            RunCreateRequest(input={"user_message": "hello"}),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertTrue(result.output["failed"])
        self.assertIn("执行失败", result.output["summary"])
        self.assertEqual(result.steps[-1].status, StepStatus.FAILED)
        self.assertIn("agent_missing not found", result.steps[-1].error or "")
        self.assertEqual(result.events[-1].event_type, "run.failed")
        self.assertEqual(result.events[-1].payload["reason"], "dependency_not_found")

    def test_run_flow_returns_failed_run_when_agent_execution_raises(self) -> None:
        with patch.object(agent_runner, "run", side_effect=RuntimeError("boom")):
            result = self.runner.run_flow(
                "flow_demo",
                RunCreateRequest(input={"user_message": "hello"}),
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertTrue(result.output["failed"])
        self.assertEqual(result.steps[-1].status, StepStatus.FAILED)
        self.assertEqual(result.steps[-1].error, "boom")
        self.assertEqual(result.events[-1].event_type, "run.failed")
        self.assertEqual(result.events[-1].payload["reason"], "step_execution_failed")


if __name__ == "__main__":
    unittest.main()
