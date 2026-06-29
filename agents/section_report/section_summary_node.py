"""LangGraph 节点：汇总多章评价结果。"""

from __future__ import annotations

import logging

from utils.section_summary import build_section_summary
from state import LearningState, SectionSummaryNodeUpdate

logger = logging.getLogger(__name__)


def section_summary_node(state: LearningState) -> SectionSummaryNodeUpdate:
    section_results = list(state.get("section_results") or [])
    summary = build_section_summary(
        section_results,
        skipped_sections=list(state.get("section_skipped") or []),
        parse_warnings=list(state.get("section_parse_warnings") or []),
    )

    overall_comment = str(summary.get("overall_comment") or "").strip()
    overall_score = float(summary.get("overall_score") or 0.0)

    logger.info(
        "section summary done (overall_score=%.2f, evaluated=%d)",
        overall_score,
        len(section_results),
    )

    return {
        "section_summary": summary,
        "total_score": overall_score,
        "final_feedback": overall_comment,
        "final_comment": overall_comment,
    }


__all__ = ["section_summary_node"]
