"""PDF 解析：使用 PyPDFLoader 提取文本供 LangGraph 使用。"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from state import UploadedFile

DEFAULT_CONTENT_TYPE = "application/pdf"


def parse_pdf_documents(pdf_path: str | Path) -> list[Document]:
    """加载 PDF，按页返回 LangChain Document 列表。"""
    path = Path(pdf_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF 不存在: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"仅支持 .pdf 文件: {path}")
    return PyPDFLoader(str(path)).load()


def parse_pdf_text(pdf_path: str | Path) -> str:
    """提取 PDF 全文（按页拼接）。"""
    docs = parse_pdf_documents(pdf_path)
    if not docs:
        return ""
    pages: list[str] = []
    for doc in docs:
        page_num = doc.metadata.get("page")
        text = (doc.page_content or "").strip()
        if not text:
            continue
        if page_num is not None:
            pages.append(f"--- 第 {int(page_num) + 1} 页 ---\n{text}")
        else:
            pages.append(text)
    return "\n\n".join(pages)


def build_uploaded_file(pdf_path: str | Path) -> UploadedFile:
    """构造 uploaded_files 条目。"""
    path = Path(pdf_path).resolve()
    return {
        "name": path.name,
        "path": str(path),
        "content_type": DEFAULT_CONTENT_TYPE,
    }


def load_pdf_for_graph(pdf_path: str | Path) -> tuple[str, list[UploadedFile]]:
    """
    为 LangGraph 准备输入。

    Returns
    -------
    student_input : 写入 state["student_input"] 的文本（含 PDF 正文）
    uploaded_files : 写入 state["uploaded_files"] 的元数据列表
    """
    path = Path(pdf_path).resolve()
    content = parse_pdf_text(path).strip()
    if not content:
        raise ValueError(f"PDF 未解析到有效文本: {path}")

    uploaded = build_uploaded_file(path)
    student_input = (
        f"【来源 PDF：{uploaded['name']}】\n\n{content}"
    )
    return student_input, [uploaded]
