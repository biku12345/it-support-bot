import os
from typing import Any
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)

def get_embeddings():
    # WHY HuggingFace embeddings?
    # Runs 100% locally - no API key, no credits, no cost.
    # all-MiniLM-L6-v2 is small (80MB) but very good quality.
    # Downloads once, cached forever.
    return HuggingFaceEmbeddings(
        model_name="all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
    )

def get_vector_store() -> Chroma:
    os.makedirs("/chromadb", exist_ok=True)
    return Chroma(
        collection_name="it_support_kb",
        embedding_function=get_embeddings(),
        persist_directory="/chromadb",
    )

def add_documents(documents: list[Document]) -> int:
    if not documents:
        return 0
    store = get_vector_store()
    store.add_documents(documents)
    return len(documents)

def similarity_search(query: str, k: int | None = None) -> list[Document]:
    k = k or settings.retrieval_top_k
    store = get_vector_store()
    return store.similarity_search(query, k=k)

def similarity_search_with_score(query: str, k: int | None = None) -> list[tuple[Document, float]]:
    k = k or settings.retrieval_top_k
    store = get_vector_store()
    return store.similarity_search_with_relevance_scores(query, k=k)

def get_collection_stats() -> dict[str, Any]:
    try:
        store = get_vector_store()
        count = store._collection.count()
        return {"status": "ok", "document_count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}
