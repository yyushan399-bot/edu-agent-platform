"""认证路由：登录、注册."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, UserRole
from backend.schemas import (
    LoginRequest,
    StudentRegisterRequest,
    StudentRegisterResponse,
    TokenResponse,
    UserCreate,
    UserOut,
)
from backend.auth import hash_password, verify_password, create_access_token
from backend.dependencies import get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录。使用学号+密码+角色验证。"""
    user = db.query(User).filter(
        User.student_id == req.student_id,
        User.role == req.role,
    ).first()

    if user is None:
        by_id = db.query(User).filter(User.student_id == req.student_id).first()
        if by_id is not None:
            role_labels = {
                UserRole.group_leader: "项目组长 (Group Leader)",
                UserRole.group_member: "小组成员 (Student)",
                UserRole.teacher: "授课教师 (Teacher)",
                UserRole.admin: "系统管理员 (Administrator)",
            }
            expected = role_labels.get(by_id.role, by_id.role.value)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"角色选择不正确，学号 {req.student_id} 请使用「{expected}」登录",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="学号或密码错误")

    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="学号或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已禁用")

    token = create_access_token(data={"sub": user.id, "role": user.role.value})
    return TokenResponse(access_token=token, user=user)


@router.post("/register-student", response_model=StudentRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_student(req: StudentRegisterRequest, db: Session = Depends(get_db)):
    """学生自助注册（公开）。角色固定为 group_member，学号由学生自行填写。"""
    student_id = req.student_id.strip()
    if not student_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="学号不能为空")

    existing = db.query(User).filter(User.student_id == student_id).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="学号已存在，请更换后重试")

    user = User(
        student_id=student_id,
        name=req.name.strip(),
        hashed_password=hash_password(req.password),
        role=UserRole.group_member,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return StudentRegisterResponse(
        message="注册成功，请使用学号与「小组成员」身份登录",
        user=user,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """注册新用户（管理员操作或初始导入）。"""
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


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return user
