"""FastAPI 依赖项（认证、数据库等）. """

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.auth import decode_access_token
from backend.models import User

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """从 JWT token 中解析当前用户."""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌")

    user_id: int | None = int(payload.get("sub", 0)) if payload.get("sub") else None
    role: str | None = payload.get("role")
    if user_id is None or role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌数据不完整")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    db: Session = Depends(get_db),
) -> User | None:
    """可选 JWT：AI 路由在未登录时仍可调用。"""
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    user_id: int | None = int(payload.get("sub", 0)) if payload.get("sub") else None
    if user_id is None:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        return None
    return user


def _user_role_value(user: User) -> str:
    role = user.role
    return role.value if hasattr(role, "value") else str(role)


def require_role(*roles: str):
    """角色权限依赖。用法: `require_role("teacher", "admin")`."""
    allowed = set(roles)

    def _check(user: User = Depends(get_current_user)) -> User:
        if _user_role_value(user) not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return _check
