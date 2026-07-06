"""Shared pytest fixtures for the retrieval-api tests.

Builds a FastAPI ``TestClient`` against the shipped demo corpus, and an in-memory
OTel span exporter so tests can assert that the request path is traced.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture(scope="session")
def span_exporter() -> InMemorySpanExporter:
    """Install an in-memory span exporter as the global tracer provider.

    Must run before the app imports its tracer, so it is session-scoped and
    autouse-adjacent (pulled in by the ``client`` fixture below).
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


@pytest.fixture()
def client(span_exporter: InMemorySpanExporter) -> TestClient:
    """A TestClient with the app started (lifespan runs, corpus loaded)."""
    from app.main import app

    span_exporter.clear()
    with TestClient(app) as c:
        yield c
