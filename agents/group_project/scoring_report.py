"""PBL 评分汇总报告生成（共享）。"""

from __future__ import annotations

import json
import statistics
from typing import Any, Dict, List, Optional, TypedDict

from agents.group_project.scoring_models import DeepSeekClient, DimensionScoreSummary, FinalGradeReport
from agents.group_project.scoring_utils import (
    build_dimension_summary,
    build_dimension_summary_text,
    ensure_list,
    summarize_dimension_scores,
)


class UnifiedEvaluationResult(TypedDict):
    score: float
    feedback: str
    evidence: str


def generate_final_comment_with_llm(
    llm: DeepSeekClient,
    dimension_results: Dict[str, DimensionScoreSummary],
    risk_flags: List[str],
) -> Dict[str, Any]:
    dimension_brief = {
        key: {
            "dimension_name": value.dimension_name,
            "mean": value.mean,
            "std": value.std,
            "cv": value.cv,
            "min_score": value.min_score,
            "max_score": value.max_score,
            "consistency_level": value.consistency_level,
            "summary_comment": value.summary_comment,
            "student_dimension_text": value.student_dimension_text,
        }
        for key, value in dimension_results.items()
    }

    system_prompt = """
你是一名教育评价专家。你现在只做汇总评价，不重新评分。
你必须基于已给出的四个维度统计结果，生成最终反馈。
不能修改各维度分数。
不能计算、生成或展示报告总分。
不能输出或复述 RAG 参考报告原文。
只能基于当前学生报告相关文本和各维度评分总结进行反馈。
输出必须是 JSON object，不要输出 Markdown。
""".strip()

    user_prompt = f"""
四个维度统计结果：
{json.dumps(dimension_brief, ensure_ascii=False, indent=2)}

风险标记：
{json.dumps(risk_flags, ensure_ascii=False, indent=2)}

请输出以下 JSON 格式：

{{
  "strengths": ["学生报告的主要优势1", "学生报告的主要优势2"],
  "weaknesses": ["学生报告的主要不足1", "学生报告的主要不足2"],
  "revision_suggestions": ["具体修改建议1", "具体修改建议2"],
  "final_comment": "一段完整、客观、适合反馈给学生的总评。注意不要出现报告总分。"
}}
""".strip()

    try:
        raw = llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.4)
        return {
            "strengths": ensure_list(raw.get("strengths")),
            "weaknesses": ensure_list(raw.get("weaknesses")),
            "revision_suggestions": ensure_list(raw.get("revision_suggestions")),
            "final_comment": str(raw.get("final_comment", "")),
        }
    except Exception as exc:
        return {
            "strengths": [],
            "weaknesses": [],
            "revision_suggestions": [],
            "final_comment": f"最终汇总生成失败：{exc}",
        }


def aggregate_final_report(
    llm: DeepSeekClient,
    dimension_results: Dict[str, DimensionScoreSummary],
) -> FinalGradeReport:
    risk_flags: List[str] = []

    for result in dimension_results.values():
        if result.cv is not None and result.cv >= 0.20:
            risk_flags.append(
                f"{result.dimension_name} 维度 CV={result.cv}，评分分歧较大，建议人工复核。"
            )
        if result.max_score - result.min_score >= 2:
            risk_flags.append(
                f"{result.dimension_name} 维度最高分与最低分差距为 "
                f"{result.max_score - result.min_score:.1f}，建议检查报告内容是否存在歧义。"
            )
        if not result.student_dimension_text:
            risk_flags.append(
                f"{result.dimension_name} 维度未能抽取到明显相关片段，评分可靠性可能较低。"
            )

    final_meta = generate_final_comment_with_llm(llm, dimension_results, risk_flags)

    return FinalGradeReport(
        dimension_summary=build_dimension_summary(dimension_results),
        dimension_summary_text=build_dimension_summary_text(dimension_results),
        dimension_results=dimension_results,
        strengths=final_meta.get("strengths", []),
        weaknesses=final_meta.get("weaknesses", []),
        revision_suggestions=final_meta.get("revision_suggestions", []),
        risk_flags=risk_flags,
        final_comment=final_meta.get("final_comment", ""),
    )


def collect_evidence_text(
    dimension_results: Dict[str, DimensionScoreSummary],
    *,
    fallback_message: str,
) -> str:
    evidence_items: List[str] = []
    seen: set[str] = set()

    for result in dimension_results.values():
        for single in result.scores:
            for item in single.evidence:
                text = str(item).strip()
                if text and text not in seen:
                    seen.add(text)
                    evidence_items.append(text)

    if evidence_items:
        return "；".join(evidence_items[:12])

    fallback_blocks: List[str] = []
    for result in dimension_results.values():
        snippet = (result.student_dimension_text or "").strip()
        if snippet:
            fallback_blocks.append(f"【{result.dimension_name}】{snippet[:300]}")
    if fallback_blocks:
        return "\n".join(fallback_blocks[:4])

    return fallback_message


def build_feedback_text(final_report: FinalGradeReport) -> str:
    parts: List[str] = []

    if final_report.final_comment:
        parts.append(final_report.final_comment)
    if final_report.strengths:
        parts.append("主要优势：" + "；".join(final_report.strengths))
    if final_report.weaknesses:
        parts.append("主要不足：" + "；".join(final_report.weaknesses))
    if final_report.revision_suggestions:
        parts.append("改进建议：" + "；".join(final_report.revision_suggestions))
    if final_report.risk_flags:
        parts.append("风险提示：" + "；".join(final_report.risk_flags))
    if not parts and final_report.dimension_summary_text:
        parts.append(final_report.dimension_summary_text)

    return "\n".join(parts).strip() or "未生成有效反馈。"


def compute_overall_score(dimension_results: Dict[str, DimensionScoreSummary]) -> float:
    if not dimension_results:
        return 0.0
    means = [result.mean for result in dimension_results.values()]
    return round(float(statistics.mean(means)), 2)


def make_unified_output(
    final_report: FinalGradeReport,
    *,
    evidence_fallback: str,
) -> UnifiedEvaluationResult:
    return {
        "score": compute_overall_score(final_report.dimension_results),
        "feedback": build_feedback_text(final_report),
        "evidence": collect_evidence_text(
            final_report.dimension_results,
            fallback_message=evidence_fallback,
        ),
    }


__all__ = [
    "UnifiedEvaluationResult",
    "aggregate_final_report",
    "build_feedback_text",
    "collect_evidence_text",
    "compute_overall_score",
    "generate_final_comment_with_llm",
    "make_unified_output",
]
