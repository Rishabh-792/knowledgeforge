"""KnowledgeForge local-mode demo — zero cloud credentials required.

Seeds the three sample documents, then runs a hybrid search, a RAG chat
question, and an agent calculation, printing each result.

    python scripts/demo.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.api.deps import (
    get_agent,
    get_embedder,
    get_pii_redactor,
    get_rag,
    get_vector_store,
)
from app.core.config import get_settings
from app.services.chunking import chunk_text
from app.services.vector_store import ChunkRecord


def seed_sample_docs() -> None:
    settings = get_settings()
    embedder, store, redactor = get_embedder(), get_vector_store(), get_pii_redactor()
    for i, path in enumerate(sorted((REPO_ROOT / "sample_docs").glob("*.md"))):
        clean, findings = redactor.redact(path.read_text(encoding="utf-8"))
        chunks = chunk_text(clean, settings.chunk_size, settings.chunk_overlap)
        vectors = embedder.embed([c.text for c in chunks])
        store.upsert(
            [
                ChunkRecord(
                    id=f"sample{i}-{c.index}",
                    doc_id=f"sample{i}",
                    title=path.stem,
                    category="handbook",
                    chunk_index=c.index,
                    content=c.text,
                    vector=v,
                    acl_groups=["public"],
                )
                for c, v in zip(chunks, vectors, strict=True)
            ]
        )
        print(
            f"  indexed {path.name}: {len(chunks)} chunks, "
            f"{len(findings)} PII redactions"
        )


def main() -> None:
    settings = get_settings()
    print(f"== KnowledgeForge demo (mode: {settings.mode}) ==\n")

    print("[1/4] Seeding sample documents...")
    seed_sample_docs()

    print("\n[2/4] Hybrid search: 'how often is password rotation required?'")
    rag = get_rag()
    for hit in rag.retrieve("how often is password rotation required?", None, top_k=3):
        print(f"  {hit.score:>7.4f}  {hit.record.title} #{hit.record.chunk_index}")

    print("\n[3/4] RAG chat: 'What do I do if my laptop is stolen?'")
    answer = rag.answer("What do I do if my laptop is stolen?", allowed_groups=None)
    print(f"  answer   : {answer.answer}")
    print(f"  citations: {[c['title'] for c in answer.citations[:3]]}")

    print("\n[4/4] Agent: 'What is (14 + 90) * 2?'")
    result = get_agent().run("What is (14 + 90) * 2?", allowed_groups=None)
    print(f"  steps  : {[s['tool'] for s in result.steps]}")
    print(f"  answer : {result.answer}")

    print("\nDone. Start the API with: uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
