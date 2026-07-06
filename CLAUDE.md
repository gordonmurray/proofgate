# CLAUDE.md

Name: `proofgate` — no promotion without proof. The project exists to prove out Firn (the S3-backed vector store at the centre of the runtime): it will not ship a retrieval build that cannot prove its quality and latency at the gate.

## What this is

A reference deployment of a production retrieval system on AWS, fully defined in code, that **refuses to ship if retrieval quality or latency regresses**.

The through-line: traditional infra is up or down, so we gate on health checks. A retrieval system can be up and returning garbage, so we gate on quality. The eval gate is to this project what an InSpec compliance check was to a 2018 IaC showcase: the thing that makes "it deployed" mean "it deployed *and it is actually good*".

Audience is engineers and the people who hire them. The screenshot moment is pushing a deliberately bad corpus or config and watching the pipeline fail the eval gate and refuse to promote. Build toward that moment.

## Architecture (three planes)

**Runtime (the request path)**
```
Client -> ALB -> ECS Fargate: retrieval-api (orchestration)
    |- embed query  -> Bedrock (phase 1)  OR  self-hosted on GPU EC2 (phase 2)
    |- vector + FTS -> Firn on S3 (foyer cache is internal to Firn)
    |- rerank       -> Bedrock (phase 1)  OR  self-hosted reranker (phase 2)
 -> response
```
There is no separate cache tier. Caching lives inside Firn (foyer). Do not add ElastiCache. The cache-hit-rate story is a Firn-internal property, not bolted-on infrastructure.

**Delivery (GitHub Actions, gated)**
```
1 validate/fmt    ruff + terraform fmt + validate
2 policy scan     checkov (tfsec / trivy optional)   <- infra gate
3 build           docker image (+ packer AMI in phase 2)
4 plan + apply    -> staging  (guarded on AWS creds)
5 eval gate       recall@k, p99 SLO, optional LLM-judge   <- quality gate
6 promote         -> prod  (only if 5 passes)
```
Stage 5 is the point of the whole project. It must be able to actually fail the build (see Eval gate below).

CI runs on **GitHub Actions** (`.github/workflows/ci.yml`), the single source of truth for the pipeline. The original design named GitLab CI; the delivery plane was moved to GitHub Actions so the repo host and the pipeline are the same system, and so branch protection can gate auto-merge on the eval gate. The six stages and the eval-gate contract are unchanged.

**Observability**
```
retrieval-api (OTel SDK) -> OTel Collector -> Prometheus (metrics) -> Grafana
                                           -> Tempo OR FirnTel (traces)
```
OTel and Prometheus/Grafana are layers, not competitors: OTel is how telemetry leaves the app; Prometheus and Grafana are where metrics land and get looked at. Eval gate results are also emitted as metrics, so retrieval quality is graphable over time, not just pass/fail in CI.

## Eval gate

- **Golden set:** `eval/golden.jsonl`, versioned in the repo. One JSON object per line: `{"query": ..., "relevant_ids": [...], "notes": ...}`. Start around 50 queries against the demo corpus and grow it like a test suite. Changes to the golden set go through PR review like code.
- **Metrics:** recall@10 against the golden set; p99 latency from a fixed, repeatable load run against staging (warm). Optional nDCG later if graded relevance is added.
- **Thresholds:** live in `eval/thresholds.toml`: an absolute floor for recall@10, a max allowed drop versus the committed baseline, and the p99 SLO in ms. The baseline is committed to the repo and only moves via a deliberate PR. Never auto-ratchet the baseline from a passing run.
- **Mechanics:** stage 5 runs the harness against the staging endpoint, writes `eval-report.json` as a CI artifact, and exits non-zero on any breach. The promote job requires it.
- **Optional LLM-judge:** sampled answer-quality scoring. Advisory (reported, not blocking) until it proves stable across runs, then optionally promoted to blocking.
- **The demo:** a branch with a deliberately bad corpus or embedding config must fail stage 5 visibly. That failing pipeline screenshot is the marketing asset. Keep the branch around.

## Phasing

**Phase 0 — skeleton.** Terraform for VPC, ALB, ECS; retrieval-api stub deployed; pipeline stages 1–4 green; Firn on S3 with a small corpus.

**Phase 1 — the point.** Bedrock embed and rerank wired in; golden set v1; eval gate live and able to fail; the bad-corpus demo captured end to end.

**Phase 2 — the forks.** Self-hosted inference on GPU EC2 (Packer enters here, and only here, as the cold-start fix); FirnTel as the trace backend option; LLM-judge experiments.

Two deliberate forks, kept addressable via config rather than decided prematurely:
1. Bedrock vs self-hosted inference.
2. Tempo vs FirnTel as trace backend.

## Terraform conventions

- `terraform fmt` and `validate` gate stage 1; checkov/tfsec/trivy gate stage 2. A pipeline that skips either is broken.
- Precise syntax matters: `aws_lb_listener_rule` takes singular `condition` and `action` blocks, not plurals.
- Remote state in S3 with locking. No ad-hoc console changes; every change goes through plan output in CI.
- Modules per plane (`runtime/`, `delivery/`, `observability/`). Small and readable beats clever.

## retrieval-api conventions

- Python, FastAPI.
- OTel instrumentation is first-class, not a follow-up: every handler and every downstream call (Bedrock, Firn) emits spans from the first commit.
- Config via environment; the same image runs staging and prod.
- Every public function has a docstring. Every module has a header comment explaining what it is and what it is not.

## Guardrails

- **No Ansible. No ElastiCache. No Packer before Phase 2.** Each was cut deliberately, not forgotten. Ansible and InSpec have no natural home in a containerised architecture; InSpec's spirit lives on as policy scanning plus the eval harness. If one of these seems needed, write the proposal first.

## Project conventions

These are non-negotiable. They exist because past projects without them produced lower-quality output and slower iteration.

- **Two-attempt debug limit.** After two failed attempts at the same bug, stop and propose a different approach in writing. Do not loop.
- **Propose before implement.** For any change touching more than one file or introducing a new dependency, write the proposal before writing code.
- **Migrations only** for schema and state changes. No ad-hoc `ALTER` anywhere, including local.
- **No AI attribution** in commits, PRs, docs, or blog posts. Ever. This project is human-authored; Claude is a development tool in the same way a compiler is.
- **Conventional commits.**
- **Tests are part of the change**, not a follow-up. PRs without tests are rejected by default.
- **Tracing is non-optional.** Every operation that crosses a process boundary emits an OpenTelemetry span.
- Claude Code runs with `--permission-mode bypassPermissions`; git worktrees for parallel sessions.

## Repository layout

```
proofgate/
  terraform/
    runtime/
    delivery/
    observability/
  services/
    retrieval-api/
  eval/
    golden.jsonl
    thresholds.toml
    baseline.json
    harness/
    tools/
  .github/
    workflows/
  docs/
  CLAUDE.md
  README.md
```

## Tooling

CLI tools are installed via **Docker**, not onto the host, so the environment is
reproducible and nothing is left behind on the machine. Terraform and checkov run
through their official images (see the `tf-*` and `policy-scan` targets in the
`Makefile`); GitHub Actions uses the equivalent marketplace actions. `gh` (the
GitHub CLI) is installed and authenticated for repo, PR, and merge automation.
