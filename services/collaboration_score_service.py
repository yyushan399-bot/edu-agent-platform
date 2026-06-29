"""聚合自评、互评与智能体分数，供终结性评价智能体使用。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Evaluation, PeerAssessment, SelfAssessment, User
from services.group_service import UserNotFoundError


def _clamp_score(value: float) -> float:
    """将分数限制在 1-5 分制范围内。"""
    return float(max(1.0, min(5.0, round(float(value), 2))))


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _get_user_or_raise(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(f"用户不存在: user_id={user_id}")
    return user


def get_latest_ai_score(
    db: Session,
    *,
    user_id: int,
    assignment_id: int,
) -> float | None:
    """取该用户在该作业上最新一条智能体评估分数（1-5 分制）。"""
    stmt = (
        select(Evaluation.total_score)
        .where(
            Evaluation.user_id == user_id,
            Evaluation.assignment_id == assignment_id,
            Evaluation.total_score.isnot(None),
        )
        .order_by(Evaluation.created_at.desc())
        .limit(1)
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    return _clamp_score(row)


def get_self_assessment_record(
    db: Session,
    *,
    user_id: int,
    assignment_id: int,
) -> SelfAssessment | None:
    return (
        db.query(SelfAssessment)
        .filter_by(user_id=user_id, assignment_id=assignment_id)
        .one_or_none()
    )


def get_peer_scores_received(
    db: Session,
    *,
    user_id: int,
    assignment_id: int,
) -> list[float]:
    """被评者收到的互评分数列表（1-5 分制）。"""
    stmt = select(PeerAssessment.score).where(
        PeerAssessment.target_user_id == user_id,
        PeerAssessment.assignment_id == assignment_id,
    )
    rows = db.execute(stmt).scalars().all()
    return [_clamp_score(score) for score in rows]


def get_peer_reviews_given(
    db: Session,
    *,
    reviewer_id: int,
    assignment_id: int,
) -> list[PeerAssessment]:
    return (
        db.query(PeerAssessment)
        .filter_by(reviewer_id=reviewer_id, assignment_id=assignment_id)
        .order_by(PeerAssessment.created_at.asc())
        .all()
    )


def build_collaboration_payload(
    db: Session,
    *,
    user_id: int,
    assignment_id: int,
) -> dict[str, Any]:
    """
    汇总协作能力相关三分数（均为 1-5 分制）：

    - ai_score：智能体（LangGraph）评估
    - self_score：学生自评
    - peer_score：同伴互评均值（被评者收到）
    """
    _get_user_or_raise(db, user_id)

    ai_score = get_latest_ai_score(db, user_id=user_id, assignment_id=assignment_id)
    self_record = get_self_assessment_record(
        db, user_id=user_id, assignment_id=assignment_id
    )
    peer_scores = get_peer_scores_received(
        db, user_id=user_id, assignment_id=assignment_id
    )
    peer_score = _mean(peer_scores)

    self_score = None
    self_comment = None
    if self_record is not None:
        self_score = _clamp_score(self_record.score)
        self_comment = (self_record.comment or "").strip() or None

    missing: list[str] = []
    if ai_score is None:
        missing.append("ai_score")
    if self_score is None:
        missing.append("self_score")
    if peer_score is None:
        missing.append("peer_score")

    return {
        "user_id": user_id,
        "assignment_id": assignment_id,
        "ai_score": ai_score,
        "self_score": self_score,
        "self_comment": self_comment,
        "peer_score": peer_score,
        "peer_scores": peer_scores,
        "peer_review_count": len(peer_scores),
        "missing_scores": missing,
        "ready_for_summative": ai_score is not None,
    }


__all__ = [
    "build_collaboration_payload",
    "get_latest_ai_score",
    "get_peer_reviews_given",
    "get_peer_scores_received",
    "get_self_assessment_record",
]
