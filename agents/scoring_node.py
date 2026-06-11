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

ROUTE_RESULT_KEY: dict[str, str] = {
    "theory": "theory_result",
    "practice": "practice_result",
    "data": "data_result",
    "literature": "literature_result",
}


def _read_score(result: object) -> float | None:
    if not isinstance(result, dict):
        return None
    raw = result.get("score")
    if raw is None:
        return None
    try:
        return float(max(0.0, min(100.0, round(float(raw), 2))))
    except (TypeError, ValueError):
        return None


def collect_route_scores(state: LearningState) -> ScoreDetail:
    """仅统计当前路由实际执行的 Agent 分数。"""
    routes = get_active_routes(state)
    items: list[ScoreDetailItem] = []
    scores: dict[str, float] = {}

    for route in routes:
        result_key = ROUTE_RESULT_KEY.get(route)
        if not result_key:
            continue
        score = _read_score(state.get(result_key))
        if score is None:
            continue
        label = ROUTE_LABELS.get(route, route)
        items.append({"route": route, "label": label, "score": score})
        scores[route] = score

    count = len(items)
    average = round(sum(scores.values()) / count, 2) if count else 0.0

    return {
        "routes": routes,
        "items": items,
        "scores": scores,
        "count": count,
        "average": average,
    }


def compute_total_score(score_detail: ScoreDetail) -> float:
    """total_score 为已执行 Agent 分数的算术平均（单路由时即该 Agent 分数）。"""
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
    "collect_route_scores",
    "compute_total_score",
    "scoring_node",
]
