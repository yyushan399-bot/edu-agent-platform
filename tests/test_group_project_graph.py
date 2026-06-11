"""
小组项目评价图集成测试。

运行方式：
    pytest tests/test_group_project_graph.py -v -s
    venv/Scripts/python.exe -m pytest tests/test_group_project_graph.py -v -s

需要环境变量：OPENAI_API_KEY 或 DEEPSEEK_API_KEY
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graphs.group_project_graph import run_group_evaluation


SAMPLE_REPORT_TEXT = """
水火箭加速度影响因素研究 —— 小组项目报告（节选）

一、问题提出（创造性思维）
本小组关注中学物理课堂中斜抛与反冲运动的综合应用。我们并未沿用教材中
“仅测量最大高度”的常规任务，而是从跨学科视角重新框定问题：在固定坡道角度
与电机电压的前提下，车身质量如何影响水火箭上升阶段的加速度—时间曲线？

一、问题界定（问题解决）
研究问题：在固定坡道角度与电机电压下，车身质量如何影响水火箭上升阶段加速度？
自变量：瓶内装水量、打气量（对应压强）、瓶身长径比。
因变量：上升阶段加速度 a-t 曲线特征（峰值加速度、上升时间）。
控制变量：坡道角度、电机电压、瓶口单向阀型号、尾翼结构。
核心假设：气压推动与质量减少共同导致加速度先增后减。
边界条件：仅讨论动力上升阶段；检验指标为 a-t 曲线与理论预测的半定量吻合度。

二、方案设计（新颖性 / 方案建构）
相比常见单变量实验，我们自主设计了三变量对照方案：打气量、装水量、瓶身长径比。
技术路线：理论建模 → Tracker 视频分析 → 理论—实验对照。
操作步骤：理论建模 → 装置制作 → 视频采集 → Tracker 标点 → 数据导出 → 对照分析。
变量控制：三组对照实验，每组重复 3 次；数据记录计划含 t-x-y-a 表格与误差控制预案。

三、理论依据与文献（批判性思维）
我们查阅了反冲运动与变质量体相关文献，指出经典教材模型通常假设瞬时喷出，
而实际水火箭存在持续喷水过程。前人研究多聚焦最大高度测量，对加速度—时间
曲线的系统分析较少。

四、实验与数据采集
实验重复测量 3 组有效数据。采用 Tracker 对视频逐帧标点，导出 t-x-y 表格，
再计算速度与加速度。数据处理使用均值与标准差，并将实验 a-t 曲线与理论预测
进行半定量对照。

五、方案实施
按方案完成 3 组有效数据采集，记录关键条件与测试结果；实验 a-t 曲线在上升
阶段与理论趋势基本一致，部分回应研究问题。

六、逻辑推演与结论
由斜抛规律可推得 x 方向加速度先增后减；y 方向在动力上升期加速度由正转负，
与“气压推动 + 质量减少”机制一致。结论认为模型在上升阶段与实验趋势吻合。

七、局限性与反思调节
主要局限：镜头未固定导致标点误差、下落阶段未分类讨论。
改进方案：固定机位、增加重复实验次数、对下落与反冲阶段分别建模。
预期效果：降低标点误差，提高 a-t 曲线与理论预测吻合度。
""".strip()

TOP_LEVEL_KEYS = ("creativity", "critical", "problemsolving", "final_score", "final_feedback")
AGENT_KEYS = ("creativity", "critical", "problemsolving")
AGENT_RESULT_FIELDS = ("score", "feedback", "evidence")


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
class TestGroupProjectGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scoring_times = int(os.getenv("TEST_SCORING_TIMES", "1"))
        cls.rag_top_k = int(os.getenv("TEST_RAG_TOP_K", "4"))

    def test_run_group_evaluation_returns_expected_fields(self) -> None:
        result = asyncio.run(
            run_group_evaluation(
                SAMPLE_REPORT_TEXT,
                scoring_times=self.scoring_times,
                rag_top_k=self.rag_top_k,
            )
        )

        print("\n========== run_group_evaluation() 输出 ==========")
        _safe_print_json(result)
        print("================================================\n")

        self.assertIsInstance(result, dict)
        for key in TOP_LEVEL_KEYS:
            self.assertIn(key, result, f"缺少顶层字段: {key}")

        for agent_key in AGENT_KEYS:
            agent_result = result[agent_key]
            self.assertIsInstance(agent_result, dict, f"{agent_key} 应为字典")
            for field in AGENT_RESULT_FIELDS:
                self.assertIn(field, agent_result, f"{agent_key} 缺少字段: {field}")

            self.assertIsInstance(agent_result["score"], (int, float))
            self.assertIsInstance(agent_result["feedback"], str)
            self.assertIsInstance(agent_result["evidence"], str)
            self.assertGreater(agent_result["score"], 0.0)
            self.assertLessEqual(agent_result["score"], 5.0)
            self.assertTrue(len(agent_result["feedback"].strip()) > 0)

        self.assertIsInstance(result["final_score"], (int, float))
        self.assertIsInstance(result["final_feedback"], str)
        self.assertGreater(result["final_score"], 0.0)
        self.assertLessEqual(result["final_score"], 5.0)
        self.assertTrue(len(result["final_feedback"].strip()) > 0)

        agent_scores = [result[key]["score"] for key in AGENT_KEYS]
        expected_mean = round(sum(agent_scores) / len(agent_scores), 2)
        self.assertEqual(result["final_score"], expected_mean)


if __name__ == "__main__":
    unittest.main(verbosity=2)
