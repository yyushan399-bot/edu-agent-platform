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

from agents.group_project.creativity_agent import evaluate as evaluate_creativity
from agents.group_project.critical_agent import evaluate as evaluate_critical
from agents.group_project.problemsolving_agent import evaluate as evaluate_problemsolving

logger = logging.getLogger(__name__)


class AgentEvaluationResult(TypedDict):
    score: float
    feedback: str
    evidence: str


class GroupEvaluationResult(TypedDict):
    creativity: AgentEvaluationResult
    critical: AgentEvaluationResult
    problemsolving: AgentEvaluationResult
    final_score: float
    final_feedback: str


_AGENT_SEQUENCE: list[tuple[str, str, Callable[..., dict[str, Any]]]] = [
    ("creativity", "创造性思维", evaluate_creativity),
    ("critical", "批判性思维", evaluate_critical),
    ("problemsolving", "问题解决能力", evaluate_problemsolving),
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


def _build_final_feedback(results: dict[str, AgentEvaluationResult]) -> str:
    sections: list[str] = []
    for result_key, label, _ in _AGENT_SEQUENCE:
        feedback = results[result_key]["feedback"]
        if feedback:
            sections.append(f"【{label}】\n{feedback}")
    return "\n\n".join(sections).strip() or "未生成有效综合评语。"


def _compute_final_score(results: dict[str, AgentEvaluationResult]) -> float:
    scores = [item["score"] for item in results.values()]
    if not scores:
        return 0.0
    return round(float(statistics.mean(scores)), 2)


async def _run_agent(
    agent_key: str,
    label: str,
    evaluate_fn: Callable[..., dict[str, Any]],
    report_text: str,
    *,
    scoring_times: int,
    rag_top_k: int,
) -> AgentEvaluationResult:
    logger.info("group evaluation agent start (%s)", agent_key)
    try:
        raw = await asyncio.to_thread(
            evaluate_fn,
            report_text,
            scoring_times=scoring_times,
            rag_top_k=rag_top_k,
        )
        result = _normalize_agent_result(raw)
    except Exception:
        logger.exception("group evaluation agent failed (%s)", agent_key)
        raise

    logger.info(
        "group evaluation agent done (%s, label=%s, score=%.2f)",
        agent_key,
        label,
        result["score"],
    )
    return result


async def run_group_evaluation(
    report_text: str,
    *,
    scoring_times: int = 10,
    rag_top_k: int = 8,
) -> GroupEvaluationResult:
    """
    依次调用三个小组项目 Agent，汇总分数与反馈。

    Args:
        report_text: 学生项目报告纯文本。
        scoring_times: 每个 agent 每维度独立评分次数，默认 10。
        rag_top_k: 每个 agent 每维度 RAG 检索数量，默认 8。

    Returns:
        {
            "creativity": {"score", "feedback", "evidence"},
            "critical": {"score", "feedback", "evidence"},
            "problemsolving": {"score", "feedback", "evidence"},
            "final_score": 三 agent 分数平均值（1.0–5.0）,
            "final_feedback": 三段 feedback 拼接的综合评语,
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

    for result_key, label, evaluate_fn in _AGENT_SEQUENCE:
        collected[result_key] = await _run_agent(
            result_key,
            label,
            evaluate_fn,
            report_text,
            scoring_times=scoring_times,
            rag_top_k=rag_top_k,
        )

    final_score = _compute_final_score(collected)
    final_feedback = _build_final_feedback(collected)

    logger.info(
        "group evaluation done (final_score=%.2f, creativity=%.2f, critical=%.2f, problemsolving=%.2f)",
        final_score,
        collected["creativity"]["score"],
        collected["critical"]["score"],
        collected["problemsolving"]["score"],
    )

    return {
        "creativity": collected["creativity"],
        "critical": collected["critical"],
        "problemsolving": collected["problemsolving"],
        "final_score": final_score,
        "final_feedback": final_feedback,
    }


__all__ = [
    "AgentEvaluationResult",
    "GroupEvaluationResult",
    "run_group_evaluation",
]
