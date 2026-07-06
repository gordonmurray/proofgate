"""Hybrid retrieval over the in-memory corpus.

This is the local stand-in for Firn on S3. It combines two planes, exactly like
the production path in docs/DESIGN.md:

  - Vector search: cosine similarity between the query embedding and each
    document embedding.
  - Full-text search (FTS): a compact BM25 scorer over the tokenised corpus.

Scores from both planes are min-max normalised per query and blended, then an
optional rerank pass reorders the top candidates. Every stage that would be a
downstream call in production (embed, vector, fts, rerank) emits its own span so
traces mirror the real request path.

What it is NOT: a persistent index, a cache, or the foyer tier. Caching is a
Firn-internal property and is not modelled here.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .embedders import Embedder, cosine, tokenize
from .telemetry import get_tracer

_tracer = get_tracer()


@dataclass(frozen=True)
class Document:
    """A single corpus document.

    Attributes:
        id: Stable identifier used by the golden set (``relevant_ids``).
        title: Short human-readable title.
        text: Body text that is indexed and returned.
        topic: Topic label, used only for corpus organisation/debugging.
    """

    id: str
    title: str
    text: str
    topic: str


@dataclass(frozen=True)
class ScoredDocument:
    """A document paired with its blended retrieval score."""

    document: Document
    score: float


def load_corpus(path: Path) -> List[Document]:
    """Load a JSONL corpus from disk.

    Args:
        path: Path to a JSONL file, one document object per line.

    Returns:
        The documents in file order.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If a line is present but missing a required field.
    """
    docs: List[Document] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            try:
                docs.append(
                    Document(
                        id=obj["id"],
                        title=obj.get("title", ""),
                        text=obj["text"],
                        topic=obj.get("topic", ""),
                    )
                )
            except KeyError as exc:  # noqa: PERF203 - clarity over speed at load
                raise ValueError(f"{path}:{lineno} missing field {exc}") from exc
    return docs


class BM25:
    """A minimal BM25 full-text scorer.

    Standard Okapi BM25 with the usual ``k1``/``b`` parameters. Small enough to
    read in one sitting; good enough to make the FTS plane a real signal rather
    than a stub.
    """

    def __init__(self, docs: List[Document], k1: float = 1.5, b: float = 0.75) -> None:
        """Build the inverted statistics for ``docs``.

        Args:
            docs: Corpus documents to index.
            k1: Term-frequency saturation parameter.
            b: Length-normalisation parameter.
        """
        self.k1 = k1
        self.b = b
        self._doc_tokens: List[List[str]] = [tokenize(f"{d.title} {d.text}") for d in docs]
        self._doc_len = [len(t) for t in self._doc_tokens]
        self._avg_len = (sum(self._doc_len) / len(self._doc_len)) if docs else 0.0
        self._tf: List[Counter] = [Counter(t) for t in self._doc_tokens]

        n_docs = len(docs)
        df: Counter = Counter()
        for tokens in self._doc_tokens:
            for term in set(tokens):
                df[term] += 1
        # Standard BM25 idf with the +1 inside the log to keep it non-negative.
        self._idf: Dict[str, float] = {
            term: math.log(1 + (n_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def scores(self, query: str) -> List[float]:
        """Score every document against ``query``.

        Args:
            query: Raw query string.

        Returns:
            One BM25 score per document, in corpus order. Documents sharing no
            terms with the query score 0.0.
        """
        q_terms = tokenize(query)
        out = [0.0] * len(self._tf)
        for term in q_terms:
            idf = self._idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self._tf):
                freq = tf.get(term, 0)
                if freq == 0:
                    continue
                denom = freq + self.k1 * (
                    1 - self.b + self.b * self._doc_len[i] / (self._avg_len or 1.0)
                )
                out[i] += idf * (freq * (self.k1 + 1)) / denom
        return out


def _minmax(values: List[float]) -> List[float]:
    """Min-max normalise a list of scores into ``[0, 1]``.

    A flat input (all equal) maps to all zeros, contributing nothing to the blend.
    """
    if not values:
        return values
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


class Retriever:
    """Owns the indexed corpus and answers search queries.

    The retriever is built once at startup and treated as immutable. It holds the
    document embeddings (vector plane) and a :class:`BM25` index (FTS plane).
    """

    def __init__(self, docs: List[Document], embedder: Embedder, alpha: float = 0.5) -> None:
        """Index ``docs`` for hybrid retrieval.

        Args:
            docs: Corpus documents.
            embedder: Embedder used for both documents (now) and queries (per call).
            alpha: Blend weight in ``[0, 1]``; vector weight is ``alpha``, FTS is
                ``1 - alpha``.
        """
        self.docs = docs
        self.embedder = embedder
        self.alpha = alpha
        self._bm25 = BM25(docs)
        with _tracer.start_as_current_span("index.embed_corpus") as span:
            span.set_attribute("corpus.size", len(docs))
            self._doc_vectors = [embedder.embed(f"{d.title} {d.text}") for d in docs]

    def search(self, query: str, k: int = 10, rerank: bool = False) -> List[ScoredDocument]:
        """Retrieve the top ``k`` documents for ``query``.

        Args:
            query: The user query.
            k: Number of results to return.
            rerank: If true, run the (currently identity) rerank pass over the
                candidate window and reorder by its score.

        Returns:
            Up to ``k`` :class:`ScoredDocument` results, highest score first.
        """
        if not self.docs:
            return []

        with _tracer.start_as_current_span("retrieval.search") as span:
            span.set_attribute("query.length", len(query))
            span.set_attribute("retrieval.k", k)
            span.set_attribute("retrieval.rerank", rerank)

            with _tracer.start_as_current_span("retrieval.embed_query"):
                q_vec = self.embedder.embed(query)

            with _tracer.start_as_current_span("retrieval.vector"):
                vec_scores = [cosine(q_vec, dv) for dv in self._doc_vectors]

            with _tracer.start_as_current_span("retrieval.fts"):
                fts_scores = self._bm25.scores(query)

            vec_n = _minmax(vec_scores)
            fts_n = _minmax(fts_scores)
            blended = [
                self.alpha * v + (1 - self.alpha) * f for v, f in zip(vec_n, fts_n)
            ]

            order = sorted(range(len(self.docs)), key=lambda i: blended[i], reverse=True)
            window = order[: max(k * 3, k)]

            if rerank:
                with _tracer.start_as_current_span("retrieval.rerank") as rspan:
                    rspan.set_attribute("rerank.candidates", len(window))
                    window = self._rerank(query, window, blended)

            top = window[:k]
            span.set_attribute("retrieval.returned", len(top))
            return [ScoredDocument(self.docs[i], blended[i]) for i in top]

    def _rerank(self, query: str, window: List[int], blended: List[float]) -> List[int]:
        """Rerank a candidate window.

        This is fork #1's rerank seam. Today it is an identity pass (keeps the
        blended order) so the span and the ``rerank=true`` path are real and
        traced; a Bedrock reranker can be swapped in behind this method later.

        Args:
            query: The original query (unused by the identity reranker).
            window: Candidate document indices, already in blended order.
            blended: Blended scores per document.

        Returns:
            The reordered candidate indices.
        """
        return window
