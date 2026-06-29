"""章节评价结果汇总（无 LLM / agents 依赖）。"""

from __future__ import annotations

from typing import Any


def build_section_summary(
    section_results: list[dict[str, Any]],
    *,
    skipped_sections: list[str] | None = None,
    parse_warnings: list[str] | None = None,
) -> dict[str, Any]:
    skipped_sections = list(skipped_sections or [])
    scores = {
        item["section_name"]: float(item.get("total_score") or 0.0)
        for item in section_results
        if item.get("section_name")
    }

    overall_score = round(sum(scores.values()) / len(scores), 2) if scores else 0.0

    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    strongest = [name for name, score in ranked[:2] if score >= 3.5]
    weakest = [name for name, score in reversed(ranked[-2:]) if score <= 3.0]

    comments: list[str] = []
    for item in section_results:
        name = item.get("section_name", "")
        score = item.get("total_score")
        if name and score is not None:
            comments.append(f"「{name}」{score}/5.0")

    overall_comment = "；".join(comments) if comments else "暂无有效章节评分。"

    return {
        "overall_score": overall_score,
        "section_scores": scores,
        "evaluated_sections": [item.get("section_name") for item in section_results],
        "skipped_sections": skipped_sections,
        "strongest_sections": strongest,
        "weakest_sections": weakest,
        "overall_comment": overall_comment,
        "parse_warnings": list(parse_warnings or []),
    }


__all__ = ["build_section_summary"]
