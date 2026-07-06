"""proofgate retrieval-api.

This package is the request-path orchestration service: it takes a query,
embeds it, runs vector + full-text retrieval against the local corpus (a stand-in
for Firn on S3), optionally reranks, and returns ranked results.

What it is NOT:
  - It is not the vector store itself. In production that is Firn on S3; here it
    is an in-memory index loaded from a JSONL corpus.
  - It is not a cache tier. Caching lives inside Firn (foyer), never here.
"""

__version__ = "0.1.0"
