"""RAG 检索结果格式化（各域共用）。"""

from __future__ import annotations

from langchain_core.documents import Document


def format_rag_context(
    docs: list[Document],
    *,
    empty_hint: str,
    domain_label: str = "参考",
) -> str:
    if not docs:
        return empty_hint

    blocks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "未知来源")
        page = doc.metadata.get("page")
        header = f"[{domain_label}{index}] 来源: {source}"
        if page is not None:
            header += f"（第 {page} 页）"
        blocks.append(f"{header}\n{doc.page_content.strip()}")
    return "\n\n".join(blocks)
