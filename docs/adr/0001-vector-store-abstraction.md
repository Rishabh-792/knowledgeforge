# ADR 0001 — Vector store behind a Protocol

**Status:** accepted

## Context

The platform targets Azure AI Search, but the retrieval logic (hybrid scoring,
ACL filtering, citation assembly) is engine-agnostic. Coupling the RAG
pipeline to one SDK makes local development require cloud credentials and
makes future engine swaps (Qdrant, pgvector) invasive.

## Decision

Define a `VectorStore` Protocol (`upsert`, `hybrid_search`, `delete_document`,
`delete_category`, `list_documents`) and ship two implementations:

- `InMemoryStore` — complete reference implementation with cosine + keyword
  hybrid scoring and ACL filtering; the local-mode backend and the test
  fixture.
- `AzureAISearchStore` — production adapter mapping the same contract onto
  vector + BM25 hybrid queries with OData filters.

Dependency providers select the implementation from settings; routes and the
RAG pipeline see only the Protocol.

## Consequences

- The entire pipeline is testable offline; CI needs zero secrets.
- The contract keeps ACL filtering *inside* the store query on every engine.
- Each new engine costs one adapter file (Qdrant is on the roadmap).
- Hybrid score semantics differ slightly per engine (RRF vs weighted sum);
  scores are comparable within one engine, not across engines. Acceptable —
  ranking, not the absolute score, is the interface guarantee.
