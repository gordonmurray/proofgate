# proofgate

**A reference deployment of a production retrieval system on AWS, defined entirely
in code, that refuses to ship if retrieval quality or latency regresses.**

Traditional infrastructure is up or down, so you gate deploys on health checks. A
retrieval system can be *up and returning garbage* — so proofgate gates on **quality**.
The eval gate is to this project what a compliance check is to an infrastructure
showcase: the thing that makes "it deployed" mean "it deployed **and it is actually
good**".

> **proofgate**: *no promotion without proof.* The project proves out **Firn**, the
> S3-backed vector store at the centre of the runtime — and refuses to ship a build
> that can't prove its quality at the gate.

---

## The idea in one screenshot

Push a deliberately bad corpus and watch the pipeline refuse to promote it:

```
=== proofgate eval gate — http://127.0.0.1:8080 ===
recall@10: 0.3800  (baseline 0.9, floor 0.8)
p99: 210.85ms  p50: 127.32ms  (200 reqs)
  [FAIL] recall_floor: recall@10 0.3800 must be >= floor 0.8
  [FAIL] recall_drop_vs_baseline: drop 0.5200 vs baseline 0.9 must be <= 0.05
  [PASS] p99_latency_slo: p99 210.85ms must be <= SLO 750.0ms

EVAL GATE FAILED — promotion blocked.   # exit 1
```

The service is healthy the whole time. Health checks are green. Recall is not.
See [docs/eval-gate-demo.md](docs/eval-gate-demo.md).

---

## Architecture (three planes)

**Runtime — the request path**

```
Client -> ALB -> ECS Fargate: retrieval-api (orchestration)
   |- embed query  -> local hashing embedder (phase 0/1)  OR  Bedrock (phase 1)
   |- vector + FTS -> Firn on S3 (foyer cache is internal to Firn)
   |- rerank       -> identity (phase 0)  OR  Bedrock (phase 1)
 -> ranked response
```

There is no separate cache tier. Caching lives **inside Firn** (foyer); the
cache-hit-rate story is a Firn-internal property, not bolted-on infrastructure.

**Delivery — GitHub Actions, gated**

```
1 validate/fmt   ruff + terraform fmt/validate     <- code + infra gate
2 policy scan    checkov                            <- infra gate
3 build          docker image
4 apply          -> staging (guarded on AWS creds)
5 eval gate      recall@10 + p99 SLO                <- QUALITY GATE (the point)
6 promote        -> prod, only if 5 passes
```

**Observability**

```
retrieval-api (OTel SDK) -> OTel Collector -> Amazon Managed Prometheus -> Grafana
                                           -> Tempo OR FirnTel (phase 2 fork)
```

Eval-gate results are emitted as metrics, so retrieval quality is graphable over
time — not just pass/fail in one CI run.

---

## Repository layout

```
proofgate/
  services/retrieval-api/   FastAPI orchestration service (OTel-first)
  eval/                     the eval gate: golden set, thresholds, harness, generator
  terraform/                three planes: runtime / delivery / observability
  .github/workflows/        the gated pipeline
  docs/                     the eval-gate demo walkthrough
```

---

## Quickstart

Requires Python 3.11+. CLI tools (terraform, checkov) run via Docker — see
[docs/DESIGN.md](docs/DESIGN.md) for the tooling convention.

```bash
make install          # install retrieval-api + dev deps
make test             # unit tests (service + harness)
make lint             # ruff

# Run the service and the eval gate against it:
make serve &          # http://127.0.0.1:8080
make eval             # EVAL GATE PASSED

# Infra gates (Docker):
make tf-validate
make policy-scan
```

Try a query:

```bash
curl -s localhost:8080/search \
  -H 'content-type: application/json' \
  -d '{"query": "what is the foyer cache", "k": 3}' | jq
```

---

## The eval gate

- **Golden set** — [`eval/golden.jsonl`](eval/golden.jsonl), 50 queries against the
  demo corpus, versioned and reviewed like code. One `{query, relevant_ids, notes}`
  object per line.
- **Metrics** — macro recall@10 against the golden set; p99 latency from a fixed,
  repeatable warm load run.
- **Thresholds** — [`eval/thresholds.toml`](eval/thresholds.toml): an absolute
  recall floor, a max allowed drop versus the committed
  [`baseline.json`](eval/baseline.json), and the p99 SLO in ms. The baseline moves
  only via a deliberate PR — never auto-ratcheted from a passing run.
- **Mechanics** — the harness runs the golden set through the real HTTP path,
  writes `eval-report.json`, and exits non-zero on any breach; `promote` requires it.

---

## Configuration

The same image runs staging and prod; behaviour is driven by the environment.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROOFGATE_CORPUS_PATH` | bundled `demo.jsonl` | Corpus to index at startup |
| `PROOFGATE_EMBEDDER` | `local` | Embedder fork: `local` or `bedrock` |
| `PROOFGATE_RERANKER` | `none` | Reranker fork: `none` or `bedrock` |
| `PROOFGATE_ENV` | `local` | Environment label |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset)* | When set, spans export over OTLP |

Two forks are kept addressable via config rather than decided prematurely:
Bedrock vs self-hosted inference, and Tempo vs FirnTel for traces.

---

## Phasing

- **Phase 0 — skeleton (this repo).** retrieval-api runnable against a local corpus,
  the eval gate live and able to fail, Terraform for the three planes validated,
  the full pipeline green in GitHub Actions.
- **Phase 1 — the point.** Bedrock embed + rerank wired in; golden set grown; the
  bad-corpus demo captured end to end.
- **Phase 2 — the forks.** Self-hosted GPU inference (Packer enters here as the
  cold-start fix); FirnTel as a trace backend; LLM-judge experiments.

See [docs/DESIGN.md](docs/DESIGN.md) for the full design, conventions, and guardrails.
