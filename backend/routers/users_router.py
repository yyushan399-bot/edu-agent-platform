"""用户管理路由（管理员端）. """

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, UserRole
from backend.schemas import UserCreate, UserOut, UserUpdate, PasswordReset
from backend.auth import hash_password
from backend.dependencies import get_current_user, require_role

router = APIRouter(prefix="/api/users", tags=["用户管理"])


@router.get("/", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin", "teacher")),
):
    """获取所有用户列表。"""
    return db.query(User).order_by(User.student_id).all()


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """管理员创建新用户。"""
    existing = db.query(User).filter(User.student_id == user_in.student_id).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="学号已存在")

    user = User(
        student_id=user_in.student_id,
        name=user_in.name,
        hashed_password=hash_password(user_in.password),
        role=user_in.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    update: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """更新用户信息。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if update.name is not None:
        user.name = update.name
    if update.role is not None:
        user.role = update.role
    if update.is_active is not None:
        user.is_active = update.is_active

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """删除用户。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    db.delete(user)
    db.commit()


@router.post("/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: int,
    reset: PasswordReset,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """重置用户密码。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user.hashed_password = hash_password(reset.new_password)
    db.commit()
    db.refresh(user)
    return user
