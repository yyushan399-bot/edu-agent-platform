"""一级指标汇总单元测试（不调用 LLM）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.group_project.primary_indicator_agent import (
    PRIMARY_INDICATOR_GROUPS,
    build_primary_indicator_summary,
    normalize_dimension_name,
)


SAMPLE_DIMENSION_SUMMARY = [
    {"dimension_name": "问题提出", "mean": 4.0, "summary_comment": "问题提出较好"},
    {"dimension_name": "方案新颖性", "mean": 3.0, "summary_comment": "方案较新"},
    {"dimension_name": "创新表征", "mean": 3.5, "summary_comment": "表征一般"},
    {"dimension_name": "创新表达", "mean": 3.0, "summary_comment": "表达尚可"},
    {"dimension_name": "证据分析", "mean": 2.5, "summary_comment": "证据不足"},
    {"dimension_name": "数据分析", "mean": 3.0, "summary_comment": "数据一般"},
    {"dimension_name": "逻辑推演", "mean": 3.5, "summary_comment": "逻辑尚可"},
    {"dimension_name": "局限性评价", "mean": 2.0, "summary_comment": "局限分析弱"},
    {"dimension_name": "问题界定", "mean": 3.5, "summary_comment": "界定清楚"},
    {"dimension_name": "方案建构", "mean": 3.0, "summary_comment": "方案完整"},
    {"dimension_name": "方案实施", "mean": 3.5, "summary_comment": "实施较完整"},
    {"dimension_name": "反思调节", "mean": 3.0, "summary_comment": "反思一般"},
]


class TestPrimaryIndicatorAgent(unittest.TestCase):
    def test_normalize_dimension_name(self) -> None:
        self.assertEqual(normalize_dimension_name(" 证据分析 "), "证据分析")

    @patch(
        "agents.group_project.primary_indicator_agent._summarize_primary_indicators_with_llm",
        side_effect=lambda **kwargs: kwargs["primary_summary"],
    )
    def test_build_primary_indicator_summary_structure(self, _mock_llm) -> None:
        result = build_primary_indicator_summary(dimension_summary=SAMPLE_DIMENSION_SUMMARY)

        self.assertEqual(len(result), 3)
        names = {item["primary_indicator_name"] for item in result}
        expected = {group["primary_indicator_name"] for group in PRIMARY_INDICATOR_GROUPS}
        self.assertEqual(names, expected)

        creativity = next(
            item for item in result if item["primary_indicator_name"] == "创造性思维"
        )
        self.assertEqual(creativity["mean"], 3.38)
        self.assertTrue(creativity["advantages"])
        self.assertTrue(creativity["summary_comment"])
        self.assertEqual(len(creativity["secondary_dimensions"]), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
