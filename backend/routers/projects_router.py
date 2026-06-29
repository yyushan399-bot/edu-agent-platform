"""项目管理路由（教师端）. """

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import User, Project, ProjectNode
from backend.schemas import ProjectCreate, ProjectOut, ProjectNodeOut
from backend.dependencies import get_current_user, require_role

import os
import shutil

UPLOAD_DIR = "uploads/guides"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/api/projects", tags=["项目管理"])


@router.get("/", response_model=List[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取所有项目。"""
    projects = (
        db.query(Project)
        .options(joinedload(Project.nodes))
        .order_by(Project.created_at.desc())
        .all()
    )
    return projects


@router.post("/", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin")),
):
    """创建新项目。"""
    if project_in.deadline is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请设置项目截止时间")
    if project_in.group_size is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请设置项目小组人数")

    project = Project(
        title=project_in.title,
        description=project_in.description,
        deadline=project_in.deadline,
        group_size=project_in.group_size,
        created_by=teacher.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取项目详情。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    update: ProjectCreate,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin")),
):
    """更新项目信息。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    project.title = update.title
    project.description = update.description
    project.deadline = update.deadline
    if update.group_size is not None:
        project.group_size = update.group_size
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin")),
):
    """删除项目。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    db.delete(project)
    db.commit()


# ── 项目节点管理 ────────────────────────────────────────

@router.post("/{project_id}/nodes", response_model=ProjectNodeOut, status_code=status.HTTP_201_CREATED)
def create_node(
    project_id: int,
    name: str,
    deadline: str = None,
    order: int = 0,
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin")),
):
    """为项目添加节点。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    from datetime import datetime
    from backend.datetime_utils import ensure_utc

    parsed_deadline = None
    if deadline:
        parsed_deadline = ensure_utc(datetime.fromisoformat(deadline.replace("Z", "+00:00")))

    node = ProjectNode(
        project_id=project_id,
        name=name,
        deadline=parsed_deadline,
        order=order,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


# ── 上传指南文件 ────────────────────────────────────────

@router.post("/{project_id}/upload-guide")
def upload_guide(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    teacher: User = Depends(require_role("teacher", "admin")),
):
    """上传项目指南附件。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    file_path = os.path.join(UPLOAD_DIR, f"project_{project_id}_{file.filename}")
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    project.guide_file_path = file_path
    db.commit()
    return {"file_path": file_path, "filename": file.filename}
