from __future__ import annotations

import json
import os
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ["STORAGE_BACKEND"] = "memory"

from fastapi.testclient import TestClient

from app.api.run_routes import encode_sse, stream_run_detail
from app.main import app
from app.schemas.contracts import RunDetail, RunEvent, RunStatus, RunStepResult, StepStatus


class RunRoutesSseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_encode_sse_formats_unicode_payload(self) -> None:
        payload = {"message": "你好", "status": "running"}

        event = encode_sse("run.started", payload)

        self.assertEqual(
            event,
            'event: run.started\ndata: {"message": "你好", "status": "running"}\n\n',
        )

    def test_stream_run_detail_emits_started_events_steps_and_completion(self) -> None:
        now = datetime.utcnow()
        run = RunDetail(
            id="run_demo",
            flow_id="flow_demo",
            flow_version=1,
            status=RunStatus.COMPLETED,
            input={"user_message": "hello"},
            output={"final_text": "Hello"},
            started_at=now,
            finished_at=now,
            events=[
                RunEvent(
                    id="evt_1",
                    run_id="run_demo",
                    event_type="token.delta",
                    created_at=now,
                    payload={"delta": "Hel"},
                )
            ],
            steps=[
                RunStepResult(
                    id="step_1",
                    node_id="node_agent_1",
                    node_type="agent",
                    status=StepStatus.COMPLETED,
                    started_at=now,
                    finished_at=now,
                    output={"message": "Hello"},
                )
            ],
        )

        events = list(stream_run_detail(run))

        self.assertEqual(len(events), 4)
        self.assertTrue(events[0].startswith("event: run.started"))
        self.assertIn("event: token.delta", events[1])
        self.assertIn("event: step.completed", events[2])
        self.assertIn("event: run.completed", events[3])

    def test_stream_endpoint_returns_sse_sequence(self) -> None:
        captured_stream_flags: list[bool] = []

        def fake_stream(flow_id: str, request) -> iter:
            captured_stream_flags.append(request.stream)
            self.assertEqual(flow_id, "flow_demo")
            self.assertEqual(request.input["user_message"], "hello")
            return iter(
                [
                    ("run.started", {"run_id": "run_demo", "flow_id": flow_id, "status": "running"}),
                    ("token.delta", {"delta": "Hi"}),
                    (
                        "run.completed",
                        {
                            "id": "run_demo",
                            "flow_id": flow_id,
                            "status": "completed",
                            "output": {"final_text": "Hi"},
                        },
                    ),
                ]
            )

        with patch("app.api.run_routes.flow_runner.run_flow_stream", side_effect=fake_stream):
            response = self.client.post(
                "/api/v1/flows/flow_demo/runs/stream",
                json={"input": {"user_message": "hello"}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertEqual(captured_stream_flags, [True])

        chunks = [chunk for chunk in response.text.strip().split("\n\n") if chunk]
        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[0].startswith("event: run.started"))
        self.assertIn('data: {"delta": "Hi"}', chunks[1])
        self.assertTrue(chunks[2].startswith("event: run.completed"))

        payload = json.loads(chunks[2].split("data: ", 1)[1])
        self.assertEqual(payload["output"]["final_text"], "Hi")


if __name__ == "__main__":
    unittest.main()
