"""长期记忆检索：从历史评估记录中提取上下文。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.evaluation_store import list_evaluations, load_student_memory

EMPTY_MEMORY_HINT = "（该学生暂无历史评估记录。）"

MEMORY_CONTEXT_HEADER = (
    "【学生历史评估参考 — 含过往分数与反馈】\n"
    "请对照以下记录识别进步趋势、重复出现的薄弱点与已给过的建议；"
    "避免向学生复述「根据历史记录」等表述，将历史洞见自然融入本次评价。"
)


def _format_routes(routes: object) -> str:
    if isinstance(routes, list) and routes:
        return ", ".join(str(r) for r in routes)
    if isinstance(routes, str) and routes:
        return routes
    return "未知"


def _truncate(text: str, limit: int = 200) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _score_from_result(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    score = result.get("score")
    if score is None or score == "":
        return ""
    return f"score={score}"


def _summarize_result(result: Any, *, keys: tuple[str, ...]) -> str:
    if not isinstance(result, dict):
        return ""
    parts: list[str] = []
    score_part = _score_from_result(result)
    if score_part:
        parts.append(score_part)
    for key in keys:
        value = result.get(key)
        if value is None or value == "":
            continue
        text = _truncate(str(value).strip(), 180)
        parts.append(f"{key}: {text}")
    return "; ".join(parts)


def format_evaluation_summary(record: dict[str, Any], *, index: int | None = None) -> str:
    """将单条评估记录格式化为可读摘要（含分数）。"""
    header_parts: list[str] = []
    if index is not None:
        header_parts.append(f"记录{index}")
    ts = record.get("timestamp", "")
    routes = _format_routes(record.get("routes") or record.get("route"))
    if ts:
        header_parts.append(ts)
    header_parts.append(f"路由[{routes}]")

    total = record.get("total_score")
    if total is not None and total != "":
        header_parts.append(f"综合分[{total}]")

    header = " | ".join(header_parts)
    lines = [header]

    preview = (record.get("student_input_preview") or "").strip()
    if preview:
        lines.append(f"作答摘要: {_truncate(preview, 300)}")

    theory = _summarize_result(
        record.get("theory_result"),
        keys=("concept_understanding", "logic", "critical_thinking", "feedback"),
    )
    if theory:
        lines.append(f"理论: {theory}")

    practice = _summarize_result(
        record.get("practice_result"),
        keys=("experiment_design", "operation_standard", "problem_solving", "feedback"),
    )
    if practice:
        lines.append(f"实践: {practice}")

    data = _summarize_result(
        record.get("data_result"),
        keys=("data_analysis", "visualization", "modeling", "feedback"),
    )
    if data:
        lines.append(f"数据: {data}")

    literature = _summarize_result(
        record.get("literature_result"),
        keys=(
            "student_viewpoint",
            "alignment_analysis",
            "critical_thinking_score",
            "innovation_score",
            "suggestions",
        ),
    )
    if literature:
        lines.append(f"文献: {literature}")

    score_detail = record.get("score_detail")
    if isinstance(score_detail, dict):
        scores = score_detail.get("scores")
        if isinstance(scores, dict) and scores:
            detail = ", ".join(f"{k}={v}" for k, v in scores.items())
            lines.append(f"分项得分: {detail}")

    feedback = (record.get("final_feedback") or "").strip()
    if feedback:
        lines.append(f"综合反馈: {_truncate(feedback, 400)}")

    return "\n".join(lines)


def retrieve_recent_evaluations(
    student_id: str,
    *,
    k: int = 3,
    memory_dir: Path | None = None,
    exclude_evaluation_id: str | None = None,
) -> list[dict[str, Any]]:
    """检索最近 k 条评估记录（不含当前条时可传 exclude_evaluation_id）。"""
    if k <= 0:
        return []
    records = list_evaluations(student_id, memory_dir=memory_dir, limit=k + 5)
    if exclude_evaluation_id:
        records = [
            r for r in records if r.get("evaluation_id") != exclude_evaluation_id
        ]
    return records[-k:]


def retrieve_memory_context(
    student_id: str,
    *,
    k: int = 3,
    memory_dir: Path | None = None,
    query: str | None = None,
) -> str:
    """
    检索并格式化为可注入 Prompt 的长期记忆文本。

    query 非空时做简单关键词过滤（在作答摘要与综合反馈中匹配）。
    """
    try:
        records = list_evaluations(student_id, memory_dir=memory_dir)
    except FileNotFoundError:
        return EMPTY_MEMORY_HINT

    if not records:
        return EMPTY_MEMORY_HINT

    if query and query.strip():
        q = query.strip().lower()
        filtered: list[dict[str, Any]] = []
        for rec in records:
            blob = " ".join(
                [
                    str(rec.get("student_input_preview") or ""),
                    str(rec.get("final_feedback") or ""),
                ]
            ).lower()
            if q in blob:
                filtered.append(rec)
        records = filtered[-k:] if filtered else records[-k:]
    else:
        records = records[-k:]

    if not records:
        return EMPTY_MEMORY_HINT

    blocks = [
        format_evaluation_summary(rec, index=i + 1)
        for i, rec in enumerate(records)
    ]
    body = "\n\n---\n\n".join(blocks)
    return f"{MEMORY_CONTEXT_HEADER}\n\n{body}"


def retrieve_student_profile(
    student_id: str,
    *,
    memory_dir: Path | None = None,
) -> dict[str, Any]:
    """返回学生记忆元信息（不含完整 evaluations 时可截断）。"""
    memory = load_student_memory(
        student_id, memory_dir=memory_dir, create_if_missing=True
    )
    evaluations = memory.get("evaluations") or []
    recent_scores = [
        r.get("total_score")
        for r in evaluations[-5:]
        if r.get("total_score") is not None
    ]
    return {
        "student_id": memory.get("student_id"),
        "created_at": memory.get("created_at"),
        "updated_at": memory.get("updated_at"),
        "total_evaluations": len(evaluations),
        "recent_routes": [
            r.get("routes") for r in evaluations[-5:] if r.get("routes")
        ],
        "recent_total_scores": recent_scores,
    }


__all__ = [
    "EMPTY_MEMORY_HINT",
    "MEMORY_CONTEXT_HEADER",
    "format_evaluation_summary",
    "retrieve_memory_context",
    "retrieve_recent_evaluations",
    "retrieve_student_profile",
]
