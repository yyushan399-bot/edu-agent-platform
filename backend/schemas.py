"""Pydantic 数据模型（API 请求/响应）. """

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_serializer, model_validator

from backend.datetime_utils import ensure_utc, serialize_utc_iso
from backend.models import UserRole, SubmissionStatus


# ── Auth ───────────────────────────────────────────────

class LoginRequest(BaseModel):
    student_id: str
    password: str
    role: UserRole  # 前端选择角色，后端校验


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


# ── User ───────────────────────────────────────────────

class UserCreate(BaseModel):
    student_id: str
    name: str
    password: str = Field(default="12345")
    role: UserRole


class StudentRegisterRequest(BaseModel):
    """学生自助注册（公开接口，固定为小组成员）。"""

    student_id: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class StudentRegisterResponse(BaseModel):
    message: str
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    student_id: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return serialize_utc_iso(value) or ""


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class PasswordReset(BaseModel):
    new_password: str = Field(default="12345")


# ── Project ────────────────────────────────────────────

class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    group_size: Optional[int] = Field(default=None, ge=1, le=50, description="项目小组人数（含组长）")

    @model_validator(mode="after")
    def normalize_deadline(self) -> "ProjectCreate":
        if self.deadline is not None:
            self.deadline = ensure_utc(self.deadline)
        return self


class ProjectNodeOut(BaseModel):
    id: int
    name: str
    deadline: Optional[datetime] = None
    order: int

    model_config = {"from_attributes": True}

    @field_serializer("deadline")
    def serialize_deadline(self, value: datetime | None) -> str | None:
        return serialize_utc_iso(value)


class ProjectOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    group_size: Optional[int] = None
    created_by: int
    created_at: datetime
    nodes: list[ProjectNodeOut] = []

    model_config = {"from_attributes": True}

    @field_serializer("deadline", "created_at")
    def serialize_datetimes(self, value: datetime | None) -> str | None:
        return serialize_utc_iso(value)


# ── Group ──────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str
    project_id: Optional[int] = None
    leader_student_id: str = Field(min_length=1, max_length=32, description="组长学号")
    member_student_ids: list[str] = Field(default_factory=list, description="组员学号列表")


class GroupMemberOut(BaseModel):
    id: int
    user_id: int
    user: Optional[UserOut] = None

    model_config = {"from_attributes": True}


class GroupOut(BaseModel):
    id: int
    name: str
    project_id: Optional[int] = None
    leader_id: Optional[int] = None
    members: list[GroupMemberOut] = []
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return serialize_utc_iso(value) or ""


class GroupImportOut(BaseModel):
    created: int
    message: str
    groups: list[GroupOut] = []


# ── Submission ─────────────────────────────────────────

class SubmissionCreate(BaseModel):
    node_id: int
    text_content: Optional[str] = None
    # file 走 multipart 上传


class SubmissionOut(BaseModel):
    id: int
    user_id: int
    node_id: int
    file_path: Optional[str] = None
    text_content: Optional[str] = None
    status: SubmissionStatus
    submitted_at: datetime
    user: Optional[UserOut] = None
    node: Optional[ProjectNodeOut] = None

    model_config = {"from_attributes": True}

    @field_serializer("submitted_at")
    def serialize_submitted_at(self, value: datetime) -> str:
        return serialize_utc_iso(value) or ""


# ── Evaluation ─────────────────────────────────────────

class EvaluationOut(BaseModel):
    id: int
    dim_key: str
    scores: Optional[dict] = None
    feedbacks: Optional[dict] = None
    summary: Optional[str] = None
    dimension_score: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MetaReportOut(BaseModel):
    id: int
    total_score: Optional[float] = None
    collaboration_score: Optional[float] = None
    report_content: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvaluationDetailOut(BaseModel):
    """一次提交的完整评估结果."""
    submission: SubmissionOut
    evaluations: list[EvaluationOut] = []
    meta_report: Optional[MetaReportOut] = None


# ── Peer Review ────────────────────────────────────────

class PeerAssessmentOut(BaseModel):
    id: int
    reviewer_id: int
    target_user_id: int
    ai_analyze_submission_id: Optional[int] = None
    score: float
    comment: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return serialize_utc_iso(value) or ""


class PeerReviewItemOut(BaseModel):
    """待互评的 AI 作业分析条目。"""
    item_type: str = "ai_analyze"
    ai_analyze_submission_id: int
    target_user_id: int
    student_name: str
    node_name: str
    has_file: bool
    file_name: Optional[str] = None
    file_download_url: Optional[str] = None
    text_preview: Optional[str] = None
    self_score: Optional[float] = None
    ai_total_score: Optional[float] = None
    submit_time: Optional[datetime] = None
    my_review: Optional[PeerAssessmentOut] = None

    @field_serializer("submit_time")
    def serialize_submit_time(self, value: datetime | None) -> str | None:
        return serialize_utc_iso(value)


class PeerReviewListOut(BaseModel):
    count: int
    items: list[PeerReviewItemOut] = []


class SubmitPeerReviewRequest(BaseModel):
    ai_analyze_submission_id: int = Field(..., description="被评 AI 作业分析记录 ID")
    score: float = Field(..., ge=1, le=5, description="互评分数 1-5")
    comment: Optional[str] = Field(None, description="互评评语（可选）")


class SubmitPeerReviewResponse(BaseModel):
    success: bool = True
    peer_assessment: PeerAssessmentOut


class TeacherPeerReviewOut(BaseModel):
    """教师端查看的单条互评记录。"""
    id: int
    reviewer_id: int
    reviewer_name: str
    reviewer_student_id: str
    target_user_id: int
    target_name: str
    target_student_id: str
    submission_id: int
    node_name: str
    project_id: int
    project_title: str
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    score: float
    comment: Optional[str] = None
    file_name: Optional[str] = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return serialize_utc_iso(value) or ""


class TeacherPeerReviewListOut(BaseModel):
    count: int
    items: list[TeacherPeerReviewOut] = []
