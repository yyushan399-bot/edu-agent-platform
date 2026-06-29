"""评估路由：触发评估、查询结果."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import User, Submission, Evaluation, MetaReport, SubmissionStatus
from backend.schemas import EvaluationOut, MetaReportOut, EvaluationDetailOut
from backend.dependencies import get_current_user, require_role
from backend.services.evaluation_pipeline import run_evaluation

router = APIRouter(prefix="/api/evaluations", tags=["评估管理"])


@router.get("/submission/{submission_id}", response_model=EvaluationDetailOut)
def get_submission_evaluation(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取某次提交的完整评估结果。"""
    submission = (
        db.query(Submission)
        .options(joinedload(Submission.node), joinedload(Submission.user))
        .filter(Submission.id == submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提交不存在")

    # 只允许提交者、教师、管理员查看
    if user.role.value not in ("teacher", "admin") and submission.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看")

    evaluations = db.query(Evaluation).filter(
        Evaluation.submission_id == submission_id
    ).all()
    meta_report = db.query(MetaReport).filter(
        MetaReport.submission_id == submission_id
    ).first()

    return EvaluationDetailOut(
        submission=submission,
        evaluations=evaluations,
        meta_report=meta_report,
    )


@router.get("/submission/{submission_id}/report", response_model=MetaReportOut)
def get_meta_report(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取元评估综合报告。"""
    report = db.query(MetaReport).filter(
        MetaReport.submission_id == submission_id
    ).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告尚未生成")
    return report


@router.post("/run/{submission_id}")
def trigger_evaluation(
    submission_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin")),
):
    """手动触发评估流水线。"""
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提交不存在")

    # 异步触发评估（当前为同步简化版）
    try:
        result = run_evaluation(submission, db)
        submission.status = SubmissionStatus.evaluated
        db.commit()
        return {"status": "ok", "result": result}
    except Exception as e:
        submission.status = SubmissionStatus.submitted
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
