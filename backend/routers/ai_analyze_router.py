"""AI 作业分析提交：同组可见与文件下载。"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models import AiAnalyzeSubmission, User
from backend.services.peer_review_service import can_access_ai_analyze_file

router = APIRouter(prefix="/api/ai-analyze-submissions", tags=["AI作业分析"])


@router.get("/{submission_id}/file")
def download_ai_analyze_file(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载 AI 作业分析上传的原文件（本人 / 同组 / 教师 / 管理员）。"""
    record = db.query(AiAnalyzeSubmission).filter(AiAnalyzeSubmission.id == submission_id).first()
    if not record or not record.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    if not can_access_ai_analyze_file(db, viewer=user, record=record):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该文件")

    path = Path(record.file_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件已丢失")

    filename = record.filename or path.name
    return FileResponse(path, filename=filename)
