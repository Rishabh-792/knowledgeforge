# ADR 0002 — Local-first fallbacks for every cloud dependency

**Status:** accepted

## Context

RAG reference implementations are usually un-runnable without a paid cloud
account, which kills evaluation, onboarding, and CI. We want `git clone` →
`pytest` → running API with zero credentials, while keeping one code path.

## Decision

Every external dependency sits behind a typed interface with a working local
implementation, and mode selection is automatic (derived from credential
presence, never a manual flag):

| Dependency | Azure implementation | Local fallback |
|------------|---------------------|----------------|
| Embeddings | Azure OpenAI | Deterministic signed feature hashing |
| Vector index | Azure AI Search | In-memory cosine + keyword store |
| Chat LLM | Azure OpenAI | Extractive mock over retrieved chunks |
| PII detection | Azure AI Language | Regex redactor |
| Content safety | Azure Content Safety | Keyword gate |

The fallbacks are *functional*, not stubs: hash embeddings give real
similarity signal for shared vocabulary, and the mock LLM answers from the
retrieved context, so the full pipeline is exercised end to end.

## Consequences

- CI and the demo run with no secrets; the security tests (RBAC, redaction,
  safety gate) execute on every push.
- Answer quality in local mode is intentionally modest — extractive, not
  generative. That is a feature: it proves grounding, since the mock cannot
  say anything that is not in a retrieved chunk.
- Auto-detection means a half-configured environment silently runs local;
  `/healthz` reports the active mode to make this observable.
