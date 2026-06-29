"""LangGraph 节点：小组项目 PBL 评价（快速或完整审核模式）。"""

from __future__ import annotations

import asyncio
import logging

from graphs.group_project_graph import run_full_pbl_evaluation, run_group_evaluation
from memory.memory_retriever import EMPTY_MEMORY_HINT
from state import GroupEvaluationNodeUpdate, LearningState

logger = logging.getLogger(__name__)


def _resolve_report_text(state: LearningState) -> str:
    explicit = (state.get("report_text") or "").strip()
    if explicit:
        return explicit
    return (state.get("student_input") or "").strip()


def _inject_memory_context(state: LearningState, report_text: str) -> str:
    memory_context = (state.get("memory_context") or "").strip()
    if not memory_context or memory_context == EMPTY_MEMORY_HINT:
        return report_text
    if memory_context.startswith("（"):
        return report_text
    return (
        f"{memory_context}\n\n"
        f"【本次项目报告】\n"
        f"{report_text}"
    )


def _map_evaluation_to_state(
    result: dict,
    *,
    report_text: str,
) -> GroupEvaluationNodeUpdate:
    creativity = result.get("creativity") or {}
    critical = result.get("critical") or {}
    problemsolving = result.get("problemsolving") or {}

    update: GroupEvaluationNodeUpdate = {
        "evaluation_mode": "pbl_report",
        "report_text": report_text,
        "group_project_results": {
            "creativity": creativity,
            "critical": critical,
            "problemsolving": problemsolving,
        },
        "dimension_summary": list(result.get("dimension_summary") or []),
        "primary_indicator_summary": list(result.get("primary_indicator_summary") or []),
        "dimension_mean_score": float(result.get("dimension_mean_score") or 0.0),
        "total_score": float(result.get("final_score") or 0.0),
        "final_feedback": str(result.get("final_feedback") or "").strip(),
        "final_comment": str(
            result.get("final_comment") or result.get("final_feedback") or ""
        ).strip(),
        "pbl_errors": [str(item) for item in (result.get("errors") or []) if item],
    }

    if "audit_passed" in result:
        update["audit_passed"] = bool(result.get("audit_passed"))
    if result.get("audit_status"):
        update["audit_status"] = str(result.get("audit_status"))
    if result.get("output_mode"):
        update["output_mode"] = str(result.get("output_mode"))
    if isinstance(result.get("internal_audit"), dict):
        update["internal_audit"] = dict(result.get("internal_audit") or {})
    if result.get("strengths"):
        update["pbl_strengths"] = list(result.get("strengths") or [])
    if result.get("weaknesses"):
        update["pbl_weaknesses"] = list(result.get("weaknesses") or [])
    if result.get("revision_suggestions"):
        update["pbl_revision_suggestions"] = list(result.get("revision_suggestions") or [])

    return update


async def _run_pbl_evaluation_async(state: LearningState) -> GroupEvaluationNodeUpdate:
    report_text = _resolve_report_text(state)
    if not report_text:
        raise ValueError("report_text / student_input 不能为空")

    report_text = _inject_memory_context(state, report_text)
    scoring_times = max(1, int(state.get("pbl_scoring_times") or 10))
    rag_top_k = max(1, int(state.get("pbl_rag_top_k") or 8))
    review_rounds = max(0, int(state.get("pbl_review_rounds") or 5))
    enable_review = bool(state.get("enable_pbl_review"))

    logger.info(
        "group evaluation node start (len=%d, review=%s, scoring_times=%d)",
        len(report_text),
        enable_review,
        scoring_times,
    )

    if enable_review:
        result = await run_full_pbl_evaluation(
            report_text,
            scoring_times=scoring_times,
            rag_top_k=rag_top_k,
            review_rounds=review_rounds,
        )
    else:
        result = await run_group_evaluation(
            report_text,
            scoring_times=scoring_times,
            rag_top_k=rag_top_k,
        )

    mapped = _map_evaluation_to_state(result, report_text=report_text)
    logger.info(
        "group evaluation node done (final_score=%.2f, dimensions=%d)",
        mapped.get("total_score", 0.0),
        len(mapped.get("dimension_summary") or []),
    )
    return mapped


def group_evaluation_node(state: LearningState) -> GroupEvaluationNodeUpdate:
    """同步 LangGraph 节点：内部 asyncio.run 调用 PBL 评价。"""
    return asyncio.run(_run_pbl_evaluation_async(state))


__all__ = ["group_evaluation_node"]
