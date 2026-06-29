"""同伴互评业务（仅 AI 作业分析 /analyze 模块）。"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session, joinedload

from backend.models import AiAnalyzeSubmission, Group, PeerAssessment, Project, User

AI_ANALYZE_LABEL = "AI 作业分析"


class PeerReviewError(ValueError):
    pass


class SelfReviewNotAllowedError(PeerReviewError):
    pass


class PeerReviewAlreadyExistsError(PeerReviewError):
    pass


class SubmissionNotFoundError(LookupError):
    pass


class NotGroupPeerError(PeerReviewError):
    pass


def _clamp_score(value: float) -> float:
    return float(max(1.0, min(5.0, round(float(value), 2))))


def _group_member_ids(group: Group) -> set[int]:
    ids = {m.user_id for m in group.members}
    if group.leader_id is not None:
        ids.add(group.leader_id)
    return ids


def get_user_group_in_project(db: Session, user_id: int, project_id: int) -> Group | None:
    groups = (
        db.query(Group)
        .options(joinedload(Group.members))
        .filter(Group.project_id == project_id)
        .all()
    )
    for group in groups:
        if user_id in _group_member_ids(group):
            return group
    return None


def users_share_project_group(
    db: Session,
    user_a_id: int,
    user_b_id: int,
    project_id: int,
) -> bool:
    group = get_user_group_in_project(db, user_a_id, project_id)
    if group is None:
        return False
    return user_b_id in _group_member_ids(group)


def _file_name_from_path(path: str | None) -> str | None:
    if not path:
        return None
    return os.path.basename(path.replace("\\", "/"))


def _routes_label(routes: list | None) -> str:
    if not routes:
        return AI_ANALYZE_LABEL
    labels = {"theory": "理论", "literature": "文献", "practice": "实践", "data": "数据"}
    names = [labels.get(str(r), str(r)) for r in routes]
    return f"{AI_ANALYZE_LABEL} · " + "、".join(names)


def _peer_assessment_to_dict(record: PeerAssessment) -> dict[str, Any]:
    return {
        "id": record.id,
        "reviewer_id": record.reviewer_id,
        "target_user_id": record.target_user_id,
        "ai_analyze_submission_id": record.ai_analyze_submission_id,
        "score": record.score,
        "comment": record.comment,
        "created_at": record.created_at,
    }


def _build_ai_analyze_item(
    record: AiAnalyzeSubmission,
    owner: User | None,
    my_review: PeerAssessment | None,
) -> dict[str, Any]:
    file_name = record.filename or _file_name_from_path(record.file_path)
    return {
        "item_type": "ai_analyze",
        "ai_analyze_submission_id": record.id,
        "target_user_id": record.user_id,
        "student_name": owner.name if owner else "未知",
        "node_name": _routes_label(record.routes if isinstance(record.routes, list) else None),
        "has_file": bool(record.file_path),
        "file_name": file_name,
        "file_download_url": (
            f"/api/ai-analyze-submissions/{record.id}/file" if record.file_path else None
        ),
        "text_preview": (record.self_comment or record.feedback_preview or "")[:120] or None,
        "self_score": record.self_score,
        "ai_total_score": record.ai_total_score,
        "submit_time": record.created_at,
        "my_review": _peer_assessment_to_dict(my_review) if my_review else None,
    }


def list_peer_review_items(
    db: Session,
    *,
    reviewer: User,
    project_id: int,
) -> list[dict[str, Any]]:
    """列出同组其他成员在本项目下的 AI 作业分析提交。"""
    group = get_user_group_in_project(db, reviewer.id, project_id)
    if group is None:
        return []

    peer_ids = _group_member_ids(group) - {reviewer.id}
    if not peer_ids:
        return []

    records = (
        db.query(AiAnalyzeSubmission)
        .options(joinedload(AiAnalyzeSubmission.user))
        .filter(
            AiAnalyzeSubmission.project_id == project_id,
            AiAnalyzeSubmission.user_id.in_(peer_ids),
        )
        .order_by(AiAnalyzeSubmission.created_at.desc())
        .all()
    )
    if not records:
        return []

    record_ids = [r.id for r in records]
    my_reviews = {
        r.ai_analyze_submission_id: r
        for r in db.query(PeerAssessment)
        .filter(
            PeerAssessment.reviewer_id == reviewer.id,
            PeerAssessment.ai_analyze_submission_id.in_(record_ids),
        )
        .all()
        if r.ai_analyze_submission_id is not None
    }

    return [
        _build_ai_analyze_item(r, r.user, my_reviews.get(r.id))
        for r in records
    ]


def submit_peer_review(
    db: Session,
    *,
    reviewer: User,
    score: float,
    comment: str | None = None,
    ai_analyze_submission_id: int | None = None,
    **_legacy: Any,
) -> PeerAssessment:
    if ai_analyze_submission_id is None:
        raise SubmissionNotFoundError("请指定 ai_analyze_submission_id")

    target = (
        db.query(AiAnalyzeSubmission)
        .filter(AiAnalyzeSubmission.id == ai_analyze_submission_id)
        .first()
    )
    if target is None:
        raise SubmissionNotFoundError(f"作业分析记录不存在: id={ai_analyze_submission_id}")

    if reviewer.id == target.user_id:
        raise SelfReviewNotAllowedError("不允许评价自己的作业分析")

    if not users_share_project_group(db, reviewer.id, target.user_id, target.project_id):
        raise NotGroupPeerError("只能评价同组成员的 AI 作业分析")

    existing = (
        db.query(PeerAssessment)
        .filter_by(
            reviewer_id=reviewer.id,
            ai_analyze_submission_id=ai_analyze_submission_id,
        )
        .one_or_none()
    )
    if existing is not None:
        raise PeerReviewAlreadyExistsError("您已评价过该作业分析，不可重复提交")

    record = PeerAssessment(
        reviewer_id=reviewer.id,
        target_user_id=target.user_id,
        ai_analyze_submission_id=ai_analyze_submission_id,
        score=_clamp_score(score),
        comment=(comment or "").strip() or None,
    )
    db.add(record)
    db.flush()
    return record


def list_teacher_peer_reviews(
    db: Session,
    *,
    project_id: int | None = None,
    group_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    records = (
        db.query(PeerAssessment)
        .options(joinedload(PeerAssessment.ai_analyze_submission))
        .filter(PeerAssessment.ai_analyze_submission_id.isnot(None))
        .order_by(PeerAssessment.created_at.desc())
        .all()
    )
    if not records:
        return []

    user_ids = {r.reviewer_id for r in records} | {r.target_user_id for r in records}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    project_ids = {
        r.ai_analyze_submission.project_id
        for r in records
        if r.ai_analyze_submission
    }
    projects = {
        p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids)).all()
    }
    groups_cache: dict[int, list[Group]] = {}

    items: list[dict[str, Any]] = []
    for record in records:
        target_row = record.ai_analyze_submission
        if target_row is None:
            continue
        pid = target_row.project_id
        if project_id is not None and pid != project_id:
            continue

        group = _group_for_user_in_project(db, record.target_user_id, pid, groups_cache)
        if group_id is not None and (group is None or group.id != group_id):
            continue

        reviewer = users.get(record.reviewer_id)
        target = users.get(record.target_user_id)
        project = projects.get(pid)
        file_name = target_row.filename or _file_name_from_path(target_row.file_path)

        items.append(
            {
                "id": record.id,
                "reviewer_id": record.reviewer_id,
                "reviewer_name": reviewer.name if reviewer else "未知",
                "reviewer_student_id": reviewer.student_id if reviewer else "",
                "target_user_id": record.target_user_id,
                "target_name": target.name if target else "未知",
                "target_student_id": target.student_id if target else "",
                "submission_id": target_row.id,
                "node_name": _routes_label(
                    target_row.routes if isinstance(target_row.routes, list) else None
                ),
                "project_id": pid,
                "project_title": project.title if project else f"项目#{pid}",
                "group_id": group.id if group else None,
                "group_name": group.name if group else None,
                "score": record.score,
                "comment": record.comment,
                "file_name": file_name,
                "created_at": record.created_at,
            }
        )

    if limit is not None and limit > 0:
        items = items[:limit]
    return items


def _group_for_user_in_project(
    db: Session,
    user_id: int,
    project_id: int,
    groups_cache: dict[int, list[Group]] | None = None,
) -> Group | None:
    if groups_cache is not None and project_id in groups_cache:
        groups = groups_cache[project_id]
    else:
        groups = (
            db.query(Group)
            .options(joinedload(Group.members))
            .filter(Group.project_id == project_id)
            .all()
        )
        if groups_cache is not None:
            groups_cache[project_id] = groups
    for group in groups:
        if user_id in _group_member_ids(group):
            return group
    return None


def can_access_ai_analyze_file(
    db: Session,
    *,
    viewer: User,
    record: AiAnalyzeSubmission,
) -> bool:
    role = viewer.role.value if hasattr(viewer.role, "value") else str(viewer.role)
    if role in ("teacher", "admin"):
        return True
    if viewer.id == record.user_id:
        return True
    return users_share_project_group(db, viewer.id, record.user_id, record.project_id)


def can_access_group_pbl_file(
    db: Session,
    *,
    viewer: User,
    record: Any,
) -> bool:
    """小组 PBL 报告下载权限（本人 / 同组 / 教师 / 管理员）。"""
    from backend.models import GroupPblEvaluation

    if not isinstance(record, GroupPblEvaluation):
        return False
    role = viewer.role.value if hasattr(viewer.role, "value") else str(viewer.role)
    if role in ("teacher", "admin"):
        return True
    if viewer.id == record.user_id:
        return True
    if record.group_id is None:
        return False
    return users_share_group(db, viewer.id, record.user_id, record.group_id)


def can_access_submission_file(
    db: Session,
    *,
    viewer: User,
    submission: Any,
) -> bool:
    """保留：节点提交文件下载（非互评模块）。"""
    from backend.models import Submission as SubmissionModel

    if not isinstance(submission, SubmissionModel):
        return False
    role = viewer.role.value if hasattr(viewer.role, "value") else str(viewer.role)
    if role in ("teacher", "admin"):
        return True
    if viewer.id == submission.user_id:
        return True
    from backend.models import ProjectNode

    node = submission.node or db.query(ProjectNode).filter(ProjectNode.id == submission.node_id).first()
    if node is None:
        return False
    return users_share_project_group(db, viewer.id, submission.user_id, node.project_id)
