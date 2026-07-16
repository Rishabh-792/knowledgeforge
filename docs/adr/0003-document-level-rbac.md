# ADR 0003 — Document-level RBAC enforced in the store query

**Status:** accepted

## Context

Enterprise knowledge bases mix world-readable handbooks with restricted
material (HR, finance, legal). A RAG system that retrieves first and filters
later can leak restricted text into prompts, logs, or truncated result sets —
and post-filtering breaks `top_k` (you asked for 5, got 2 after filtering).

## Decision

- Every chunk carries `acl_groups`, set at ingest time; `public` marks
  world-readable content.
- Every JWT carries the caller's `groups`; roles (`reader`/`curator`/`admin`)
  gate endpoints, groups gate documents. Admin bypasses the group filter.
- The visibility predicate executes **inside** the store query: an OData
  filter in Azure AI Search, an in-scan predicate in the in-memory store. It
  is part of the `VectorStore.hybrid_search` contract, so no implementation
  can skip it.

## Consequences

- Restricted chunks never enter the application layer, the LLM prompt, or the
  logs for an unauthorized caller.
- `top_k` always means "top k *visible* results".
- Group membership is trusted from the JWT; the identity provider owns group
  assignment. Token TTL bounds staleness after a group change.
- Chunk-level ACLs inherit from the document today. Row-level (per-section)
  security would reuse the same mechanism with finer-grained `acl_groups`.
