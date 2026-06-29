"""
汇总 Agent：并行运行创造性 / 批判性 / 问题解决三套「评分 → 审核 → 重评」流程。

从 preview-agent 迁移，输入改为 report_text（纯文本），评分改为 run_grading_from_text。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List

from agents.group_project.creativity_agent import (
    DEFAULT_MODEL,
    DEFAULT_RAG_TOP_K,
    DEFAULT_SCORING_TIMES,
    RUBRICS as CREATIVITY_RUBRICS,
    SCORING_DIMENSIONS as CREATIVITY_SCORING_DIMENSIONS,
    DeepSeekClient,
    score_one_dimension as creativity_score_one_dimension,
    run_grading_from_text as run_creativity_grading,
)
from agents.group_project.creativity_review import build_independent_audit_agent as build_creativity_audit_agent
from agents.group_project.critical_agent import (
    RUBRICS as CRITICAL_RUBRICS,
    SCORING_DIMENSIONS as CRITICAL_SCORING_DIMENSIONS,
    score_one_dimension as critical_score_one_dimension,
    run_grading_from_text as run_critical_grading,
)
from agents.group_project.critical_review import build_independent_audit_agent as build_critical_audit_agent
from agents.group_project.problemsolving_agent import (
    RUBRICS as PROBLEMSOLVING_RUBRICS,
    SCORING_DIMENSIONS as PROBLEMSOLVING_SCORING_DIMENSIONS,
    score_one_dimension as problemsolving_score_one_dimension,
    run_grading_from_text as run_problemsolving_grading,
)
from agents.group_project.problemsolving_review import (
    build_independent_audit_agent as build_problemsolving_audit_agent,
)

logger = logging.getLogger(__name__)

DEFAULT_REVIEW_ROUNDS = 5

_PART_CONFIG: dict[str, dict[str, Any]] = {
    "creativity": {
        "primary_indicator": "创造性思维",
        "run_grading": run_creativity_grading,
        "build_audit_agent": build_creativity_audit_agent,
        "score_one_dimension": creativity_score_one_dimension,
        "rubrics": CREATIVITY_RUBRICS,
        "scoring_dimensions": CREATIVITY_SCORING_DIMENSIONS,
    },
    "critical": {
        "primary_indicator": "批判性思维",
        "run_grading": run_critical_grading,
        "build_audit_agent": build_critical_audit_agent,
        "score_one_dimension": critical_score_one_dimension,
        "rubrics": CRITICAL_RUBRICS,
        "scoring_dimensions": CRITICAL_SCORING_DIMENSIONS,
    },
    "problemsolving": {
        "primary_indicator": "问题解决能力",
        "run_grading": run_problemsolving_grading,
        "build_audit_agent": build_problemsolving_audit_agent,
        "score_one_dimension": problemsolving_score_one_dimension,
        "rubrics": PROBLEMSOLVING_RUBRICS,
        "scoring_dimensions": PROBLEMSOLVING_SCORING_DIMENSIONS,
    },
}


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    return value


def _extract_required_dimension_summary(
    final_payload: Dict[str, Any],
    *,
    agent_key: str,
    primary_indicator: str,
) -> List[Dict[str, Any]]:
    items = final_payload.get("dimension_summary", [])
    if not isinstance(items, list):
        return []

    summary: List[Dict[str, Any]] = []
    for item in items:
        item = _to_plain(item)
        if not isinstance(item, dict):
            continue
        summary.append(
            {
                "dimension_key": item.get("dimension_key", ""),
                "dimension_name": item.get("dimension_name", ""),
                "primary_indicator": primary_indicator,
                "agent_key": agent_key,
                "mean": item.get("mean"),
                "cv": item.get("cv"),
                "consistency_level": item.get("consistency_level", ""),
                "summary_comment": item.get("summary_comment", ""),
            }
        )
    return summary


def _compact_failure_payload(part_result: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in part_result:
        return {
            "audit_passed": False,
            "audit_status": "运行失败",
            "error": part_result.get("error"),
        }

    final_payload = part_result.get("final_payload", {}) or {}
    return {
        "audit_passed": final_payload.get("audit_passed", False),
        "audit_status": final_payload.get("audit_status", "审核未通过"),
        "output_mode": final_payload.get("output_mode"),
        "failed_dimension_keys": final_payload.get("failed_dimension_keys", []),
        "review_rounds_used": final_payload.get("review_rounds_used"),
        "max_review_rounds_reached": final_payload.get("max_review_rounds_reached"),
        "overall_explanation": final_payload.get("overall_explanation", ""),
        "grading_errors": part_result.get("grading_errors", []),
    }


def _compute_overall_audit(
    part_results: Dict[str, Dict[str, Any]],
) -> tuple[bool, bool, str]:
    """
    12 维审核汇总：
    任一级能力域在达到最大审核轮次后仍有未通过维度 → 审核未通过；否则审核通过。
    """
    max_review_rounds_reached = False
    has_failed_at_max = False

    for name in ("creativity", "critical", "problemsolving"):
        final_payload = (part_results.get(name, {}) or {}).get("final_payload", {}) or {}
        if not final_payload.get("max_review_rounds_reached"):
            continue
        max_review_rounds_reached = True
        failed_keys = list(final_payload.get("failed_dimension_keys") or [])
        if final_payload.get("audit_passed") is not True or failed_keys:
            has_failed_at_max = True

    audit_passed = not has_failed_at_max
    audit_status = "审核通过" if audit_passed else "审核未通过"
    return audit_passed, max_review_rounds_reached, audit_status


def _part_to_agent_result(final_payload: Dict[str, Any]) -> Dict[str, Any]:
    dimension_summary = final_payload.get("dimension_summary") or []
    means: List[float] = []
    for item in dimension_summary:
        if not isinstance(item, dict):
            continue
        try:
            means.append(float(item.get("mean")))
        except (TypeError, ValueError):
            continue

    score = round(sum(means) / len(means), 2) if means else 0.0
    feedback = str(final_payload.get("overall_explanation") or "").strip()

    evidence_items: List[str] = []
    dimension_results = final_payload.get("dimension_results") or {}
    if isinstance(dimension_results, dict):
        for raw in dimension_results.values():
            result = _to_plain(raw)
            if not isinstance(result, dict):
                continue
            for single in result.get("scores", []):
                if not isinstance(single, dict):
                    continue
                for ev in single.get("evidence", []):
                    text = str(ev).strip()
                    if text and text not in evidence_items:
                        evidence_items.append(text)

    return {
        "score": score,
        "feedback": feedback or "未生成该能力域反馈。",
        "evidence": "；".join(evidence_items[:12]),
    }


def _run_reviewed_part(
    *,
    part_name: str,
    report_text: str,
    model: str,
    scoring_times: int,
    rag_top_k: int,
    review_rounds: int,
    verbose: bool,
    config: dict[str, Any],
) -> Dict[str, Any]:
    prefix = f"[summary_agent:{part_name}]"
    logger.info("%s 开始评分", prefix)

    llm = DeepSeekClient(model=model)
    run_grading_fn: Callable[..., Dict[str, Any]] = config["run_grading"]
    score_one_dimension_fn = config["score_one_dimension"]
    rubrics = config["rubrics"]
    scoring_dimensions = config["scoring_dimensions"]

    grading_result = run_grading_fn(
        report_text,
        model=model,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
    )

    merged_report_context = grading_result.get("merged_report_context", "")
    dimension_results = grading_result.get("dimension_results", {})

    if not dimension_results:
        return {
            "part_name": part_name,
            "primary_indicator": config["primary_indicator"],
            "final_payload": {
                "audit_passed": False,
                "audit_status": "评分结果为空",
                "output_mode": "grading_failed",
                "failed_dimension_keys": list(scoring_dimensions.keys()),
                "overall_explanation": f"{part_name} 未生成 dimension_results，无法进入审核。",
            },
            "grading_errors": grading_result.get("errors", []),
        }

    def rescore_fn(state: Dict[str, Any]) -> Dict[str, Any]:
        failed_keys = list(state.get("failed_dimension_keys", []))
        audit_feedback_all = state.get("audit_feedback", {}) or {}
        new_results: Dict[str, Any] = {}

        for dimension_key in failed_keys:
            if dimension_key not in scoring_dimensions:
                continue
            dimension_name = scoring_dimensions[dimension_key]
            summary = score_one_dimension_fn(
                llm=llm,
                dimension_key=dimension_key,
                dimension_name=dimension_name,
                rubric=rubrics[dimension_key],
                merged_report_context=state["merged_report_context"],
                scoring_times=scoring_times,
                rag_top_k=rag_top_k,
                audit_feedback=audit_feedback_all.get(dimension_key, {}),
            )
            new_results[dimension_key] = summary.model_dump()

        return {"dimension_results": new_results}

    logger.info("%s 开始审核", prefix)
    review_agent = config["build_audit_agent"](
        audit_llm=llm,
        scoring_fn=rescore_fn,
        max_review_rounds=review_rounds,
    )

    review_state = review_agent.invoke(
        {
            "merged_report_context": merged_report_context,
            "dimension_results": dimension_results,
            "rubrics": rubrics,
            "review_round": 0,
            "max_review_rounds": review_rounds,
            "verbose": verbose,
        }
    )

    final_payload = review_state.get("final_payload", {})
    logger.info(
        "%s 审核完成：%s",
        prefix,
        "通过" if final_payload.get("audit_passed") is True else "未通过",
    )

    return {
        "part_name": part_name,
        "primary_indicator": config["primary_indicator"],
        "final_payload": final_payload,
        "grading_errors": grading_result.get("errors", []),
    }


def run_summary_agent(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    review_rounds: int = DEFAULT_REVIEW_ROUNDS,
    verbose: bool = False,
) -> Dict[str, Any]:
    """并行运行 creativity / critical / problemsolving 审核流程，合并 12 维 dimension_summary。"""
    if not (report_text or "").strip():
        raise ValueError("报告文本为空，无法运行 summary agent。")

    part_results: Dict[str, Dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_name = {
            executor.submit(
                _run_reviewed_part,
                part_name=name,
                report_text=report_text,
                model=model,
                scoring_times=scoring_times,
                rag_top_k=rag_top_k,
                review_rounds=review_rounds,
                verbose=verbose,
                config=config,
            ): name
            for name, config in _PART_CONFIG.items()
        }

        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                part_results[name] = future.result()
            except Exception as exc:
                logger.exception("summary agent part failed (%s)", name)
                part_results[name] = {
                    "part_name": name,
                    "primary_indicator": _PART_CONFIG[name]["primary_indicator"],
                    "error": str(exc),
                    "final_payload": {
                        "audit_passed": False,
                        "audit_status": "运行失败",
                        "output_mode": "runtime_error",
                        "failed_dimension_keys": [],
                        "overall_explanation": f"{name} 运行失败：{exc}",
                    },
                }

    creativity_payload = part_results.get("creativity", {}).get("final_payload", {})
    critical_payload = part_results.get("critical", {}).get("final_payload", {})
    problemsolving_payload = part_results.get("problemsolving", {}).get("final_payload", {})

    creativity_passed = creativity_payload.get("audit_passed") is True
    critical_passed = critical_payload.get("audit_passed") is True
    problemsolving_passed = problemsolving_payload.get("audit_passed") is True

    dimension_summary: List[Dict[str, Any]] = []
    for part_name, payload in (
        ("creativity", creativity_payload),
        ("critical", critical_payload),
        ("problemsolving", problemsolving_payload),
    ):
        dimension_summary.extend(
            _extract_required_dimension_summary(
                payload,
                agent_key=part_name,
                primary_indicator=_PART_CONFIG[part_name]["primary_indicator"],
            )
        )

    failed_parts: List[str] = []
    if not creativity_passed:
        failed_parts.append("creativity")
    if not critical_passed:
        failed_parts.append("critical")
    if not problemsolving_passed:
        failed_parts.append("problemsolving")

    audit_passed, max_review_rounds_reached, audit_status = _compute_overall_audit(part_results)

    part_agents = {
        part_name: _part_to_agent_result(part_results[part_name].get("final_payload", {}))
        for part_name in _PART_CONFIG
        if part_name in part_results
    }

    grading_errors: List[str] = []
    for part in part_results.values():
        grading_errors.extend(str(item) for item in (part.get("grading_errors") or []) if item)

    if dimension_summary:
        return {
            "audit_passed": audit_passed,
            "audit_status": audit_status,
            "max_review_rounds_reached": max_review_rounds_reached,
            "output_mode": "verified" if audit_passed else "audit_failed_at_max_rounds",
            "dimension_summary": dimension_summary,
            "creativity": part_agents.get("creativity", {"score": 0.0, "feedback": "", "evidence": ""}),
            "critical": part_agents.get("critical", {"score": 0.0, "feedback": "", "evidence": ""}),
            "problemsolving": part_agents.get(
                "problemsolving",
                {"score": 0.0, "feedback": "", "evidence": ""},
            ),
            "internal_audit": {
                "all_parts_passed": creativity_passed and critical_passed and problemsolving_passed,
                "failed_parts": failed_parts,
                "creativity": _compact_failure_payload(part_results.get("creativity", {})),
                "critical": _compact_failure_payload(part_results.get("critical", {})),
                "problemsolving": _compact_failure_payload(part_results.get("problemsolving", {})),
            },
            "part_results": part_results,
            "errors": grading_errors,
        }

    return {
        "audit_passed": False,
        "audit_status": "评分失败",
        "output_mode": "grading_failed",
        "dimension_summary": [],
        "creativity": part_agents.get("creativity", {"score": 0.0, "feedback": "", "evidence": ""}),
        "critical": part_agents.get("critical", {"score": 0.0, "feedback": "", "evidence": ""}),
        "problemsolving": part_agents.get(
            "problemsolving",
            {"score": 0.0, "feedback": "", "evidence": ""},
        ),
        "failed_parts": failed_parts,
        "internal_audit": {
            "all_parts_passed": False,
            "failed_parts": failed_parts,
            "creativity": _compact_failure_payload(part_results.get("creativity", {})),
            "critical": _compact_failure_payload(part_results.get("critical", {})),
            "problemsolving": _compact_failure_payload(part_results.get("problemsolving", {})),
        },
        "part_results": part_results,
        "errors": grading_errors,
    }


__all__ = [
    "DEFAULT_REVIEW_ROUNDS",
    "run_summary_agent",
]
