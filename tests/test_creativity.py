"""
创造性思维 Agent 集成测试。

运行方式：
    pytest tests/test_creativity.py -v
    python -m pytest tests/test_creativity.py -v
    python -m unittest tests.test_creativity -v

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

from agents.group_project.creativity_agent import evaluate_creativity as evaluate


SAMPLE_REPORT_TEXT = """
水火箭加速度影响因素研究 —— 小组项目报告（节选）

一、问题提出
本小组关注中学物理课堂中斜抛与反冲运动的综合应用。我们并未沿用教材中
“仅测量最大高度”的常规任务，而是从跨学科视角重新框定问题：在固定坡道角度
与电机电压的前提下，车身质量如何影响水火箭上升阶段的加速度—时间曲线？
该问题将力学模型、实验测量与数据可视化结合，具备向其他推进模型迁移的潜力。

二、方案设计（新颖性）
相比常见单变量实验，我们自主设计了三变量对照方案：打气量（对应压强）、
瓶内装水量、瓶身长径比。实验装置在瓶口加装单向阀并自制尾翼，以提升重复性。
技术路线为：理论建模 → Tracker 视频分析 → 理论—实验对照。

三、创新表征
我们使用 Python（SciPy）联立求解含时变质量的方程组，生成理想 a-t 曲线；
实验部分采用 Tracker 软件对视频逐帧标点，导出 t-x-y-a 数据表，并用 Origin
绘制对比图，对关键机制（气压衰减、喷水变强度、空气阻力）作图示说明。

四、创新表达
本项目的核心创新点在于：将专业课编程用于 PBL 报告的理论可视化，并用
Tracker 获得可溯源的实验加速度曲线。相较常规“公式罗列 + 单次测量”做法，
我们提供了可重复的数据链条。该思路可迁移至其他反冲运动情境；局限在于
瓶身翻转导致重心标定误差，以及下落阶段模型尚未分类讨论。
""".strip()


def _has_api_key() -> bool:
    for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        value = (os.getenv(key) or "").strip()
        if value and value not in {"", "your_api_key_here", "sk-xxx"}:
            return True
    return False


@unittest.skipUnless(_has_api_key(), "需要配置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY")
class TestCreativityAgent(unittest.TestCase):
    """调用 evaluate() 并对统一输出字段做断言。"""

    @classmethod
    def setUpClass(cls) -> None:
        # 集成测试减少采样次数，降低 API 调用量
        cls.scoring_times = int(os.getenv("TEST_SCORING_TIMES", "1"))

    def test_evaluate_returns_unified_fields(self) -> None:
        result = evaluate(
            SAMPLE_REPORT_TEXT,
            scoring_times=self.scoring_times,
            rag_top_k=4,
        )

        print("\n========== evaluate() 输出 ==========")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("=====================================\n")

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
