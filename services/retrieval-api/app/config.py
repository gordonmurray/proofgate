"""Runtime configuration, sourced entirely from the environment.

The same image runs in staging and prod; only the environment differs. The two
deliberate forks from docs/DESIGN.md (Bedrock vs self-hosted inference) are selected
here via ``PROOFGATE_EMBEDDER`` / ``PROOFGATE_RERANKER`` rather than decided at build time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The corpus that ships in the image. A separate, deliberately bad corpus lives
# alongside it and is used by the eval-gate demo to prove the gate can fail.
_DEFAULT_CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "demo.jsonl"


@dataclass(frozen=True)
class Settings:
    """Immutable view of the service configuration for one process.

    Attributes:
        corpus_path: Path to the JSONL corpus to index at startup.
        embedder: Which embedder to use ("local" or "bedrock").
        reranker: Which reranker to use ("none" or "bedrock").
        embedding_dim: Dimensionality of the local hashing embedder.
        otel_endpoint: OTLP endpoint; when empty, spans are created but not exported.
        service_name: Resource name attached to every span.
        environment: Free-form deploy environment label ("local"/"staging"/"prod").
    """

    corpus_path: Path
    embedder: str
    reranker: str
    embedding_dim: int
    otel_endpoint: str
    service_name: str
    environment: str


def load_settings() -> Settings:
    """Build :class:`Settings` from environment variables.

    Returns:
        A frozen :class:`Settings` instance. Unset values fall back to defaults
        chosen so the service runs locally with no configuration at all.
    """
    return Settings(
        corpus_path=Path(os.environ.get("PROOFGATE_CORPUS_PATH", str(_DEFAULT_CORPUS))),
        embedder=os.environ.get("PROOFGATE_EMBEDDER", "local").lower(),
        reranker=os.environ.get("PROOFGATE_RERANKER", "none").lower(),
        embedding_dim=int(os.environ.get("PROOFGATE_EMBEDDING_DIM", "512")),
        otel_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        service_name=os.environ.get("OTEL_SERVICE_NAME", "retrieval-api"),
        environment=os.environ.get("PROOFGATE_ENV", "local"),
    )
