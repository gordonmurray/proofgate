#!/usr/bin/env python3
"""Generate the demo corpus and golden set from a single curated source.

This script is the source of truth for three committed artifacts:

  - services/retrieval-api/corpus/demo.jsonl      the good corpus the API serves
  - services/retrieval-api/corpus/demo-bad.jsonl  a deliberately broken corpus
  - eval/golden.jsonl                             queries + relevant_ids

Keeping them generated from one place means the golden set can never drift out of
sync with the corpus by accident. The output files are committed and reviewed like
code (CLAUDE.md, "Eval gate"); regenerate with:

    python eval/tools/generate_demo_data.py

The "bad" corpus keeps every document id but rotates the *contents* onto the wrong
ids, so queries retrieve real-looking documents that are the wrong answers. That is
what lets the eval-gate demo fail visibly without crashing the service.

The output is deterministic: no randomness, stable ordering, so regenerating on a
clean checkout produces a byte-identical diff-free result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO / "services" / "retrieval-api" / "corpus"
GOLDEN = REPO / "eval" / "golden.jsonl"

# Each topic: (key, [(title, text), ...], [(query, [relevant local indices], notes), ...]).
Topic = Tuple[str, List[Tuple[str, str]], List[Tuple[str, List[int], str]]]

TOPICS: List[Topic] = [
    (
        "vpc",
        [
            ("VPC layout", "The reference VPC spans three availability zones with public and private subnets in each. Public subnets hold the ALB; private subnets hold the Fargate tasks."),
            ("NAT egress", "Private subnets reach the internet through NAT gateways, one per availability zone, so tasks can pull images and call Bedrock without being publicly reachable."),
            ("Subnet CIDRs", "The VPC uses a /16 CIDR block carved into /20 subnets, leaving headroom to add more services without renumbering the network."),
            ("VPC endpoints", "Gateway and interface VPC endpoints keep S3 and ECR traffic on the AWS backbone, avoiding NAT charges and reducing exposure for the vector store on S3."),
            ("Availability zones", "Spreading subnets across three zones lets the load balancer and ECS service survive the loss of a single zone without downtime."),
        ],
        [
            ("how many availability zones does the network use", [0, 4], "AZ spread"),
            ("how do private tasks reach the internet for image pulls", [1], "NAT egress"),
            ("how is S3 traffic kept off the public internet", [3], "VPC endpoints"),
            ("what CIDR block size does the VPC use", [2], "CIDR sizing"),
        ],
    ),
    (
        "alb",
        [
            ("Application Load Balancer", "The Application Load Balancer terminates TLS and forwards requests to the retrieval-api target group on the container port."),
            ("Listener rules", "Listener rules route by path: a single condition block matches the /search prefix and forwards to the retrieval-api target group."),
            ("Target group health", "The target group health check hits /health; unhealthy tasks are drained and replaced before they receive traffic."),
            ("HTTPS redirect", "An HTTP listener redirects every request to HTTPS so no query is ever served over plaintext."),
            ("Deregistration delay", "A short deregistration delay lets in-flight searches finish during a deploy before a task is removed from the target group."),
        ],
        [
            ("how does the load balancer check if a task is healthy", [2], "health check"),
            ("how are requests routed to the search service", [1], "listener rules"),
            ("is traffic forced onto TLS", [0, 3], "HTTPS"),
            ("what happens to in-flight requests during a deploy", [4], "deregistration"),
        ],
    ),
    (
        "ecs",
        [
            ("ECS Fargate service", "retrieval-api runs as an ECS Fargate service so there are no EC2 hosts to patch in phase 1; the platform manages the underlying capacity."),
            ("Task definition", "The task definition pins CPU and memory, the container image tag, and the environment variables that select the embedder and reranker forks."),
            ("Rolling deploys", "The service uses a rolling deployment with a minimum healthy percent so a new revision is validated by health checks before the old one is stopped."),
            ("Autoscaling", "Target-tracking autoscaling adds tasks when average CPU or request count per target crosses a threshold, keeping p99 latency inside the SLO under load."),
            ("Task role", "Each task assumes an IAM task role scoped to exactly the S3 prefix and Bedrock models it needs, nothing more."),
        ],
        [
            ("why are there no servers to patch in phase 1", [0], "fargate"),
            ("how does the service scale under load", [3], "autoscaling"),
            ("where are the embedder and reranker selected", [1], "task def env"),
            ("how is a new revision rolled out safely", [2], "rolling deploy"),
        ],
    ),
    (
        "firn_s3",
        [
            ("Firn on S3", "Firn stores vectors and the full-text index as objects on S3, so the corpus is durable and cheap and needs no database server to operate."),
            ("Foyer cache", "Firn's foyer cache keeps hot vectors and postings in memory and on local disk; the cache-hit rate is a property of Firn, not a separate cache tier."),
            ("No ElastiCache", "There is deliberately no ElastiCache or external cache in front of retrieval; caching lives inside Firn so the hit-rate story is not bolted on."),
            ("Corpus objects", "Documents, their embeddings, and the inverted index are written as immutable objects; a new corpus version is a new set of objects, never an in-place edit."),
            ("Cold reads", "On a cache miss Firn reads segments from S3 and warms the foyer cache, so the first query after a deploy is slower than the steady state."),
        ],
        [
            ("where does the vector store keep its data", [0, 3], "S3 storage"),
            ("what is the foyer cache", [1], "foyer"),
            ("why is there no separate cache tier like ElastiCache", [2], "no elasticache"),
            ("why is the first query after deploy slower", [4], "cold read"),
        ],
    ),
    (
        "embeddings",
        [
            ("Query embedding", "Each incoming query is embedded into a dense vector before the vector search runs; the same model embeds the documents at index time."),
            ("Bedrock embeddings", "In phase 1 the embedder calls Amazon Bedrock; the model id is configuration, so switching models never requires a code change."),
            ("Self-hosted embeddings", "Phase 2 can move embedding onto a GPU EC2 instance behind the same embedder interface, trading per-call cost for cold-start complexity."),
            ("Embedder as a fork", "Bedrock versus self-hosted inference is a deliberate fork kept addressable by an environment variable rather than decided prematurely."),
            ("Embedding dimensionality", "Higher-dimensional embeddings capture more nuance but cost more memory in the foyer cache; the dimension is tuned against the eval gate."),
        ],
        [
            ("how is a query turned into a vector", [0], "query embed"),
            ("can the embedding model be swapped without code changes", [1, 3], "config-selected"),
            ("what is the tradeoff of self-hosting embeddings", [2], "gpu tradeoff"),
            ("how is embedding dimension chosen", [4], "dimensionality"),
        ],
    ),
    (
        "reranking",
        [
            ("Rerank pass", "After hybrid retrieval, an optional rerank pass reorders the top candidates with a stronger cross-encoder before the response is returned."),
            ("Bedrock reranker", "The phase 1 reranker is a Bedrock model; like the embedder it is selected by configuration so the fork stays open."),
            ("Rerank window", "Reranking runs only over a small candidate window from the first-stage retrieval, keeping the extra latency bounded."),
            ("Rerank and latency", "Because reranking adds a model call it is measured against the p99 SLO; it is only enabled when the quality gain justifies the latency."),
            ("Identity reranker", "Until the real reranker is wired, an identity pass preserves ordering so the rerank code path and its span are exercised end to end."),
        ],
        [
            ("what does the rerank stage do", [0], "rerank purpose"),
            ("how is rerank latency kept bounded", [2], "window"),
            ("when should reranking be turned on", [3], "latency tradeoff"),
            ("is the reranker model configurable", [1], "config"),
        ],
    ),
    (
        "eval_gate",
        [
            ("Eval gate purpose", "The eval gate refuses to promote a build if retrieval quality or latency regresses; infra is up-or-down, but retrieval can be up and returning garbage."),
            ("Recall at k", "The gate measures recall@10 against a versioned golden set: the fraction of known-relevant documents that appear in the top ten results."),
            ("Thresholds and baseline", "Thresholds set an absolute recall floor and a maximum allowed drop versus a committed baseline; the baseline only moves through a deliberate pull request."),
            ("Golden set", "The golden set is versioned in the repository, one query and its relevant ids per line, and grows like a test suite through reviewed changes."),
            ("Failing the build", "The harness writes eval-report.json and exits non-zero on any breach, so the promote stage cannot run when quality or latency has regressed."),
        ],
        [
            ("why gate on quality instead of just health checks", [0], "the point"),
            ("what does recall at 10 measure", [1], "recall"),
            ("how is the baseline allowed to change", [2], "baseline policy"),
            ("what makes the pipeline actually fail on a regression", [4], "non-zero exit"),
            ("where does the golden set live", [3], "golden set"),
        ],
    ),
    (
        "latency",
        [
            ("p99 latency SLO", "The gate enforces a p99 latency SLO measured from a fixed, repeatable load run against a warmed staging endpoint."),
            ("Warm versus cold", "Latency is measured warm, after the foyer cache is primed, so the number reflects steady-state serving rather than cold starts."),
            ("Load run", "A fixed load generator replays a set of queries at a target concurrency and records the latency distribution used for the SLO check."),
            ("Tail latency", "Tail latency matters more than the average because a slow p99 means a real fraction of users wait too long, even if the mean looks fine."),
            ("Latency as a metric", "The p99 result is emitted as a metric so latency is graphable over time in Grafana, not just a pass or fail in one pipeline run."),
        ],
        [
            ("which latency percentile does the SLO use", [0, 3], "p99"),
            ("is latency measured warm or cold", [1], "warm"),
            ("how is the latency distribution produced", [2], "load run"),
            ("can latency be tracked over time", [4], "grafana metric"),
        ],
    ),
    (
        "tracing",
        [
            ("OpenTelemetry spans", "Every operation that crosses a process boundary emits an OpenTelemetry span; the retrieval-api instruments each handler and each downstream call."),
            ("OTel collector", "The service exports spans over OTLP to an OpenTelemetry Collector, which fans them out to the chosen trace backend."),
            ("Trace backend fork", "Tempo versus FirnTel is the second deliberate fork; the collector's exporter is swapped without touching application code."),
            ("Span attributes", "Spans carry attributes like the query length, k, and result count, so a slow trace can be read without guessing what the request was."),
            ("OTel versus Prometheus", "OpenTelemetry is how telemetry leaves the app; Prometheus and Grafana are where metrics land — layers, not competitors."),
        ],
        [
            ("what emits a span in the service", [0], "spans everywhere"),
            ("how do traces leave the application", [1], "collector"),
            ("what are the two trace backend options", [2], "tempo vs firntel"),
            ("how do otel and prometheus relate", [4], "layers not competitors"),
        ],
    ),
    (
        "metrics",
        [
            ("Prometheus metrics", "The collector forwards metrics to Prometheus, which stores the time series that Grafana then visualises."),
            ("Grafana dashboards", "Grafana dashboards show request rate, error rate, p99 latency, and the eval-gate recall over time on one pane."),
            ("Eval results as metrics", "Eval-gate results are emitted as metrics, so retrieval quality is a graph that trends, not only a pass or fail buried in CI logs."),
            ("Alerting", "Alerts fire when p99 crosses the SLO or recall drops below the floor, catching regressions that slip past a single pipeline run."),
            ("RED method", "Dashboards follow the RED method — rate, errors, duration — so an on-call engineer can triage the request path at a glance."),
        ],
        [
            ("where are metrics stored and graphed", [0, 1], "prom + grafana"),
            ("can retrieval quality be graphed over time", [2], "eval as metric"),
            ("what triggers an alert", [3], "alerting"),
            ("what dashboard method is used", [4], "RED"),
        ],
    ),
    (
        "cicd",
        [
            ("Pipeline stages", "The pipeline validates and formats, scans policy, builds the image, applies to staging, runs the eval gate, and only then promotes to prod."),
            ("Policy scanning", "Static policy scanning with checkov and trivy is an infra gate; a pipeline that skips it is considered broken."),
            ("Promotion", "Promotion to prod is guarded by the eval gate: the promote job runs only if the recall and latency checks pass."),
            ("Remote state", "Terraform state lives in S3 with locking; every change goes through plan output in the pipeline rather than an ad-hoc console edit."),
            ("Bad corpus demo", "A branch with a deliberately bad corpus fails the eval stage on purpose, proving the gate can stop a low-quality build from shipping."),
        ],
        [
            ("what are the ordered stages of the pipeline", [0], "stages"),
            ("what gates promotion to production", [2], "promote gate"),
            ("what infra checks run before build", [1], "policy scan"),
            ("how is terraform state managed", [3], "remote state"),
            ("how is the eval gate proven to work", [4], "bad corpus demo"),
        ],
    ),
    (
        "iam",
        [
            ("Least privilege", "Every role follows least privilege: the task role can read only its S3 prefix and invoke only the Bedrock models it actually uses."),
            ("CI role", "The pipeline assumes a scoped deploy role via OIDC, so no long-lived cloud keys are stored in the CI system."),
            ("Secrets handling", "Configuration is environment-driven and secrets come from the parameter store at task start, never baked into the image."),
            ("Network isolation", "Security groups allow only the ALB to reach the task port, and only the tasks to reach S3 and Bedrock endpoints."),
            ("Audit trail", "All infrastructure changes flow through reviewed plans, giving a complete audit trail with no out-of-band console edits."),
        ],
        [
            ("how are permissions scoped for a task", [0], "least privilege"),
            ("how does CI authenticate to the cloud without stored keys", [1], "oidc"),
            ("where do secrets come from at runtime", [2], "param store"),
            ("what can reach the container port", [3], "security groups"),
        ],
    ),
]


def build() -> Tuple[List[dict], List[dict]]:
    """Assemble the document list and golden query list from ``TOPICS``.

    Returns:
        A tuple ``(docs, golden)`` where ``docs`` is the list of corpus document
        objects and ``golden`` is the list of golden query objects.
    """
    docs: List[dict] = []
    golden: List[dict] = []
    # First pass: assign stable ids per topic so query relevance can reference them.
    topic_doc_ids: Dict[str, List[str]] = {}
    for t_index, (key, topic_docs, _) in enumerate(TOPICS):
        ids: List[str] = []
        for d_index, (title, text) in enumerate(topic_docs):
            doc_id = f"{key}-{d_index:02d}"
            ids.append(doc_id)
            docs.append({"id": doc_id, "title": title, "text": text, "topic": key})
        topic_doc_ids[key] = ids

    # Second pass: expand queries into golden rows with resolved relevant ids.
    for key, _topic_docs, queries in TOPICS:
        ids = topic_doc_ids[key]
        for query, relevant_local, notes in queries:
            golden.append(
                {
                    "query": query,
                    "relevant_ids": [ids[i] for i in relevant_local],
                    "notes": notes,
                }
            )
    return docs, golden


def make_bad(docs: List[dict]) -> List[dict]:
    """Produce the deliberately bad corpus by rotating contents onto wrong ids.

    Each document keeps its id but receives the title/text/topic of a different
    document (rotated by one). Queries then retrieve plausible-looking documents
    that are the wrong answers, so recall collapses and the eval gate fails.

    Args:
        docs: The good corpus documents.

    Returns:
        A new list of the same length with contents rotated by one position.
    """
    n = len(docs)
    bad: List[dict] = []
    for i, doc in enumerate(docs):
        donor = docs[(i + 1) % n]
        bad.append(
            {
                "id": doc["id"],
                "title": donor["title"],
                "text": donor["text"],
                "topic": donor["topic"],
            }
        )
    return bad


def write_jsonl(path: Path, rows: List[dict]) -> None:
    """Write ``rows`` to ``path`` as JSONL, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    """Generate all three artifacts and print a short summary."""
    docs, golden = build()
    bad = make_bad(docs)
    write_jsonl(CORPUS_DIR / "demo.jsonl", docs)
    write_jsonl(CORPUS_DIR / "demo-bad.jsonl", bad)
    write_jsonl(GOLDEN, golden)
    print(f"corpus: {len(docs)} docs -> {CORPUS_DIR / 'demo.jsonl'}")
    print(f"bad corpus: {len(bad)} docs -> {CORPUS_DIR / 'demo-bad.jsonl'}")
    print(f"golden: {len(golden)} queries -> {GOLDEN}")


if __name__ == "__main__":
    main()
