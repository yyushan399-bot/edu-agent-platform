"""PBL 配置、缓存与 scoring 工具单元测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.group_project.pbl_config import DEFAULT_SCORING_TIMES
from agents.group_project.scoring_utils import judge_consistency, safe_json_loads
from services.pbl_evaluation_cache import build_cache_key, get_cached_evaluation, set_cached_evaluation


class TestPblConfig(unittest.TestCase):
    def test_default_scoring_times_is_three(self) -> None:
        with patch.dict("os.environ", {"PBL_SCORING_TIMES": "3"}, clear=False):
            from importlib import reload

            import agents.group_project.pbl_config as cfg

            reload(cfg)
            self.assertEqual(cfg.DEFAULT_SCORING_TIMES, 3)

        self.assertGreaterEqual(DEFAULT_SCORING_TIMES, 1)


class TestScoringUtils(unittest.TestCase):
    def test_safe_json_loads(self) -> None:
        payload = safe_json_loads('{"score": 4, "reason": "ok"}')
        self.assertEqual(payload["score"], 4)

    def test_judge_consistency_stable(self) -> None:
        label = judge_consistency(0.05, 0.1, 3.0, 4.0)
        self.assertEqual(label, "评分稳定")


class TestPblEvaluationCache(unittest.TestCase):
    def test_cache_roundtrip(self) -> None:
        with patch("services.pbl_evaluation_cache.PBL_CACHE_ENABLED", True):
            key = build_cache_key(
                "sample report",
                enable_review=False,
                scoring_times=3,
                rag_top_k=8,
                review_rounds=0,
            )
            sample = {"final_score": 3.5, "dimension_summary": []}
            set_cached_evaluation(key, sample)
            loaded = get_cached_evaluation(key)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.get("final_score"), 3.5)


class TestGroupEvaluationApiMock(unittest.TestCase):
    @patch("pbl_main_graph.pbl_app.invoke")
    def test_run_pbl_analysis_mock(self, mock_invoke) -> None:
        from backend.api.graph_service import run_pbl_analysis

        mock_invoke.return_value = {
            "evaluation_mode": "pbl_report",
            "total_score": 3.2,
            "dimension_mean_score": 3.1,
            "final_feedback": "ok",
            "final_comment": "ok",
            "group_project_results": {
                "creativity": {"score": 3.0, "feedback": "f", "evidence": "e"},
                "critical": {"score": 3.0, "feedback": "f", "evidence": "e"},
                "problemsolving": {"score": 3.5, "feedback": "f", "evidence": "e"},
            },
            "dimension_summary": [{"dimension_name": "问题提出", "mean": 3.0}],
            "primary_indicator_summary": [],
            "pbl_strengths": [],
            "pbl_weaknesses": [],
            "pbl_revision_suggestions": [],
            "pbl_errors": [],
            "audit_passed": False,
            "audit_status": "",
            "output_mode": "",
            "internal_audit": {},
            "last_saved_evaluation_id": "",
        }

        with patch("llm_config.is_dotenv_loaded", return_value=True):
            result = run_pbl_analysis(
                "测试报告正文",
                enable_pbl_review=False,
                pbl_scoring_times=1,
                use_cache=False,
            )

        self.assertEqual(result["final_score"], 3.2)
        self.assertFalse(result.get("cache_hit"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
