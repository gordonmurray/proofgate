# The eval-gate demo: making the pipeline refuse a bad build

This is the screenshot moment. Traditional infra is up or down, so you gate on
health checks. A retrieval system can be **up and returning garbage**, so we gate
on quality. This page shows the gate doing its job.

## What the gate checks

Stage 5 of the pipeline runs `eval/harness/run.py` against a live endpoint and
enforces three contracts from `eval/thresholds.toml`:

| Check | Meaning | Source |
| --- | --- | --- |
| `recall_floor` | recall@10 over the golden set must be ≥ an absolute floor | `thresholds.toml` |
| `recall_drop_vs_baseline` | recall@10 may not drop more than `max_drop` below the committed baseline | `baseline.json` |
| `p99_latency_slo` | p99 latency from a warm load run must be ≤ the SLO | `thresholds.toml` |

Any breach writes `eval-report.json` and exits non-zero, so the `promote` job
cannot run.

## Run it locally

Good corpus — the gate passes:

```bash
make serve &                      # serves corpus/demo.jsonl
make eval                         # -> EVAL GATE PASSED, exit 0
```

Bad corpus — the gate fails:

```bash
make serve CORPUS=services/retrieval-api/corpus/demo-bad.jsonl &
make eval                         # -> EVAL GATE FAILED, exit 1
```

The "bad" corpus keeps every document id but rotates the contents onto the wrong
ids (see `eval/tools/generate_demo_data.py`). The service stays healthy and
returns plausible-looking documents — they are simply the wrong answers. Health
checks are green; recall collapses from ~0.91 to ~0.38; the gate stops the build.

## Run it in CI

The `demo/bad-corpus` branch points the eval-gate job at `demo-bad.jsonl` by
changing a single line in `.github/workflows/ci.yml`:

```yaml
      CORPUS: services/retrieval-api/corpus/demo-bad.jsonl
```

Open a PR from that branch and the required **eval-gate** check goes red, so the
PR cannot merge. That failing pipeline is the marketing asset. Keep the branch
around; do not merge it.
