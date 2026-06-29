"""阶段 3：PBL 主图 / 记忆 / API 平台打通单元测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.graph_service import format_pbl_state_response
from memory.evaluation_store import build_evaluation_record
from memory.memory_retriever import format_evaluation_summary
from state import create_pbl_initial_state


SAMPLE_PBL_STATE = {
    "evaluation_mode": "pbl_report",
    "total_score": 3.5,
    "dimension_mean_score": 3.2,
    "final_feedback": "整体表现良好",
    "final_comment": "建议加强证据分析",
    "group_project_results": {
        "creativity": {"score": 3.5, "feedback": "创造较好", "evidence": "ev1"},
        "critical": {"score": 3.0, "feedback": "批判一般", "evidence": "ev2"},
        "problemsolving": {"score": 3.8, "feedback": "问题解决较好", "evidence": "ev3"},
    },
    "dimension_summary": [
        {"dimension_name": "问题提出", "mean": 4.0, "summary_comment": "较好"},
        {"dimension_name": "证据分析", "mean": 2.5, "summary_comment": "不足"},
    ],
    "primary_indicator_summary": [
        {"primary_indicator_name": "创造性思维", "mean": 3.5, "summary_comment": "尚可"},
    ],
    "audit_passed": True,
    "audit_status": "passed",
    "pbl_strengths": ["方案完整"],
    "pbl_weaknesses": ["证据不足"],
    "pbl_revision_suggestions": ["补充数据"],
    "last_saved_evaluation_id": "abc-123",
}


class TestPblPlatform(unittest.TestCase):
    def test_create_pbl_initial_state(self) -> None:
        state = create_pbl_initial_state(
            "项目报告正文",
            student_id="stu001",
            enable_pbl_review=True,
            pbl_scoring_times=3,
        )
        self.assertEqual(state["evaluation_mode"], "pbl_report")
        self.assertEqual(state["report_text"], "项目报告正文")
        self.assertEqual(state["student_id"], "stu001")
        self.assertTrue(state["enable_pbl_review"])
        self.assertEqual(state["pbl_scoring_times"], 3)

    def test_format_pbl_state_response(self) -> None:
        payload = format_pbl_state_response(SAMPLE_PBL_STATE)
        self.assertEqual(payload["evaluation_mode"], "pbl_report")
        self.assertEqual(payload["final_score"], 3.5)
        self.assertEqual(len(payload["dimension_summary"]), 2)
        self.assertEqual(payload["creativity"]["score"], 3.5)
        self.assertEqual(payload["strengths"], ["方案完整"])
        self.assertEqual(payload["last_saved_evaluation_id"], "abc-123")

    def test_build_evaluation_record_pbl_fields(self) -> None:
        record = build_evaluation_record(
            student_input="PBL 报告",
            evaluation_mode="pbl_report",
            dimension_summary=[{"dimension_name": "问题提出", "mean": 4.0}],
            primary_indicator_summary=[{"primary_indicator_name": "创造性思维", "mean": 3.5}],
            dimension_mean_score=3.2,
            total_score=3.5,
            final_feedback="反馈",
            final_comment="评语",
            audit_passed=True,
            audit_status="passed",
        )
        self.assertEqual(record["evaluation_mode"], "pbl_report")
        self.assertEqual(len(record["dimension_summary"]), 1)
        self.assertEqual(record["dimension_mean_score"], 3.2)
        self.assertTrue(record["audit_passed"])

    def test_format_evaluation_summary_includes_pbl_dimensions(self) -> None:
        record = build_evaluation_record(
            student_input="PBL 报告",
            evaluation_mode="pbl_report",
            dimension_summary=[
                {"dimension_name": "问题提出", "mean": 4.0},
                {"dimension_name": "证据分析", "mean": 2.5},
            ],
            primary_indicator_summary=[
                {"primary_indicator_name": "创造性思维", "mean": 3.5},
            ],
            dimension_mean_score=3.2,
            total_score=3.5,
            group_project_results={
                "creativity": {"score": 3.5, "feedback": "创造较好"},
            },
            final_feedback="综合反馈",
        )
        summary = format_evaluation_summary(record, index=1)
        self.assertIn("PBL小组项目", summary)
        self.assertIn("12维", summary)
        self.assertIn("一级指标", summary)
        self.assertIn("创造性", summary)

    def test_extract_text_from_path_txt(self) -> None:
        from utils.file_parser import extract_text_from_path

        with tempfile.NamedTemporaryFile(
            "w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write("小组项目报告内容")
            temp_path = handle.name

        try:
            text = extract_text_from_path(temp_path)
            self.assertEqual(text, "小组项目报告内容")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch("agents.group_project.group_evaluation_node.run_group_evaluation")
    def test_pbl_graph_invoke_with_mock(self, mock_run) -> None:
        async def _fake_run(*_args, **_kwargs):
            return {
                "creativity": {"score": 3.0, "feedback": "f1", "evidence": "e1"},
                "critical": {"score": 3.0, "feedback": "f2", "evidence": "e2"},
                "problemsolving": {"score": 3.0, "feedback": "f3", "evidence": "e3"},
                "dimension_summary": [{"dimension_name": "问题提出", "mean": 3.0}],
                "final_score": 3.0,
                "dimension_mean_score": 3.0,
                "final_feedback": "ok",
                "errors": [],
            }

        mock_run.side_effect = _fake_run

        from pbl_main_graph import pbl_app
        from state import create_pbl_initial_state

        state = create_pbl_initial_state("测试报告", student_id="stu_mock")
        result = pbl_app.invoke(state)

        self.assertEqual(result.get("evaluation_mode"), "pbl_report")
        self.assertEqual(result.get("total_score"), 3.0)
        self.assertEqual(len(result.get("dimension_summary") or []), 1)
        self.assertTrue(result.get("last_saved_evaluation_id"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
