"""
小组项目评价图：串联创造性思维、批判性思维、问题解决能力三个 Agent。

对外入口：
    run_group_evaluation(report_text) -> 综合评估结果字典
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from typing import Any, Callable, TypedDict

from agents.group_project.creativity_agent import DEFAULT_MODEL, run_grading_from_text as run_grading_creativity
from agents.group_project.critical_agent import run_grading_from_text as run_grading_critical
from agents.group_project.pbl_config import DEFAULT_RAG_TOP_K, DEFAULT_REVIEW_ROUNDS, DEFAULT_SCORING_TIMES
from agents.group_project.primary_indicator_agent import build_primary_indicator_summary
from agents.group_project.problemsolving_agent import run_grading_from_text as run_grading_problemsolving
from agents.group_project.summary_agent import run_summary_agent

logger = logging.getLogger(__name__)


class AgentEvaluationResult(TypedDict):
    score: float
    feedback: str
    evidence: str


class DimensionSummaryItem(TypedDict):
    dimension_key: str
    dimension_name: str
    primary_indicator: str
    agent_key: str
    mean: float
    cv: float | None
    consistency_level: str
    summary_comment: str


class GroupEvaluationResult(TypedDict):
    creativity: AgentEvaluationResult
    critical: AgentEvaluationResult
    problemsolving: AgentEvaluationResult
    dimension_summary: list[DimensionSummaryItem]
    final_score: float
    dimension_mean_score: float
    final_feedback: str
    errors: list[str]


class PrimaryIndicatorSummaryItem(TypedDict, total=False):
    primary_indicator_name: str
    mean: float | None
    advantages: str
    disadvantages: str
    improvement_suggestions: str
    summary_comment: str
    secondary_dimensions: list[dict[str, Any]]


class FullPblEvaluationResult(GroupEvaluationResult, total=False):
    primary_indicator_summary: list[PrimaryIndicatorSummaryItem]
    audit_passed: bool
    audit_status: str
    output_mode: str
    internal_audit: dict[str, Any]
    strengths: list[str]
    weaknesses: list[str]
    revision_suggestions: list[str]
    final_comment: str


_AGENT_SEQUENCE: list[tuple[str, str, Callable[..., dict[str, Any]]]] = [
    ("creativity", "创造性思维", run_grading_creativity),
    ("critical", "批判性思维", run_grading_critical),
    ("problemsolving", "问题解决能力", run_grading_problemsolving),
]


def _normalize_agent_result(raw: dict[str, Any]) -> AgentEvaluationResult:
    score = raw.get("score", 0.0)
    try:
        score = round(float(score), 2)
    except (TypeError, ValueError):
        score = 0.0

    return {
        "score": score,
        "feedback": str(raw.get("feedback") or "").strip(),
        "evidence": str(raw.get("evidence") or "").strip(),
    }


def _extract_dimension_summary(
    grading_result: dict[str, Any],
    *,
    agent_key: str,
    primary_indicator: str,
) -> list[DimensionSummaryItem]:
    final_report = grading_result.get("final_report") or {}
    items = final_report.get("dimension_summary") or []
    if not isinstance(items, list):
        return []

    merged: list[DimensionSummaryItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mean_raw = item.get("mean")
        try:
            mean = round(float(mean_raw), 3)
        except (TypeError, ValueError):
            mean = 0.0

        cv_raw = item.get("cv")
        cv: float | None
        if cv_raw is None:
            cv = None
        else:
            try:
                cv = round(float(cv_raw), 3)
            except (TypeError, ValueError):
                cv = None

        merged.append(
            {
                "dimension_key": str(item.get("dimension_key") or ""),
                "dimension_name": str(item.get("dimension_name") or ""),
                "primary_indicator": primary_indicator,
                "agent_key": agent_key,
                "mean": mean,
                "cv": cv,
                "consistency_level": str(item.get("consistency_level") or ""),
                "summary_comment": str(item.get("summary_comment") or ""),
            }
        )
    return merged


def _build_final_feedback(results: dict[str, AgentEvaluationResult]) -> str:
    sections: list[str] = []
    for result_key, label, _ in _AGENT_SEQUENCE:
        feedback = results[result_key]["feedback"]
        if feedback:
            sections.append(f"【{label}】\n{feedback}")
    return "\n\n".join(sections).strip() or "未生成有效综合评语。"


def _build_final_feedback_from_primary(
    primary_indicator_summary: list[dict[str, Any]],
) -> str:
    sections: list[str] = []
    for item in primary_indicator_summary:
        name = str(item.get("primary_indicator_name") or "").strip()
        comment = str(item.get("summary_comment") or "").strip()
        if name and comment:
            sections.append(f"【{name}】\n{comment}")
    return "\n\n".join(sections).strip() or "未生成有效综合评语。"


def _collect_primary_texts(
    primary_indicator_summary: list[dict[str, Any]],
    field: str,
) -> list[str]:
    values: list[str] = []
    for item in primary_indicator_summary:
        text = str(item.get(field) or "").strip()
        if not text:
            continue
        name = str(item.get("primary_indicator_name") or "").strip()
        if name and field in ("advantages", "disadvantages", "improvement_suggestions"):
            if not text.startswith(f"{name}：") and not text.startswith(f"{name}:"):
                text = f"{name}：{text}"
        values.append(text)
    return values


def _normalize_dimension_summary_items(
    items: list[dict[str, Any]],
) -> list[DimensionSummaryItem]:
    normalized: list[DimensionSummaryItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mean_raw = item.get("mean")
        try:
            mean = round(float(mean_raw), 3)
        except (TypeError, ValueError):
            mean = 0.0

        cv_raw = item.get("cv")
        cv: float | None
        if cv_raw is None:
            cv = None
        else:
            try:
                cv = round(float(cv_raw), 3)
            except (TypeError, ValueError):
                cv = None

        normalized.append(
            {
                "dimension_key": str(item.get("dimension_key") or ""),
                "dimension_name": str(item.get("dimension_name") or ""),
                "primary_indicator": str(item.get("primary_indicator") or ""),
                "agent_key": str(item.get("agent_key") or ""),
                "mean": mean,
                "cv": cv,
                "consistency_level": str(item.get("consistency_level") or ""),
                "summary_comment": str(item.get("summary_comment") or ""),
            }
        )
    return normalized


def _compute_final_score(results: dict[str, AgentEvaluationResult]) -> float:
    scores = [item["score"] for item in results.values()]
    if not scores:
        return 0.0
    return round(float(statistics.mean(scores)), 2)


def _compute_dimension_mean_score(dimension_summary: list[DimensionSummaryItem]) -> float:
    if not dimension_summary:
        return 0.0
    means = [item["mean"] for item in dimension_summary]
    return round(float(statistics.mean(means)), 2)


async def _run_agent_grading(
    agent_key: str,
    primary_indicator: str,
    run_grading_fn: Callable[..., dict[str, Any]],
    report_text: str,
    *,
    scoring_times: int,
    rag_top_k: int,
) -> tuple[AgentEvaluationResult, list[DimensionSummaryItem], list[str]]:
    logger.info("group evaluation agent start (%s)", agent_key)
    try:
        grading_result = await asyncio.to_thread(
            run_grading_fn,
            report_text,
            scoring_times=scoring_times,
            rag_top_k=rag_top_k,
        )
    except Exception:
        logger.exception("group evaluation agent failed (%s)", agent_key)
        raise

    unified_raw = grading_result.get("unified_output") or {}
    if not isinstance(unified_raw, dict):
        unified_raw = {}

    result = _normalize_agent_result(unified_raw)
    dimension_summary = _extract_dimension_summary(
        grading_result,
        agent_key=agent_key,
        primary_indicator=primary_indicator,
    )
    errors = [str(item) for item in (grading_result.get("errors") or []) if item]

    logger.info(
        "group evaluation agent done (%s, label=%s, score=%.2f, dimensions=%d)",
        agent_key,
        primary_indicator,
        result["score"],
        len(dimension_summary),
    )
    return result, dimension_summary, errors


async def run_group_evaluation(
    report_text: str,
    *,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
) -> GroupEvaluationResult:
    """
    依次调用三个小组项目 Agent，汇总分数与反馈。

    Args:
        report_text: 学生项目报告纯文本。
        scoring_times: 每个 agent 每维度独立评分次数，默认见 PBL_SCORING_TIMES（生产默认 10）。
        rag_top_k: 每个 agent 每维度 RAG 检索数量，默认 8。

    Returns:
        {
            "creativity": {"score", "feedback", "evidence"},
            "critical": {"score", "feedback", "evidence"},
            "problemsolving": {"score", "feedback", "evidence"},
            "dimension_summary": 12 个二级指标明细,
            "final_score": 三个一级能力 agent 分数的算术平均（1.0–5.0）,
            "dimension_mean_score": 12 个二级维度 mean 的算术平均（1.0–5.0）,
            "final_feedback": 三段 feedback 拼接的综合评语,
            "errors": 各 agent 运行过程中的非致命警告/错误,
        }
    """
    text_len = len((report_text or "").strip())
    logger.info(
        "group evaluation start (input_len=%d, scoring_times=%d, rag_top_k=%d)",
        text_len,
        scoring_times,
        rag_top_k,
    )

    collected: dict[str, AgentEvaluationResult] = {}
    dimension_summary: list[DimensionSummaryItem] = []
    all_errors: list[str] = []

    for result_key, primary_indicator, run_grading_fn in _AGENT_SEQUENCE:
        agent_result, agent_dimensions, agent_errors = await _run_agent_grading(
            result_key,
            primary_indicator,
            run_grading_fn,
            report_text,
            scoring_times=scoring_times,
            rag_top_k=rag_top_k,
        )
        collected[result_key] = agent_result
        dimension_summary.extend(agent_dimensions)
        all_errors.extend(agent_errors)

    final_score = _compute_final_score(collected)
    dimension_mean_score = _compute_dimension_mean_score(dimension_summary)
    final_feedback = _build_final_feedback(collected)

    logger.info(
        "group evaluation done (final_score=%.2f, dimension_mean_score=%.2f, "
        "creativity=%.2f, critical=%.2f, problemsolving=%.2f, dimensions=%d)",
        final_score,
        dimension_mean_score,
        collected["creativity"]["score"],
        collected["critical"]["score"],
        collected["problemsolving"]["score"],
        len(dimension_summary),
    )

    return {
        "creativity": collected["creativity"],
        "critical": collected["critical"],
        "problemsolving": collected["problemsolving"],
        "dimension_summary": dimension_summary,
        "final_score": final_score,
        "dimension_mean_score": dimension_mean_score,
        "final_feedback": final_feedback,
        "errors": all_errors,
    }


async def run_full_pbl_evaluation(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    review_rounds: int = DEFAULT_REVIEW_ROUNDS,
    verbose: bool = False,
) -> FullPblEvaluationResult:
    """
    完整 PBL 评价：三链路并行（评分 → 审核 → 重评）+ 12 维合并 + 3 一级指标汇总。

    对齐 preview-agent 的 summary_agent + primary_indicator_agent 流程。
    """
    text_len = len((report_text or "").strip())
    logger.info(
        "full PBL evaluation start (input_len=%d, scoring_times=%d, rag_top_k=%d, review_rounds=%d)",
        text_len,
        scoring_times,
        rag_top_k,
        review_rounds,
    )

    summary_result = await asyncio.to_thread(
        run_summary_agent,
        report_text,
        model=model,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
        review_rounds=review_rounds,
        verbose=verbose,
    )

    dimension_summary = _normalize_dimension_summary_items(
        summary_result.get("dimension_summary") or []
    )
    primary_indicator_summary = await asyncio.to_thread(
        build_primary_indicator_summary,
        dimension_summary=dimension_summary,
        model=model,
    )

    creativity = _normalize_agent_result(summary_result.get("creativity") or {})
    critical = _normalize_agent_result(summary_result.get("critical") or {})
    problemsolving = _normalize_agent_result(summary_result.get("problemsolving") or {})
    collected = {
        "creativity": creativity,
        "critical": critical,
        "problemsolving": problemsolving,
    }

    primary_means: list[float] = []
    for item in primary_indicator_summary:
        try:
            if item.get("mean") is not None:
                primary_means.append(float(item["mean"]))
        except (TypeError, ValueError):
            continue

    final_score = (
        round(float(statistics.mean(primary_means)), 2)
        if primary_means
        else _compute_final_score(collected)
    )
    dimension_mean_score = _compute_dimension_mean_score(dimension_summary)
    final_feedback = _build_final_feedback_from_primary(primary_indicator_summary)
    if not final_feedback.strip():
        final_feedback = _build_final_feedback(collected)

    strengths = _collect_primary_texts(primary_indicator_summary, "advantages")
    weaknesses = _collect_primary_texts(primary_indicator_summary, "disadvantages")
    revision_suggestions = _collect_primary_texts(
        primary_indicator_summary,
        "improvement_suggestions",
    )
    final_comment = final_feedback

    logger.info(
        "full PBL evaluation done (final_score=%.2f, dimension_mean_score=%.2f, dimensions=%d, audit=%s)",
        final_score,
        dimension_mean_score,
        len(dimension_summary),
        summary_result.get("audit_status"),
    )

    return {
        "creativity": creativity,
        "critical": critical,
        "problemsolving": problemsolving,
        "dimension_summary": dimension_summary,
        "primary_indicator_summary": primary_indicator_summary,
        "final_score": final_score,
        "dimension_mean_score": dimension_mean_score,
        "final_feedback": final_feedback,
        "final_comment": final_comment,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "revision_suggestions": revision_suggestions,
        "audit_passed": bool(summary_result.get("audit_passed")),
        "audit_status": str(summary_result.get("audit_status") or ""),
        "max_review_rounds_reached": bool(summary_result.get("max_review_rounds_reached")),
        "output_mode": str(summary_result.get("output_mode") or ""),
        "internal_audit": dict(summary_result.get("internal_audit") or {}),
        "errors": [str(item) for item in (summary_result.get("errors") or []) if item],
    }


__all__ = [
    "AgentEvaluationResult",
    "DimensionSummaryItem",
    "FullPblEvaluationResult",
    "GroupEvaluationResult",
    "PrimaryIndicatorSummaryItem",
    "run_full_pbl_evaluation",
    "run_group_evaluation",
]
