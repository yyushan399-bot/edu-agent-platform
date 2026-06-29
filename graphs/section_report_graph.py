"""章节反馈评价编排（单章 / 批量）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from utils.section_constants import SECTION_NAMES
from utils.section_summary import build_section_summary

logger = logging.getLogger(__name__)

MIN_SECTION_TEXT_CHARS = 50


def _summaries_to_criterion_details(
    summaries: dict[str, Any],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for name, summary in summaries.items():
        details.append(
            {
                "criterion_name": name,
                "weight": summary.weight,
                "mean": summary.mean,
                "std": summary.std,
                "cv": summary.cv,
                "consistency_level": summary.consistency_level,
                "summary_reason": summary.summary_reason,
            }
        )
    details.sort(key=lambda item: item["weight"], reverse=True)
    return details


def _final_report_to_result(
    report: Any,
    *,
    graphrag_backend: str,
    criterion_details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "section_name": report.section_name,
        "total_score": report.total_score,
        "strengths": list(report.strengths),
        "weaknesses": list(report.weaknesses),
        "suggestions": list(report.suggestions),
        "audit_rounds_used": report.audit_rounds_used,
        "criterion_details": criterion_details or [],
        "graphrag_backend": graphrag_backend,
    }


async def evaluate_one_section(
    section_name: str,
    student_text: str,
    *,
    enable_review: bool = True,
    scoring_times: int | None = None,
    max_rounds: int | None = None,
    cv_threshold: float | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """评价单个章节，返回 SectionResult 兼容 dict。"""
    from agents.group_project.pbl_config import DEFAULT_SCORING_TIMES
    from agents.group_project.scoring_models import DeepSeekClient
    from agents.section_report.section_config import (
        DEFAULT_CV_THRESHOLD,
        DEFAULT_MAX_REVIEW_ROUNDS,
    )
    from agents.section_report.section_review_agent import run_review_loop
    from agents.section_report.section_scoring_agent import score_criteria
    from services.section_graphrag_service import create_section_retriever

    scoring_times = scoring_times or DEFAULT_SCORING_TIMES
    max_rounds = max_rounds or DEFAULT_MAX_REVIEW_ROUNDS
    cv_threshold = cv_threshold if cv_threshold is not None else DEFAULT_CV_THRESHOLD

    if section_name not in SECTION_NAMES:
        raise ValueError(f"未知章节：{section_name}")
    text = (student_text or "").strip()
    if len(text) < MIN_SECTION_TEXT_CHARS:
        raise ValueError(
            f"章节「{section_name}」文本过短（{len(text)} 字），至少需要 {MIN_SECTION_TEXT_CHARS} 字。"
        )

    retriever = create_section_retriever()
    llm = DeepSeekClient(model=model) if model else DeepSeekClient()
    backend = retriever.backend_name

    try:
        if enable_review:
            report = await asyncio.to_thread(
                run_review_loop,
                section_name=section_name,
                student_text=text,
                scoring_llm=llm,
                audit_llm=llm,
                retriever=retriever,
                max_rounds=max_rounds,
                scoring_times=scoring_times,
                cv_threshold=cv_threshold,
            )
            return _final_report_to_result(report, graphrag_backend=backend)

        summaries = await asyncio.to_thread(
            score_criteria,
            llm=llm,
            retriever=retriever,
            section_name=section_name,
            student_text=text,
            scoring_times=scoring_times,
        )
        from agents.section_report.section_review_agent import generate_final_report

        report = await asyncio.to_thread(
            generate_final_report,
            section_name,
            summaries,
            0,
            llm,
        )
        return _final_report_to_result(
            report,
            graphrag_backend=backend,
            criterion_details=_summaries_to_criterion_details(summaries),
        )
    finally:
        retriever.close()


async def run_section_batch(
    section_texts: dict[str, str],
    *,
    section_target: str | None = None,
    enable_review: bool = True,
    scoring_times: int | None = None,
    max_rounds: int | None = None,
    cv_threshold: float | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """
    批量评价章节。

    Returns:
        (section_results, skipped_sections, errors)
    """
    if section_target:
        targets = [section_target]
    else:
        targets = list(SECTION_NAMES)

    results: list[dict[str, Any]] = []
    skipped: list[str] = []
    errors: list[str] = []

    for section_name in targets:
        text = (section_texts.get(section_name) or "").strip()
        if not text:
            skipped.append(section_name)
            continue
        if len(text) < MIN_SECTION_TEXT_CHARS:
            skipped.append(section_name)
            errors.append(
                f"{section_name}: 文本过短（{len(text)} 字），已跳过"
            )
            continue
        try:
            result = await evaluate_one_section(
                section_name,
                text,
                enable_review=enable_review,
                scoring_times=scoring_times,
                max_rounds=max_rounds,
                cv_threshold=cv_threshold,
            )
            results.append(result)
        except Exception as exc:
            logger.exception("section evaluation failed: %s", section_name)
            errors.append(f"{section_name}: {exc}")

    return results, skipped, errors


__all__ = [
    "MIN_SECTION_TEXT_CHARS",
    "evaluate_one_section",
    "run_section_batch",
]
