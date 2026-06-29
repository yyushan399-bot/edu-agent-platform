"""阶段 5：协作能力分数 → 终结性评价智能体。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.summative_evaluation_agent import (
    compute_weighted_collaboration_score,
    run_summative_evaluation,
)


class TestCollaborationComposite(unittest.TestCase):
    def test_equal_weights_when_all_present(self) -> None:
        score, weights = compute_weighted_collaboration_score(
            ai_score=80.0,
            self_score=70.0,
            peer_score=90.0,
        )
        self.assertIsNotNone(score)
        self.assertAlmostEqual(score, 80.0, places=1)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=5)

    def test_renormalize_when_peer_missing(self) -> None:
        score, weights = compute_weighted_collaboration_score(
            ai_score=80.0,
            self_score=60.0,
            peer_score=None,
        )
        self.assertIsNotNone(score)
        self.assertNotIn("peer_score", weights)
        self.assertGreater(score, 60.0)
        self.assertLess(score, 80.0)


class TestSummativeEvaluationAgent(unittest.TestCase):
    def test_run_with_three_scores(self) -> None:
        collaboration = {
            "user_id": 1,
            "assignment_id": 10,
            "ai_score": 82.0,
            "self_score": 98.0,
            "peer_score": 78.0,
            "peer_scores": [76.0, 80.0],
            "peer_review_count": 2,
            "missing_scores": [],
            "ready_for_summative": True,
        }
        result = run_summative_evaluation(collaboration, use_llm=False)
        self.assertEqual(result["collaboration_scores"]["ai_score"], 82.0)
        self.assertEqual(result["self_calibration"]["self_type"], "over_estimation")
        self.assertEqual(result["peer_calibration"]["count"], 2)
        self.assertIsNotNone(result["collaboration_score"])
        self.assertIsNotNone(result["summative_score"])
        self.assertTrue(result["summative_comment"])

    def test_run_with_ai_only(self) -> None:
        collaboration = {
            "user_id": 2,
            "assignment_id": 11,
            "ai_score": 75.0,
            "self_score": None,
            "peer_score": None,
            "peer_scores": [],
            "peer_review_count": 0,
            "missing_scores": ["self_score", "peer_score"],
            "ready_for_summative": True,
        }
        result = run_summative_evaluation(collaboration, use_llm=False)
        self.assertEqual(result["collaboration_score"], 75.0)
        self.assertIn("self_score", result["missing_scores"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
