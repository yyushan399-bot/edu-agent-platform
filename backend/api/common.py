"""API 公共工具：文件上传与多模态解析。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_SUFFIXES = {".pdf", ".docx", ".png", ".jpg", ".jpeg"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "image/png",
    "image/jpeg",
    "image/jpg",
}


def validate_upload(file: UploadFile) -> str:
    """校验并返回小写扩展名。"""
    name = file.filename or ""
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的文件类型: {suffix or '(无扩展名)'}，"
                f"允许: {', '.join(sorted(ALLOWED_SUFFIXES))}"
            ),
        )
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的 Content-Type: {content_type}",
            )
    return suffix


async def save_upload_file(file: UploadFile) -> dict[str, str]:
    """保存到 backend/uploads/ 并返回元数据。"""
    suffix = validate_upload(file)
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    dest = UPLOAD_DIR / safe_name

    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "name": file.filename or safe_name,
        "path": str(dest.resolve()),
        "content_type": file.content_type or "",
        "stored_name": safe_name,
    }


def build_student_input_from_files(
    saved_paths: list[str],
    *,
    extra_text: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """使用 multimodal_processor 解析上传文件。"""
    from input.multimodal_processor import MultimodalProcessor

    if not saved_paths and not (extra_text or "").strip():
        raise HTTPException(status_code=400, detail="请上传文件或提供 text 字段")

    if saved_paths:
        result = MultimodalProcessor.process(
            saved_paths,
            extra_text=extra_text,
        )
        uploaded = [
            {
                "name": meta["name"],
                "path": meta["path"],
                "content_type": meta.get("content_type", ""),
                "modality": meta.get("modality", ""),
                "label": meta.get("label", ""),
            }
            for meta in result.uploaded_files
        ]
        return result.to_student_input(), uploaded

    result = MultimodalProcessor.process_text(extra_text or "")
    return result.to_student_input(), []


def clamp_score(value: float, *, min_score: float = 0.0, max_score: float = 100.0) -> float:
    """将分数限制在指定区间。"""
    return float(max(min_score, min(max_score, round(float(value), 2))))


def build_public_file_url(stored_name: str) -> str:
    """生成可对外访问的上传文件 URL。"""
    name = (stored_name or "").strip().lstrip("/")
    if not name:
        return ""
    return f"/uploads/{name}"


def first_file_url(saved_meta: list[dict[str, str]]) -> str | None:
    """从上传元数据取首个文件的公开 URL。"""
    for item in saved_meta:
        stored = (item.get("stored_name") or "").strip()
        if stored:
            return build_public_file_url(stored)
    return None


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "ALLOWED_SUFFIXES",
    "UPLOAD_DIR",
    "build_public_file_url",
    "build_student_input_from_files",
    "clamp_score",
    "first_file_url",
    "save_upload_file",
    "validate_upload",
]
