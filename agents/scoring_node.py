"""Graph 节点：汇总已执行评估 Agent 的分数，计算 total_score。"""

from __future__ import annotations

from state import (
    LearningState,
    ROUTE_LABELS,
    ScoreDetail,
    ScoreDetailItem,
    ScoringNodeUpdate,
    get_active_routes,
)
from rubrics.rubric_prompt_utils import average_sub_scores, compute_rubric_average, percent_to_rubric_level

ROUTE_RESULT_KEY: dict[str, str] = {
    "theory": "theory_result",
    "practice": "practice_result",
    "data": "data_result",
    "literature": "literature_result",
}

# 路由 → {量规二级指标 id: agent 结果字段名}
ROUTE_SUB_SCORE_FIELDS: dict[str, dict[str, str]] = {
    "theory": {
        "concept_accuracy": "concept_accuracy_score",
        "logic_integrity": "logic_integrity_score",
        "theory_transfer": "theory_transfer_score",
    },
    "practice": {
        "design_completeness": "design_score",
        "operational_standard": "operation_score",
        "problem_solving": "problem_solving_score",
    },
    "data": {
        "data_collection": "data_collection_score",
        "data_analysis": "data_analysis_score",
        "visualization": "visualization_score",
    },
    "literature": {
        "lit_understanding": "lit_understanding_score",
        "viewpoint_consistency": "viewpoint_consistency_score",
        "critical_thinking": "critical_thinking_score",
        "innovation_extension": "innovation_extension_score",
    },
}


def _read_score(result: object) -> float | None:
    """读取路由综合分（优先 1-5 量规分）。"""
    if not isinstance(result, dict):
        return None
    raw = result.get("score")
    if raw is None:
        return None
    try:
        value = float(raw)
        if value > 5.0:
            return percent_to_rubric_level(value)
        return float(max(0.0, min(5.0, round(value, 2))))
    except (TypeError, ValueError):
        return None


def _route_rubric_score(route: str, result: object) -> float | None:
    """从二级指标或 score 字段得到 1-5 路由分。"""
    sub = collect_sub_scores(route, result)
    if sub:
        return average_sub_scores(list(sub.values()))
    return _read_score(result)


def _read_sub_score(raw: object) -> int | None:
    if raw is None:
        return None
    try:
        return int(max(1, min(5, round(float(raw)))))
    except (TypeError, ValueError):
        return None


def collect_sub_scores(route: str, result: object) -> dict[str, int]:
    """从单路由 agent 结果中提取二级指标 1-5 分。"""
    if not isinstance(result, dict):
        return {}

    field_map = ROUTE_SUB_SCORE_FIELDS.get(route, {})
    sub_scores: dict[str, int] = {}
    for indicator_id, field_name in field_map.items():
        value = _read_sub_score(result.get(field_name))
        if value is not None:
            sub_scores[indicator_id] = value
    return sub_scores


def collect_route_scores(state: LearningState) -> ScoreDetail:
    """仅统计当前路由实际执行的 Agent 分数及二级指标分。"""
    routes = get_active_routes(state)
    items: list[ScoreDetailItem] = []
    scores: dict[str, float] = {}
    sub_scores: dict[str, dict[str, int]] = {}

    for route in routes:
        result_key = ROUTE_RESULT_KEY.get(route)
        if not result_key:
            continue
        result = state.get(result_key)
        score = _route_rubric_score(route, result)
        if score is None:
            continue
        label = ROUTE_LABELS.get(route, route)
        items.append({"route": route, "label": label, "score": score})
        scores[route] = score

        route_sub_scores = collect_sub_scores(route, result)
        if route_sub_scores:
            sub_scores[route] = route_sub_scores

    count = len(items)
    average = round(sum(scores.values()) / count, 2) if count else 0.0
    rubric_average = compute_rubric_average(sub_scores, percent_scores=scores)

    return {
        "routes": routes,
        "items": items,
        "scores": scores,
        "sub_scores": sub_scores,
        "count": count,
        "average": average,
        "rubric_average": rubric_average,
    }


def compute_total_score(score_detail: ScoreDetail) -> float:
    """total_score 为量规 1-5 分均值（与 scoring_rubric_v4 一致）。"""
    rubric = score_detail.get("rubric_average")
    if rubric is not None and rubric > 0:
        return float(rubric)
    return float(score_detail.get("average") or 0.0)


def scoring_node(state: LearningState) -> ScoringNodeUpdate:
    score_detail = collect_route_scores(state)
    total_score = compute_total_score(score_detail)
    return {
        "total_score": total_score,
        "score_detail": score_detail,
    }


__all__ = [
    "ROUTE_RESULT_KEY",
    "ROUTE_SUB_SCORE_FIELDS",
    "collect_route_scores",
    "collect_sub_scores",
    "compute_total_score",
    "scoring_node",
]
