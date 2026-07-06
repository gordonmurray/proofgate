"""Tests for liveness and metadata endpoints."""

from __future__ import annotations


def test_health_ok_after_startup(client):
    """/health reports ok and a non-empty corpus once startup has run."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["corpus_size"] > 0


def test_root_metadata(client):
    """/ returns the service identity and the selected forks."""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "retrieval-api"
    assert body["embedder"] == "local"
    assert body["reranker"] == "none"
