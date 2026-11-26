from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class RetrievalSource(str, Enum):
    KB = "kb"
    WEB = "web"
    KB_AND_WEB = "kb_and_web"
    FAILED = "failed"

class SourceCitation(BaseModel):
    title: str
    source: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    snippet: str | None = None

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    session_id: str | None = None
    max_tokens: int = Field(default=1000, ge=100, le=4000)
    stream: bool = Field(default=False)

class IngestRequest(BaseModel):
    s3_prefix: str = Field(default="")
    force_reingest: bool = Field(default=False)

class ChatResponse(BaseModel):
    answer: str
    session_id: str
    retrieval_source: RetrievalSource
    sources: list[SourceCitation] = []
    query_was_rewritten: bool = False
    original_query: str | None = None
    rewritten_query: str | None = None
    latency_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

class IngestResponse(BaseModel):
    documents_processed: int
    chunks_created: int
    documents_skipped: int
    errors: list[str] = []
    duration_seconds: float

class HealthResponse(BaseModel):
    status: str
    components: dict[str, str]
    version: str = "0.1.0"
    uptime_seconds: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
