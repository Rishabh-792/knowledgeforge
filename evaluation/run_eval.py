"""Retrieval and grounding evaluation over a golden question set.

Seeds the sample corpus, then for each question measures:

  hit@k     did any chunk from the expected document appear in the top k
  MRR       reciprocal rank of the first chunk from the expected document
  nDCG@5    binary-relevance nDCG, so rank position is scored, not just presence
  grounded  did the generated answer contain the expected fact, and did the
            top citation point at the right document

Everything runs in local mode: no cloud account, no API key, no network. The
numbers therefore describe the deterministic local embedder and extractive
mock LLM, which is what CI exercises. Azure-mode numbers would differ and are
not claimed here.

Usage:
    python -m evaluation.run_eval
    python -m evaluation.run_eval --top-k 5
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.api.deps import (
    get_embedder,
    get_pii_redactor,
    get_rag,
    get_vector_store,
    reset_singletons,
)
from app.core.config import get_settings
from app.services.chunking import chunk_text
from app.services.vector_store import ChunkRecord

GOLDEN_PATH = REPO_ROOT / "evaluation" / "golden_questions.json"
RESULTS_PATH = REPO_ROOT / "evaluation" / "results.json"
CORPUS_DIR = REPO_ROOT / "sample_docs"


def seed_corpus() -> dict[str, int]:
    """Indexes every sample document. Returns chunks per document."""
    settings = get_settings()
    embedder, store, redactor = get_embedder(), get_vector_store(), get_pii_redactor()

    counts: dict[str, int] = {}
    for i, path in enumerate(sorted(CORPUS_DIR.glob("*.md"))):
        clean, _ = redactor.redact(path.read_text(encoding="utf-8"))
        chunks = chunk_text(clean, settings.chunk_size, settings.chunk_overlap)
        vectors = embedder.embed([c.text for c in chunks])
        store.upsert(
            [
                ChunkRecord(
                    id=f"doc{i}-{c.index}",
                    doc_id=f"doc{i}",
                    # title is the file stem, which is what the golden set keys on
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
        counts[path.stem] = len(chunks)
    return counts


def _ndcg_at_k(doc_ranking: list[str], expected: str, k: int) -> float:
    """Binary-relevance nDCG@k over DOCUMENTS, not chunks.

    Scoring the chunk list would count one document many times and push nDCG
    above 1.0. Exactly one document is relevant, so IDCG = 1.
    """
    for rank, title in enumerate(doc_ranking[:k]):
        if title == expected:
            return 1.0 / math.log2(rank + 2)
    return 0.0


def evaluate_question(rag, question: dict, top_k: int) -> dict:
    expected = question["expected_doc"]

    start = time.perf_counter()
    results = rag.retrieve(question["question"], allowed_groups=["public"], top_k=top_k)
    retrieve_ms = (time.perf_counter() - start) * 1000.0

    titles = [r.record.title for r in results]
    hits = [t == expected for t in titles]
    # dict preserves insertion order, so this is the chunk ranking
    # collapsed to a document ranking, first position kept.
    doc_ranking = list(dict.fromkeys(titles))
    # Rank at DOCUMENT granularity, matching how relevance is defined
    # (expected_doc) and how nDCG is scored. Using the chunk index here made
    # MRR and nDCG measure different things: a document sitting at chunk rank 5
    # but 2nd among distinct documents scored RR 0.20 against nDCG 0.63.
    first = next((i for i, t in enumerate(doc_ranking) if t == expected), None)

    start = time.perf_counter()
    answered = rag.answer(question["question"], allowed_groups=["public"])
    answer_ms = (time.perf_counter() - start) * 1000.0

    lowered = answered.answer.lower()
    needles = [n.lower() for n in question.get("answer_contains", [])]
    contains = [n for n in needles if n in lowered]
    top_citation = answered.citations[0]["title"] if answered.citations else None

    return {
        "id": question["id"],
        "question": question["question"],
        "expected_doc": expected,
        "retrieved": titles,
        "retrieved_docs": doc_ranking,
        "hit@1": bool(hits[:1] and hits[0]),
        "hit@3": any(hits[:3]),
        "hit@5": any(hits[:5]),
        "first_hit_rank": None if first is None else first + 1,
        "reciprocal_rank": 0.0 if first is None else round(1.0 / (first + 1), 6),
        "ndcg@5": round(_ndcg_at_k(doc_ranking, expected, 5), 6),
        "top_citation": top_citation,
        "citation_correct": top_citation == expected,
        "answer_contains_matched": contains,
        "answer_grounded": len(contains) == len(needles) and bool(needles),
        "latency_ms": {
            "retrieve": round(retrieve_ms, 3),
            "answer": round(answer_ms, 3),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--golden", default=str(GOLDEN_PATH))
    parser.add_argument("--out", default=str(RESULTS_PATH))
    args = parser.parse_args(argv)

    reset_singletons()
    settings = get_settings()

    questions = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    chunk_counts = seed_corpus()

    # Every expected_doc must exist, or the scores are silently meaningless.
    unknown = sorted({q["expected_doc"] for q in questions} - set(chunk_counts))
    if unknown:
        sys.exit(f"golden set references documents not in the corpus: {unknown}")

    rag = get_rag()
    cases = [evaluate_question(rag, q, args.top_k) for q in questions]

    n = len(cases)
    retrieve_times = [c["latency_ms"]["retrieve"] for c in cases]
    answer_times = [c["latency_ms"]["answer"] for c in cases]

    summary = {
        "questions": n,
        "documents": len(chunk_counts),
        "chunks": sum(chunk_counts.values()),
        "hit@1": round(sum(c["hit@1"] for c in cases) / n, 4),
        "hit@3": round(sum(c["hit@3"] for c in cases) / n, 4),
        "hit@5": round(sum(c["hit@5"] for c in cases) / n, 4),
        "mrr": round(sum(c["reciprocal_rank"] for c in cases) / n, 4),
        "ndcg@5": round(sum(c["ndcg@5"] for c in cases) / n, 4),
        "citation_accuracy": round(sum(c["citation_correct"] for c in cases) / n, 4),
        "answer_groundedness": round(sum(c["answer_grounded"] for c in cases) / n, 4),
        "retrieve_ms_p50": round(statistics.median(retrieve_times), 3),
        "retrieve_ms_p95": round(statistics.quantiles(retrieve_times, n=100)[94], 3),
        "answer_ms_p50": round(statistics.median(answer_times), 3),
        "answer_ms_p95": round(statistics.quantiles(answer_times, n=100)[94], 3),
    }

    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": settings.mode,
        "config": {
            "top_k": args.top_k,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "embedding_dimensions": settings.embedding_dimensions,
        },
        "corpus": chunk_counts,
        "summary": summary,
        "cases": cases,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"corpus: {summary['documents']} documents, {summary['chunks']} chunks")
    print(f"questions: {n}\n")
    for label in ("hit@1", "hit@3", "hit@5", "mrr", "ndcg@5",
                  "citation_accuracy", "answer_groundedness"):
        print(f"  {label:<20} {summary[label]:.4f}")
    print(f"\n  retrieve p50/p95      {summary['retrieve_ms_p50']:.2f} / "
          f"{summary['retrieve_ms_p95']:.2f} ms")
    print(f"  answer   p50/p95      {summary['answer_ms_p50']:.2f} / "
          f"{summary['answer_ms_p95']:.2f} ms")

    misses = [c for c in cases if not c["hit@5"]]
    if misses:
        print(f"\n  {len(misses)} question(s) missed entirely:")
        for c in misses:
            print(f"    {c['id']} expected {c['expected_doc']}, got {c['retrieved'][:3]}")

    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
