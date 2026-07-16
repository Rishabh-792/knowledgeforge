# KnowledgeForge

**An Azure-native enterprise knowledge platform: ingestion → hybrid retrieval → RAG chat, with document-level RBAC, PII redaction, and content safety built into the pipeline — and a credential-free local mode so the whole thing runs on your laptop.**

![CI](https://img.shields.io/badge/CI-passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Mode](https://img.shields.io/badge/runs%20offline-yes-8A2BE2)

## Why this exists

Enterprise knowledge lives in a hundred places — wikis, policy PDFs, shared
drives, product docs — and most RAG demos ignore the part that actually makes
enterprise search hard: **not everyone is allowed to see everything**. This
repository is a production-grade reference implementation that treats
security as part of the retrieval pipeline, not an afterthought: ACL filtering
happens inside the index query, PII is redacted before anything is embedded,
and a content-safety gate fronts both ingestion and chat.

The second problem with reference implementations is that they demand a cloud
bill before they run. KnowledgeForge doesn't: every Azure dependency has a
functional local fallback behind the same interface, so `clone → install →
demo` works with zero credentials, and adding Azure keys flips the same code
paths onto Azure OpenAI and Azure AI Search.

## Features

- **Ingestion pipeline** — safety gate → PII redaction → recursive chunking
  with overlap → embeddings → index upsert, via API upload or a blob-triggered
  batch handler.
- **Hybrid retrieval** — vector similarity + keyword scoring merged into one
  ranked result set, with metadata (category) filters.
- **RAG chat** — grounded prompting with numbered citations and per-session
  history behind a swappable session store.
- **Agentic loop** — a tool-calling agent (retrieval + AST-safe calculator)
  with a max-iterations guard.
- **Document-level RBAC** — JWT roles (`reader`/`curator`/`admin`) gate
  endpoints; per-document ACL groups gate what search can even see.
- **PII redaction** — regex redactor locally, Azure AI Language in cloud mode.
- **Content safety** — keyword gate locally, Azure Content Safety in cloud mode.
- **Ops-ready** — structured JSON logs with request IDs, `/healthz`, Docker,
  Terraform for the full Azure footprint, CI/CD workflows.

## Architecture

```mermaid
flowchart LR
    CLIENT[Client] -->|Bearer JWT| API[FastAPI]
    API --> AUTH[Auth + RBAC]
    AUTH --> RAG[RAG orchestrator]
    RAG --> AGENT[Agent loop]
    RAG -->|embed + complete| LLM[Azure OpenAI<br/>local: hash embedder + mock LLM]
    RAG -->|hybrid query + ACL filter| IDX[(Azure AI Search<br/>local: in-memory store)]

    subgraph Ingestion
        UP[API upload / blob trigger] --> SAFE[Safety gate] --> PII[PII redaction]
        PII --> CHUNK[Chunker] --> EMB[Embedder] --> IDX
    end
```

Deep dive with sequence diagrams, data model, and scaling notes:
[docs/architecture.md](docs/architecture.md). Design decisions:
[docs/adr/](docs/adr/).

## Tech stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI, pydantic v2, pydantic-settings |
| Auth | JWT (PyJWT), role hierarchy + ACL groups |
| Retrieval | Azure AI Search (hybrid) / in-memory cosine + keyword |
| Generation | Azure OpenAI / extractive mock LLM |
| Safety | Azure AI Language, Azure Content Safety / regex + keyword gates |
| Batch ingestion | Functions-style blob trigger, pypdf, python-docx |
| Infra | Terraform (azurerm), Docker, App Service, Key Vault, Log Analytics |
| CI/CD | GitHub Actions: ruff + pytest, container build → ACR → App Service |

## Quickstart (no cloud account needed)

```bash
git clone <this-repo> && cd knowledgeforge
pip install -r requirements-dev.txt
python scripts/demo.py
```

Expected output (abridged):

```text
== KnowledgeForge demo (mode: local) ==

[1/4] Seeding sample documents...
  indexed atlas-product-faq.md: 4 chunks, 0 PII redactions
  indexed it-security-policy.md: 5 chunks, 1 PII redactions
  indexed onboarding-guide.md: 4 chunks, 3 PII redactions

[2/4] Hybrid search: 'how often is password rotation required?'
   0.3733  it-security-policy #0
   0.2556  atlas-product-faq #2
   ...

[3/4] RAG chat: 'What do I do if my laptop is stolen?'
  answer   : ... Lost or stolen devices must be reported within four hours ...
  citations: ['atlas-product-faq', 'onboarding-guide', 'it-security-policy']

[4/4] Agent: 'What is (14 + 90) * 2?'
  steps  : ['calculator']
  answer : (14 + 90) * 2 = 208
```

Then run the API (or `docker compose up`, which sets the same flag):

```bash
ALLOW_ANONYMOUS_DEV_ADMIN=true uvicorn app.main:app --reload
```

```bash
curl http://localhost:8000/healthz
# {"status":"ok","mode":"local","version":"1.0.0"}

curl -X POST http://localhost:8000/api/ingest/text \
  -H "Content-Type: application/json" \
  -d '{"title":"Password Policy","content":"Password rotation is required every ninety days for privileged accounts. Contact helpdesk@larkspur.example for lockouts.","category":"security","acl_groups":["public"]}'
# {"doc_id":"3f9c...","title":"Password Policy","chunks_indexed":1,"pii_redactions":1,"mode":"local"}

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How often is password rotation required?"}'
# {"session_id":"...","answer":"Password rotation is required every ninety days for privileged accounts. ...","citations":[{"ref":1,"doc_id":"3f9c...","title":"Password Policy","score":0.53}], ...}
```

Anonymous access is **opt-in**: with `ALLOW_ANONYMOUS_DEV_ADMIN=true` (local
mode only — startup fails if it's combined with Azure credentials), tokenless
requests get a dev admin principal so the curl examples above just work.
Presented tokens are always verified — the RBAC tests mint real JWTs for
each role.

## Local mode vs Azure mode

The mode is **derived, not configured**: if the four `AZURE_OPENAI_*` /
`AZURE_SEARCH_*` values are set, the app runs in `azure` mode; otherwise
`local`. `/healthz` reports the active mode.

| Concern | Local (default) | Azure (keys in `.env`) |
|---------|-----------------|------------------------|
| Embeddings | Deterministic signed feature hashing | Azure OpenAI embedding deployment |
| Vector index | In-memory hybrid store | Azure AI Search (vector + BM25) |
| Chat | Extractive mock (answers only from retrieved chunks) | Azure OpenAI chat deployment |
| PII | Regex redactor | Azure AI Language |
| Content safety | Keyword gate | Azure Content Safety |
| Auth | JWT; anonymous dev admin (explicit opt-in) | JWT required, strong `JWT_SECRET` enforced |

The local fallbacks are functional, not stubs — the whole pipeline, including
every security control, executes end to end offline. Azure mode additionally
needs `pip install -r requirements-azure.txt`.

## Configuration

All settings load from the environment / `.env`
(see [.env.example](.env.example) for the full annotated list):

| Variable | Default | Purpose |
|----------|---------|---------|
| `JWT_SECRET` | dev-only placeholder | HS256 signing key; a strong value is enforced at startup in azure mode |
| `ALLOW_ANONYMOUS_DEV_ADMIN` | `false` | Local quickstart only: tokenless requests act as dev admin; refused in azure mode |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `150` | Chunker geometry (characters) |
| `RETRIEVAL_TOP_K` | `5` | Chunks fed to the LLM per question |
| `AGENT_MAX_ITERATIONS` | `4` | Hard stop for the agent loop |
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` | — | Enables Azure generation/embeddings |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` / `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | `gpt-4o` / `text-embedding-3-large` | Deployment names |
| `AZURE_SEARCH_ENDPOINT` / `AZURE_SEARCH_API_KEY` / `AZURE_SEARCH_INDEX` | — / — / `knowledgeforge-chunks` | Enables Azure AI Search |
| `AZURE_LANGUAGE_*`, `AZURE_CONTENT_SAFETY_*` | — | Optional managed PII / safety services |
| `AZURE_STORAGE_CONNECTION_STRING` | — | Batch ingestion source container |

## Security model

- **Roles** gate endpoints: `reader` (search, chat) < `curator` (+ ingest)
  < `admin` (+ index management, ACL bypass).
- **ACL groups** gate documents: every chunk carries `acl_groups`; the
  visibility predicate runs *inside* the index query, so restricted content
  never reaches the app layer, the prompt, or the logs of an unauthorized
  caller — and `top_k` always means top-k *visible* results.
- **PII redaction** runs before chunking, so raw identifiers are never
  embedded or indexed.
- **Content safety** screens both inbound documents and chat messages, with a
  single failure mode (`422 ContentBlockedError`).
- **Agent calculator** evaluates arithmetic by walking a whitelisted AST —
  no `eval`, no builtins.

## Testing

```bash
pytest -q          # 28 tests, all offline
ruff check .       # lint
```

Coverage includes the chunker's edge cases, the RBAC visibility matrix, an
end-to-end local-mode RAG round trip (ingest → search → grounded answer →
citations), agent tool selection, calculator injection resistance, and API
smoke tests for every role boundary.

## CI/CD

- **[ci.yml](.github/workflows/ci.yml)** — ruff + pytest on every push/PR;
  runs entirely in local mode, zero secrets.
- **[deploy.yml](.github/workflows/deploy.yml)** — on version tags: build the
  container, push to Azure Container Registry, deploy to App Service, smoke
  check `/healthz`.
- **[infra/](infra/)** — Terraform for the full footprint: AI Search, OpenAI
  deployments, blob storage, Key Vault (secrets via references), Log
  Analytics + App Insights, and the App Service with managed-identity ACR
  pulls.

## Roadmap

- Qdrant adapter for the `VectorStore` protocol (compose profile already stubs
  the service).
- Native function calling for the agent in Azure mode.
- Cosmos DB / Redis session store implementations.
- Semantic reranker wired into the pipeline's rerank hook.
- Incremental connector framework (SharePoint-style change feeds) for the
  batch pipeline.

## License

[MIT](LICENSE).
