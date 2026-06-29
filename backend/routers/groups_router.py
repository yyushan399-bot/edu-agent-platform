"""分组管理路由（教师端、管理员端）. """

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import User, Group, GroupMember, Project
from backend.schemas import GroupCreate, GroupImportOut, GroupOut, GroupMemberOut
from backend.dependencies import get_current_user, require_role
from backend.services.group_import import import_groups_from_spreadsheet

router = APIRouter(prefix="/api/groups", tags=["分组管理"])


def _resolve_student(db: Session, student_id: str) -> User:
    """按学号查找学生用户。"""
    sid = (student_id or "").strip()
    if not sid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="学号不能为空")
    user = db.query(User).filter(User.student_id == sid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"学号 {sid} 不存在",
        )
    return user


@router.get("/", response_model=List[GroupOut])
def list_groups(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取所有小组，可按项目筛选。"""
    query = (
        db.query(Group)
        .options(joinedload(Group.members).joinedload(GroupMember.user))
        .order_by(Group.name)
    )
    if project_id is not None:
        query = query.filter(Group.project_id == project_id)
    return query.all()


@router.post("/import-spreadsheet", response_model=GroupImportOut)
async def import_group_spreadsheet(
    project_id: int = Form(...),
    replace_existing: bool = Form(True),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """管理员上传分组表格：第一列为组号，第二列为组长，第三列起为组员。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")

    groups = import_groups_from_spreadsheet(
        db,
        project_id,
        raw,
        file.filename or "groups.csv",
        replace_existing=replace_existing,
    )
    return GroupImportOut(
        created=len(groups),
        message=f"已成功导入 {len(groups)} 个小组",
        groups=groups,
    )


@router.post("/", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    group_in: GroupCreate,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin")),
):
    """创建小组（组长/组员使用学号）。"""
    leader = _resolve_student(db, group_in.leader_student_id)

    member_student_ids: list[str] = []
    for raw in group_in.member_student_ids:
        sid = (raw or "").strip()
        if sid and sid not in member_student_ids:
            member_student_ids.append(sid)

    leader_sid = leader.student_id.strip()
    if leader_sid not in member_student_ids:
        member_student_ids.insert(0, leader_sid)

    member_users: list[User] = []
    for sid in member_student_ids:
        member_users.append(_resolve_student(db, sid))

    if group_in.project_id:
        project = db.query(Project).filter(Project.id == group_in.project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联项目不存在")
        if project.group_size and len(member_users) != project.group_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"该项目要求小组人数为 {project.group_size} 人（含组长），当前为 {len(member_users)} 人",
            )

    group = Group(
        name=group_in.name,
        project_id=group_in.project_id,
        leader_id=leader.id,
    )
    db.add(group)
    db.flush()  # 获取 group.id

    seen_user_ids: set[int] = set()
    for member_user in member_users:
        if member_user.id in seen_user_ids:
            continue
        seen_user_ids.add(member_user.id)
        db.add(GroupMember(group_id=group.id, user_id=member_user.id))

    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin")),
):
    """解散小组。"""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="小组不存在")
    db.delete(group)
    db.commit()


@router.post("/{group_id}/members", response_model=GroupMemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin", "group_leader")),
):
    """向小组添加成员。"""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="小组不存在")

    existing = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户已在组内")

    member = GroupMember(group_id=group_id, user_id=user_id)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin", "group_leader")),
):
    """从小组移除成员。"""
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不在组内")
    db.delete(member)
    db.commit()
