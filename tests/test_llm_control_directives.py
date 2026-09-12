from __future__ import annotations

import unittest

from app.core.llm import _extract_flow_directives, _strip_control_markup_progressively


class LLMControlDirectiveTests(unittest.TestCase):
    def test_embedded_control_payload_is_extracted_and_removed_from_message(self) -> None:
        directives = _extract_flow_directives(
            '任务完成。\n<agent_studio_control>{"flow_status":"success","status":"success","result":"已完成"}</agent_studio_control>'
        )

        self.assertEqual(directives["flow_status"], "success")
        self.assertEqual(directives["status"], "success")
        self.assertEqual(directives["result"], "已完成")
        self.assertEqual(directives["clean_message"], "任务完成。")
        self.assertEqual(
            directives["control"],
            {"flow_status": "success", "status": "success", "result": "已完成"},
        )

    def test_plain_text_fallback_still_works(self) -> None:
        directives = _extract_flow_directives("结果：玩家A获胜\nflow_status: success")

        self.assertEqual(directives["flow_status"], "success")
        self.assertEqual(directives["result"], "玩家A获胜")
        self.assertEqual(directives["clean_message"], "结果：玩家A获胜\nflow_status: success")

    def test_partial_control_tag_is_hidden_during_streaming(self) -> None:
        self.assertEqual(
            _strip_control_markup_progressively('任务完成<agent_studio_control>{"flow_status":"success"'),
            "任务完成",
        )
        self.assertEqual(
            _strip_control_markup_progressively(
                '任务完成<agent_studio_control>{"flow_status":"success"}</agent_studio_control>'
            ),
            "任务完成",
        )


if __name__ == "__main__":
    unittest.main()
