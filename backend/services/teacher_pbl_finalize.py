"""教师介入后：汇总一级指标并完成小组 PBL 评价。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models import GroupPblEvaluation

_PART_PRIMARY = {
    "creativity": "创造性思维",
    "critical": "批判性思维",
    "problemsolving": "问题解决能力",
}

_PRIMARY_AGENT = {
    "创造性思维": "creativity",
    "批判性思维": "critical",
    "问题解决能力": "problemsolving",
    "问题解决": "problemsolving",
}


def _collect_text_lists(primary_summary: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
    strengths: list[str] = []
    weaknesses: list[str] = []
    suggestions: list[str] = []
    for item in primary_summary:
        name = str(item.get("primary_indicator_name") or "")
        adv = str(item.get("advantages") or "").strip()
        dis = str(item.get("disadvantages") or "").strip()
        sug = str(item.get("improvement_suggestions") or "").strip()
        if adv:
            strengths.append(f"{name}：{adv}" if name else adv)
        if dis:
            weaknesses.append(f"{name}：{dis}" if name else dis)
        if sug:
            suggestions.append(f"{name}：{sug}" if name else sug)
    return strengths, weaknesses, suggestions


def _build_primary_summary_from_dimensions(
    dimension_summary: list[dict[str, Any]], *, use_llm: bool
) -> list[dict[str, Any]]:
    from agents.group_project.primary_indicator_agent import (
        build_primary_indicator_summary,
        calculate_primary_indicator_summary,
    )

    if use_llm:
        return build_primary_indicator_summary(dimension_summary=dimension_summary)
    return calculate_primary_indicator_summary(dimension_summary)


def _merge_dimension_summary_into_result(
    result: dict[str, Any],
    dimension_summary: list[dict[str, Any]],
    primary_summary: list[dict[str, Any]],
    *,
    teacher_modified: bool,
    pre_release: bool = False,
    audit_status: str | None = None,
) -> dict[str, Any]:
    agents: dict[str, dict[str, Any]] = {}
    primary_means: list[float] = []
    for item in primary_summary:
        name = str(item.get("primary_indicator_name") or "")
        mean = item.get("mean")
        agent_key = _PRIMARY_AGENT.get(name)
        if agent_key and mean is not None:
            agents[agent_key] = {
                "score": float(mean),
                "feedback": str(item.get("summary_comment") or ""),
                "evidence": "",
            }
        if mean is not None:
            primary_means.append(float(mean))

    dim_means = [
        float(d["mean"])
        for d in dimension_summary
        if d.get("mean") is not None
    ]
    dimension_mean_score = sum(dim_means) / len(dim_means) if dim_means else None
    final_score = (
        sum(primary_means) / len(primary_means) if primary_means else dimension_mean_score
    )

    strengths, weaknesses, suggestions = _collect_text_lists(primary_summary)
    final_comment = "；".join(
        str(item.get("summary_comment") or "").strip()
        for item in primary_summary
        if str(item.get("summary_comment") or "").strip()
    )

    if audit_status is None:
        if pre_release and teacher_modified:
            audit_status = "教师截止前已改分（待组长查看）"
        elif teacher_modified:
            audit_status = "教师改分后已确认"
        else:
            audit_status = "教师已直接通过"

    merged = dict(result)
    merged.update(
        {
            "dimension_summary": dimension_summary,
            "primary_indicator_summary": primary_summary,
            "creativity": agents.get(
                "creativity", {"score": 0.0, "feedback": "", "evidence": ""}
            ),
            "critical": agents.get(
                "critical", {"score": 0.0, "feedback": "", "evidence": ""}
            ),
            "problemsolving": agents.get(
                "problemsolving", {"score": 0.0, "feedback": "", "evidence": ""}
            ),
            "dimension_mean_score": dimension_mean_score,
            "final_score": final_score,
            "final_feedback": final_comment,
            "final_comment": final_comment,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "revision_suggestions": suggestions,
            "audit_passed": True,
            "audit_status": audit_status,
            "output_mode": "teacher_confirmed",
            "teacher_modified": teacher_modified or bool(result.get("teacher_modified")),
            "needs_teacher_intervention": False,
        }
    )
    if pre_release:
        merged["teacher_pre_release_adjustment"] = True
    return merged


def _primary_summary_needs_llm_refresh(primary_summary: list[dict[str, Any]]) -> bool:
    if not primary_summary:
        return True
    for item in primary_summary:
        if str(item.get("disadvantages") or "").strip():
            return False
        if str(item.get("improvement_suggestions") or "").strip():
            return False
    return True


def sync_leader_display_payload(result: dict[str, Any]) -> dict[str, Any]:
    """
    若教师已改分，按当前 12 维均分重算三维度展示字段（读取时兜底，确保组长看到改分后汇总）。
    若缺少 LLM 汇总的缺点/建议，尝试重新调用一级指标 LLM 汇总（修复历史数据）。
    """
    dimension_summary = list(result.get("dimension_summary") or [])
    if not dimension_summary:
        return result

    needs_sync = bool(
        result.get("teacher_modified") or result.get("teacher_pre_release_adjustment")
    )
    primary_summary = list(result.get("primary_indicator_summary") or [])

    if not needs_sync and not _primary_summary_needs_llm_refresh(primary_summary):
        return result

    primary_summary = _build_primary_summary_from_dimensions(
        dimension_summary, use_llm=True
    )
    return _merge_dimension_summary_into_result(
        result,
        dimension_summary,
        primary_summary,
        teacher_modified=bool(result.get("teacher_modified")),
        pre_release=bool(result.get("teacher_pre_release_adjustment")),
    )


def apply_teacher_pre_release_score_update(
    db: Session,
    record: GroupPblEvaluation,
    *,
    note: str | None = None,
) -> GroupPblEvaluation:
    """截止后组长可见前教师改分：按 12 维均分重算三维度，待组长开放查看时呈现。"""
    result = dict(record.result_json or {})
    dimension_summary = list(result.get("dimension_summary") or [])
    if not dimension_summary:
        raise ValueError("缺少 12 维评分数据，无法完成汇总")

    primary_summary = _build_primary_summary_from_dimensions(
        dimension_summary, use_llm=True
    )
    merged = _merge_dimension_summary_into_result(
        result,
        dimension_summary,
        primary_summary,
        teacher_modified=True,
        pre_release=True,
    )

    record.result_json = merged
    record.audit_passed = True
    record.needs_teacher_intervention = False
    record.teacher_reviewed = True
    final_score = merged.get("final_score")
    dimension_mean_score = merged.get("dimension_mean_score")
    record.final_score = float(final_score) if final_score is not None else None
    record.dimension_mean_score = (
        float(dimension_mean_score) if dimension_mean_score is not None else None
    )
    if note:
        record.teacher_intervention_note = note
    elif not record.teacher_intervention_note:
        record.teacher_intervention_note = "教师截止前已修改分数"

    db.commit()
    db.refresh(record)
    return record


def finalize_teacher_intervention(
    db: Session,
    record: GroupPblEvaluation,
    *,
    teacher_modified: bool = False,
    note: str | None = None,
    use_llm: bool = True,
    pre_release: bool = False,
) -> GroupPblEvaluation:
    """根据当前 12 维结果生成三维度汇总，并标记评价已完成。"""
    result = dict(record.result_json or {})
    dimension_summary = list(result.get("dimension_summary") or [])
    if not dimension_summary:
        raise ValueError("缺少 12 维评分数据，无法完成汇总")

    primary_summary = _build_primary_summary_from_dimensions(
        dimension_summary, use_llm=use_llm
    )
    merged = _merge_dimension_summary_into_result(
        result,
        dimension_summary,
        primary_summary,
        teacher_modified=teacher_modified,
        pre_release=pre_release,
    )

    record.result_json = merged
    record.audit_passed = True
    record.needs_teacher_intervention = False
    record.teacher_reviewed = True
    final_score = merged.get("final_score")
    dimension_mean_score = merged.get("dimension_mean_score")
    record.final_score = float(final_score) if final_score is not None else None
    record.dimension_mean_score = (
        float(dimension_mean_score) if dimension_mean_score is not None else None
    )
    if note:
        record.teacher_intervention_note = note
    elif not record.teacher_intervention_note:
        record.teacher_intervention_note = (
            "教师改分后已确认" if teacher_modified else "教师已直接通过"
        )

    db.commit()
    db.refresh(record)
    return record


def _dim_agent_key(dim: dict[str, Any]) -> str:
    agent = str(dim.get("agent_key") or "").strip()
    if agent:
        return agent
    primary = str(dim.get("primary_indicator") or "").strip()
    return _PRIMARY_AGENT.get(primary, "")


def _collect_failed_dimension_targets(internal: dict[str, Any]) -> set[tuple[str, str]]:
    """
    收集审核未通过的 (agent_key, dimension_key)。
    dimension_key 为 ``*`` 表示该 agent 下全部子维度（无 failed_dimension_keys 时的兜底）。
    """
    targets: set[tuple[str, str]] = set()
    failed_parts = {str(p) for p in (internal.get("failed_parts") or [])}

    for part in ("creativity", "critical", "problemsolving"):
        part_audit = internal.get(part)
        if not isinstance(part_audit, dict):
            if part in failed_parts:
                targets.add((part, "*"))
            continue

        if not part_audit.get("max_review_rounds_reached"):
            continue

        keys = [str(k) for k in (part_audit.get("failed_dimension_keys") or []) if k]
        if keys:
            for key in keys:
                targets.add((part, key))
        elif part_audit.get("audit_passed") is False or part in failed_parts:
            targets.add((part, "*"))

    return targets


def has_failed_dimensions_at_max_rounds(result: dict[str, Any]) -> bool:
    """任一二阶维度在达到最大审核轮次后仍未通过。"""
    if extract_failed_dimension_views(result):
        return True
    internal = dict(result.get("internal_audit") or {})
    for part in ("creativity", "critical", "problemsolving"):
        pa = internal.get(part)
        if not isinstance(pa, dict) or not pa.get("max_review_rounds_reached"):
            continue
        if pa.get("audit_passed") is False:
            return True
        if pa.get("failed_dimension_keys"):
            return True
    return False


def resolve_max_review_rounds_reached(result: dict[str, Any]) -> bool:
    if result.get("max_review_rounds_reached"):
        return True
    internal = dict(result.get("internal_audit") or {})
    return any(
        bool((internal.get(part) or {}).get("max_review_rounds_reached"))
        for part in ("creativity", "critical", "problemsolving")
    )


def is_teacher_audit_passed(
    *,
    result: dict[str, Any],
    teacher_reviewed: bool,
    max_review_rounds_reached: bool = False,
) -> bool:
    """
    教师端审核标签：
    - 教师已确认 → 审核通过
    - 未达最大轮次 → 审核通过
    - 达最大轮次且仍有未通过维度 → 审核未通过
    - 其余 → 审核通过
    """
    if teacher_reviewed:
        return True
    max_reached = max_review_rounds_reached or resolve_max_review_rounds_reached(result)
    if not max_reached:
        return True
    return not has_failed_dimensions_at_max_rounds(result)


def _dimension_matches_failed_target(
    dim: dict[str, Any], targets: set[tuple[str, str]]
) -> bool:
    if not targets:
        return False
    agent = _dim_agent_key(dim)
    dim_key = str(dim.get("dimension_key") or "").strip()
    if not agent:
        return False
    for target_agent, target_key in targets:
        if agent != target_agent:
            continue
        if target_key == "*" or (dim_key and target_key == dim_key):
            return True
    return False


def extract_failed_dimension_views(result: dict[str, Any]) -> list[dict[str, Any]]:
    """提取审核未通过的 12 维子项明细（均分、一级指标、评语），供教师介入页展示。"""
    internal = dict(result.get("internal_audit") or {})
    targets = _collect_failed_dimension_targets(internal)

    views: list[dict[str, Any]] = []
    for dim in result.get("dimension_summary") or []:
        if not isinstance(dim, dict):
            continue
        if not _dimension_matches_failed_target(dim, targets):
            continue
        views.append(
            {
                "dimension_key": str(dim.get("dimension_key") or ""),
                "dimension_name": str(dim.get("dimension_name") or ""),
                "primary_indicator": str(dim.get("primary_indicator") or ""),
                "agent_key": _dim_agent_key(dim),
                "mean": dim.get("mean"),
                "summary_comment": dim.get("summary_comment"),
                "audit_failed": True,
            }
        )
    return views
