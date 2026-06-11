"""
数据域 RAG：ChromaDB + BAAI/bge-m3 + PDF 入库 + similarity 检索。

供 data_agent 在评估前自动检索 reference_context。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document

from rag._format import format_rag_context
from rag.chroma_manager import ChromaManager
from rag.embeddings import BGE_M3_MODEL
from rag.retrievers import get_retriever

logger = logging.getLogger(__name__)

DATA_COLLECTION = "data"
DEFAULT_TOP_K = 4
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"

EMPTY_CONTEXT_HINT = (
    "（数据知识库中未检索到相关参考资料，请仅依据学生作答内容进行评估。）"
)


@lru_cache(maxsize=1)
def get_data_manager() -> ChromaManager:
    return ChromaManager(persist_directory=DEFAULT_PERSIST_DIR)


class DataRAG:
    """数据知识库 RAG 门面（Chroma collection: data）。"""

    def __init__(
        self,
        *,
        persist_directory: str | Path | None = None,
        k: int = DEFAULT_TOP_K,
    ) -> None:
        self.k = k
        if persist_directory is not None:
            self.manager = ChromaManager(persist_directory=persist_directory)
        else:
            self.manager = get_data_manager()

    @property
    def embedding_model(self) -> str:
        return BGE_M3_MODEL

    def ingest_pdf(self, pdf_path: str | Path, *, split: bool = True) -> list[str]:
        ids = self.manager.ingest_pdf(DATA_COLLECTION, pdf_path, split=split)
        logger.info("data 入库 PDF %s，chunks=%d", pdf_path, len(ids))
        return ids

    def ingest_pdf_directory(
        self,
        directory: str | Path,
        *,
        recursive: bool = True,
        split: bool = True,
    ) -> list[str]:
        ids = self.manager.ingest_pdf_directory(
            DATA_COLLECTION, directory, recursive=recursive, split=split
        )
        logger.info("data 入库目录 %s，chunks=%d", directory, len(ids))
        return ids

    def retrieve_documents(self, query: str, *, k: int | None = None) -> list[Document]:
        return self.manager.similarity_search(DATA_COLLECTION, query, k=k or self.k)

    def retrieve_context(self, query: str, *, k: int | None = None) -> str:
        return format_data_context(self.retrieve_documents(query, k=k))

    def get_retriever(self, *, k: int | None = None):
        return get_retriever(DATA_COLLECTION, manager=self.manager, k=k or self.k)


@lru_cache(maxsize=1)
def _default_rag() -> DataRAG:
    return DataRAG()


def format_data_context(docs: list[Document]) -> str:
    return format_rag_context(docs, empty_hint=EMPTY_CONTEXT_HINT, domain_label="数据参考")


def retrieve_data_documents(
    query: str,
    *,
    k: int = DEFAULT_TOP_K,
    manager: ChromaManager | None = None,
) -> list[Document]:
    if manager is not None:
        rag = DataRAG(k=k)
        rag.manager = manager
        return rag.retrieve_documents(query, k=k)
    return _default_rag().retrieve_documents(query, k=k)


def retrieve_data_context(
    query: str,
    *,
    k: int = DEFAULT_TOP_K,
    manager: ChromaManager | None = None,
) -> str:
    if manager is not None:
        rag = DataRAG(k=k)
        rag.manager = manager
        return rag.retrieve_context(query, k=k)
    return _default_rag().retrieve_context(query, k=k)


def ingest_data_pdf(pdf_path: str | Path, *, split: bool = True) -> list[str]:
    return _default_rag().ingest_pdf(pdf_path, split=split)


def ingest_data_pdf_directory(
    directory: str | Path,
    *,
    recursive: bool = True,
    split: bool = True,
) -> list[str]:
    return _default_rag().ingest_pdf_directory(
        directory, recursive=recursive, split=split
    )


def get_data_retriever(
    *,
    k: int = DEFAULT_TOP_K,
    manager: ChromaManager | None = None,
):
    mgr = manager or get_data_manager()
    return get_retriever(DATA_COLLECTION, manager=mgr, k=k)


__all__ = [
    "DEFAULT_TOP_K",
    "DATA_COLLECTION",
    "DataRAG",
    "format_data_context",
    "get_data_manager",
    "get_data_retriever",
    "ingest_data_pdf",
    "ingest_data_pdf_directory",
    "retrieve_data_context",
    "retrieve_data_documents",
]
