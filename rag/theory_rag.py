"""
理论域 RAG：ChromaDB + BAAI/bge-m3 + PDF 入库 + similarity 检索。

供 agents.theory_agent 在评估前自动检索 reference_context。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document

from rag.chroma_manager import ChromaManager
from rag.embeddings import BGE_M3_MODEL, get_embeddings
from rag.retrievers import get_retriever

logger = logging.getLogger(__name__)

THEORY_COLLECTION = "theory"
DEFAULT_TOP_K = 4
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"

EMPTY_CONTEXT_HINT = (
    "（知识库中未检索到相关参考资料，请仅依据学生作答内容进行评估。）"
)


@lru_cache(maxsize=1)
def get_theory_manager() -> ChromaManager:
    """
    共享 ChromaManager（theory collection，BGE-M3 嵌入，持久化到 data/chroma）。
    """
    return ChromaManager(persist_directory=DEFAULT_PERSIST_DIR)


class TheoryRAG:
    """
    理论知识库 RAG 门面。

    - 嵌入：BAAI/bge-m3（见 rag.embeddings）
    - 向量库：ChromaDB collection `theory`
    - 入库：PDF（单文件 / 目录）
    - 检索：similarity search
    """

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
            self.manager = get_theory_manager()

    @property
    def embedding_model(self) -> str:
        return BGE_M3_MODEL

    def ingest_pdf(self, pdf_path: str | Path, *, split: bool = True) -> list[str]:
        """将单个 PDF 入库到 theory collection。"""
        ids = self.manager.ingest_pdf(
            THEORY_COLLECTION, pdf_path, split=split
        )
        logger.info("已入库 PDF %s，chunks=%d", pdf_path, len(ids))
        return ids

    def ingest_pdf_directory(
        self,
        directory: str | Path,
        *,
        recursive: bool = True,
        split: bool = True,
    ) -> list[str]:
        """将目录下所有 PDF 入库到 theory collection。"""
        ids = self.manager.ingest_pdf_directory(
            THEORY_COLLECTION,
            directory,
            recursive=recursive,
            split=split,
        )
        logger.info("已入库目录 %s，chunks=%d", directory, len(ids))
        return ids

    def retrieve_documents(self, query: str, *, k: int | None = None) -> list[Document]:
        """Similarity search，返回 Document 列表。"""
        top_k = k or self.k
        return self.manager.similarity_search(
            THEORY_COLLECTION, query, k=top_k
        )

    def retrieve_context(self, query: str, *, k: int | None = None) -> str:
        """检索并格式化为 theory_agent Prompt 可用的参考文本。"""
        docs = self.retrieve_documents(query, k=k)
        return format_theory_context(docs)

    def get_retriever(self, *, k: int | None = None):
        """LangChain Retriever（search_type=similarity）。"""
        return get_retriever(
            THEORY_COLLECTION,
            manager=self.manager,
            k=k or self.k,
        )


@lru_cache(maxsize=1)
def _default_rag() -> TheoryRAG:
    return TheoryRAG()


def format_theory_context(docs: list[Document]) -> str:
    """将检索结果格式化为可注入 Prompt 的参考文本。"""
    if not docs:
        return EMPTY_CONTEXT_HINT

    blocks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "未知来源")
        page = doc.metadata.get("page")
        header = f"[参考{index}] 来源: {source}"
        if page is not None:
            header += f"（第 {page} 页）"
        blocks.append(f"{header}\n{doc.page_content.strip()}")
    return "\n\n".join(blocks)


def retrieve_theory_documents(
    query: str,
    *,
    k: int = DEFAULT_TOP_K,
    manager: ChromaManager | None = None,
) -> list[Document]:
    """对学生问题在 theory collection 中做 similarity search。"""
    if manager is not None:
        rag = TheoryRAG(k=k)
        rag.manager = manager
        return rag.retrieve_documents(query, k=k)
    return _default_rag().retrieve_documents(query, k=k)


def retrieve_theory_context(
    query: str,
    *,
    k: int = DEFAULT_TOP_K,
    manager: ChromaManager | None = None,
) -> str:
    """检索参考上下文（theory_agent 自动调用入口）。"""
    if manager is not None:
        rag = TheoryRAG(k=k)
        rag.manager = manager
        return rag.retrieve_context(query, k=k)
    return _default_rag().retrieve_context(query, k=k)


def ingest_theory_pdf(pdf_path: str | Path, *, split: bool = True) -> list[str]:
    """便捷函数：单 PDF 入库。"""
    return _default_rag().ingest_pdf(pdf_path, split=split)


def ingest_theory_pdf_directory(
    directory: str | Path,
    *,
    recursive: bool = True,
    split: bool = True,
) -> list[str]:
    """便捷函数：目录批量 PDF 入库。"""
    return _default_rag().ingest_pdf_directory(
        directory, recursive=recursive, split=split
    )


def get_theory_retriever(
    *,
    k: int = DEFAULT_TOP_K,
    manager: ChromaManager | None = None,
):
    """获取 theory collection 的 LangChain Retriever。"""
    mgr = manager or get_theory_manager()
    return get_retriever(THEORY_COLLECTION, manager=mgr, k=k)


__all__ = [
    "BGE_M3_MODEL",
    "DEFAULT_TOP_K",
    "THEORY_COLLECTION",
    "TheoryRAG",
    "format_theory_context",
    "get_theory_manager",
    "get_theory_retriever",
    "ingest_theory_pdf",
    "ingest_theory_pdf_directory",
    "retrieve_theory_context",
    "retrieve_theory_documents",
]
