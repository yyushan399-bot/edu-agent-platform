"""PBL 维度评分 prompt 构建（共享模板）。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from agents.group_project.scoring_utils import format_audit_feedback_for_prompt, format_student_report_sections


def build_standard_dimension_scoring_prompt(
    dimension_key: str,
    dimension_name: str,
    rubric: str,
    merged_report_context: str,
    student_dimension_text: str,
    rag_context: str,
    round_index: int,
    audit_feedback: Optional[Dict[str, Any]] = None,
    *,
    expert_intro: str,
    extra_rules: str = "",
) -> Tuple[str, str]:
    audit_feedback_text = format_audit_feedback_for_prompt(audit_feedback)
    primary_block = format_student_report_sections(
        dimension_name=dimension_name,
        student_dimension_text=student_dimension_text,
    )

    system_prompt = f"""
{expert_intro}

你必须遵守：
1. 只评价当前维度：{dimension_name}
2. 评分范围为1-5分整数
3. 必须基于当前学生报告相关片段进行判断
4. RAG 参考片段只作为评分标尺和对照样例，不能把参考报告内容当作当前学生报告内容
5. 评分证据 evidence 必须来自当前学生报告，不能来自 RAG 参考报告
6. 不要编造当前学生报告中不存在的内容
7. 如果当前学生报告没有体现某项能力，应明确指出缺失，而不是根据参考片段补充
8. 输出必须是 JSON object，不要输出 Markdown
9. 本次是第 {round_index} 次独立评分，请独立判断，不要假设其他评分结果
10. 如果提供了“上一轮审核不通过原因”，你必须在本次评分时重点修正这些问题
{extra_rules}
""".strip()

    user_prompt = f"""
请根据以下量规，对当前学生报告的【{dimension_name}】维度进行评分。

# 当前维度评分量规
{rubric}

# 上一轮审核不通过原因
{audit_feedback_text}

# RAG 参考报告片段
{rag_context if rag_context else "[未检索到参考片段]"}

{primary_block}

# 评分任务
请比较当前学生报告的当前维度相关片段与 RAG 参考片段的质量差异。最终分数必须基于当前学生报告在本维度的实际表现。

# 输出格式
请严格输出以下 JSON 格式：
{{
  "evidence": ["依据1", "依据2"],
  "reason": "评分理由",
  "reference_comparison": "与参考片段的质量差异说明",
  "weakness": "主要不足",
  "suggestion": "改进建议",
  "score": 整数分数
}}
""".strip()

    return system_prompt, user_prompt


PHYSICS_PBL_EXPERT_INTRO = (
    "作为一名资深大学物理项目化学习实践专家，你的职责是根据评价量规，"
    "对大一工科班学生设计的项目化学习报告评分。"
    "你需要根据项目报告【{dimension_name}】维度的情况，对学生的项目报告给出1到5之间的分数。"
)

PHYSICS_PBL_EXTRA_RULES = """
4. 评分首要依据是「当前学生报告相关片段」；「完整报告补充」仅用于片段不足时核对上下文，不得用其他维度的内容抬高本维分数
11. 不要机械迎合审核意见，最终仍必须基于学生报告相关片段/补充全文与当前维度量规进行独立评分
12. 如果上一轮问题是证据不可追溯，本次 evidence 必须尽量引用「当前维度相关片段」中的原文短句
13. 如果上一轮问题是量规不匹配，本次必须严格对齐当前维度量规，不要混入其他维度标准
14. 如果上一轮问题是分数—理由不一致，本次必须保证 score、reason、weakness、suggestion 的含义自洽
""".strip()


def build_physics_pbl_scoring_prompt(
    dimension_key: str,
    dimension_name: str,
    rubric: str,
    merged_report_context: str,
    student_dimension_text: str,
    rag_context: str,
    round_index: int,
    audit_feedback: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    return build_standard_dimension_scoring_prompt(
        dimension_key,
        dimension_name,
        rubric,
        merged_report_context,
        student_dimension_text,
        rag_context,
        round_index,
        audit_feedback,
        expert_intro=PHYSICS_PBL_EXPERT_INTRO.format(dimension_name=dimension_name),
        extra_rules=PHYSICS_PBL_EXTRA_RULES,
    )


CREATIVITY_EXPERT_INTRO = (
    "作为一名资深项目化学习与创造性思维评价专家，你的职责是根据创造性思维评价量规，"
    "对学生项目报告评分。你需要根据项目报告【{dimension_name}】维度的情况，"
    "对学生的项目报告给出1到5之间的分数。"
)

CREATIVITY_EXTRA_RULES = """
4. 评分依据只能是「当前学生报告相关片段」
5. student_dimension_text 必须来自当前学生报告，不能来自 RAG 参考报告
11. 不要机械迎合审核意见，最终仍必须基于学生报告相关片段与当前维度量规进行独立评分
12. 如果上一轮问题是证据不可追溯，本次 evidence 必须尽量引用「当前维度相关片段」中的原文短句
13. 如果上一轮问题是量规不匹配，本次必须严格对齐【{dimension_name}】维度量规，不要混入其他维度标准
14. 如果上一轮问题是分数—理由不一致，本次必须保证 score、reason、weakness、suggestion 的含义自洽
""".strip()


def build_creativity_scoring_prompt(
    dimension_key: str,
    dimension_name: str,
    rubric: str,
    merged_report_context: str,
    student_dimension_text: str,
    rag_context: str,
    round_index: int,
    audit_feedback: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    return build_standard_dimension_scoring_prompt(
        dimension_key,
        dimension_name,
        rubric,
        merged_report_context,
        student_dimension_text,
        rag_context,
        round_index,
        audit_feedback,
        expert_intro=CREATIVITY_EXPERT_INTRO.format(dimension_name=dimension_name),
        extra_rules=CREATIVITY_EXTRA_RULES.format(dimension_name=dimension_name),
    )


__all__ = [
    "build_creativity_scoring_prompt",
    "build_physics_pbl_scoring_prompt",
    "build_standard_dimension_scoring_prompt",
]
