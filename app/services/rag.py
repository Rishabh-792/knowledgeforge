"""Retrieval-augmented generation pipeline.

Flow: embed query -> hybrid search (RBAC-filtered) -> rerank hook ->
grounded prompt -> LLM -> answer + citations. Works identically against the
local mocks and the Azure backends because it only talks to the Protocols.
"""

import logging
from dataclasses import dataclass, field

from app.services.embeddings import Embedder
from app.services.llm import LLM, Message
from app.services.vector_store import SearchResult, VectorStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are KnowledgeForge, an enterprise knowledge assistant. Answer using "
    "only the numbered sources below. If the sources do not contain the "
    "answer, say so plainly. Cite sources inline as [n]."
)


@dataclass
class RagAnswer:
    answer: str
    citations: list[dict] = field(default_factory=list)


class RagPipeline:
    def __init__(self, embedder: Embedder, store: VectorStore, llm: LLM, top_k: int = 5):
        self._embedder = embedder
        self._store = store
        self._llm = llm
        self._top_k = top_k

    def retrieve(
        self,
        query: str,
        allowed_groups: list[str] | None,
        category: str | None = None,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        vector = self._embedder.embed([query])[0]
        results = self._store.hybrid_search(
            query=query,
            vector=vector,
            top_k=top_k or self._top_k,
            allowed_groups=allowed_groups,
            category=category,
        )
        return self.rerank(query, results)

    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        """Rerank hook — identity by default.

        NOTE: production deployment would plug a cross-encoder or the Azure AI
        Search semantic ranker in here; the pipeline shape stays the same.
        """
        return results

    def answer(
        self,
        query: str,
        allowed_groups: list[str] | None,
        history: list[Message] | None = None,
    ) -> RagAnswer:
        results = self.retrieve(query, allowed_groups)
        if not results:
            return RagAnswer(
                answer="No accessible documents matched your question.", citations=[]
            )
        sources = "\n\n".join(
            f"[{i + 1}] ({r.record.title}) {r.record.content}"
            for i, r in enumerate(results)
        )
        messages: list[Message] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"SOURCES:\n{sources}"},
            *(history or []),
            {"role": "user", "content": query},
        ]
        text = self._llm.complete(messages)
        citations = [
            {
                "ref": i + 1,
                "doc_id": r.record.doc_id,
                "title": r.record.title,
                "score": round(r.score, 4),
            }
            for i, r in enumerate(results)
        ]
        logger.info(
            "rag answer produced", extra={"ctx": {"query": query, "sources": len(results)}}
        )
        return RagAnswer(answer=text, citations=citations)
