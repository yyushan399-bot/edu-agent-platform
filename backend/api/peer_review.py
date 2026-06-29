"""互评 API。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services.group_service import UserNotFoundError
from services.peer_review_service import (
    AssignmentNotFoundError,
    NotGroupPeerError,
    PeerReviewAlreadyExistsError,
    PeerReviewService,
    SelfReviewNotAllowedError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/peer-review", tags=["peer-review"])


class SubmitPeerReviewRequest(BaseModel):
    reviewer_id: int = Field(..., description="评价者 user_id")
    target_user_id: int = Field(..., description="被评价者 user_id")
    assignment_id: int = Field(..., description="作业 ID")
    score: float = Field(..., ge=1, le=5, description="互评分数 1-5")
    comment: str | None = Field(None, description="互评评语（可选）")


@router.get("/assignments")
async def list_peer_review_assignments(
    user_id: int = Query(..., description="当前用户 ID（users.id）"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    获取当前用户所在小组其他成员已提交的作业（排除本人）。

    返回字段：assignment_id, student_name, file_url, submit_time
    """
    service = PeerReviewService(db)
    try:
        items = service.list_group_peer_assignments(user_id)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return jsonable_encoder(
        {
            "success": True,
            "user_id": user_id,
            "count": len(items),
            "items": items,
        }
    )


@router.post("/submit")
async def submit_peer_review(
    body: SubmitPeerReviewRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    提交同伴评价。

    - 不允许评价自己
    - 同一评价者对同一被评价者的同一作业只能评价一次
    - 被评价者须与评价者在同一小组
    """
    service = PeerReviewService(db)
    try:
        record = service.submit_peer_review(
            reviewer_id=body.reviewer_id,
            target_user_id=body.target_user_id,
            assignment_id=body.assignment_id,
            score=body.score,
            comment=body.comment,
        )
        db.commit()
        db.refresh(record)
    except UserNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AssignmentNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SelfReviewNotAllowedError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PeerReviewAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotGroupPeerError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"提交互评失败: {exc}") from exc

    summative_evaluation = None
    try:
        from api.summative_evaluation import run_summative_for_assignment

        summative_evaluation = run_summative_for_assignment(
            db,
            user_id=body.target_user_id,
            assignment_id=body.assignment_id,
            use_llm=False,
        )
    except Exception as exc:
        logger.warning(
            "被评者终结性评价跳过 target=%s assignment=%s: %s",
            body.target_user_id,
            body.assignment_id,
            exc,
        )

    return jsonable_encoder(
        {
            "success": True,
            "peer_assessment": service.peer_assessment_to_dict(record),
            "summative_evaluation": summative_evaluation,
        }
    )


__all__ = ["router", "SubmitPeerReviewRequest"]
