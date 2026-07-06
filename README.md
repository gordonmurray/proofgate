# proofgate

proofgate is a reference deployment of a retrieval system on AWS, defined in
Terraform and shipped through a gated CI pipeline. The pipeline includes an
evaluation step that runs a versioned golden set against the deployed service and
fails the build if retrieval quality or latency falls outside configured thresholds.
A regression therefore cannot be promoted to production.

The motivation is simple. Most infrastructure is either up or down, and a health
check is enough to decide whether to ship. A retrieval system can pass every health
check and still return poor results, so proofgate adds a quality check to the
pipeline alongside the usual format, policy, build, and deploy steps.

proofgate is also the harness used to develop and validate Firn, the S3-backed
vector store on the request path.

## Example

The evaluation step runs the golden set against a live endpoint and compares recall
and latency to the thresholds. Running it against a deliberately broken corpus makes
it fail, which blocks promotion:

```
=== proofgate eval gate — http://127.0.0.1:8080 ===
recall@10: 0.3800  (baseline 0.9, floor 0.8)
p99: 210.85ms  p50: 127.32ms  (200 reqs)
  [FAIL] recall_floor: recall@10 0.3800 must be >= floor 0.8
  [FAIL] recall_drop_vs_baseline: drop 0.5200 vs baseline 0.9 must be <= 0.05
  [PASS] p99_latency_slo: p99 210.85ms must be <= SLO 750.0ms

EVAL GATE FAILED — promotion blocked.   # exit 1
```

The service stays healthy throughout; only recall drops. A full walkthrough is in
[docs/eval-gate-demo.md](docs/eval-gate-demo.md).

## Architecture

The system is split into three Terraform modules.

Runtime (the request path):

```
Client -> ALB -> ECS Fargate: retrieval-api
   |- embed query  -> local hashing embedder (default)  or  Bedrock (optional)
   |- vector + FTS -> Firn on S3 (foyer cache is internal to Firn)
   |- rerank       -> identity (default)  or  Bedrock (optional)
 -> ranked response
```

There is no separate cache tier. Caching is handled inside Firn (foyer), so the
cache-hit rate is a property of the store rather than a bolted-on service.

Delivery (GitHub Actions):

```
1 validate/fmt   ruff + terraform fmt/validate
2 policy scan    checkov
3 build          docker image
4 apply          staging (guarded on AWS credentials)
5 eval gate      recall@10 + p99 SLO
6 promote        prod, only if the eval gate passes
```

Observability:

```
retrieval-api (OTel SDK) -> OTel Collector -> Amazon Managed Prometheus -> Grafana
                                           -> Tempo or FirnTel
```

Eval results are exported as metrics, so recall and latency can be tracked over time
rather than only read from CI logs.

## Repository layout

```
proofgate/
  services/retrieval-api/   FastAPI orchestration service, instrumented with OpenTelemetry
  eval/                     golden set, thresholds, baseline, and the evaluation harness
  terraform/                three modules: runtime, delivery, observability
  .github/workflows/        the CI pipeline
  docs/                     design notes and the eval walkthrough
```

## Quickstart

Requires Python 3.11 or newer. The Terraform and checkov commands run via Docker;
see [docs/DESIGN.md](docs/DESIGN.md) for the tooling setup.

```bash
make install          # install retrieval-api and dev dependencies
make test             # unit tests (service and harness)
make lint             # ruff

# Run the service and the eval gate against it:
make serve &          # http://127.0.0.1:8080
make eval             # runs the golden set and reports pass/fail

# Infrastructure gates:
make tf-validate
make policy-scan
```

Query the running service:

```bash
curl -s localhost:8080/search \
  -H 'content-type: application/json' \
  -d '{"query": "what is the foyer cache", "k": 3}' | jq
```

## The eval gate

- **Golden set** ([`eval/golden.jsonl`](eval/golden.jsonl)): 50 queries against the
  demo corpus, versioned and reviewed like code, one `{query, relevant_ids, notes}`
  object per line.
- **Metrics**: macro recall@10 against the golden set, and p99 latency from a fixed,
  repeatable warm load run.
- **Thresholds** ([`eval/thresholds.toml`](eval/thresholds.toml)): an absolute recall
  floor, a maximum allowed drop from the committed
  [`baseline.json`](eval/baseline.json), and the p99 SLO in milliseconds. The baseline
  is only changed through a deliberate pull request; it is not ratcheted automatically
  from a passing run.
- **Mechanics**: the harness runs the golden set over the real HTTP path, writes
  `eval-report.json`, and exits non-zero on any breach. The promote job depends on it.

## Configuration

The same image runs in staging and production; behaviour comes from the environment.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROOFGATE_CORPUS_PATH` | bundled `demo.jsonl` | Corpus to index at startup |
| `PROOFGATE_EMBEDDER` | `local` | Embedder: `local` or `bedrock` |
| `PROOFGATE_RERANKER` | `none` | Reranker: `none` or `bedrock` |
| `PROOFGATE_ENV` | `local` | Environment label |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset)* | When set, spans are exported over OTLP |

Two choices are left configurable rather than fixed in code: Bedrock versus
self-hosted inference, and Tempo versus FirnTel for traces.

## Status

The current code runs retrieval-api against a local corpus, with the eval gate live
and able to fail, the three Terraform modules validating, and the pipeline green in
GitHub Actions. Bedrock embedding and reranking are configurable but not yet
implemented; the default embedder is the local one.

Design notes, conventions, and guardrails are in [docs/DESIGN.md](docs/DESIGN.md).
