"""小组管理服务（SQLAlchemy）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from database.models import Group, GroupMember, User


class GroupNotFoundError(LookupError):
    """小组不存在。"""


class UserNotFoundError(LookupError):
    """用户不存在。"""


class MemberAlreadyExistsError(ValueError):
    """用户已在该小组中。"""


class GroupService:
    """小组 CRUD 与成员管理。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # 1. 创建小组
    # ------------------------------------------------------------------

    def create_group(self, name: str) -> Group:
        """创建学习小组。"""
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("小组名称不能为空")
        group = Group(name=clean_name)
        self.db.add(group)
        self.db.flush()
        return group

    # ------------------------------------------------------------------
    # 2. 给学生分组（加入小组）
    # ------------------------------------------------------------------

    def add_member(self, group_id: int, user_id: int) -> GroupMember:
        """将单个用户加入小组。"""
        self._require_group(group_id)
        self._require_user(user_id)

        existing = self.db.get(GroupMember, {"user_id": user_id, "group_id": group_id})
        if existing is not None:
            raise MemberAlreadyExistsError(
                f"用户 {user_id} 已在小组 {group_id} 中"
            )

        membership = GroupMember(user_id=user_id, group_id=group_id)
        self.db.add(membership)
        self.db.flush()
        return membership

    def add_members(self, group_id: int, user_ids: list[int]) -> list[GroupMember]:
        """批量将用户加入小组；已存在的成员跳过。"""
        if not user_ids:
            return []

        self._require_group(group_id)

        unique_ids = list(dict.fromkeys(user_ids))
        for uid in unique_ids:
            self._require_user(uid)

        stmt = select(GroupMember.user_id).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id.in_(unique_ids),
        )
        already_in = set(self.db.scalars(stmt).all())

        added: list[GroupMember] = []
        for uid in unique_ids:
            if uid in already_in:
                continue
            membership = GroupMember(user_id=uid, group_id=group_id)
            self.db.add(membership)
            added.append(membership)

        if added:
            self.db.flush()
        return added

    def remove_member(self, group_id: int, user_id: int) -> None:
        """将用户移出小组。"""
        membership = self.db.get(GroupMember, {"user_id": user_id, "group_id": group_id})
        if membership is None:
            raise LookupError(f"用户 {user_id} 不在小组 {group_id} 中")
        self.db.delete(membership)
        self.db.flush()

    # ------------------------------------------------------------------
    # 3. 获取用户所在小组
    # ------------------------------------------------------------------

    def get_groups_for_user(self, user_id: int) -> list[Group]:
        """返回用户加入的所有小组。"""
        self._require_user(user_id)
        stmt = (
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.id)
        )
        return list(self.db.scalars(stmt).all())

    def get_peer_member_ids(self, user_id: int) -> list[int]:
        """返回同组其他成员 user_id（不含本人）。"""
        self._require_user(user_id)
        peer_ids: set[int] = set()
        for group in self.get_groups_for_user(user_id):
            for member in self.get_group_members(group.id):
                if member.id != user_id:
                    peer_ids.add(member.id)
        return sorted(peer_ids)

    # ------------------------------------------------------------------
    # 4. 获取组内成员
    # ------------------------------------------------------------------

    def get_group_members(self, group_id: int) -> list[User]:
        """返回小组内全部成员（User 对象）。"""
        self._require_group(group_id)
        stmt = (
            select(User)
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == group_id)
            .order_by(User.id)
        )
        return list(self.db.scalars(stmt).all())

    def get_group_with_members(self, group_id: int) -> Group:
        """返回小组及其成员关系（预加载 members.user）。"""
        stmt = (
            select(Group)
            .where(Group.id == group_id)
            .options(joinedload(Group.members).joinedload(GroupMember.user))
        )
        group = self.db.scalars(stmt).unique().one_or_none()
        if group is None:
            raise GroupNotFoundError(f"小组不存在: group_id={group_id}")
        return group

    def get_group(self, group_id: int) -> Group:
        """按 ID 获取小组。"""
        return self._require_group(group_id)

    # ------------------------------------------------------------------
    # 序列化辅助
    # ------------------------------------------------------------------

    @staticmethod
    def group_to_dict(group: Group, *, member_count: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": group.id, "name": group.name}
        if member_count is not None:
            payload["member_count"] = member_count
        return payload

    @staticmethod
    def user_to_dict(user: User) -> dict[str, Any]:
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        }

    @staticmethod
    def member_to_dict(user: User, group_id: int) -> dict[str, Any]:
        data = GroupService.user_to_dict(user)
        data["group_id"] = group_id
        return data

    # ------------------------------------------------------------------
    # 内部校验
    # ------------------------------------------------------------------

    def _require_group(self, group_id: int) -> Group:
        group = self.db.get(Group, group_id)
        if group is None:
            raise GroupNotFoundError(f"小组不存在: group_id={group_id}")
        return group

    def _require_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"用户不存在: user_id={user_id}")
        return user


__all__ = [
    "GroupNotFoundError",
    "GroupService",
    "MemberAlreadyExistsError",
    "UserNotFoundError",
]
