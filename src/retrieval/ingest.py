import hashlib
import os
from pathlib import Path
from dataclasses import dataclass, field

from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings
from src.retrieval.vector_store import add_documents
from src.utils.logger import get_logger

log = get_logger(__name__)

@dataclass
class IngestionResult:
    documents_processed: int = 0
    chunks_created: int = 0
    documents_skipped: int = 0
    errors: list[str] = field(default_factory=list)

def get_text_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

def load_document(file_path: str) -> list[Document]:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return PyPDFLoader(file_path).load()
    elif ext in {".docx", ".doc"}:
        return Docx2txtLoader(file_path).load()
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return [Document(page_content=content, metadata={"source": file_path})]
    else:
        raise ValueError(f"Unsupported file type: {ext}")

def add_metadata(chunks: list[Document], source_file: str) -> list[Document]:
    filename = Path(source_file).name
    doc_name = Path(source_file).stem
    doc_hash = hashlib.md5(source_file.encode()).hexdigest()[:8]
    for i, chunk in enumerate(chunks):
        chunk.metadata.update({
            "source": source_file,
            "filename": filename,
            "doc_name": doc_name,
            "doc_hash": doc_hash,
            "chunk_index": i,
            "total_chunks": len(chunks),
        })
    return chunks

def ingest_file(file_path: str, force_reingest: bool = False) -> IngestionResult:
    result = IngestionResult()
    try:
        raw_docs = load_document(file_path)
        if not raw_docs:
            result.documents_skipped += 1
            return result
        chunks = get_text_splitter().split_documents(raw_docs)
        chunks = add_metadata(chunks, file_path)
        stored = add_documents(chunks)
        result.documents_processed += 1
        result.chunks_created += stored
    except Exception as e:
        result.errors.append(f"{Path(file_path).name}: {str(e)}")
    return result

def ingest_local_folder(folder_path: str, force_reingest: bool = False) -> IngestionResult:
    total = IngestionResult()
    supported = {".pdf", ".docx", ".doc", ".txt"}
    files = [str(p) for p in Path(folder_path).rglob("*") if p.suffix.lower() in supported]
    if not files:
        log.warning("No supported files found", folder=folder_path)
        return total
    log.info("Starting ingestion", folder=folder_path, files=len(files))
    for file_path in files:
        result = ingest_file(file_path, force_reingest)
        total.documents_processed += result.documents_processed
        total.chunks_created += result.chunks_created
        total.documents_skipped += result.documents_skipped
        total.errors.extend(result.errors)
    return total

def ingest_from_s3(bucket: str | None = None, prefix: str = "", force_reingest: bool = False) -> IngestionResult:
    total = IngestionResult()
    supported = {".pdf", ".docx", ".doc", ".txt"}

    try:
        import boto3
        bucket = bucket or settings.s3_bucket_name
        s3 = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if Path(key).suffix.lower() not in supported:
                    continue
                local_path = f"/tmp/{Path(key).name}"
                log.info("Downloading from S3", key=key)
                s3.download_file(bucket, key, local_path)
                result = ingest_file(local_path, force_reingest)
                total.documents_processed += result.documents_processed
                total.chunks_created += result.chunks_created
                total.documents_skipped += result.documents_skipped
                total.errors.extend(result.errors)
                os.remove(local_path)
    except Exception as e:
        log.error("S3 ingestion failed", error=str(e))
        total.errors.append(f"S3 error: {str(e)}")

    return total
