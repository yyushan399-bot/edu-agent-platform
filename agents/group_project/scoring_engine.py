"""PBL 单维度 / 全维度评分引擎（共享）。"""

from __future__ import annotations

import statistics
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from agents.group_project.pbl_config import DEFAULT_RAG_TOP_K, DEFAULT_SCORING_TIMES
from agents.group_project.scoring_models import DeepSeekClient, DimensionScoreSummary, SingleScore
from agents.group_project.scoring_report import UnifiedEvaluationResult, aggregate_final_report, make_unified_output
from agents.group_project.scoring_utils import (
    build_merged_report_context,
    judge_consistency,
    retrieve_reference_context_for_dimension,
    summarize_dimension_scores,
)

BuildPromptFn = Callable[
    [str, str, str, str, str, str, int, Optional[Dict[str, Any]]],
    Tuple[str, str],
]
RetrieveStudentFn = Callable[[str, str, str], Tuple[str, Dict[str, Any]]]


def score_one_dimension(
    llm: DeepSeekClient,
    dimension_key: str,
    dimension_name: str,
    rubric: str,
    merged_report_context: str,
    *,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    audit_feedback: Optional[Dict[str, Any]] = None,
    retrieve_student_fn: RetrieveStudentFn,
    build_prompt_fn: BuildPromptFn,
) -> DimensionScoreSummary:
    student_dimension_text, student_dimension_debug = retrieve_student_fn(
        merged_report_context,
        dimension_name,
        rubric,
    )
    rag_context, _rag_debug = retrieve_reference_context_for_dimension(
        student_dimension_text or merged_report_context,
        dimension_key,
        dimension_name,
        rubric,
        rag_top_k,
    )

    scores: List[SingleScore] = []
    for i in range(1, scoring_times + 1):
        sys_p, usr_p = build_prompt_fn(
            dimension_key,
            dimension_name,
            rubric,
            merged_report_context,
            student_dimension_text,
            rag_context,
            i,
            audit_feedback,
        )
        raw = llm.chat_json(sys_p, usr_p, temperature=0.0)
        try:
            parsed = SingleScore(**raw)
        except ValidationError:
            fixed = {
                "score": max(1, min(5, int(raw.get("score", 1)))),
                "reason": str(raw.get("reason", "")),
                "evidence": raw.get("evidence", []),
                "reference_comparison": str(raw.get("reference_comparison", "")),
                "weakness": str(raw.get("weakness", "")),
                "suggestion": str(raw.get("suggestion", "")),
            }
            if not isinstance(fixed["evidence"], list):
                fixed["evidence"] = [str(fixed["evidence"])]
            parsed = SingleScore(**fixed)
        scores.append(parsed)

    numeric_scores = [s.score for s in scores]
    mean_score = float(statistics.mean(numeric_scores))
    std_score = float(statistics.pstdev(numeric_scores)) if len(numeric_scores) > 1 else 0.0
    min_score = float(min(numeric_scores))
    max_score = float(max(numeric_scores))
    cv: Optional[float] = std_score / mean_score if mean_score > 1e-8 else None

    consistency_level = judge_consistency(cv, std_score, min_score, max_score)
    summary_comment = summarize_dimension_scores(
        dimension_name, scores, mean_score, std_score, cv, consistency_level
    )

    return DimensionScoreSummary(
        dimension_key=dimension_key,
        dimension_name=dimension_name,
        student_dimension_text=student_dimension_text,
        student_dimension_debug=student_dimension_debug,
        scores=scores,
        mean=round(mean_score, 3),
        std=round(std_score, 3),
        cv=round(cv, 3) if cv is not None else None,
        min_score=round(min_score, 3),
        max_score=round(max_score, 3),
        consistency_level=consistency_level,
        summary_comment=summary_comment,
    )


