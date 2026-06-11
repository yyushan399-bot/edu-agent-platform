"""文档加载：支持 PDF 入库。"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

SUPPORTED_COLLECTIONS = frozenset({"theory", "practice", "data"})


def load_pdf(
    file_path: str | Path,
    *,
    collection: str | None = None,
) -> list[Document]:
    """
    加载单个 PDF，返回 LangChain Document 列表。

    若指定 collection，会写入 metadata["collection"] 便于追溯。
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF 不存在: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"仅支持 PDF 文件: {path}")

    docs = PyPDFLoader(str(path)).load()
    if collection:
        if collection not in SUPPORTED_COLLECTIONS:
            raise ValueError(
                f"collection 必须是 {sorted(SUPPORTED_COLLECTIONS)} 之一"
            )
        for doc in docs:
            doc.metadata["collection"] = collection
            doc.metadata.setdefault("source", str(path))

    return docs


def load_pdfs_from_directory(
    directory: str | Path,
    *,
    collection: str | None = None,
    recursive: bool = True,
) -> list[Document]:
    """批量加载目录下所有 PDF。"""
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"目录不存在: {root}")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    all_docs: list[Document] = []
    for pdf_path in sorted(root.glob(pattern)):
        all_docs.extend(load_pdf(pdf_path, collection=collection))
    return all_docs
