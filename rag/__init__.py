"""RAG 模块：BGE-M3 嵌入 + ChromaDB 三域独立检索。"""

from rag.chroma_manager import COLLECTIONS, ChromaManager
from rag.data_rag import (
    DataRAG,
    ingest_data_pdf,
    ingest_data_pdf_directory,
    retrieve_data_context,
    retrieve_data_documents,
    get_data_retriever,
)
from rag.embeddings import get_embeddings
from rag.loaders import load_pdf, load_pdfs_from_directory
from rag.practice_rag import (
    PracticeRAG,
    ingest_practice_pdf,
    ingest_practice_pdf_directory,
    retrieve_practice_context,
    retrieve_practice_documents,
    get_practice_retriever,
)
from rag.retrievers import DomainRetriever, get_retriever
from rag.theory_rag import (
    TheoryRAG,
    ingest_theory_pdf,
    ingest_theory_pdf_directory,
    retrieve_theory_context,
    retrieve_theory_documents,
    get_theory_retriever,
)

__all__ = [
    "COLLECTIONS",
    "ChromaManager",
    "DataRAG",
    "DomainRetriever",
    "PracticeRAG",
    "TheoryRAG",
    "get_data_retriever",
    "get_embeddings",
    "get_practice_retriever",
    "get_retriever",
    "get_theory_retriever",
    "ingest_data_pdf",
    "ingest_data_pdf_directory",
    "ingest_practice_pdf",
    "ingest_practice_pdf_directory",
    "ingest_theory_pdf",
    "ingest_theory_pdf_directory",
    "load_pdf",
    "load_pdfs_from_directory",
    "retrieve_data_context",
    "retrieve_data_documents",
    "retrieve_practice_context",
    "retrieve_practice_documents",
    "retrieve_theory_context",
    "retrieve_theory_documents",
]
