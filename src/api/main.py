import time
import uuid
from contextlib import asynccontextmanager

import redis as redis_client
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.agents.graph import run_agent
from src.config import settings
from src.models.schemas import (
    ChatRequest, ChatResponse, HealthResponse,
    IngestRequest, IngestResponse, RetrievalSource, SourceCitation,
)
from src.retrieval.ingest import ingest_local_folder, ingest_from_s3
from src.retrieval.vector_store import get_collection_stats
from src.utils.exceptions import ITSupportError, RetrievalError, LLMError
from src.utils.logger import configure_logging, get_logger

configure_logging(settings.log_level)
log = get_logger(__name__)
START_TIME = time.time()

# Rate limiter — 10 req/min per IP
limiter = Limiter(key_func=get_remote_address)

def get_redis():
    try:
        r = redis_client.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        log.warning("Redis unavailable", error=str(e))
        return None

def get_session_history(session_id: str) -> list[dict]:
    r = get_redis()
    if not r:
        return []
    try:
        import json
        data = r.get(f"session:{session_id}")
        return json.loads(data) if data else []
    except Exception:
        return []

def save_session_history(session_id: str, history: list[dict]) -> None:
    r = get_redis()
    if not r:
        return
    try:
        import json
        r.setex(f"session:{session_id}", settings.redis_ttl_seconds, json.dumps(history))
    except Exception as e:
        log.warning("Failed to save session", error=str(e))

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting IT Support Bot", env=settings.app_env)
    from src.agents.graph import graph
    log.info("LangGraph agent ready", nodes=list(graph.nodes.keys()))
    stats = get_collection_stats()
    log.info("Vector store", **stats)
    yield
    log.info("Shutting down")

app = FastAPI(
    title="IT Support Chatbot API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.exception_handler(ITSupportError)
async def it_support_error_handler(request: Request, exc: ITSupportError):
    return JSONResponse(status_code=503, content={"error": exc.message})

@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    return JSONResponse(status_code=429, content={"error": "AI service unavailable, retry"})

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
@limiter.limit(settings.rate_limit)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    start = time.time()
    session_id = body.session_id or str(uuid.uuid4())
    history = get_session_history(session_id)

    log.info("Chat request", session_id=session_id, query=body.query[:80])

    result = run_agent(body.query)

    history.append({"role": "user", "content": body.query})
    history.append({"role": "assistant", "content": result["answer"]})
    history = history[-(settings.max_conversation_turns * 2):]
    save_session_history(session_id, history)

    sources = [
        SourceCitation(
            title=doc.metadata.get("doc_name", "Unknown"),
            source=doc.metadata.get("source", ""),
            relevance_score=0.9,
            snippet=doc.page_content[:200],
        )
        for doc in result.get("documents", [])
    ]

    latency_ms = int((time.time() - start) * 1000)
    return ChatResponse(
        answer=result["answer"],
        session_id=session_id,
        retrieval_source=RetrievalSource(result["retrieval_source"]),
        sources=sources,
        query_was_rewritten=result.get("query_was_rewritten", False),
        original_query=body.query if result.get("query_was_rewritten") else None,
        rewritten_query=result.get("rewritten_question"),
        latency_ms=latency_ms,
    )

@app.post("/ingest", response_model=IngestResponse, tags=["Operations"])
async def ingest(body: IngestRequest) -> IngestResponse:
    start = time.time()
    if settings.aws_access_key_id:
        result = ingest_from_s3(prefix=body.s3_prefix, force_reingest=body.force_reingest)
    else:
        result = ingest_local_folder(folder_path="./docs", force_reingest=body.force_reingest)
    return IngestResponse(
        documents_processed=result.documents_processed,
        chunks_created=result.chunks_created,
        documents_skipped=result.documents_skipped,
        errors=result.errors,
        duration_seconds=round(time.time() - start, 2),
    )

@app.get("/health", response_model=HealthResponse, tags=["Operations"])
async def health_check() -> HealthResponse:
    components = {}
    overall = "ok"
    stats = get_collection_stats()
    components["vector_db"] = f"ok ({stats.get('document_count', 0)} chunks)" if stats["status"] == "ok" else "degraded"
    components["redis"] = "ok" if get_redis() else "degraded"
    components["api"] = "ok"
    try:
        from src.agents.nodes import get_llm
        components["llm"] = "ok"
    except Exception as e:
        components["llm"] = "degraded"
        overall = "degraded"
    return HealthResponse(
        status=overall,
        components=components,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )
