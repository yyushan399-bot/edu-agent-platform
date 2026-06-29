"""一键初始化测试数据。

用法（在项目根目录执行）::

    python -m backend.seed          # 首次写入；已存在则跳过
    python -m backend.seed --reset  # 清空后重新写入
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from backend.auth import hash_password
from backend.database import Base, SessionLocal, engine
from backend.models import (
    Group,
    GroupMember,
    Project,
    ProjectNode,
    User,
    UserRole,
)

SEED_USERS: list[tuple[str, str, UserRole, str]] = [
    ("A001", "系统管理员", UserRole.admin, "admin123"),
    ("T001", "林老师", UserRole.teacher, "12345"),
    ("2023101", "张华", UserRole.group_leader, "12345"),
    ("2023102", "李雷", UserRole.group_member, "12345"),
    ("2023103", "韩梅梅", UserRole.group_member, "12345"),
]

PROJECT_TITLE = "Lumeebot 小羊 — 智能学伴交互系统"
PROJECT_DESCRIPTION = (
    "设计并实现 Lumeebot 小羊的 10 个真实用户交互场景，"
    "包括：早晨唤醒、挂包出门、情绪安慰、番茄钟专注、"
    "NFC 地铁彩蛋、充电干饭、摇晃互动、深夜陪伴、"
    "敲头攒星星、NFC 社交名片。"
    "评估每个场景的触发机制、反馈方式与情感价值。"
)
PROJECT_NODES: list[tuple[str, datetime | None, int]] = [
    ("场景一：早晨第一眼", datetime(2026, 6, 30, tzinfo=timezone.utc), 0),
    ("场景二：挂包出门", datetime(2026, 7, 5, tzinfo=timezone.utc), 1),
    ("场景三：被骂后的安慰", datetime(2026, 7, 10, tzinfo=timezone.utc), 2),
    ("场景四：番茄钟专注", datetime(2026, 7, 15, tzinfo=timezone.utc), 3),
    ("场景五：地铁 NFC 彩蛋", datetime(2026, 7, 20, tzinfo=timezone.utc), 4),
    ("场景六：充电干饭", datetime(2026, 7, 25, tzinfo=timezone.utc), 5),
    ("场景七：摇晃互动", datetime(2026, 8, 1, tzinfo=timezone.utc), 6),
    ("场景八：深夜陪伴", datetime(2026, 8, 8, tzinfo=timezone.utc), 7),
    ("场景九：敲头攒星星", datetime(2026, 8, 15, tzinfo=timezone.utc), 8),
    ("场景十：NFC 社交名片", datetime(2026, 8, 22, tzinfo=timezone.utc), 9),
]
GROUP_NAME = "第1组"
LEADER_STUDENT_ID = "2023101"
MEMBER_STUDENT_IDS = ("2023101", "2023102", "2023103")


def _reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("已清空并重建数据库表。")


def _ensure_tables() -> None:
    Base.metadata.create_all(bind=engine)


def _is_seeded(db) -> bool:
    return db.query(User).filter(User.student_id == "A001").first() is not None


def _get_or_create_user(
    db,
    *,
    student_id: str,
    name: str,
    role: UserRole,
    password: str,
) -> tuple[User, bool]:
    user = db.query(User).filter(User.student_id == student_id).first()
    if user:
        return user, False
    user = User(
        student_id=student_id,
        name=name,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()
    return user, True


def seed(*, reset: bool = False) -> None:
    if reset:
        _reset_database()
    else:
        _ensure_tables()

    db = SessionLocal()
    try:
        if not reset and _is_seeded(db):
            print("数据库已有种子数据（A001 已存在），跳过。使用 --reset 可清空后重写。")
            return

        created_users = 0
        users_by_sid: dict[str, User] = {}
        for student_id, name, role, password in SEED_USERS:
            user, created = _get_or_create_user(
                db,
                student_id=student_id,
                name=name,
                role=role,
                password=password,
            )
            users_by_sid[student_id] = user
            if created:
                created_users += 1

        teacher = users_by_sid["T001"]

        project = (
            db.query(Project)
            .filter(Project.title == PROJECT_TITLE, Project.created_by == teacher.id)
            .first()
        )
        if project is None:
            project = Project(
                title=PROJECT_TITLE,
                description=PROJECT_DESCRIPTION,
                deadline=datetime(2026, 8, 22, 23, 59, tzinfo=timezone.utc),
                group_size=3,
                created_by=teacher.id,
            )
            db.add(project)
            db.flush()
            print(f"创建项目: {project.title} (id={project.id})")
        else:
            print(f"项目已存在: {project.title} (id={project.id})")
            updated = False
            if project.deadline is None:
                project.deadline = datetime(2026, 8, 22, 23, 59, tzinfo=timezone.utc)
                updated = True
            if project.group_size is None:
                project.group_size = 3
                updated = True
            if updated:
                db.flush()

        existing_node_names = {
            node.name for node in db.query(ProjectNode).filter(ProjectNode.project_id == project.id).all()
        }
        for name, deadline, order in PROJECT_NODES:
            if name in existing_node_names:
                continue
            db.add(
                ProjectNode(
                    project_id=project.id,
                    name=name,
                    deadline=deadline,
                    order=order,
                )
            )
        db.flush()
        node_count = db.query(ProjectNode).filter(ProjectNode.project_id == project.id).count()
        print(f"项目节点: {node_count} 个")

        leader = users_by_sid[LEADER_STUDENT_ID]
        group = db.query(Group).filter(Group.name == GROUP_NAME, Group.project_id == project.id).first()
        if group is None:
            group = Group(
                name=GROUP_NAME,
                project_id=project.id,
                leader_id=leader.id,
            )
            db.add(group)
            db.flush()
            print(f"创建小组: {group.name} (id={group.id})")
        else:
            print(f"小组已存在: {group.name} (id={group.id})")

        existing_member_ids = {
            m.user_id
            for m in db.query(GroupMember).filter(GroupMember.group_id == group.id).all()
        }
        for sid in MEMBER_STUDENT_IDS:
            user = users_by_sid[sid]
            if user.id not in existing_member_ids:
                db.add(GroupMember(group_id=group.id, user_id=user.id))

        db.commit()

        print()
        print("=" * 44)
        print("种子数据写入完成")
        print("=" * 44)
        print(f"  新建用户: {created_users} 个（共 {len(SEED_USERS)} 个账号）")
        print(f"  项目 id={project.id}，小组 id={group.id}")
        print()
        print("测试账号：")
        print("  管理员  A001 / admin123  (admin)")
        print("  教师    T001 / 12345     (teacher)")
        print("  组长    2023101 / 12345  (group_leader) 张华")
        print("  组员    2023102 / 12345  (group_member)  李雷")
        print("  组员    2023103 / 12345  (group_member)  韩梅梅")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化智能学伴系统测试数据")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="清空数据库表后重新写入种子数据",
    )
    args = parser.parse_args(argv)

    try:
        seed(reset=args.reset)
    except Exception as exc:
        print(f"种子数据写入失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
