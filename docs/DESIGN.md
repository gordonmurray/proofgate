# proofgate — design

**No promotion without proof.** proofgate is a reference deployment of a production
retrieval system on AWS, defined entirely in code, whose pipeline refuses to ship a
build if retrieval quality or latency regresses.

The through-line: traditional infrastructure is up or down, so you gate on health
checks. A retrieval system can be up and returning garbage, so you gate on quality.
The eval gate is the thing that makes "it deployed" mean "it deployed *and it is
actually good*". The project proves out **Firn**, the S3-backed vector store at the
centre of the runtime.

The audience is engineers and the people who hire them. The moment worth showing is
pushing a deliberately bad corpus or config and watching the pipeline fail the eval
gate and refuse to promote.

## Architecture (three planes)

**Runtime — the request path**

```
Client -> ALB -> ECS Fargate: retrieval-api (orchestration)
    |- embed query  -> local hashing embedder (default)  OR  Bedrock (optional)
    |- vector + FTS -> Firn on S3 (foyer cache is internal to Firn)
    |- rerank       -> identity (default)  OR  Bedrock (optional)
 -> ranked response
```

There is no separate cache tier. Caching lives inside Firn (foyer); the cache-hit-rate
story is a Firn-internal property, not bolted-on infrastructure. Do not add ElastiCache.

**Delivery — GitHub Actions, gated**

```
1 validate/fmt   ruff + terraform fmt + validate      <- code + infra gate
2 policy scan    checkov (tfsec / trivy optional)      <- infra gate
3 build          docker image
4 apply          -> staging (guarded on AWS creds)
5 eval gate      recall@k, p99 SLO, optional LLM-judge <- quality gate
6 promote        -> prod, only if 5 passes
```

Stage 5 is the point of the whole project. It must be able to actually fail the build.

**Observability**

```
retrieval-api (OTel SDK) -> OTel Collector -> Prometheus (metrics) -> Grafana
                                           -> Tempo OR FirnTel (traces)
```

OpenTelemetry is how telemetry leaves the app; Prometheus and Grafana are where
metrics land and get looked at — layers, not competitors. Eval-gate results are also
emitted as metrics, so retrieval quality is graphable over time, not just pass/fail in CI.

## Eval gate

- **Golden set:** `eval/golden.jsonl`, versioned in the repo. One JSON object per line:
  `{"query": ..., "relevant_ids": [...], "notes": ...}`. It grows like a test suite, and
  changes go through PR review like code.
- **Metrics:** macro recall@10 against the golden set; p99 latency from a fixed,
  repeatable load run against a warmed staging endpoint. Optional nDCG later if graded
  relevance is added.
- **Thresholds:** live in `eval/thresholds.toml` — an absolute floor for recall@10, a
  maximum allowed drop versus the committed `eval/baseline.json`, and the p99 SLO in ms.
  The baseline is committed and only moves via a deliberate PR; it is never auto-ratcheted
  from a passing run.
- **Mechanics:** stage 5 runs the harness against the staging endpoint, writes
  `eval-report.json` as a CI artifact, and exits non-zero on any breach. The promote job
  requires it.
- **Optional LLM-judge:** sampled answer-quality scoring. Advisory until it proves stable,
  then optionally promoted to blocking.
- **The demo:** a branch with a deliberately bad corpus fails stage 5 visibly. See
  [eval-gate-demo.md](eval-gate-demo.md).

## Status and open choices

The current code runs retrieval-api against a local corpus, with the eval gate live and
able to fail, the three Terraform modules validating, and the pipeline green in CI.
Bedrock embedding and reranking are configurable seams but not yet implemented, so the
default embedder is the local one.

Two choices are kept addressable via config rather than fixed in code: Bedrock versus
self-hosted inference, and Tempo versus FirnTel as the trace backend.

## Conventions

**Terraform**
- `terraform fmt` and `validate` gate stage 1; checkov gates stage 2. A pipeline that
  skips either is broken.
- `aws_lb_listener_rule` takes singular `condition` and `action` blocks, not plurals.
- Remote state in S3 with locking. Every change goes through plan output in CI; no
  ad-hoc console changes.
- Modules per plane (`runtime/`, `delivery/`, `observability/`). Small and readable
  beats clever.

**retrieval-api**
- Python, FastAPI. Config via environment; the same image runs staging and prod.
- OpenTelemetry instrumentation is first-class: every handler and every downstream call
  emits spans. Every operation that crosses a process boundary emits a span.
- Every public function has a docstring; every module has a header comment explaining
  what it is and what it is not.

**Working norms**
- Conventional commits.
- Tests are part of the change, not a follow-up. PRs without tests are rejected by default.
- Schema and state changes go through migrations — no ad-hoc `ALTER`, including locally.

## Guardrails

No Ansible. No ElastiCache. No Packer until self-hosted inference is added. Each was cut
deliberately, not forgotten: Ansible has no natural home in a containerised architecture,
caching belongs inside Firn, and Packer only earns its place as a cold-start fix for
self-hosted GPU inference. If one of these seems needed, write the proposal first.

## Tooling

CLI tools (terraform, checkov) run via Docker rather than being installed onto the host,
so the environment stays reproducible. See the `tf-*` and `policy-scan` targets in the
`Makefile`; GitHub Actions uses the equivalent marketplace actions.

## Repository layout

```
proofgate/
  services/retrieval-api/   FastAPI orchestration service (OTel-first)
  eval/                     the eval gate: golden set, thresholds, baseline, harness, tools
  terraform/                three planes: runtime / delivery / observability
  .github/workflows/        the gated pipeline
  docs/                     design + the eval-gate demo walkthrough
```
