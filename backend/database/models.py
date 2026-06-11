"""教育智能体 SQLAlchemy ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# 已有表
# ---------------------------------------------------------------------------


class User(Base):
    """用户（学生 / 教师）。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="student", comment="student | teacher | admin"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    assignments_created: Mapped[list["Assignment"]] = relationship(
        back_populates="creator",
        foreign_keys="Assignment.created_by",
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="user")
    group_memberships: Mapped[list["GroupMember"]] = relationship(back_populates="user")
    self_assessments: Mapped[list["SelfAssessment"]] = relationship(
        back_populates="user",
        foreign_keys="SelfAssessment.user_id",
    )
    peer_reviews_given: Mapped[list["PeerAssessment"]] = relationship(
        back_populates="reviewer",
        foreign_keys="PeerAssessment.reviewer_id",
    )
    peer_reviews_received: Mapped[list["PeerAssessment"]] = relationship(
        back_populates="target_user",
        foreign_keys="PeerAssessment.target_user_id",
    )
    evaluation_profile: Mapped[Optional["EvaluationProfile"]] = relationship(
        back_populates="user",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class Assignment(Base):
    """作业 / 任务。"""

    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    creator: Mapped[Optional["User"]] = relationship(
        back_populates="assignments_created",
        foreign_keys=[created_by],
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="assignment")
    self_assessments: Mapped[list["SelfAssessment"]] = relationship(
        back_populates="assignment"
    )
    peer_assessments: Mapped[list["PeerAssessment"]] = relationship(
        back_populates="assignment"
    )

    def __repr__(self) -> str:
        return f"<Assignment id={self.id} title={self.title!r}>"


class Evaluation(Base):
    """AI 智能体评估结果（LangGraph 产出）。"""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("assignments.id", ondelete="SET NULL"), index=True
    )
    route: Mapped[Optional[str]] = mapped_column(
        String(32), comment="theory | practice | data | literature"
    )
    total_score: Mapped[Optional[float]] = mapped_column(Float)
    final_feedback: Mapped[Optional[str]] = mapped_column(Text)
    file_url: Mapped[Optional[str]] = mapped_column(
        String(512), comment="提交文件访问路径，如 /uploads/{stored_name}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="evaluations")
    assignment: Mapped[Optional["Assignment"]] = relationship(back_populates="evaluations")

    def __repr__(self) -> str:
        return f"<Evaluation id={self.id} user_id={self.user_id} score={self.total_score}>"


# ---------------------------------------------------------------------------
# 新增表
# ---------------------------------------------------------------------------


class Group(Base):
    """学习小组。"""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    members: Mapped[list["GroupMember"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Group id={self.id} name={self.name!r}>"


class GroupMember(Base):
    """小组成员（用户 ↔ 小组 多对多）。"""

    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_group_members_user_group"),
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )

    user: Mapped["User"] = relationship(back_populates="group_memberships")
    group: Mapped["Group"] = relationship(back_populates="members")

    def __repr__(self) -> str:
        return f"<GroupMember user_id={self.user_id} group_id={self.group_id}>"


class SelfAssessment(Base):
    """学生自评。"""

    __tablename__ = "self_assessments"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "assignment_id",
            name="uq_self_assessments_user_assignment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(
        back_populates="self_assessments",
        foreign_keys=[user_id],
    )
    assignment: Mapped["Assignment"] = relationship(back_populates="self_assessments")

    def __repr__(self) -> str:
        return (
            f"<SelfAssessment id={self.id} user_id={self.user_id} "
            f"assignment_id={self.assignment_id} score={self.score}>"
        )


class PeerAssessment(Base):
    """同伴互评。"""

    __tablename__ = "peer_assessments"
    __table_args__ = (
        UniqueConstraint(
            "reviewer_id",
            "target_user_id",
            "assignment_id",
            name="uq_peer_assessments_reviewer_target_assignment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reviewer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    reviewer: Mapped["User"] = relationship(
        back_populates="peer_reviews_given",
        foreign_keys=[reviewer_id],
    )
    target_user: Mapped["User"] = relationship(
        back_populates="peer_reviews_received",
        foreign_keys=[target_user_id],
    )
    assignment: Mapped["Assignment"] = relationship(back_populates="peer_assessments")

    def __repr__(self) -> str:
        return (
            f"<PeerAssessment id={self.id} reviewer_id={self.reviewer_id} "
            f"target_user_id={self.target_user_id} score={self.score}>"
        )


class EvaluationProfile(Base):
    """
    用户评估画像（用于校准 AI 评分偏差）。

    - self_bias / peer_bias：相对客观分的系统性偏差（正=偏高，负=偏低）
    - confidence_type：自信程度类型
    - reviewer_type：评价者角色倾向
    - emotion_state：当前情绪状态（影响自评/互评权重）
    """

    __tablename__ = "evaluation_profiles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    self_bias: Mapped[Optional[float]] = mapped_column(
        Float, comment="自评偏差系数，如 +5 表示习惯性高估 5 分"
    )
    peer_bias: Mapped[Optional[float]] = mapped_column(
        Float, comment="互评偏差系数"
    )
    confidence_type: Mapped[Optional[str]] = mapped_column(
        String(64), comment="如 overconfident | underconfident | calibrated"
    )
    reviewer_type: Mapped[Optional[str]] = mapped_column(
        String(64), comment="如 strict | lenient | balanced"
    )
    emotion_state: Mapped[Optional[str]] = mapped_column(
        String(64), comment="如 anxious | neutral | motivated"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="evaluation_profile")

    def __repr__(self) -> str:
        return f"<EvaluationProfile user_id={self.user_id}>"


__all__ = [
    "Assignment",
    "Evaluation",
    "EvaluationProfile",
    "Group",
    "GroupMember",
    "PeerAssessment",
    "SelfAssessment",
    "User",
]
