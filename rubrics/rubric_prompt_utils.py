"""从 scoring_rubric_v4.json 生成四路由 Agent 的量规 prompt 片段。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RUBRIC_PATH = Path(__file__).resolve().parent / "scoring_rubric_v4.json"


@lru_cache(maxsize=1)
def _load_rubric_data() -> dict:
    with RUBRIC_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _get_dimension(dimension_id: str) -> dict:
    for dim in _load_rubric_data().get("dimensions", []):
        if dim.get("id") == dimension_id:
            return dim
    raise KeyError(f"Unknown rubric dimension: {dimension_id}")


def clamp_sub_score(value: int | float | None) -> int:
    """将二级指标分数限制在 1-5。"""
    try:
        return int(max(1, min(5, round(float(value)))))
    except (TypeError, ValueError):
        return 1


def get_sub_indicator_ids(dimension_id: str) -> list[str]:
    """返回维度下二级指标 id 列表（按 order 排序）。"""
    dim = _get_dimension(dimension_id)
    sub_indicators = sorted(
        dim.get("sub_indicators", []),
        key=lambda item: item.get("order", 0),
    )
    return [str(sub.get("id") or "") for sub in sub_indicators if sub.get("id")]


def percent_to_rubric_level(score: float) -> float:
    """将百分制分数映射为量规 1-5 档（与 scoring_rubric_v4.json percent_range 对齐）。"""
    value = float(score)
    if value >= 90:
        return 5.0
    if value >= 75:
        return 4.0
    if value >= 60:
        return 3.0
    if value >= 40:
        return 2.0
    return 1.0


def average_sub_scores(values: list[int | float]) -> float:
    """二级指标 1-5 分的算术平均，作为维度综合分。"""
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return 0.0
    return round(sum(nums) / len(nums), 2)


def compute_rubric_average(
    sub_scores: dict[str, dict[str, int]],
    *,
    percent_scores: dict[str, float] | None = None,
) -> float:
    """汇总二级指标 1-5 分；若无 sub_scores 则从百分制路由分回退映射。"""
    values: list[int] = []
    for route_scores in (sub_scores or {}).values():
        values.extend(int(v) for v in route_scores.values() if v is not None)
    if values:
        return round(sum(values) / len(values), 2)

    percent_values = list((percent_scores or {}).values())
    if not percent_values:
        return 0.0
    mapped = [percent_to_rubric_level(score) for score in percent_values]
    return round(sum(mapped) / len(mapped), 2)


def format_dimension_rubric_block(dimension_id: str) -> str:
    """将指定维度的二级指标 1-5 级描述格式化为 system prompt 注入块。"""
    dim = _get_dimension(dimension_id)
    dim_name = str(dim.get("name") or dimension_id)
    lines = [f"【{dim_name}评分参照（1-5分）】"]

    sub_indicators = sorted(
        dim.get("sub_indicators", []),
        key=lambda item: item.get("order", 0),
    )
    for sub in sub_indicators:
        name = str(sub.get("name") or sub.get("id") or "")
        lines.append(f"{name}：")
        levels = sub.get("levels") or {}
        for score in (5, 4, 3, 2, 1):
            desc = str(levels.get(str(score), "")).strip()
            if desc:
                lines.append(f"{score}分={desc}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
