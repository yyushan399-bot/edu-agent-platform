"""LangGraph 节点：按章节执行 GraphRAG 评分 / 审核。"""

from __future__ import annotations

import asyncio
import logging

from agents.group_project.pbl_config import DEFAULT_SCORING_TIMES
from agents.section_report.section_config import DEFAULT_MAX_REVIEW_ROUNDS
from graphs.section_report_graph import run_section_batch
from memory.memory_retriever import EMPTY_MEMORY_HINT
from state import LearningState, SectionEvaluationNodeUpdate

logger = logging.getLogger(__name__)


def section_evaluation_node(state: LearningState) -> SectionEvaluationNodeUpdate:
    """同步 LangGraph 节点：串行评价各章节。"""
    return asyncio.run(_section_evaluation_async(state))


async def _section_evaluation_async(state: LearningState) -> SectionEvaluationNodeUpdate:
    section_texts = dict(state.get("section_texts") or {})
    if not section_texts:
        raise ValueError("section_texts 为空，请先执行 section_split_node 或预填章节文本。")

    target = (state.get("section_target") or "").strip() or None
    enable_review = bool(state.get("enable_section_review"))
    scoring_times = max(1, int(state.get("section_scoring_times") or DEFAULT_SCORING_TIMES))
    max_rounds = max(1, int(state.get("section_review_rounds") or DEFAULT_MAX_REVIEW_ROUNDS))
    cv_threshold = float(state.get("section_cv_threshold") or 0.20)

    logger.info(
        "section evaluation start (sections=%d, target=%s, review=%s)",
        len(section_texts),
        target or "ALL",
        enable_review,
    )

    results, skipped, errors = await run_section_batch(
        section_texts,
        section_target=target,
        enable_review=enable_review,
        scoring_times=scoring_times,
        max_rounds=max_rounds,
        cv_threshold=cv_threshold,
    )

    graphrag_backend = ""
    if results:
        graphrag_backend = str(results[0].get("graphrag_backend") or "")

    memory_context = (state.get("memory_context") or "").strip()
    if memory_context and memory_context != EMPTY_MEMORY_HINT:
        logger.info("section evaluation used memory context (len=%d)", len(memory_context))

    update: SectionEvaluationNodeUpdate = {
        "evaluation_mode": "section_report",
        "section_results": results,
        "section_skipped": skipped,
        "section_errors": errors,
        "graphrag_backend": graphrag_backend,
    }
    logger.info(
        "section evaluation done (evaluated=%d, skipped=%d, errors=%d)",
        len(results),
        len(skipped),
        len(errors),
    )
    return update


__all__ = ["section_evaluation_node"]
