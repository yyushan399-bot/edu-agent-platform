"""组长 / 管理员：小组 PBL 评价结果与报告文档。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.models import Group, GroupPblEvaluation, User
from backend.services.group_pbl_store import resolve_group_pbl_file_path
from backend.services.peer_review_service import can_access_group_pbl_file
from backend.services.pbl_visibility import can_leader_view_scores, mask_leader_scores
from backend.services.teacher_pbl_finalize import sync_leader_display_payload

router = APIRouter(prefix="/api/group-pbl", tags=["group-pbl"])


@router.get("/my-latest")
def get_my_latest_group_pbl(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("group_leader")),
):
    """组长获取本组最新 PBL 评价；三维度得分按项目截止+30 天规则返回。"""
    group_q = db.query(Group).filter(Group.leader_id == user.id)
    if project_id is not None:
        group_q = group_q.filter(Group.project_id == project_id)
    group = group_q.first()
    if not group:
        raise HTTPException(status_code=404, detail="未找到您负责的小组")

    record = (
        db.query(GroupPblEvaluation)
        .filter(GroupPblEvaluation.group_id == group.id)
        .order_by(GroupPblEvaluation.created_at.desc())
        .first()
    )
    if not record:
        return {"has_evaluation": False}

    visible, visible_at = can_leader_view_scores(
        db, user, project_id or group.project_id
    )
    payload = sync_leader_display_payload(dict(record.result_json or {}))
    payload.update(
        {
            "evaluation_id": record.id,
            "filename": record.filename,
            "file_path": record.file_path,
            "has_document": bool(record.file_path),
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "audit_passed": record.audit_passed,
        }
    )
    return {
        "has_evaluation": True,
        **mask_leader_scores(payload, visible=visible, visible_at=visible_at),
    }


@router.get("/evaluations/{evaluation_id}/report-file")
def download_group_pbl_report_file(
    evaluation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载小组 PBL 报告原文件（本人 / 同组 / 教师 / 管理员）。"""
    record = (
        db.query(GroupPblEvaluation)
        .filter(GroupPblEvaluation.id == evaluation_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评价记录不存在")
    if not record.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该记录未存档报告文档")

    if not can_access_group_pbl_file(db, viewer=user, record=record):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该报告")

    path = resolve_group_pbl_file_path(record.file_path)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告文件已丢失")

    download_name = Path(record.filename or path.name).name
    return FileResponse(path, filename=download_name, media_type="application/octet-stream")
