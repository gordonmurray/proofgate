"""Tests for the /search endpoint and retrieval quality on the demo corpus."""

from __future__ import annotations

import pytest


def test_search_returns_k_results(client):
    """A normal query returns at most k ranked, descending-scored results."""
    resp = client.post(
        "/search", json={"query": "how does the load balancer health check work", "k": 5}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["k"] == 5
    assert 0 < len(body["results"]) <= 5
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_search_finds_relevant_document(client):
    """A pointed query surfaces the obviously-relevant document in the top 3."""
    resp = client.post("/search", json={"query": "what is the foyer cache", "k": 3})
    ids = [r["id"] for r in resp.json()["results"]]
    assert any(i.startswith("firn_s3") for i in ids)


def test_empty_query_rejected(client):
    """An empty query fails validation (422), never a silent empty search."""
    resp = client.post("/search", json={"query": "", "k": 5})
    assert resp.status_code == 422


@pytest.mark.parametrize("k", [0, 101])
def test_out_of_range_k_rejected(client, k):
    """k outside [1, 100] is rejected by request validation."""
    resp = client.post("/search", json={"query": "vpc subnets", "k": k})
    assert resp.status_code == 422


def test_rerank_path_runs(client):
    """The rerank=true path returns results (identity reranker preserves order)."""
    base = client.post("/search", json={"query": "reranking latency tradeoff", "k": 5}).json()
    reranked = client.post(
        "/search", json={"query": "reranking latency tradeoff", "k": 5, "rerank": True}
    ).json()
    assert [r["id"] for r in reranked["results"]] == [r["id"] for r in base["results"]]
