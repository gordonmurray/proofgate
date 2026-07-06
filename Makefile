# Developer convenience targets. These mirror what the CI pipeline does so you
# can run any gate locally before pushing.
#
# Tooling note: this project installs CLI tools (terraform, checkov) via Docker
# rather than onto the host — see CLAUDE.md > Tooling.

PY ?= python3
SERVICE := services/retrieval-api
CORPUS ?= $(SERVICE)/corpus/demo.jsonl
ENDPOINT ?= http://127.0.0.1:8080

.PHONY: help install test lint gen serve eval eval-bad tf-fmt tf-validate policy-scan build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS=":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install retrieval-api with dev dependencies
	pip install -e "$(SERVICE)[dev]"

test: ## Run all unit tests
	cd $(SERVICE) && pytest -q
	pytest -q eval/harness/tests

lint: ## Ruff lint
	ruff check $(SERVICE) eval

gen: ## Regenerate the demo corpus + golden set
	$(PY) eval/tools/generate_demo_data.py

serve: ## Run retrieval-api locally (CORPUS overrides the corpus)
	PROOFGATE_CORPUS_PATH="$(CORPUS)" $(PY) -m uvicorn app.main:app \
		--host 127.0.0.1 --port 8080 --app-dir $(SERVICE)

eval: ## Run the eval gate against a running endpoint (expects PASS)
	$(PY) -m eval.harness.run --endpoint $(ENDPOINT)

eval-bad: ## Serve the bad corpus + run the gate (expects FAIL) — the demo
	@echo "Start a bad-corpus server with: make serve CORPUS=$(SERVICE)/corpus/demo-bad.jsonl"
	$(PY) -m eval.harness.run --endpoint $(ENDPOINT)

tf-fmt: ## terraform fmt (via Docker)
	docker run --rm -v "$(PWD)/terraform:/tf" -w /tf hashicorp/terraform:1.9.8 fmt -recursive

tf-validate: ## terraform validate (via Docker)
	docker run --rm -v "$(PWD)/terraform:/tf" -w /tf hashicorp/terraform:1.9.8 init -backend=false
	docker run --rm -v "$(PWD)/terraform:/tf" -w /tf hashicorp/terraform:1.9.8 validate

policy-scan: ## checkov over terraform/ (via Docker)
	docker run --rm -v "$(PWD)/terraform:/tf" bridgecrew/checkov:latest -d /tf --config-file /tf/.checkov.yaml

build: ## Build the retrieval-api image
	docker build -t retrieval-api:local $(SERVICE)
