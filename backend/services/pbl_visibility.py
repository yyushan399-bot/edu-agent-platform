"""小组 PBL 评分对组长的可见性控制（教师发布的项目截止后 30 天）。"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.datetime_utils import ensure_utc
from backend.models import Group, GroupMember, Project, User, UserRole

LEADER_SCORE_GRACE_DAYS = int(os.getenv("PBL_LEADER_SCORE_GRACE_DAYS", "30"))

_SCORE_KEYS = (
    "creativity",
    "critical",
    "problemsolving",
    "dimension_summary",
    "primary_indicator_summary",
    "dimension_mean_score",
    "final_score",
    "final_comment",
    "final_feedback",
    "strengths",
    "weaknesses",
    "revision_suggestions",
    "internal_audit",
)

SCORES_HIDDEN_MESSAGE = (
    f"小组三维度得分与雷达图将在项目截止 {LEADER_SCORE_GRACE_DAYS} 天后开放查看。"
)


def _ensure_utc(dt: datetime) -> datetime:
    return ensure_utc(dt) or dt


def get_project_deadline(db: Session, project_id: int | None) -> datetime | None:
    """仅使用教师在「项目发布」中设置的项目截止时间。"""
    if not project_id:
        return None
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.deadline:
        return None
    return _ensure_utc(project.deadline)


def resolve_user_group(
    db: Session, user: User, project_id: int | None = None
) -> Group | None:
    """解析用户所在小组；若提供 project_id 则限定为该项目下的小组。"""
    leader_q = db.query(Group).filter(Group.leader_id == user.id)
    if project_id is not None:
        leader_q = leader_q.filter(Group.project_id == project_id)
    group = leader_q.first()
    if group:
        return group

    member_rows = (
        db.query(GroupMember)
        .filter(GroupMember.user_id == user.id)
        .all()
    )
    for member in member_rows:
        q = db.query(Group).filter(Group.id == member.group_id)
        if project_id is not None:
            q = q.filter(Group.project_id == project_id)
        group = q.first()
        if group:
            return group
    return None


def leader_scores_visible_at(
    db: Session, user: User, project_id: int | None = None
) -> datetime | None:
    if user.role in (UserRole.teacher, UserRole.admin):
        return None
    group = resolve_user_group(db, user, project_id)
    if not group:
        return None
    deadline = get_project_deadline(db, group.project_id)
    if deadline is None:
        return None
    return deadline + timedelta(days=LEADER_SCORE_GRACE_DAYS)


def can_leader_view_scores(
    db: Session, user: User, project_id: int | None = None
) -> tuple[bool, datetime | None]:
    if user.role in (UserRole.teacher, UserRole.admin):
        return True, None
    if user.role != UserRole.group_leader:
        return True, None
    visible_at = leader_scores_visible_at(db, user, project_id)
    if visible_at is None:
        return False, None
    now = datetime.now(timezone.utc)
    return now >= visible_at, visible_at


def are_leader_scores_hidden_for_group(db: Session, group_id: int | None) -> bool:
    """组长是否尚未到可查看三维度得分的时间（项目截止后 grace 天内）。"""
    if not group_id:
        return False
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group or not group.project_id:
        return False
    deadline = get_project_deadline(db, group.project_id)
    if deadline is None:
        return False
    visible_at = deadline + timedelta(days=LEADER_SCORE_GRACE_DAYS)
    return datetime.now(timezone.utc) < visible_at


def mask_leader_scores(payload: dict, *, visible: bool, visible_at: datetime | None) -> dict:
    """组长在可见时间前隐藏三维度、12 维明细与文字总评。"""
    if visible:
        payload["scores_visible"] = True
        payload.pop("scores_hidden_reason", None)
        payload.pop("scores_visible_at", None)
        return payload

    masked = dict(payload)
    for key in _SCORE_KEYS:
        masked.pop(key, None)
    masked.pop("text_preview", None)
    masked["scores_visible"] = False
    masked["scores_hidden_reason"] = SCORES_HIDDEN_MESSAGE
    return masked
