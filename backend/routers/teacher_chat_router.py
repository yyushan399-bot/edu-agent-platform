"""教师端：查看学生 AI 聊天记录。"""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.dependencies import require_role
from backend.models import User
from backend.services.chat_history import get_student_chat_messages

router = APIRouter(prefix="/api/teacher", tags=["教师端"])


@router.get("/students/{student_id}/chat-messages")
def student_chat_messages(
    student_id: str,
    limit: int = 300,
    _: User = Depends(require_role("teacher", "admin")),
):
    """按学号读取学生与 AI 智能体的历史对话（读取 memory/sessions）。"""
    try:
        data = get_student_chat_messages(student_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取聊天记录失败: {exc}",
        ) from exc

    return {"success": True, **data}
