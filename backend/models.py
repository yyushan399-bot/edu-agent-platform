"""SQLAlchemy 数据模型."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Enum,
    ForeignKey, JSON, Boolean, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base


# ── 枚举 ───────────────────────────────────────────────

class UserRole(str, enum.Enum):
    teacher = "teacher"
    admin = "admin"
    group_leader = "group_leader"
    group_member = "group_member"


class SubmissionStatus(str, enum.Enum):
    pending = "pending"          # 未提交
    submitted = "submitted"      # 已提交
    evaluating = "evaluating"    # 评估中
    evaluated = "evaluated"      # 已完成评估


# ── 用户 ───────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String(32), unique=True, index=True, nullable=False)  # 学号/工号
    name = Column(String(64), nullable=False)
    hashed_password = Column(String(256), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # 关系
    group_members = relationship("GroupMember", back_populates="user")
    submissions = relationship("Submission", back_populates="user")


# ── 项目 ───────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    group_size = Column(Integer, nullable=True)  # 项目小组人数（含组长）
    guide_file_path = Column(String(512), nullable=True)  # 指南附件路径
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # 关系
    nodes = relationship("ProjectNode", back_populates="project", cascade="all, delete-orphan")


class ProjectNode(Base):
    """项目的阶段性节点（如 节点一、节点二...）"""
    __tablename__ = "project_nodes"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(128), nullable=False)       # 节点名称
    deadline = Column(DateTime(timezone=True), nullable=True)
    order = Column(Integer, default=0)               # 排序

    project = relationship("Project", back_populates="nodes")
    submissions = relationship("Submission", back_populates="node")


# ── 小组 ───────────────────────────────────────────────

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)       # 第1组, 第2组...
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    leader_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_members")


# ── 提交物 ─────────────────────────────────────────────

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    node_id = Column(Integer, ForeignKey("project_nodes.id"), nullable=False)
    file_path = Column(String(512), nullable=True)    # 上传文件路径
    text_content = Column(Text, nullable=True)         # 文本提交内容
    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.submitted)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="submissions")
    node = relationship("ProjectNode", back_populates="submissions")
    evaluations = relationship("Evaluation", back_populates="submission", cascade="all, delete-orphan")


# ── 评估结果 ───────────────────────────────────────────

class Evaluation(Base):
    """各智能体评分 + 元评估综合报告."""
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    dim_key = Column(String(32), nullable=False)          # theory / practice / data / literature
    scores = Column(JSON, nullable=True)                  # {"concept_accuracy": 4, ...}
    feedbacks = Column(JSON, nullable=True)               # {"concept_accuracy": "反馈文字", ...}
    summary = Column(Text, nullable=True)
    dimension_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    submission = relationship("Submission", back_populates="evaluations")


class MetaReport(Base):
    """元评估综合报告."""
    __tablename__ = "meta_reports"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False, unique=True)
    total_score = Column(Float, nullable=True)
    collaboration_score = Column(Float, nullable=True)
    report_content = Column(Text, nullable=True)           # Markdown 综合报告
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AiAnalyzeSubmission(Base):
    """AI 作业分析（/analyze）提交记录，供同组互评可见。"""
    __tablename__ = "ai_analyze_submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    student_id = Column(String(32), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    session_id = Column(String(64), nullable=True)
    filename = Column(String(256), nullable=True)
    file_path = Column(String(512), nullable=True)
    self_score = Column(Float, nullable=True)
    self_comment = Column(Text, nullable=True)
    routes = Column(JSON, nullable=True)
    ai_total_score = Column(Float, nullable=True)
    feedback_preview = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User")


class PeerAssessment(Base):
    """同伴互评：仅针对 AI 作业分析提交。"""
    __tablename__ = "peer_assessments"
    __table_args__ = (
        UniqueConstraint(
            "reviewer_id", "ai_analyze_submission_id", name="uq_peer_reviewer_ai_analyze"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=True)
    group_pbl_evaluation_id = Column(
        Integer, ForeignKey("group_pbl_evaluations.id"), nullable=True
    )
    ai_analyze_submission_id = Column(
        Integer, ForeignKey("ai_analyze_submissions.id"), nullable=True
    )
    score = Column(Float, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    reviewer = relationship("User", foreign_keys=[reviewer_id])
    target_user = relationship("User", foreign_keys=[target_user_id])
    submission = relationship("Submission")
    group_pbl_evaluation = relationship("GroupPblEvaluation")
    ai_analyze_submission = relationship("AiAnalyzeSubmission")


class GroupPblEvaluation(Base):
    """小组项目 PBL 评价结果（LangGraph /group-evaluation）。"""
    __tablename__ = "group_pbl_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    student_id = Column(String(32), nullable=False, index=True)
    filename = Column(String(256), nullable=True)
    file_path = Column(String(512), nullable=True)
    report_text = Column(Text, nullable=True)
    result_json = Column(JSON, nullable=False)
    audit_passed = Column(Boolean, default=False)
    max_review_rounds_reached = Column(Boolean, default=False)
    needs_teacher_intervention = Column(Boolean, default=False)
    teacher_reviewed = Column(Boolean, default=False)
    teacher_intervention_note = Column(Text, nullable=True)
    final_score = Column(Float, nullable=True)
    dimension_mean_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
