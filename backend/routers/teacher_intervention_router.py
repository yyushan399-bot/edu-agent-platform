"""教师智能评分体介入中心。"""



from __future__ import annotations



from typing import Any



from fastapi import APIRouter, Depends, HTTPException, status

from pydantic import BaseModel, Field

from sqlalchemy.orm import Session



from backend.database import get_db

from backend.dependencies import require_role

from backend.models import Group, GroupPblEvaluation, Project, User

from backend.services.group_pbl_store import apply_teacher_score_override

from backend.services.teacher_pbl_finalize import (

    apply_teacher_pre_release_score_update,

    extract_failed_dimension_views,

    finalize_teacher_intervention,

    is_teacher_audit_passed,

)

from backend.services.pbl_visibility import are_leader_scores_hidden_for_group



router = APIRouter(prefix="/api/teacher/intervention", tags=["teacher-intervention"])





class DimensionScoreUpdate(BaseModel):

    dimension_name: str

    mean: float = Field(ge=1.0, le=5.0)





class TeacherScorePatch(BaseModel):

    dimension_scores: list[DimensionScoreUpdate]

    note: str | None = None





class TeacherApproveBody(BaseModel):

    note: str | None = None





def _serialize_record(
    record: GroupPblEvaluation,
    group_name: str | None = None,
    project_id: int | None = None,
    project_title: str | None = None,
) -> dict[str, Any]:

    result = dict(record.result_json or {})

    return {

        "id": record.id,

        "group_id": record.group_id,

        "group_name": group_name,

        "project_id": project_id,

        "project_title": project_title,

        "student_id": record.student_id,

        "filename": record.filename,

        "file_path": record.file_path,

        "has_document": bool(record.file_path),

        "report_text_preview": (
            (record.report_text[:800] + "…")
            if record.report_text and len(record.report_text) > 800
            else record.report_text
        ),

        "created_at": record.created_at.isoformat() if record.created_at else None,

        "audit_passed": is_teacher_audit_passed(
            result=result,
            teacher_reviewed=bool(record.teacher_reviewed),
            max_review_rounds_reached=bool(record.max_review_rounds_reached),
        ),

        "max_review_rounds_reached": record.max_review_rounds_reached,

        "needs_teacher_intervention": record.needs_teacher_intervention,

        "teacher_reviewed": record.teacher_reviewed,

        "teacher_intervention_note": record.teacher_intervention_note,

        "final_score": record.final_score,

        "dimension_mean_score": record.dimension_mean_score,

        "dimension_summary": result.get("dimension_summary") or [],

        "primary_indicator_summary": result.get("primary_indicator_summary") or [],

        "failed_dimension_views": extract_failed_dimension_views(result),

        "internal_audit": result.get("internal_audit") or {},

        "final_comment": result.get("final_comment") or result.get("final_feedback"),

        "teacher_modified": bool(result.get("teacher_modified")),

    }





def _group_context(db: Session, group_id: int | None) -> tuple[str | None, int | None, str | None]:

    if not group_id:

        return None, None, None

    group = db.query(Group).filter(Group.id == group_id).first()

    if not group:

        return None, None, None

    project_title = None

    if group.project_id:

        project = db.query(Project).filter(Project.id == group.project_id).first()

        project_title = project.title if project else None

    return group.name, group.project_id, project_title





def _serialize_with_group(db: Session, record: GroupPblEvaluation) -> dict[str, Any]:

    group_name, project_id, project_title = _group_context(db, record.group_id)

    return _serialize_record(
        record,
        group_name=group_name,
        project_id=project_id,
        project_title=project_title,
    )





def _group_name(db: Session, group_id: int | None) -> str | None:

    if not group_id:

        return None

    group = db.query(Group).filter(Group.id == group_id).first()

    return group.name if group else None





@router.get("/pending")

def list_pending_interventions(

    db: Session = Depends(get_db),

    _: User = Depends(require_role("teacher", "admin")),

):

    """审核智能体达最大轮次仍未通过、需教师介入的记录。"""

    rows = (

        db.query(GroupPblEvaluation)

        .filter(

            GroupPblEvaluation.needs_teacher_intervention.is_(True),

            GroupPblEvaluation.teacher_reviewed.is_(False),

        )

        .order_by(GroupPblEvaluation.created_at.desc())

        .all()

    )

    return [

        _serialize_with_group(db, row)

        for row in rows

    ]





@router.get("/evaluations")

def list_completed_evaluations(

    db: Session = Depends(get_db),

    _: User = Depends(require_role("teacher", "admin")),

):

    """全部小组 PBL 评价记录（含审核通过与达最大轮次未通过）。"""

    rows = (

        db.query(GroupPblEvaluation)

        .order_by(GroupPblEvaluation.created_at.desc())

        .all()

    )

    return [

        _serialize_with_group(db, row)

        for row in rows

    ]





@router.post("/{evaluation_id}/approve")

def approve_evaluation(

    evaluation_id: int,

    body: TeacherApproveBody | None = None,

    db: Session = Depends(get_db),

    _: User = Depends(require_role("teacher", "admin")),

):

    """教师直接通过当前评分，并触发三维度汇总。"""

    record = db.query(GroupPblEvaluation).filter(GroupPblEvaluation.id == evaluation_id).first()

    if not record:

        raise HTTPException(status_code=404, detail="评价记录不存在")

    if not record.needs_teacher_intervention:

        raise HTTPException(status_code=400, detail="该记录无需教师介入")



    try:

        pre_release = are_leader_scores_hidden_for_group(db, record.group_id)

        updated = finalize_teacher_intervention(

            db,

            record,

            teacher_modified=False,

            note=(body.note if body else None) or "教师已直接通过评分",

            use_llm=True,

            pre_release=pre_release,

        )

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"汇总失败: {exc}") from exc



    return {

        "success": True,

        "message": "已直接通过并完成三维度汇总",

        "record": _serialize_with_group(db, updated),

    }





@router.patch("/{evaluation_id}/scores")

def patch_scores(

    evaluation_id: int,

    body: TeacherScorePatch,

    db: Session = Depends(get_db),

    _: User = Depends(require_role("teacher", "admin")),

):

    """教师修改 12 维得分后完成三维度汇总。"""

    record = db.query(GroupPblEvaluation).filter(GroupPblEvaluation.id == evaluation_id).first()

    if not record:

        raise HTTPException(status_code=404, detail="评价记录不存在")



    updated = apply_teacher_score_override(

        db,

        record,

        [item.model_dump() for item in body.dimension_scores],

    )

    try:

        pre_release = are_leader_scores_hidden_for_group(db, updated.group_id)

        if pre_release:

            finalized = apply_teacher_pre_release_score_update(

                db,

                updated,

                note=body.note or "教师截止前已修改分数",

            )

        else:

            finalized = finalize_teacher_intervention(

                db,

                updated,

                teacher_modified=True,

                note=body.note or "教师已修改分数并确认",

            )

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"汇总失败: {exc}") from exc



    return _serialize_with_group(db, finalized)


