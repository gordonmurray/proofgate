"""Query and document embedders.

This is fork #1 from CLAUDE.md made concrete and config-selectable: Bedrock vs
self-hosted inference. Phase 1 wires Bedrock; until then, and in CI where there
are no cloud credentials, the ``local`` hashing embedder gives a deterministic,
dependency-light vector so the whole retrieval path is exercisable offline.

The embedder is intentionally simple. It is not meant to be a good semantic model;
it is meant to make the vector plane real and testable. The eval gate measures
quality regardless of which embedder is behind this interface.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import List, Protocol, Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    """Lowercase and split text into alphanumeric tokens.

    Args:
        text: Arbitrary input text.

    Returns:
        A list of lowercase token strings, in order.
    """
    return _TOKEN_RE.findall(text.lower())


class Embedder(Protocol):
    """Anything that turns text into a fixed-length unit vector."""

    dim: int

    def embed(self, text: str) -> List[float]:
        """Return the embedding for a single piece of text."""
        ...


class LocalHashingEmbedder:
    """Deterministic bag-of-tokens hashing embedder.

    Each token (plus its character trigrams, for a little sub-word robustness) is
    hashed into one of ``dim`` buckets; the resulting vector is L2-normalised so
    cosine similarity reduces to a dot product. Deterministic and offline, which
    is exactly what CI needs.
    """

    def __init__(self, dim: int = 512) -> None:
        """Initialise the embedder.

        Args:
            dim: Output dimensionality. Larger reduces hash collisions.
        """
        self.dim = dim

    def _bucket(self, feature: str) -> int:
        """Hash a feature string to a stable bucket index in ``[0, dim)``."""
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dim

    def embed(self, text: str) -> List[float]:
        """Embed ``text`` into a unit vector of length :attr:`dim`.

        Args:
            text: Text to embed.

        Returns:
            An L2-normalised list of floats. Empty/whitespace text yields a zero
            vector, which has zero similarity to everything.
        """
        vec = [0.0] * self.dim
        for tok in tokenize(text):
            vec[self._bucket(tok)] += 1.0
            for i in range(len(tok) - 2):
                vec[self._bucket("_" + tok[i : i + 3])] += 0.5
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


class BedrockEmbedder:
    """Placeholder for the Phase 1 Bedrock embedder (fork #1).

    Deliberately not implemented: wiring live Bedrock is Phase 1 work and needs
    cloud credentials. It exists so ``PROOFGATE_EMBEDDER=bedrock`` is a real, selectable
    branch and so the seam is visible in the code today.
    """

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def embed(self, text: str) -> List[float]:  # pragma: no cover - Phase 1
        raise NotImplementedError(
            "BedrockEmbedder arrives in Phase 1; set PROOFGATE_EMBEDDER=local for now."
        )


def build_embedder(name: str, dim: int) -> Embedder:
    """Construct the embedder selected by configuration.

    Args:
        name: Embedder name, "local" or "bedrock".
        dim: Requested embedding dimensionality (local embedder only).

    Returns:
        A concrete :class:`Embedder`.

    Raises:
        ValueError: If ``name`` is not a known embedder.
    """
    if name == "local":
        return LocalHashingEmbedder(dim=dim)
    if name == "bedrock":
        return BedrockEmbedder(dim=dim)
    raise ValueError(f"unknown embedder: {name!r}")


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two equal-length vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Dot product of the two vectors. Inputs are assumed unit-normalised, so
        this equals cosine similarity; non-normalised inputs give an unnormalised
        dot product.
    """
    return sum(x * y for x, y in zip(a, b))
