"""章节反馈 · 阶段 3 平台打通单元测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from state import create_section_initial_state as _create_section_initial_state

    HAS_FULL_GRAPH_DEPS = True
except Exception:
    HAS_FULL_GRAPH_DEPS = False

from utils.section_summary import build_section_summary
from memory.evaluation_store import build_evaluation_record
from memory.memory_retriever import format_evaluation_summary


SAMPLE_SECTION_STATE = {
    "evaluation_mode": "section_report",
    "section_target": "",
    "section_texts": {"实验实施": "我们完成了三次重复实验。" * 20},
    "section_results": [
        {
            "section_name": "实验实施",
            "total_score": 3.8,
            "strengths": ["记录完整"],
            "weaknesses": ["误差分析不足"],
            "suggestions": ["补充重复实验"],
            "audit_rounds_used": 1,
            "criterion_details": [
                {"criterion_name": "方案实施", "weight": 0.9, "mean": 4.0},
            ],
            "graphrag_backend": "json",
        }
    ],
    "section_summary": {
        "overall_score": 3.8,
        "section_scores": {"实验实施": 3.8},
        "evaluated_sections": ["实验实施"],
        "skipped_sections": ["文献检索"],
        "strongest_sections": ["实验实施"],
        "weakest_sections": [],
        "overall_comment": "「实验实施」3.8/5.0",
        "parse_warnings": [],
    },
    "section_skipped": ["文献检索"],
    "section_errors": [],
    "total_score": 3.8,
    "final_feedback": "「实验实施」3.8/5.0",
    "final_comment": "「实验实施」3.8/5.0",
    "graphrag_backend": "json",
    "last_saved_evaluation_id": "sec-001",
}


class TestSectionPlatform(unittest.TestCase):
    @unittest.skipUnless(HAS_FULL_GRAPH_DEPS, "requires full LangGraph/agents dependencies")
    def test_create_section_initial_state(self) -> None:
        state = _create_section_initial_state(
            "整份报告正文",
            section_name="实验实施",
            student_id="stu001",
            enable_section_review=False,
            section_scoring_times=2,
        )
        self.assertEqual(state["evaluation_mode"], "section_report")
        self.assertEqual(state["report_text"], "整份报告正文")
        self.assertEqual(state["section_target"], "实验实施")
        self.assertEqual(state["section_scoring_times"], 2)
        self.assertFalse(state["enable_section_review"])

    def test_format_section_state_response(self) -> None:
        from backend.api.graph_service import format_section_state_response

        payload = format_section_state_response(SAMPLE_SECTION_STATE)
        self.assertEqual(payload["evaluation_mode"], "section_report")
        self.assertEqual(payload["overall_score"], 3.8)
        self.assertEqual(len(payload["section_results"]), 1)
        self.assertEqual(payload["section_results"][0]["section_name"], "实验实施")
        self.assertEqual(payload["graphrag_backend"], "json")
        self.assertEqual(payload["last_saved_evaluation_id"], "sec-001")

    def test_build_section_summary(self) -> None:
        summary = build_section_summary(
            SAMPLE_SECTION_STATE["section_results"],
            skipped_sections=["文献检索"],
        )
        self.assertEqual(summary["overall_score"], 3.8)
        self.assertIn("实验实施", summary["section_scores"])
        self.assertIn("文献检索", summary["skipped_sections"])

    def test_build_evaluation_record_section_fields(self) -> None:
        record = build_evaluation_record(
            student_input="章节报告",
            evaluation_mode="section_report",
            section_target="实验实施",
            section_results=SAMPLE_SECTION_STATE["section_results"],
            section_summary=SAMPLE_SECTION_STATE["section_summary"],
            total_score=3.8,
            final_feedback="章节反馈",
            final_comment="章节反馈",
        )
        self.assertEqual(record["evaluation_mode"], "section_report")
        self.assertEqual(record["section_target"], "实验实施")
        self.assertEqual(len(record["section_results"]), 1)
        self.assertEqual(record["section_summary"]["overall_score"], 3.8)

    def test_format_evaluation_summary_section_mode(self) -> None:
        record = build_evaluation_record(
            student_input="章节报告",
            evaluation_mode="section_report",
            section_results=SAMPLE_SECTION_STATE["section_results"],
            section_summary=SAMPLE_SECTION_STATE["section_summary"],
            total_score=3.8,
            final_feedback="章节反馈",
        )
        summary = format_evaluation_summary(record, index=1)
        self.assertIn("章节反馈", summary)
        self.assertIn("实验实施", summary)
        self.assertIn("3.8", summary)

    @unittest.skipUnless(HAS_FULL_GRAPH_DEPS, "requires full LangGraph/agents dependencies")
    @patch("section_main_graph.section_app.invoke")
    @patch("llm_config.is_dotenv_loaded", return_value=True)
    def test_run_section_analysis_invokes_graph(
        self,
        _mock_dotenv: object,
        mock_invoke: object,
    ) -> None:
        from backend.api.graph_service import run_section_analysis

        mock_invoke.return_value = dict(SAMPLE_SECTION_STATE)
        payload = run_section_analysis(
            "整份报告",
            section_name="实验实施",
            student_id="stu001",
            enable_section_review=False,
        )
        self.assertEqual(payload["evaluation_mode"], "section_report")
        self.assertEqual(payload["overall_score"], 3.8)
        mock_invoke.assert_called_once()

    def test_section_split_node_from_fixture(self) -> None:
        from utils.section_parser import split_report_text

        fixture = PROJECT_ROOT / "tests" / "fixtures" / "sample_section_report.txt"
        report_text = fixture.read_text(encoding="utf-8")
        parsed = split_report_text(report_text)
        self.assertGreaterEqual(len(parsed.sections), 5)


if __name__ == "__main__":
    unittest.main()
