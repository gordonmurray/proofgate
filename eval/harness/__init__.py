"""proofgate eval-gate harness.

Stage 5 of the pipeline and the point of the whole project: it runs the golden
set against a live staging endpoint, measures recall@10 and p99 latency, compares
them to committed thresholds and baseline, writes ``eval-report.json``, and exits
non-zero on any breach so the promote stage cannot run on a regression.

What it is NOT: it does not talk to the retriever in-process. It exercises the real
HTTP request path (ALB -> retrieval-api in production, localhost in CI) so the
numbers reflect what a client would actually get.
"""

__version__ = "0.1.0"
