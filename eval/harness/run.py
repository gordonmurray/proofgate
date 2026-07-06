#!/usr/bin/env python3
"""Eval-gate entry point.

Runs the golden set against a live endpoint, measures recall@10 and p99 latency,
compares against ``thresholds.toml`` and ``baseline.json``, writes
``eval-report.json``, and exits non-zero on any breach.

Usage:
    python -m eval.harness.run --endpoint http://localhost:8080 \
        --golden eval/golden.jsonl --thresholds eval/thresholds.toml \
        --baseline eval/baseline.json --report eval-report.json

Exit codes:
    0  all checks passed
    1  a threshold was breached (quality or latency regression)
    2  the endpoint never became healthy / a request failed
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

# Allow running as a script (python eval/harness/run.py) as well as a module.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.harness.client import RetrievalClient  # noqa: E402
from eval.harness.metrics import mean_recall_at_k, percentile  # noqa: E402


@dataclass
class Check:
    """One pass/fail check in the report."""

    name: str
    passed: bool
    value: float
    limit: float
    detail: str


@dataclass
class Report:
    """The full eval-gate report, serialised to ``eval-report.json``."""

    endpoint: str
    k: int
    queries: int
    recall_at_10: float
    baseline_recall_at_10: float
    p99_ms: float
    p50_ms: float
    load_requests: int
    checks: List[Check]
    passed: bool


def load_golden(path: Path) -> List[dict]:
    """Load and validate the golden set from JSONL.

    Each row must have a non-empty ``query`` and a non-empty ``relevant_ids``. This
    is enforced here so a malformed or typoed golden row cannot silently become an
    empty-relevance query, which recall@k would score as a perfect 1.0 and thereby
    inflate the gate result.

    Args:
        path: Path to ``golden.jsonl``.

    Returns:
        The list of validated golden query rows.

    Raises:
        ValueError: If a row is missing its query or has empty ``relevant_ids``.
    """
    rows: List[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not row.get("query"):
            raise ValueError(f"{path}:{lineno} golden row missing a non-empty 'query'")
        if not row.get("relevant_ids"):
            raise ValueError(
                f"{path}:{lineno} golden row has empty 'relevant_ids'; every query "
                "must have at least one relevant id"
            )
        rows.append(row)
    return rows


def measure_recall(client: RetrievalClient, golden: List[dict], k: int) -> tuple[float, List[float]]:
    """Query the endpoint for every golden row and compute mean recall@k.

    Args:
        client: The retrieval client.
        golden: Golden query rows.
        k: Recall cutoff.

    Returns:
        A tuple ``(recall, latencies_ms)`` where ``recall`` is the macro recall@k
        and ``latencies_ms`` are the per-query latencies collected along the way.
    """
    results: List[List[str]] = []
    relevants: List[List[str]] = []
    latencies: List[float] = []
    for row in golden:
        res = client.search(row["query"], k=k)
        results.append(res.ids)
        relevants.append(row.get("relevant_ids", []))
        latencies.append(res.latency_ms)
    return mean_recall_at_k(results, relevants, k), latencies


def run_load(client: RetrievalClient, golden: List[dict], k: int, total: int, concurrency: int) -> List[float]:
    """Replay golden queries under concurrency to build a latency distribution.

    The endpoint is assumed warm (health already polled and recall already run),
    so these samples reflect steady-state serving, matching the SLO definition.

    Args:
        client: The retrieval client.
        golden: Golden query rows to replay (cycled to reach ``total``).
        k: Number of results per request.
        total: Total number of requests to issue.
        concurrency: Number of concurrent workers.

    Returns:
        The measured per-request latencies in milliseconds.
    """
    queries = [row["query"] for row in golden] or [""]
    plan = [queries[i % len(queries)] for i in range(total)]

    def _one(q: str) -> float:
        return client.search(q, k=k).latency_ms

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(_one, plan))


def evaluate(recall: float, baseline_recall: float, p99: float, cfg: Dict) -> List[Check]:
    """Build the list of pass/fail checks from measurements and config.

    Args:
        recall: Measured macro recall@k.
        baseline_recall: Committed baseline recall.
        p99: Measured p99 latency in ms.
        cfg: Parsed thresholds config.

    Returns:
        The checks, in report order.
    """
    floor = float(cfg["recall"]["floor"])
    max_drop = float(cfg["recall"]["max_drop"])
    p99_slo = float(cfg["latency"]["p99_slo_ms"])
    drop = baseline_recall - recall

    return [
        Check(
            name="recall_floor",
            passed=recall >= floor,
            value=round(recall, 4),
            limit=floor,
            detail=f"recall@10 {recall:.4f} must be >= floor {floor}",
        ),
        Check(
            name="recall_drop_vs_baseline",
            passed=drop <= max_drop,
            value=round(drop, 4),
            limit=max_drop,
            detail=f"drop {drop:.4f} vs baseline {baseline_recall} must be <= {max_drop}",
        ),
        Check(
            name="p99_latency_slo",
            passed=p99 <= p99_slo,
            value=round(p99, 2),
            limit=p99_slo,
            detail=f"p99 {p99:.2f}ms must be <= SLO {p99_slo}ms",
        ),
    ]


def main(argv: List[str] | None = None) -> int:
    """Run the eval gate and return a process exit code.

    Args:
        argv: Optional argument vector (for tests); defaults to ``sys.argv``.

    Returns:
        0 on pass, 1 on threshold breach, 2 on operational failure.
    """
    parser = argparse.ArgumentParser(description="proofgate eval gate")
    parser.add_argument("--endpoint", default="http://localhost:8080")
    parser.add_argument("--golden", type=Path, default=Path("eval/golden.jsonl"))
    parser.add_argument("--thresholds", type=Path, default=Path("eval/thresholds.toml"))
    parser.add_argument("--baseline", type=Path, default=Path("eval/baseline.json"))
    parser.add_argument("--report", type=Path, default=Path("eval-report.json"))
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args(argv)

    cfg = tomllib.loads(args.thresholds.read_text(encoding="utf-8"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    baseline_recall = float(baseline["recall_at_10"])
    golden = load_golden(args.golden)

    client = RetrievalClient(args.endpoint)
    if not client.wait_healthy():
        print(f"ERROR: endpoint {args.endpoint} never became healthy", file=sys.stderr)
        return 2

    try:
        recall, _ = measure_recall(client, golden, args.k)
        load_cfg = cfg.get("load", {})
        latencies = run_load(
            client,
            golden,
            args.k,
            total=int(load_cfg.get("total_requests", 200)),
            concurrency=int(load_cfg.get("concurrency", 8)),
        )
    except Exception as exc:  # operational failure, not a quality breach
        print(f"ERROR: load run failed: {exc}", file=sys.stderr)
        return 2

    p99 = percentile(latencies, 99)
    p50 = percentile(latencies, 50)
    checks = evaluate(recall, baseline_recall, p99, cfg)
    passed = all(c.passed for c in checks)

    report = Report(
        endpoint=args.endpoint,
        k=args.k,
        queries=len(golden),
        recall_at_10=round(recall, 4),
        baseline_recall_at_10=baseline_recall,
        p99_ms=round(p99, 2),
        p50_ms=round(p50, 2),
        load_requests=len(latencies),
        checks=checks,
        passed=passed,
    )
    args.report.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

    print(f"\n=== proofgate eval gate — {args.endpoint} ===")
    print(f"recall@{args.k}: {recall:.4f}  (baseline {baseline_recall}, floor {cfg['recall']['floor']})")
    print(f"p99: {p99:.2f}ms  p50: {p50:.2f}ms  ({len(latencies)} reqs)")
    for c in checks:
        print(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")
    print(f"report written to {args.report}")

    if not passed:
        print("\nEVAL GATE FAILED — promotion blocked.", file=sys.stderr)
        return 1
    print("\nEVAL GATE PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
