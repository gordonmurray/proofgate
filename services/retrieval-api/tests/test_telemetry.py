"""Tests that the request path is actually traced.

Tracing is non-optional (docs/DESIGN.md), so it gets a test like any other behaviour:
a search must emit the downstream retrieval spans, not just the HTTP span.
"""

from __future__ import annotations


def test_search_emits_downstream_spans(client, span_exporter):
    """A /search call produces spans for the handler and each retrieval stage."""
    client.post("/search", json={"query": "how are metrics stored and graphed", "k": 5})
    names = {span.name for span in span_exporter.get_finished_spans()}
    for expected in {
        "handler.search",
        "retrieval.search",
        "retrieval.embed_query",
        "retrieval.vector",
        "retrieval.fts",
    }:
        assert expected in names, f"missing span {expected}: got {sorted(names)}"


def test_span_carries_query_attributes(client, span_exporter):
    """The retrieval.search span records k and the query length for debugging."""
    client.post("/search", json={"query": "vpc availability zones", "k": 7})
    search_spans = [s for s in span_exporter.get_finished_spans() if s.name == "retrieval.search"]
    assert search_spans
    attrs = search_spans[-1].attributes
    assert attrs["retrieval.k"] == 7
    assert attrs["query.length"] > 0
