"""ChromaDB 管理：theory / practice / data 三个独立 collection。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.embeddings import get_embeddings
from rag.loaders import SUPPORTED_COLLECTIONS, load_pdf, load_pdfs_from_directory

CollectionName = Literal["theory", "practice", "data"]
COLLECTIONS: tuple[CollectionName, ...] = ("theory", "practice", "data")

DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50


class ChromaManager:
    """管理三个独立 Chroma collection 的写入与读取。"""

    def __init__(
        self,
        persist_directory: str | Path | None = None,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self.persist_directory = Path(persist_directory or DEFAULT_PERSIST_DIR)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self._embeddings = get_embeddings()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", ". ", " ", ""],
        )
        self._stores: dict[str, Chroma] = {}

    def _validate_collection(self, collection: str) -> CollectionName:
        name = collection.strip().lower()
        if name not in SUPPORTED_COLLECTIONS:
            raise ValueError(
                f"collection 必须是 {list(COLLECTIONS)} 之一，收到: {collection}"
            )
        return name  # type: ignore[return-value]

    def get_vectorstore(self, collection: str) -> Chroma:
        """获取（或创建）指定 collection 的 Chroma 向量库。"""
        name = self._validate_collection(collection)
        if name not in self._stores:
            self._stores[name] = Chroma(
                collection_name=name,
                embedding_function=self._embeddings,
                persist_directory=str(self.persist_directory),
            )
        return self._stores[name]

    def add_documents(
        self,
        collection: str,
        documents: list[Document],
        *,
        split: bool = True,
    ) -> list[str]:
        """向指定 collection 写入文档，返回写入的 chunk id 列表。"""
        if not documents:
            return []

        name = self._validate_collection(collection)
        chunks = self._splitter.split_documents(documents) if split else documents
        for chunk in chunks:
            chunk.metadata["collection"] = name

        store = self.get_vectorstore(name)
        return store.add_documents(chunks)

    def ingest_pdf(
        self,
        collection: str,
        pdf_path: str | Path,
        *,
        split: bool = True,
    ) -> list[str]:
        """将单个 PDF 入库到指定 collection。"""
        name = self._validate_collection(collection)
        docs = load_pdf(pdf_path, collection=name)
        return self.add_documents(name, docs, split=split)

    def ingest_pdf_directory(
        self,
        collection: str,
        directory: str | Path,
        *,
        recursive: bool = True,
        split: bool = True,
    ) -> list[str]:
        """将目录下所有 PDF 入库到指定 collection。"""
        name = self._validate_collection(collection)
        docs = load_pdfs_from_directory(
            directory, collection=name, recursive=recursive
        )
        return self.add_documents(name, docs, split=split)

    def similarity_search(
        self,
        collection: str,
        query: str,
        *,
        k: int = 4,
    ) -> list[Document]:
        """在指定 collection 中做相似度检索。"""
        store = self.get_vectorstore(collection)
        return store.similarity_search(query, k=k)

    def similarity_search_with_score(
        self,
        collection: str,
        query: str,
        *,
        k: int = 4,
    ) -> list[tuple[Document, float]]:
        """相似度检索并返回分数。"""
        store = self.get_vectorstore(collection)
        return store.similarity_search_with_score(query, k=k)