def score_all_dimensions(
    llm: DeepSeekClient,
    merged_report_context: str,
    *,
    scoring_dimensions: Dict[str, str],
    rubrics: Dict[str, str],
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    retrieve_student_fn: RetrieveStudentFn,
    build_prompt_fn: BuildPromptFn,
) -> Tuple[Dict[str, DimensionScoreSummary], List[str]]:
    errors: List[str] = []
    results: Dict[str, DimensionScoreSummary] = {}

    if not merged_report_context:
        errors.append("merged_report_context 为空，无法评分。")
        return results, errors

    for dimension_key, dimension_name in scoring_dimensions.items():
        try:
            results[dimension_key] = score_one_dimension(
                llm=llm,
                dimension_key=dimension_key,
                dimension_name=dimension_name,
                rubric=rubrics[dimension_key],
                merged_report_context=merged_report_context,
                scoring_times=scoring_times,
                rag_top_k=rag_top_k,
                retrieve_student_fn=retrieve_student_fn,
                build_prompt_fn=build_prompt_fn,
            )
        except Exception as exc:
            errors.append(f"{dimension_name} 评分失败：{exc}")

    return results, errors


def run_grading_from_text(
    report_text: str,
    *,
    scoring_dimensions: Dict[str, str],
    rubrics: Dict[str, str],
    model: str,
    evidence_fallback: str,
    retrieve_student_fn: RetrieveStudentFn,
    build_prompt_fn: BuildPromptFn,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    llm = DeepSeekClient(api_key=api_key, model=model)
    merged_report_context = build_merged_report_context(report_text)
    dimension_results, errors = score_all_dimensions(
        llm=llm,
        merged_report_context=merged_report_context,
        scoring_dimensions=scoring_dimensions,
        rubrics=rubrics,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
        retrieve_student_fn=retrieve_student_fn,
        build_prompt_fn=build_prompt_fn,
    )

    final_report_dict: Dict[str, Any] = {}
    unified: UnifiedEvaluationResult = {"score": 0.0, "feedback": "", "evidence": ""}

    if dimension_results:
        final_report = aggregate_final_report(llm=llm, dimension_results=dimension_results)
        final_report_dict = final_report.model_dump()
        unified = make_unified_output(final_report, evidence_fallback=evidence_fallback)

    return {
        "model": model,
        "scoring_times_per_dimension": scoring_times,
        "rag_top_k_per_dimension": rag_top_k,
        "merged_report_context": merged_report_context,
        "final_report": final_report_dict,
        "dimension_results": {
            key: value.model_dump() for key, value in dimension_results.items()
        },
        "unified_output": unified,
        "errors": errors,
    }


def evaluate_report(
    report_text: str,
    *,
    scoring_dimensions: Dict[str, str],
    rubrics: Dict[str, str],
    model: str,
    empty_message: str,
    failure_message: str,
    evidence_fallback: str,
    retrieve_student_fn: RetrieveStudentFn,
    build_prompt_fn: BuildPromptFn,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    api_key: Optional[str] = None,
) -> UnifiedEvaluationResult:
    if not (report_text or "").strip():
        return {"score": 0.0, "feedback": empty_message, "evidence": ""}

    llm = DeepSeekClient(api_key=api_key, model=model)
    merged_report_context = build_merged_report_context(report_text)
    dimension_results, errors = score_all_dimensions(
        llm=llm,
        merged_report_context=merged_report_context,
        scoring_dimensions=scoring_dimensions,
        rubrics=rubrics,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
        retrieve_student_fn=retrieve_student_fn,
        build_prompt_fn=build_prompt_fn,
    )

    if not dimension_results:
        return {
            "score": 0.0,
            "feedback": failure_message + ("；" + "；".join(errors) if errors else ""),
            "evidence": "",
        }

    final_report = aggregate_final_report(llm=llm, dimension_results=dimension_results)
    unified = make_unified_output(final_report, evidence_fallback=evidence_fallback)

    if errors:
        unified["feedback"] = unified["feedback"] + "\n[警告] " + "；".join(errors)

    return unified


__all__ = [
    "evaluate_report",
    "run_grading_from_text",
    "score_all_dimensions",
    "score_one_dimension",
]
