"""多模态输入处理器：统一文本、文档、图片、表格等为 LangGraph 可用正文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from input.docx_parser import DocxBlock, parse_docx_blocks
from input.file_router import (
    KIND_LABEL,
    SUFFIX_TO_KIND,
    FileKind,
    build_uploaded_file,
    detect_file_kind,
)
from input.image_ocr import IMAGE_SUFFIXES, parse_image_text
from input.pdf_parser import parse_pdf_documents
from state import UploadedFile

SECTION_TEXT = "文字"
SECTION_DOCUMENT = "文档"
SECTION_TABLE = "表格"
SECTION_IMAGE = "图片"


class Modality(str, Enum):
    """内容模态类型。"""

    TEXT = "text"
    DOCUMENT = "document"
    TABLE = "table"
    IMAGE = "image"


@dataclass
class ContentBlock:
    """单段可消费内容。"""

    modality: Modality
    content: str
    source: str = ""
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def format_section(self) -> str:
        """格式化为带标题的文本段。"""
        title = self.label or self.modality.value
        header = f"=== [{title}]"
        if self.source:
            header += f" {self.source}"
        header += " ==="
        return f"{header}\n{self.content.strip()}"


@dataclass
class MultimodalResult:
    """多模态处理结果。"""

    blocks: list[ContentBlock]
    uploaded_files: list[UploadedFile]
    source_summary: str = ""

    @property
    def modalities(self) -> list[str]:
        """去重后的模态列表。"""
        order = [Modality.TEXT, Modality.DOCUMENT, Modality.TABLE, Modality.IMAGE]
        present = {block.modality for block in self.blocks}
        return [m.value for m in order if m in present]

    @property
    def unified_text(self) -> str:
        """合并为单一纯文本（不含最外层来源头）。"""
        parts = [block.format_section() for block in self.blocks if block.content.strip()]
        return "\n\n".join(parts)

    def to_student_input(self, *, title: str | None = None) -> str:
        """生成写入 state['student_input'] 的正文。"""
        body = self.unified_text.strip()
        if not body:
            raise ValueError("多模态输入未解析到有效文本")

        if title:
            header = f"【多模态输入：{title}】"
        elif self.source_summary:
            header = f"【多模态输入：{self.source_summary}】"
        else:
            header = f"【多模态输入：{', '.join(self.modalities)}】"
        return f"{header}\n\n{body}"


class MultimodalProcessor:
    """
    统一处理多种输入源。

    - 纯文本
    - 文档：PDF / DOCX（含表格块）
    - 图片：PNG / JPG / JPEG（PaddleOCR）
    - 多文件合并
    """

    @staticmethod
    def process_text(
        text: str,
        *,
        source: str = "用户输入",
    ) -> MultimodalResult:
        content = (text or "").strip()
        if not content:
            raise ValueError("文本内容不能为空")
        return MultimodalResult(
            blocks=[
                ContentBlock(
                    modality=Modality.TEXT,
                    content=content,
                    source=source,
                    label=SECTION_TEXT,
                )
            ],
            uploaded_files=[],
            source_summary=source,
        )

    @staticmethod
    def _blocks_from_pdf(path: Path) -> list[ContentBlock]:
        docs = parse_pdf_documents(path)
        blocks: list[ContentBlock] = []
        for doc in docs:
            text = (doc.page_content or "").strip()
            if not text:
                continue
            page = doc.metadata.get("page")
            page_no = int(page) + 1 if page is not None else len(blocks) + 1
            blocks.append(
                ContentBlock(
                    modality=Modality.DOCUMENT,
                    content=text,
                    source=path.name,
                    label=f"{SECTION_DOCUMENT}-第{page_no}页",
                    metadata={"page": page_no},
                )
            )
        return blocks

    @staticmethod
    def _blocks_from_docx(path: Path) -> list[ContentBlock]:
        docx_blocks: list[DocxBlock] = parse_docx_blocks(path)
        blocks: list[ContentBlock] = []
        table_no = 0
        for item in docx_blocks:
            if item["type"] == "table":
                table_no += 1
                blocks.append(
                    ContentBlock(
                        modality=Modality.TABLE,
                        content=item["content"],
                        source=path.name,
                        label=f"{SECTION_TABLE} #{table_no}",
                        metadata={"block_index": item["index"]},
                    )
                )
            else:
                blocks.append(
                    ContentBlock(
                        modality=Modality.TEXT,
                        content=item["content"],
                        source=path.name,
                        label=SECTION_TEXT,
                        metadata={"block_index": item["index"]},
                    )
                )
        return blocks

    @staticmethod
    def _blocks_from_image(path: Path) -> list[ContentBlock]:
        text = parse_image_text(path).strip()
        if not text:
            return []
        return [
            ContentBlock(
                modality=Modality.IMAGE,
                content=text,
                source=path.name,
                label=SECTION_IMAGE,
            )
        ]

    @classmethod
    def process_file(cls, file_path: str | Path) -> MultimodalResult:
        """解析单个文件为分块结果。"""
        path = Path(file_path).resolve()
        kind = detect_file_kind(path)

        if kind == FileKind.PDF:
            blocks = cls._blocks_from_pdf(path)
        elif kind == FileKind.DOCX:
            blocks = cls._blocks_from_docx(path)
        else:
            blocks = cls._blocks_from_image(path)

        if not blocks:
            raise ValueError(f"文件未解析到有效内容: {path}")

        label = KIND_LABEL.get(kind.value, kind.value)
        return MultimodalResult(
            blocks=blocks,
            uploaded_files=[build_uploaded_file(path)],
            source_summary=f"{path.name} ({label})",
        )

    @classmethod
    def process_files(
        cls,
        file_paths: list[str | Path],
        *,
        extra_text: str | None = None,
    ) -> MultimodalResult:
        """合并多个文件；可选附加纯文本块。"""
        if not file_paths and not (extra_text or "").strip():
            raise ValueError("至少提供一个文件或附加文本")

        all_blocks: list[ContentBlock] = []
        uploaded: list[UploadedFile] = []
        names: list[str] = []

        for file_path in file_paths:
            partial = cls.process_file(file_path)
            all_blocks.extend(partial.blocks)
            uploaded.extend(partial.uploaded_files)
            names.append(Path(file_path).name)

        if (extra_text or "").strip():
            all_blocks.insert(
                0,
                ContentBlock(
                    modality=Modality.TEXT,
                    content=extra_text.strip(),
                    source="用户补充",
                    label=SECTION_TEXT,
                ),
            )

        summary = " + ".join(names) if names else "用户输入"
        if extra_text and names:
            summary = f"{summary}（含补充文字）"
        return MultimodalResult(
            blocks=all_blocks,
            uploaded_files=uploaded,
            source_summary=summary,
        )

    @classmethod
    def process(
        cls,
        source: str | Path | list[str | Path],
        *,
        extra_text: str | None = None,
    ) -> MultimodalResult:
        """
        统一入口。

        - str 且无对应文件路径 → 纯文本
        - Path / 存在的文件路径字符串 → 单文件
        - list → 多文件（可配合 extra_text）
        """
        if isinstance(source, list):
            return cls.process_files(source, extra_text=extra_text)

        if isinstance(source, Path):
            return cls.process_file(source)

        text = source.strip()
        path = Path(text)
        if path.is_file() and path.suffix.lower() in SUFFIX_TO_KIND:
            return cls.process_file(path)
        return cls.process_text(text)

    @classmethod
    def load_for_graph(
        cls,
        source: str | Path | list[str | Path],
        *,
        extra_text: str | None = None,
    ) -> tuple[str, list[UploadedFile]]:
        """处理并返回 LangGraph 初始状态所需字段。"""
        result = cls.process(source, extra_text=extra_text)
        return result.to_student_input(), result.uploaded_files


def is_supported_file(path: str | Path) -> bool:
    """判断扩展名是否在支持列表内。"""
    return Path(path).suffix.lower() in SUFFIX_TO_KIND


def supported_extensions() -> list[str]:
    """返回支持的文件扩展名。"""
    exts = set(SUFFIX_TO_KIND) | IMAGE_SUFFIXES
    return sorted(exts)


__all__ = [
    "CONTENT_TYPE_BY_KIND",
    "ContentBlock",
    "Modality",
    "MultimodalProcessor",
    "MultimodalResult",
    "is_supported_file",
    "load_for_graph",
    "supported_extensions",
]

# 便捷函数
load_for_graph = MultimodalProcessor.load_for_graph
