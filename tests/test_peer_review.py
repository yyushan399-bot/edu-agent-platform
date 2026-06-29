"""同伴互评单元测试（AI 作业分析模块）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import (
    AiAnalyzeSubmission,
    Group,
    GroupMember,
    Project,
    ProjectNode,
    Submission,
    User,
    UserRole,
)
from backend.services.peer_review_service import (
    NotGroupPeerError,
    PeerReviewAlreadyExistsError,
    SelfReviewNotAllowedError,
    list_peer_review_items,
    list_teacher_peer_reviews,
    submit_peer_review,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_group_project(db):
    leader = User(
        student_id="L001",
        name="组长",
        hashed_password="x",
        role=UserRole.group_leader,
    )
    member = User(
        student_id="M001",
        name="组员",
        hashed_password="x",
        role=UserRole.group_member,
    )
    outsider = User(
        student_id="O001",
        name="外人",
        hashed_password="x",
        role=UserRole.group_member,
    )
    db.add_all([leader, member, outsider])
    db.flush()

    project = Project(title="测试项目", created_by=leader.id)
    db.add(project)
    db.flush()

    node = ProjectNode(project_id=project.id, name="节点一", order=1)
    db.add(node)
    db.flush()

    group = Group(name="第1组", project_id=project.id, leader_id=leader.id)
    db.add(group)
    db.flush()
    db.add_all(
        [
            GroupMember(group_id=group.id, user_id=leader.id),
            GroupMember(group_id=group.id, user_id=member.id),
        ]
    )

    submission = Submission(
        user_id=leader.id,
        node_id=node.id,
        file_path="uploads/submissions/report.pdf",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return leader, member, outsider, project, submission


def _add_ai_analyze(db, user: User, project: Project, **kwargs) -> AiAnalyzeSubmission:
    record = AiAnalyzeSubmission(
        user_id=user.id,
        student_id=user.student_id,
        project_id=project.id,
        filename=kwargs.get("filename", "homework.pdf"),
        file_path=kwargs.get("file_path", "uploads/homework.pdf"),
        self_score=kwargs.get("self_score", 3.5),
        self_comment=kwargs.get("self_comment", "我的自评说明"),
        routes=kwargs.get("routes", ["theory"]),
        ai_total_score=kwargs.get("ai_total_score", 4.0),
        feedback_preview=kwargs.get("feedback_preview", "AI 反馈摘要"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def test_list_peer_review_items_excludes_self(db):
    leader, member, _, project, _ = _seed_group_project(db)
    _add_ai_analyze(db, leader, project)

    items = list_peer_review_items(db, reviewer=member, project_id=project.id)
    assert len(items) == 1
    assert items[0]["student_name"] == "组长"
    assert items[0]["item_type"] == "ai_analyze"

    self_items = list_peer_review_items(db, reviewer=leader, project_id=project.id)
    assert self_items == []


def test_submit_peer_review_success(db):
    leader, member, _, project, _ = _seed_group_project(db)
    ai_row = _add_ai_analyze(db, leader, project)

    record = submit_peer_review(
        db,
        reviewer=member,
        ai_analyze_submission_id=ai_row.id,
        score=4.5,
        comment="写得不错",
    )
    db.commit()
    assert record.score == 4.5

    items = list_peer_review_items(db, reviewer=member, project_id=project.id)
    assert items[0]["my_review"]["score"] == 4.5


def test_submit_peer_review_rejects_self(db):
    leader, _, _, project, _ = _seed_group_project(db)
    ai_row = _add_ai_analyze(db, leader, project)
    with pytest.raises(SelfReviewNotAllowedError):
        submit_peer_review(db, reviewer=leader, ai_analyze_submission_id=ai_row.id, score=3)


def test_submit_peer_review_rejects_duplicate(db):
    leader, member, _, project, _ = _seed_group_project(db)
    ai_row = _add_ai_analyze(db, leader, project)
    submit_peer_review(db, reviewer=member, ai_analyze_submission_id=ai_row.id, score=3)
    db.commit()
    with pytest.raises(PeerReviewAlreadyExistsError):
        submit_peer_review(db, reviewer=member, ai_analyze_submission_id=ai_row.id, score=5)


def test_submit_peer_review_rejects_outsider(db):
    leader, _, outsider, project, _ = _seed_group_project(db)
    ai_row = _add_ai_analyze(db, leader, project)
    with pytest.raises(NotGroupPeerError):
        submit_peer_review(db, reviewer=outsider, ai_analyze_submission_id=ai_row.id, score=3)


def test_list_teacher_peer_reviews(db):
    leader, member, _, project, _ = _seed_group_project(db)
    ai_row = _add_ai_analyze(db, leader, project)
    submit_peer_review(
        db, reviewer=member, ai_analyze_submission_id=ai_row.id, score=4, comment="不错"
    )
    db.commit()

    items = list_teacher_peer_reviews(db, project_id=project.id)
    assert len(items) == 1
    assert items[0]["reviewer_name"] == "组员"
    assert items[0]["target_name"] == "组长"
    assert "AI 作业分析" in items[0]["node_name"]
