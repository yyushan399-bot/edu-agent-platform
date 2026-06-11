"""文件路由：按类型自动解析并返回统一文本。"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from input.image_ocr import IMAGE_SUFFIXES, parse_image_text
from input.pdf_parser import parse_pdf_text
from state import UploadedFile

SUFFIX_TO_KIND: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    **{ext: "image" for ext in IMAGE_SUFFIXES},
}

CONTENT_TYPE_BY_KIND: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image": "image/*",
}

KIND_LABEL: dict[str, str] = {
    "pdf": "PDF",
    "docx": "DOCX",
    "image": "图片(OCR)",
}


class FileKind(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    IMAGE = "image"


def detect_file_kind(file_path: str | Path) -> FileKind:
    """根据扩展名识别文件类型。"""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    suffix = path.suffix.lower()
    kind = SUFFIX_TO_KIND.get(suffix)
    if kind is None:
        supported = ", ".join(sorted(SUFFIX_TO_KIND))
        raise ValueError(
            f"不支持的文件类型: {suffix or '(无扩展名)'}，"
            f"支持: {supported}"
        )
    return FileKind(kind)


def parse_file_text(file_path: str | Path) -> str:
    """解析任意支持格式，返回统一纯文本（不含来源头）。"""
    kind = detect_file_kind(file_path)
    path = Path(file_path).resolve()

    if kind == FileKind.PDF:
        return parse_pdf_text(path)
    if kind == FileKind.DOCX:
        from input.docx_parser import parse_docx_text

        return parse_docx_text(path)
    return parse_image_text(path)


def build_uploaded_file(file_path: str | Path) -> UploadedFile:
    """构造 uploaded_files 元数据。"""
    path = Path(file_path).resolve()
    kind = detect_file_kind(path)
    return {
        "name": path.name,
        "path": str(path),
        "content_type": CONTENT_TYPE_BY_KIND[kind.value],
        "modality": kind.value,
        "label": KIND_LABEL[kind.value],
    }


def format_student_input(file_path: str | Path, content: str) -> str:
    """为 LangGraph 包装带来源说明的正文。"""
    path = Path(file_path).resolve()
    kind = detect_file_kind(path)
    label = KIND_LABEL[kind.value]
    return f"【来源文件：{path.name} ({label})】\n\n{content}"


def load_file_for_graph(
    file_path: str | Path,
) -> tuple[str, list[UploadedFile]]:
    """
    解析文件并准备 LangGraph 初始状态字段（委托 multimodal_processor）。
    """
    from input.multimodal_processor import MultimodalProcessor

    return MultimodalProcessor.load_for_graph(file_path)
