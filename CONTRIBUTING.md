# Contributing

Thanks for your interest in proofgate. This is a reference deployment, so the bar
is "clear enough to learn from and strict enough to trust." A few conventions keep it
that way.

## Development setup

Requires Python 3.11+. CLI tools (terraform, checkov) run via Docker.

```bash
make install     # install retrieval-api + dev deps
make test        # unit tests (service + harness)
make lint        # ruff
make serve &     # run the service locally on :8080
make eval        # run the eval gate against it
```

Infra gates:

```bash
make tf-validate
make policy-scan
```

## Ground rules

- **Conventional commits** (`feat:`, `fix:`, `docs:`, `build:`, `chore:` …).
- **Tests are part of the change.** PRs without tests are rejected by default.
- **Every process boundary emits an OpenTelemetry span.** Tracing is not optional.
- **Every public function has a docstring**; every module has a header comment saying
  what it is and what it is not.
- Schema and state changes go through migrations — no ad-hoc `ALTER`, including locally.

## The eval gate

The golden set (`eval/golden.jsonl`), thresholds (`eval/thresholds.toml`), and baseline
(`eval/baseline.json`) are reviewed like code. The baseline only moves via a deliberate
PR — never auto-ratcheted from a passing run. If you change retrieval behaviour, expect
to justify the effect on recall and latency in the PR.

The demo corpus and golden set are generated:

```bash
make gen         # regenerate; CI fails if the committed data is out of sync
```

## Pull requests

Open a PR against `main`. CI runs the full pipeline (lint, tests, terraform, policy
scan, eval gate). All required checks must pass before merge. See
[docs/DESIGN.md](docs/DESIGN.md) for the architecture and conventions.
