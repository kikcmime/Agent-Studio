from __future__ import annotations

import unittest

from app.runners.flow_runtime import build_final_output, build_round_summary
from app.schemas.contracts import RunStepResult, StepStatus


class FlowRuntimeOutputTests(unittest.TestCase):
    def test_non_rps_team_does_not_produce_fake_round_summary(self) -> None:
        steps = [
            RunStepResult(
                id="step_team",
                node_id="doudizhu_players",
                node_type="team",
                status=StepStatus.COMPLETED,
                input={},
                output={
                    "result": {
                        "mode": "team",
                        "member_results": [
                            {"agent_name": "斗地主地主 Agent", "message": "我先出三带一。"},
                            {"agent_name": "斗地主农民上家 Agent", "message": "我建议先压低。"},
                        ],
                    }
                },
            ),
            RunStepResult(
                id="step_referee",
                node_id="doudizhu_referee",
                node_type="agent",
                status=StepStatus.COMPLETED,
                input={},
                output={"result": {"message": "地主先手，建议出三带一，农民保留炸弹反制。"}},
            ),
        ]

        rounds = build_round_summary(steps)
        output = build_final_output({"flow_id": "flow_doudizhu_team", "input": {"user_message": "开始一局斗地主"}}, steps)

        self.assertEqual(rounds, [])
        self.assertEqual(output["final_text"], "地主先手，建议出三带一，农民保留炸弹反制。")
        self.assertNotIn("rounds", output)


if __name__ == "__main__":
    unittest.main()
