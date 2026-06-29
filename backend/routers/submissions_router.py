"""提交管理路由（组员、组长端）. """

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import User, Submission, SubmissionStatus, ProjectNode, GroupMember
from backend.schemas import SubmissionOut
from backend.dependencies import get_current_user, require_role
from backend.services.peer_review_service import can_access_submission_file

import os
import shutil

UPLOAD_DIR = "uploads/submissions"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/api/submissions", tags=["提交管理"])


@router.get("/", response_model=List[SubmissionOut])
def list_my_submissions(
    node_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取当前用户的提交记录。"""
    query = (
        db.query(Submission)
        .options(joinedload(Submission.user), joinedload(Submission.node))
        .filter(Submission.user_id == user.id)
    )
    if node_id:
        query = query.filter(Submission.node_id == node_id)
    return query.order_by(Submission.submitted_at.desc()).all()


@router.get("/group/{group_id}", response_model=List[SubmissionOut])
def list_group_submissions(
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("teacher", "admin", "group_leader")),
):
    """获取某小组所有成员的提交（教师/组长用）。"""
    member_ids = [
        m.user_id for m in db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    ]
    return (
        db.query(Submission)
        .options(joinedload(Submission.user), joinedload(Submission.node))
        .filter(Submission.user_id.in_(member_ids))
        .order_by(Submission.submitted_at.desc())
        .all()
    )


@router.post("/", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
def create_submission(
    node_id: int = Form(...),
    text_content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交成果（文件/文本二选一或兼具）。"""
    node = db.query(ProjectNode).filter(ProjectNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在")

    file_path = None
    if file:
        file_path = os.path.join(UPLOAD_DIR, f"user_{user.id}_node_{node_id}_{file.filename}")
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

    submission = Submission(
        user_id=user.id,
        node_id=node_id,
        file_path=file_path,
        text_content=text_content,
        status=SubmissionStatus.submitted,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/{submission_id}/file")
def download_submission_file(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载提交文件（本人 / 同组成员 / 教师 / 管理员）。"""
    submission = (
        db.query(Submission)
        .options(joinedload(Submission.node))
        .filter(Submission.id == submission_id)
        .first()
    )
    if not submission or not submission.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    if not can_access_submission_file(db, viewer=user, submission=submission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该文件")

    if not os.path.exists(submission.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件已丢失")

    filename = os.path.basename(submission.file_path.replace("\\", "/"))
    return FileResponse(submission.file_path, filename=filename)


@router.delete("/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除自己的提交。"""
    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.user_id == user.id,
    ).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提交不存在或无权删除")

    # 清理文件
    if submission.file_path and os.path.exists(submission.file_path):
        os.remove(submission.file_path)

    db.delete(submission)
    db.commit()
