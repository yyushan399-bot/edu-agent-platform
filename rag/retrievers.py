"""检索器：基于 Chroma 的 similarity search。"""

from __future__ import annotations

from typing import Literal

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import Field

from rag.chroma_manager import COLLECTIONS, ChromaManager, CollectionName

SearchType = Literal["similarity"]


def get_retriever(
    collection: CollectionName,
    *,
    manager: ChromaManager | None = None,
    k: int = 4,
    search_type: SearchType = "similarity",
) -> BaseRetriever:
    """
    获取指定 collection 的 LangChain Retriever（similarity search）。

    Parameters
    ----------
    collection : theory | practice | data
    manager : 可选，共享 ChromaManager 实例
    k : 返回文档数量
    search_type : 目前仅支持 similarity
    """
    if search_type != "similarity":
        raise ValueError("当前仅支持 search_type='similarity'")

    mgr = manager or ChromaManager()
    store = mgr.get_vectorstore(collection)
    return store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )


class DomainRetriever(BaseRetriever):
    """
    按域（theory/practice/data）封装的 Retriever，便于在链或 Agent 中调用。
    """

    collection: CollectionName = Field(description="检索所属 collection")
    k: int = Field(default=4, ge=1, description="返回条数")
    manager: ChromaManager | None = Field(default=None, exclude=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        mgr = self.manager or ChromaManager()
        return mgr.similarity_search(self.collection, query, k=self.k)

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        # Chroma 同步实现，异步入口复用同步逻辑
        return self._get_relevant_documents(query, run_manager=run_manager)


def get_all_retrievers(
    *,
    manager: ChromaManager | None = None,
    k: int = 4,
) -> dict[CollectionName, BaseRetriever]:
    """一次性获取三个域的 retriever。"""
    return {
        name: get_retriever(name, manager=manager, k=k) for name in COLLECTIONS
    }
