"""
问题解决能力 Agent 集成测试。

运行方式：
    pytest tests/test_problemsolving.py -v
    venv/Scripts/python.exe -m pytest tests/test_problemsolving.py -v

需要环境变量：OPENAI_API_KEY 或 DEEPSEEK_API_KEY
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.group_project.problemsolving_agent import evaluate_problemsolving as evaluate


SAMPLE_REPORT_TEXT = """
水火箭加速度影响因素研究 —— 小组项目报告（节选）

一、问题界定
研究问题：在固定坡道角度与电机电压下，车身质量如何影响水火箭上升阶段的加速度？
自变量：瓶内装水量、打气量（对应压强）、瓶身长径比。
因变量：上升阶段加速度 a-t 曲线特征（峰值加速度、上升时间）。
控制变量：坡道角度、电机电压、瓶口单向阀型号、尾翼结构。
核心假设：气压推动与质量减少共同导致加速度先增后减；装水量与峰值加速度呈非线性关系。
边界条件：仅讨论动力上升阶段，暂不考虑落地反冲；检验指标为 a-t 曲线与理论预测的半定量吻合度。

二、方案建构
项目目标：建立含时变质量的力学模型，并通过 Tracker 实验验证。
理论依据：牛顿第二定律 + 变质量体反冲模型。
操作步骤：理论建模 → 装置制作 → 视频采集 → Tracker 标点 → 数据导出 → 理论—实验对照。
变量控制：三组对照实验，每组重复 3 次；记录打气量、装水量、瓶型。
数据记录计划：导出 t-x-y-a 表格，计算均值与标准差。
误差控制预案：固定机位、统一标定比例尺、剔除镜头晃动片段。

三、方案实施
实验过程：按方案完成 3 组有效数据采集，使用 Tracker 逐帧标点。
关键条件：打气至相同压强区间、装水量按预设刻度计量。
测试结果：实验 a-t 曲线在上升阶段与理论趋势基本一致；异常点（落地反冲）单独标注。
结果回应：峰值加速度随装水量变化呈现先升后降趋势，部分回应研究问题。

四、反思调节
主要问题：镜头未固定导致标点误差；下落阶段未分类讨论。
改进方案：增加固定支架、每组重复 5 次；对下落与反冲阶段分别建模。
预期效果：降低标点误差，提高 a-t 曲线与理论预测吻合度。
""".strip()


def _safe_print_json(data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        print(json.dumps(data, ensure_ascii=True, indent=2))


def _has_api_key() -> bool:
    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        value = (os.getenv(key) or "").strip()
        if value and value not in {"", "your_api_key_here", "sk-xxx"}:
            return True
    return False


@unittest.skipUnless(_has_api_key(), "需要配置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY")
class TestProblemSolvingAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scoring_times = int(os.getenv("TEST_SCORING_TIMES", "1"))

    def test_evaluate_returns_unified_fields(self) -> None:
        result = evaluate(
            SAMPLE_REPORT_TEXT,
            scoring_times=self.scoring_times,
            rag_top_k=4,
        )

        print("\n========== evaluate_problemsolving() 输出 ==========")
        _safe_print_json(result)
        print("====================================================\n")

        self.assertIsInstance(result, dict)
        self.assertIn("score", result)
        self.assertIn("feedback", result)
        self.assertIn("evidence", result)

        self.assertIsInstance(result["score"], (int, float))
        self.assertIsInstance(result["feedback"], str)
        self.assertIsInstance(result["evidence"], str)

        self.assertGreater(result["score"], 0.0)
        self.assertLessEqual(result["score"], 5.0)
        self.assertTrue(len(result["feedback"].strip()) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
