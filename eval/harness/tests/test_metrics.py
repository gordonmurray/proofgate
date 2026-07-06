"""Unit tests for the pure eval-gate metric functions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from eval.harness.metrics import mean_recall_at_k, percentile, recall_at_k  # noqa: E402


def test_recall_at_k_full_hit():
    """All relevant ids inside the cutoff gives recall 1.0."""
    assert recall_at_k(["a", "b", "c"], ["a", "b"], k=3) == 1.0


def test_recall_at_k_respects_cutoff():
    """A relevant id beyond the cutoff is not counted."""
    assert recall_at_k(["x", "y", "a"], ["a"], k=2) == 0.0


def test_recall_at_k_partial():
    """Half the relevant ids present gives recall 0.5."""
    assert recall_at_k(["a", "z"], ["a", "b"], k=10) == 0.5


def test_recall_no_relevant_is_one():
    """A query with no relevant ids cannot be missed; recall is 1.0."""
    assert recall_at_k(["a"], [], k=10) == 1.0


def test_mean_recall_averages_per_query():
    """Macro recall is the mean of per-query recall."""
    results = [["a"], ["z"]]
    relevants = [["a"], ["b"]]
    assert mean_recall_at_k(results, relevants, k=10) == 0.5


def test_mean_recall_length_mismatch():
    """Mismatched inputs are a programming error, not silent."""
    with pytest.raises(ValueError):
        mean_recall_at_k([["a"]], [], k=10)


def test_percentile_nearest_rank():
    """p99 of 1..100 is 100; p50 is the median-ish nearest rank."""
    values = list(range(1, 101))
    assert percentile(values, 99) == 99
    assert percentile(values, 100) == 100
    assert percentile(values, 50) == 50


def test_percentile_empty():
    """Empty input yields 0.0 rather than raising."""
    assert percentile([], 99) == 0.0


def test_percentile_out_of_range():
    """A percentile outside [0, 100] is rejected."""
    with pytest.raises(ValueError):
        percentile([1.0], 150)
