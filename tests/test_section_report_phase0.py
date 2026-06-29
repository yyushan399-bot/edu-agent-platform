"""学生反馈章节评价 · 阶段 0 单元测试（无 Neo4j / LLM）。"""

from __future__ import annotations

import statistics
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.group_project.scoring_utils import judge_consistency
from agents.section_report.section_config import (
    DEFAULT_CV_THRESHOLD,
    SECTION_NAMES,
    neo4j_configured,
)
from agents.section_report.section_scoring_agent import (
    CriterionScore,
    build_section_scoring_prompt,
    score_single_criterion,
)
from agents.section_report.section_review_agent import (
    check_evidence_traceability,
    check_score_stability,
)


class TestSectionConfig(unittest.TestCase):
    def test_section_names_count(self) -> None:
        self.assertEqual(len(SECTION_NAMES), 7)
        self.assertIn("实验实施", SECTION_NAMES)

    def test_neo4j_configured_false_without_password(self) -> None:
        with patch.dict("os.environ", {"NEO4J_PASSWORD": ""}, clear=False):
            self.assertFalse(neo4j_configured())


class TestSectionScoring(unittest.TestCase):
    def test_build_section_scoring_prompt(self) -> None:
        system_prompt, user_prompt = build_section_scoring_prompt(
            section_name="实验实施",
            criterion_name="方案实施",
            weight=0.35,
            rubrics={5: "优秀", 3: "一般", 1: "差"},
            exemplars={},
            student_text="我们完成了三次重复实验。",
            round_index=1,
        )
        self.assertIn("实验实施", system_prompt)
        self.assertIn("方案实施", user_prompt)
        self.assertIn("我们完成了三次重复实验", user_prompt)

    def test_score_single_criterion_uses_statistics(self) -> None:
        llm = MagicMock()
        llm.chat_json.side_effect = [
            {
                "score": 4,
                "reason": "实施记录较完整",
                "evidence": ["完成了三次重复实验"],
                "reference_comparison": "",
                "weakness": "",
                "suggestion": "",
            },
            {
                "score": 5,
                "reason": "实施记录较完整",
                "evidence": ["完成了三次重复实验"],
                "reference_comparison": "",
                "weakness": "",
                "suggestion": "",
            },
            {
                "score": 4,
                "reason": "实施记录较完整",
                "evidence": ["完成了三次重复实验"],
                "reference_comparison": "",
                "weakness": "",
                "suggestion": "",
            },
        ]

        summary = score_single_criterion(
            llm=llm,
            section_name="实验实施",
            criterion_name="方案实施",
            weight=0.4,
            rubrics={5: "优秀", 4: "良好", 3: "一般"},
            exemplars={},
            student_text="我们完成了三次重复实验，并记录了温度变化。",
            scoring_times=3,
        )

        numeric = [4, 5, 4]
        self.assertEqual(summary.mean, round(statistics.fmean(numeric), 3))
        self.assertEqual(summary.std, round(statistics.pstdev(numeric), 3))
        self.assertEqual(
            summary.consistency_level,
            judge_consistency(summary.cv, summary.std, summary.min_score, summary.max_score),
        )
        self.assertEqual(len(summary.scores), 3)
        self.assertTrue(all(isinstance(s, CriterionScore) for s in summary.scores))


class TestSectionReviewChecks(unittest.TestCase):
    def test_check_score_stability_passes_at_threshold(self) -> None:
        scores = [{"score": 4} for _ in range(5)] + [{"score": 5}]
        result = check_score_stability("方案实施", scores, cv_threshold=DEFAULT_CV_THRESHOLD)
        self.assertTrue(result["passed"])

    def test_check_evidence_traceability_rejects_reference_leak(self) -> None:
        student_text = "我们完成了实验并记录了数据。"
        scores = [{"evidence": ["GraphRAG 检索到的优质报告片段"]}]
        result = check_evidence_traceability("方案实施", scores, student_text)
        self.assertFalse(result["passed"])
        self.assertTrue(any("GraphRAG" in issue for issue in result["issues"]))


class TestGraphRAGService(unittest.TestCase):
    def test_create_graphrag_retriever_raises_without_password(self) -> None:
        from services.section_graphrag_service import create_graphrag_retriever

        with patch.dict("os.environ", {"NEO4J_PASSWORD": ""}, clear=False):
            with self.assertRaises(ValueError):
                create_graphrag_retriever()

    @patch("services.section_graphrag_service.GraphDatabase")
    def test_graphrag_retriever_retrieve_full_context(self, mock_graph_database) -> None:
        with patch.dict("os.environ", {"NEO4J_PASSWORD": "test-password"}, clear=False):
            session = MagicMock()
            driver = MagicMock()
            driver.session.return_value.__enter__.return_value = session
            mock_graph_database.driver.return_value = driver

            session.run.side_effect = [
                iter([{"criterion_name": "方案实施", "weight": 0.4}]),
                iter(
                    [
                        {"score": 5, "description": "优秀"},
                        {"score": 3, "description": "一般"},
                    ]
                ),
                iter([{"score": 5, "exemplars": []}, {"score": 3, "exemplars": []}]),
            ]

            from services.section_graphrag_service import GraphRAGRetriever

            retriever = GraphRAGRetriever()
            context = retriever.retrieve_full_context("实验实施")

        self.assertEqual(context["section_name"], "实验实施")
        self.assertEqual(len(context["criteria"]), 1)
        self.assertEqual(context["criteria"][0]["criterion_name"], "方案实施")
        self.assertEqual(context["criteria"][0]["rubrics"][5], "优秀")


class TestSectionReportPackage(unittest.TestCase):
    def test_import_section_report_package(self) -> None:
        import agents.section_report as section_report

        self.assertIsNotNone(section_report.run_review_loop)
        self.assertIsNotNone(section_report.score_criteria)


if __name__ == "__main__":
    unittest.main()
