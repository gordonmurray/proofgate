"""FastAPI application: the retrieval-api request path.

Endpoints:
  - ``GET  /health``  liveness/readiness for the ALB target group.
  - ``GET  /``        service metadata (name, version, config summary).
  - ``POST /search``  the retrieval endpoint.

Every handler runs under FastAPI OTel instrumentation, and every downstream
retrieval stage emits its own span (see :mod:`app.retrieval`). This module wires
config -> telemetry -> corpus -> retriever once at startup and holds the retriever
in module state for the life of the process.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, Field

from .config import Settings, load_settings
from .embedders import build_embedder
from .retrieval import Retriever, load_corpus
from .telemetry import get_tracer, setup_telemetry

_tracer = get_tracer()


class SearchRequest(BaseModel):
    """Body of a ``POST /search`` call."""

    query: str = Field(..., min_length=1, description="The user query text.")
    k: int = Field(10, ge=1, le=100, description="Number of results to return.")
    rerank: bool = Field(False, description="Run the rerank pass over candidates.")


class SearchHit(BaseModel):
    """A single ranked result."""

    id: str
    title: str
    score: float
    text: str


class SearchResponse(BaseModel):
    """Response body for ``POST /search``."""

    query: str
    k: int
    results: List[SearchHit]


class AppState:
    """Process-wide singletons built at startup."""

    settings: Optional[Settings] = None
    retriever: Optional[Retriever] = None


state = AppState()


def build_retriever(settings: Settings) -> Retriever:
    """Load the corpus and construct the retriever for ``settings``.

    Args:
        settings: Resolved service settings.

    Returns:
        A ready-to-serve :class:`~app.retrieval.Retriever`.
    """
    embedder = build_embedder(settings.embedder, settings.embedding_dim)
    docs = load_corpus(settings.corpus_path)
    return Retriever(docs, embedder)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: build telemetry and the retriever once."""
    settings = load_settings()
    setup_telemetry(settings)
    state.settings = settings
    state.retriever = build_retriever(settings)
    yield
    state.retriever = None


app = FastAPI(
    title="proofgate retrieval-api",
    version="0.1.0",
    summary="Query orchestration for the proofgate reference retrieval system.",
    lifespan=lifespan,
)
FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
def health() -> dict:
    """Liveness probe.

    Returns:
        ``{"status": "ok", "corpus_size": <int>}`` once the corpus is loaded.
        Returns ``status: "starting"`` with size 0 before startup completes.
    """
    size = len(state.retriever.docs) if state.retriever else 0
    return {"status": "ok" if state.retriever else "starting", "corpus_size": size}


@app.get("/")
def root() -> dict:
    """Service metadata and effective configuration summary."""
    s = state.settings
    return {
        "service": "retrieval-api",
        "version": app.version,
        "environment": s.environment if s else "unknown",
        "embedder": s.embedder if s else "unknown",
        "reranker": s.reranker if s else "unknown",
    }


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    """Run a hybrid retrieval query.

    Args:
        req: The parsed search request.

    Returns:
        The ranked results.

    Raises:
        HTTPException: 503 if the retriever is not yet initialised.
    """
    if state.retriever is None:
        raise HTTPException(status_code=503, detail="retriever not ready")

    with _tracer.start_as_current_span("handler.search") as span:
        span.set_attribute("query", req.query)
        span.set_attribute("k", req.k)
        hits = state.retriever.search(req.query, k=req.k, rerank=req.rerank)
        span.set_attribute("results", len(hits))

    return SearchResponse(
        query=req.query,
        k=req.k,
        results=[
            SearchHit(
                id=h.document.id,
                title=h.document.title,
                score=round(h.score, 6),
                text=h.document.text,
            )
            for h in hits
        ],
    )
