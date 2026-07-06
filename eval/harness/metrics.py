"""Pure metric functions for the eval gate.

Kept free of I/O so they can be unit-tested in isolation. Two metrics matter:
recall@k against the golden set (quality) and a latency percentile from the load
run (latency SLO).
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Set


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> float:
    """Recall@k for a single query.

    Args:
        retrieved_ids: Result ids from the service, best-first.
        relevant_ids: Known-relevant ids from the golden set.
        k: Cutoff; only the first ``k`` retrieved ids count.

    Returns:
        Fraction of relevant ids present in the top ``k`` results, in ``[0, 1]``.
        A query with no relevant ids returns 1.0 (nothing to miss).
    """
    relevant: Set[str] = set(relevant_ids)
    if not relevant:
        return 1.0
    top = set(retrieved_ids[:k])
    return len(top & relevant) / len(relevant)


def mean_recall_at_k(
    results: Sequence[Sequence[str]],
    relevants: Sequence[Iterable[str]],
    k: int,
) -> float:
    """Macro-averaged recall@k across queries.

    Macro (mean of per-query recall) is used rather than micro so a handful of
    queries with many relevant docs cannot dominate the headline number.

    Args:
        results: Per-query retrieved id lists.
        relevants: Per-query relevant id sets, aligned with ``results``.
        k: Cutoff.

    Returns:
        Mean recall@k over all queries; 0.0 if there are no queries.

    Raises:
        ValueError: If ``results`` and ``relevants`` differ in length.
    """
    if len(results) != len(relevants):
        raise ValueError("results and relevants must be the same length")
    if not results:
        return 0.0
    total = sum(recall_at_k(r, rel, k) for r, rel in zip(results, relevants))
    return total / len(results)


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile of ``values``.

    Args:
        values: Latency samples (any unit).
        pct: Percentile in ``[0, 100]``, e.g. 99 for p99.

    Returns:
        The nearest-rank percentile. Empty input returns 0.0.

    Raises:
        ValueError: If ``pct`` is outside ``[0, 100]``.
    """
    if not 0 <= pct <= 100:
        raise ValueError("pct must be in [0, 100]")
    if not values:
        return 0.0
    ordered: List[float] = sorted(values)
    # Nearest-rank: rank = ceil(pct/100 * N), 1-indexed.
    rank = max(1, -(-int(pct * len(ordered)) // 100))
    return ordered[min(rank, len(ordered)) - 1]
