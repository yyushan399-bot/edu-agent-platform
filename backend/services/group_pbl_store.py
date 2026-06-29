"""小组 PBL 评价结果持久化与教师介入。"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Group, GroupPblEvaluation, User
from backend.services.teacher_pbl_finalize import (
    has_failed_dimensions_at_max_rounds,
    resolve_max_review_rounds_reached,
)

PBL_UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads" / "group_pbl"
PBL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    base = Path(name or "report").name
    cleaned = re.sub(r"[^\w.\-()（）\u4e00-\u9fff]", "_", base)
    return cleaned or "report"


def save_group_pbl_upload_file(
    *,
    file_bytes: bytes,
    filename: str,
    student_id: str,
) -> str:
    """保存小组报告原文件，返回相对 uploads 目录的路径（如 group_pbl/xxx.pdf）。"""
    safe = _safe_filename(filename)
    stored_name = f"pbl_{student_id}_{uuid.uuid4().hex[:10]}_{safe}"
    target = PBL_UPLOAD_DIR / stored_name
    target.write_bytes(file_bytes)
    return f"group_pbl/{stored_name}"


def resolve_group_pbl_file_path(stored: str | None) -> Path | None:
    if not stored:
        return None
    raw = Path(stored)
    if raw.is_absolute() and raw.exists():
        return raw
    uploads_root = Path(__file__).resolve().parents[1] / "uploads"
    normalized = stored.replace("\\", "/").lstrip("/")
    if normalized.startswith("uploads/"):
        normalized = normalized[len("uploads/") :]
    candidate = uploads_root / normalized
    return candidate if candidate.exists() else None

def resolve_group_for_student(
    db: Session, student_id: str, project_id: int | None = None
) -> Group | None:
    user = db.query(User).filter(User.student_id == student_id).first()
    if not user:
        return None
    from backend.services.pbl_visibility import resolve_user_group

    return resolve_user_group(db, user, project_id)


def save_group_pbl_evaluation(
    db: Session,
    *,
    student_id: str,
    user_id: int | None,
    filename: str,
    report_text: str,
    evaluation: dict[str, Any],
    project_id: int | None = None,
    file_path: str | None = None,
) -> GroupPblEvaluation:
    group = resolve_group_for_student(db, student_id, project_id)
    max_reached = resolve_max_review_rounds_reached(evaluation)
    audit_passed = not (max_reached and has_failed_dimensions_at_max_rounds(evaluation))
    needs_intervention = max_reached and has_failed_dimensions_at_max_rounds(evaluation)

    record = GroupPblEvaluation(
        group_id=group.id if group else None,
        user_id=user_id or 0,
        student_id=student_id,
        filename=filename,
        file_path=file_path,
        report_text=report_text[:50000] if report_text else None,
        result_json=evaluation,
        audit_passed=audit_passed,
        max_review_rounds_reached=max_reached,
        needs_teacher_intervention=needs_intervention,
        final_score=_to_float(evaluation.get("final_score")),
        dimension_mean_score=_to_float(evaluation.get("dimension_mean_score")),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_teacher_score_override(
    db: Session,
    record: GroupPblEvaluation,
    dimension_scores: list[dict[str, Any]],
) -> GroupPblEvaluation:
    result = dict(record.result_json or {})
    existing = list(result.get("dimension_summary") or [])
    score_map = {
        str(item.get("dimension_name", "")): item.get("mean")
        for item in dimension_scores
        if item.get("dimension_name")
    }
    updated_dims = []
    for dim in existing:
        name = str(dim.get("dimension_name", ""))
        new_item = dict(dim)
        if name in score_map and score_map[name] is not None:
            new_item["mean"] = float(score_map[name])
            new_item["teacher_override"] = True
        updated_dims.append(new_item)
    result["dimension_summary"] = updated_dims
    result["teacher_modified"] = True
    record.result_json = result
    record.updated_at = datetime.now(timezone.utc)
    if updated_dims:
        means = [d["mean"] for d in updated_dims if d.get("mean") is not None]
        if means:
            record.dimension_mean_score = sum(means) / len(means)
    db.commit()
    db.refresh(record)
    return record
