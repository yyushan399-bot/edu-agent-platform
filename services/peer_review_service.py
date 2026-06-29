"""互评业务服务（SQLAlchemy）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import Assignment, Evaluation, PeerAssessment, User
from services.group_service import GroupService, UserNotFoundError


class SelfReviewNotAllowedError(ValueError):
    """不允许评价自己。"""


class PeerReviewAlreadyExistsError(ValueError):
    """该作业已评价过，不可重复提交。"""


class AssignmentNotFoundError(LookupError):
    """作业不存在。"""


class NotGroupPeerError(ValueError):
    """被评价者不在同一小组。"""


class PeerReviewService:
    """同伴互评：查询待评作业、提交互评。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.groups = GroupService(db)

    # ------------------------------------------------------------------
    # 提交同伴评价
    # ------------------------------------------------------------------

    def submit_peer_review(
        self,
        *,
        reviewer_id: int,
        target_user_id: int,
        assignment_id: int,
        score: float,
        comment: str | None = None,
    ) -> PeerAssessment:
        """
        提交同伴评价并写入 peer_assessments 表。

        规则：
        1. 不允许评价自己
        2. 同一 reviewer + target + assignment 只能评价一次
        3. 被评价者须与评价者在同一小组
        """
        if reviewer_id == target_user_id:
            raise SelfReviewNotAllowedError("不允许评价自己")

        self.groups._require_user(reviewer_id)
        self.groups._require_user(target_user_id)
        self._require_assignment(assignment_id)

        peer_ids = set(self.groups.get_peer_member_ids(reviewer_id))
        if target_user_id not in peer_ids:
            raise NotGroupPeerError(
                f"用户 {target_user_id} 不在您的同组成员中，无法互评"
            )

        existing = (
            self.db.query(PeerAssessment)
            .filter_by(
                reviewer_id=reviewer_id,
                target_user_id=target_user_id,
                assignment_id=assignment_id,
            )
            .one_or_none()
        )
        if existing is not None:
            raise PeerReviewAlreadyExistsError(
                f"您已评价过用户 {target_user_id} 的作业 {assignment_id}，不可重复提交"
            )

        record = PeerAssessment(
            reviewer_id=reviewer_id,
            target_user_id=target_user_id,
            assignment_id=assignment_id,
            score=self._clamp_score(score),
            comment=(comment or "").strip() or None,
        )
        self.db.add(record)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise PeerReviewAlreadyExistsError(
                f"您已评价过用户 {target_user_id} 的作业 {assignment_id}，不可重复提交"
            ) from exc
        return record

    def get_peer_review(
        self,
        *,
        reviewer_id: int,
        target_user_id: int,
        assignment_id: int,
    ) -> PeerAssessment | None:
        """查询是否已提交过互评。"""
        return (
            self.db.query(PeerAssessment)
            .filter_by(
                reviewer_id=reviewer_id,
                target_user_id=target_user_id,
                assignment_id=assignment_id,
            )
            .one_or_none()
        )

    # ------------------------------------------------------------------
    # 待互评作业列表
    # ------------------------------------------------------------------

    def list_group_peer_assignments(self, user_id: int) -> list[dict[str, Any]]:
        """
        获取当前用户同组其他成员已提交的作业（不含本人）。

        以 evaluations 表为提交记录，返回每组员每作业最新一条。
        """
        self.groups._require_user(user_id)
        peer_ids = self.groups.get_peer_member_ids(user_id)
        if not peer_ids:
            return []

        latest_subq = (
            select(
                Evaluation.user_id.label("user_id"),
                Evaluation.assignment_id.label("assignment_id"),
                func.max(Evaluation.created_at).label("max_created_at"),
            )
            .where(
                Evaluation.user_id.in_(peer_ids),
                Evaluation.assignment_id.isnot(None),
            )
            .group_by(Evaluation.user_id, Evaluation.assignment_id)
            .subquery()
        )

        stmt = (
            select(Evaluation, User)
            .join(
                latest_subq,
                (Evaluation.user_id == latest_subq.c.user_id)
                & (Evaluation.assignment_id == latest_subq.c.assignment_id)
                & (Evaluation.created_at == latest_subq.c.max_created_at),
            )
            .join(User, User.id == Evaluation.user_id)
            .order_by(Evaluation.created_at.desc())
        )
        rows = self.db.execute(stmt).all()

        results: list[dict[str, Any]] = []
        for evaluation, user in rows:
            results.append(self._submission_to_dict(evaluation, user))
        return results

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    @staticmethod
    def peer_assessment_to_dict(record: PeerAssessment) -> dict[str, Any]:
        return {
            "id": record.id,
            "reviewer_id": record.reviewer_id,
            "target_user_id": record.target_user_id,
            "assignment_id": record.assignment_id,
            "score": record.score,
            "comment": record.comment,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    @staticmethod
    def _student_display_name(user: User) -> str:
        full_name = (user.full_name or "").strip()
        if full_name:
            return full_name
        return user.username

    @staticmethod
    def _submission_to_dict(evaluation: Evaluation, user: User) -> dict[str, Any]:
        submit_time = evaluation.created_at
        return {
            "assignment_id": evaluation.assignment_id,
            "target_user_id": user.id,
            "student_name": PeerReviewService._student_display_name(user),
            "file_url": evaluation.file_url or "",
            "submit_time": submit_time.isoformat() if submit_time else None,
        }

    @staticmethod
    def _clamp_score(value: float) -> float:
        return float(max(1.0, min(5.0, round(float(value), 2)))

    def _require_assignment(self, assignment_id: int) -> Assignment:
        assignment = self.db.get(Assignment, assignment_id)
        if assignment is None:
            raise AssignmentNotFoundError(f"作业不存在: assignment_id={assignment_id}")
        return assignment


__all__ = [
    "AssignmentNotFoundError",
    "NotGroupPeerError",
    "PeerReviewAlreadyExistsError",
    "PeerReviewService",
    "SelfReviewNotAllowedError",
    "UserNotFoundError",
]
