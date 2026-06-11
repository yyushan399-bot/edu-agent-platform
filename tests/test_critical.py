"""
批判性思维 Agent 集成测试。

运行方式：
    pytest tests/test_critical.py -v
    venv/Scripts/python.exe -m pytest tests/test_critical.py -v

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

from agents.group_project.critical_agent import evaluate_critical as evaluate


SAMPLE_REPORT_TEXT = """
水火箭加速度影响因素研究 —— 小组项目报告（节选）

二、理论依据与文献
我们查阅了反冲运动与变质量体相关文献，指出经典教材模型通常假设瞬时喷出，
而实际水火箭存在持续喷水过程。前人研究多聚焦最大高度测量，对加速度—时间
曲线的系统分析较少。本研究在牛顿第二定律框架下建立含时变质量的方程组，
并说明推力项来自瓶内气压推动，重力与空气阻力为次要影响因素。

三、实验与数据采集
实验重复测量 3 组有效数据，记录打气量、装水量与瓶型三类条件。采用 Tracker
对视频逐帧标点，导出 t-x-y 表格，再计算速度与加速度。数据处理使用均值与
标准差描述趋势，并将实验 a-t 曲线与理论预测进行半定量对照。对异常点（落地
反冲、镜头晃动）单独标注并讨论。

四、逻辑推演与结论
由斜抛规律可推得 x 方向加速度先增后减；y 方向在动力上升期加速度由正转负，
与“气压推动 + 质量减少”机制一致。结论认为：模型在上升阶段与实验趋势吻合，
但下落阶段未分类讨论，导致部分区间预测偏差较大。

五、局限性与改进
主要局限包括：镜头未固定导致标点误差、瓶身自转影响重心标定、理论模型未
考虑喷水变强度与落地反冲。误差来源还涉及电线杆标定比例偏差。改进方向为：
固定机位、增加重复实验次数、对下落与反冲阶段分别建模，并补充变量控制说明。
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
class TestCriticalAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scoring_times = int(os.getenv("TEST_SCORING_TIMES", "1"))

    def test_evaluate_returns_unified_fields(self) -> None:
        result = evaluate(
            SAMPLE_REPORT_TEXT,
            scoring_times=self.scoring_times,
            rag_top_k=4,
        )

        print("\n========== evaluate_critical() 输出 ==========")
        _safe_print_json(result)
        print("==============================================\n")

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
