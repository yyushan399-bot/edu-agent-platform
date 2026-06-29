"""同伴互评路由（组员 / 组长）。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.models import User
from backend.services.peer_review_service import (
    NotGroupPeerError,
    PeerReviewAlreadyExistsError,
    SelfReviewNotAllowedError,
    SubmissionNotFoundError,
    list_peer_review_items,
    list_teacher_peer_reviews,
    submit_peer_review,
)
from backend.schemas import (
    PeerReviewListOut,
    SubmitPeerReviewRequest,
    SubmitPeerReviewResponse,
    TeacherPeerReviewListOut,
)

router = APIRouter(prefix="/api/peer-review", tags=["同伴互评"])


@router.get("/assignments", response_model=PeerReviewListOut)
def list_peer_review_assignments(
    project_id: int = Query(..., description="当前项目 ID"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("group_leader", "group_member")),
):
    """获取同组其他成员在本项目下的待互评提交（含本人是否已评）。"""
    items = list_peer_review_items(db, reviewer=user, project_id=project_id)
    return {"count": len(items), "items": items}


@router.get("/teacher", response_model=TeacherPeerReviewListOut)
def list_teacher_peer_review_records(
    project_id: Optional[int] = Query(None, description="按项目筛选"),
    group_id: Optional[int] = Query(None, description="按小组筛选"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="返回条数上限"),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("teacher", "admin")),
):
    """教师 / 管理员查看学生互评记录。"""
    items = list_teacher_peer_reviews(
        db,
        project_id=project_id,
        group_id=group_id,
        limit=limit,
    )
    return {"count": len(items), "items": items}


@router.post("/submit", response_model=SubmitPeerReviewResponse, status_code=status.HTTP_201_CREATED)
def create_peer_review(
    body: SubmitPeerReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("group_leader", "group_member")),
):
    """提交对同组某次节点提交的互评（每人每提交仅一次）。"""
    try:
        record = submit_peer_review(
            db,
            reviewer=user,
            ai_analyze_submission_id=body.ai_analyze_submission_id,
            score=body.score,
            comment=body.comment,
        )
        db.commit()
        db.refresh(record)
    except SelfReviewNotAllowedError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SubmissionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PeerReviewAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except NotGroupPeerError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"提交互评失败: {exc}",
        ) from exc

    return {"success": True, "peer_assessment": record}
