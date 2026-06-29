"""BAAI/bge-m3 嵌入模型封装。"""

from __future__ import annotations

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

BGE_M3_MODEL = "BAAI/bge-small-zh-v1.5"


@lru_cache(maxsize=1)
def get_embeddings(
    *,
    model_name: str = BGE_M3_MODEL,
    device: str = "cpu",
) -> HuggingFaceEmbeddings:
    """
    获取 BGE-M3 嵌入模型（LangChain HuggingFaceEmbeddings）。

    bge-m3 建议对向量做 L2 归一化，以配合余弦/相似度检索。
    """
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )
