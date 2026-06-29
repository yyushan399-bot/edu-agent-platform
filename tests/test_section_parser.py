"""学生反馈章节切分 · 阶段 1 单元测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.section_constants import SECTION_NAMES
from utils.section_parser import (
    match_section_title,
    parse_report_from_path,
    split_report_paragraphs,
    split_report_text,
)

SAMPLE_REPORT = """
项目化学习研究报告

一、文献检索
我们检索了 PubMed 与 CNKI，筛选出 12 篇近五年文献，并比较不同火箭推进方案。

二、问题提出
本研究关注水火箭射程与充水量关系，提出可检验的假设与变量定义。

三、理论分析
基于流体力学与动量守恒建立简化模型，说明压强与喷口面积的作用机理。

四、数值模拟
使用 Python 编写仿真脚本，对不同充水量进行参数扫描并输出预测曲线。

五、实验实施
搭建发射架并完成 9 组重复实验，记录射程、充水量与发射角度等关键条件。

六、数据分析
对实验数据进行均值、标准差与线性拟合，比较模拟趋势与实测结果差异。

七、结论生成
总结主要发现，指出模型局限，并提出后续改进方向与创新表达。
""".strip()


class TestSectionTitleMatching(unittest.TestCase):
    def test_exact_section_name(self) -> None:
        name, title = match_section_title("五、实验实施")
        self.assertEqual(name, "实验实施")
        self.assertEqual(title, "五、实验实施")

    def test_alias_with_number_prefix(self) -> None:
        name, _ = match_section_title("六、数据")
        self.assertEqual(name, "数据分析")

    def test_conclusion_alias_prefers_last_section_with_number(self) -> None:
        name, _ = match_section_title("七、结论")
        self.assertEqual(name, "结论生成")


class TestSectionSplitting(unittest.TestCase):
    def test_split_full_report_text(self) -> None:
        result = split_report_text(SAMPLE_REPORT)
        self.assertGreaterEqual(len(result.sections), 5)
        self.assertEqual(result.found_sections, SECTION_NAMES)
        self.assertEqual(result.missing_sections, [])

        exp = result.get_section_text("实验实施")
        self.assertIsNotNone(exp)
        assert exp is not None
        self.assertIn("9 组重复实验", exp)

    def test_split_docx_style_paragraphs(self) -> None:
        paragraphs = [line for line in SAMPLE_REPORT.split("\n") if line.strip()]
        result = split_report_paragraphs(paragraphs)
        self.assertEqual(len(result.sections), 7)
        self.assertIn("项目化学习研究报告", result.unmatched_text)

    def test_to_dict_shape(self) -> None:
        result = split_report_text(SAMPLE_REPORT)
        payload = result.to_dict()
        self.assertIn("sections", payload)
        self.assertIn("unmatched_text", payload)
        self.assertIn("missing_sections", payload)
        first = payload["sections"][0]
        self.assertEqual(set(first.keys()), {"section_name", "text", "char_count", "title_line"})


class TestParseFromPath(unittest.TestCase):
    def test_parse_txt_fixture(self) -> None:
        fixture = PROJECT_ROOT / "tests" / "fixtures" / "sample_section_report.txt"
        self.assertTrue(fixture.is_file(), f"缺少测试样例：{fixture}")
        result = parse_report_from_path(fixture)
        self.assertGreaterEqual(len(result.sections), 5)


if __name__ == "__main__":
    unittest.main()
