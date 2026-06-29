"""LangGraph 节点：整报告切分为 7 章节。"""

from __future__ import annotations

import logging

from state import LearningState, SectionSplitNodeUpdate
from utils.section_parser import split_report_text

logger = logging.getLogger(__name__)


def _resolve_report_text(state: LearningState) -> str:
    explicit = (state.get("report_text") or "").strip()
    if explicit:
        return explicit
    return (state.get("student_input") or "").strip()


def section_split_node(state: LearningState) -> SectionSplitNodeUpdate:
    """若 state 尚无 section_texts，则从 report_text 自动切分。"""
    existing = dict(state.get("section_texts") or {})
    if existing:
        return {}

    report_text = _resolve_report_text(state)
    if not report_text:
        return {
            "section_texts": {},
            "section_parse_warnings": ["report_text 为空，无法切分章节"],
            "unmatched_text": "",
        }

    parsed = split_report_text(report_text)
    section_texts = {
        chunk.section_name: chunk.text for chunk in parsed.sections
    }

    logger.info(
        "section split done (found=%d, missing=%s)",
        len(section_texts),
        parsed.missing_sections,
    )

    return {
        "section_texts": section_texts,
        "section_parse_warnings": list(parsed.warnings),
        "unmatched_text": parsed.unmatched_text,
    }


__all__ = ["section_split_node"]
