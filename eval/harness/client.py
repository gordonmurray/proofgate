"""Minimal HTTP client for the retrieval-api.

Uses only the standard library so the harness has no third-party dependencies of
its own — it must run anywhere the pipeline runs, including a bare CI image.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class SearchResult:
    """Outcome of one ``/search`` call.

    Attributes:
        ids: Retrieved document ids, best-first.
        latency_ms: Wall-clock latency of the request in milliseconds.
    """

    ids: List[str]
    latency_ms: float


class RetrievalClient:
    """Thin client wrapping the retrieval-api HTTP surface."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        """Initialise the client.

        Args:
            base_url: Base URL of the endpoint, e.g. ``http://localhost:8080``.
            timeout: Per-request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def wait_healthy(self, attempts: int = 60, delay: float = 1.0) -> bool:
        """Poll ``/health`` until the corpus is loaded or attempts run out.

        Args:
            attempts: Maximum number of polls.
            delay: Seconds to sleep between polls.

        Returns:
            True once ``/health`` reports ``status == "ok"``; False if it never
            becomes ready within ``attempts``.
        """
        for _ in range(attempts):
            try:
                with urllib.request.urlopen(
                    f"{self.base_url}/health", timeout=self.timeout
                ) as resp:
                    body = json.loads(resp.read())
                    if body.get("status") == "ok":
                        return True
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
            time.sleep(delay)
        return False

    def search(self, query: str, k: int = 10) -> SearchResult:
        """Run one search and time it.

        Args:
            query: Query text.
            k: Number of results to request.

        Returns:
            A :class:`SearchResult` with the retrieved ids and the measured latency.

        Raises:
            urllib.error.URLError: On transport failure.
        """
        payload = json.dumps({"query": query, "k": k}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read())
        latency_ms = (time.perf_counter() - start) * 1000.0
        ids = [hit["id"] for hit in body.get("results", [])]
        return SearchResult(ids=ids, latency_ms=latency_ms)
