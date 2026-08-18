"""Vector store implementations behind a common Protocol.

* InMemoryStore — fully working: cosine similarity + keyword scoring merged
  into a hybrid score, with document-level ACL and metadata filtering.
* AzureAISearchStore — production-shaped adapter for Azure AI Search using
  vector + BM25 hybrid queries and an OData ACL filter. Kept concise; the
  structure (mapping, filtering, error handling) mirrors a real deployment.
"""

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from app.core.exceptions import UpstreamServiceError

from .text import tokenize

logger = logging.getLogger(__name__)

PUBLIC_GROUP = "public"
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _odata_literal(value: str) -> str:
    """Quote a string literal for an OData filter (single quotes doubled)."""
    return "'" + value.replace("'", "''") + "'"


def _safe_ids(values: list[str]) -> list[str]:
    """Reject identifiers that could smuggle OData syntax or delimiters."""
    for v in values:
        if not _SAFE_ID_RE.match(v):
            raise ValueError(f"unsafe identifier in search filter: {v!r}")
    return values


@dataclass
class ChunkRecord:
    id: str
    doc_id: str
    title: str
    category: str
    chunk_index: int
    content: str
    vector: list[float]
    acl_groups: list[str] = field(default_factory=lambda: [PUBLIC_GROUP])


@dataclass
class SearchResult:
    record: ChunkRecord
    score: float


def is_visible(record_groups: list[str], allowed_groups: list[str] | None) -> bool:
    """Document-level RBAC check. allowed_groups=None means admin (see all).

    Callers must pass this explicitly - it has no default anywhere in the
    search path. A defaulted "None means see everything" is a fail-open
    security parameter, and an omitted keyword argument is invisible in review.
    """
    if allowed_groups is None:
        return True
    return PUBLIC_GROUP in record_groups or bool(
        set(record_groups) & set(allowed_groups)
    )


class VectorStore(Protocol):
    def upsert(self, records: list[ChunkRecord]) -> None: ...

    def hybrid_search(
        self,
        query: str,
        vector: list[float],
        allowed_groups: list[str] | None,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[SearchResult]: ...

    def delete_document(self, doc_id: str) -> int: ...

    def delete_category(self, category: str) -> int: ...

    def list_documents(self) -> list[dict]: ...


# BM25 parameters. k1 controls term-frequency saturation, b the strength of
# length normalisation; these are the standard defaults.
_BM25_K1 = 1.5
_BM25_B = 0.75

# BM25 is unbounded while cosine is in [-1, 1], so the lexical leg needs
# squashing before the two can be blended. This MUST NOT depend on the result
# set: normalising by the best score among the *visible* candidates made the
# returned score a function of the caller's ACL grant, so the same chunk scored
# 1.45x higher for a reader than for an admin who could also see a stronger
# restricted match. x/(x+k) is monotone, caller-independent, and lands in [0,1).
_BM25_SATURATION = 3.0

# Hybrid blend for the local backend. The offline embedder is signed feature
# hashing, which captures no semantics, so lexical evidence is weighted more
# heavily here than it would be against a real embedding model. Measured on
# the golden set in evaluation/: see evaluation/results.json.
_VECTOR_WEIGHT = 0.35
_KEYWORD_WEIGHT = 0.65

# Terms too common to discriminate between chunks. Deliberately a
# superset of the list in llm.py: retrieval benefits from dropping
# modals and possessives that answer extraction still needs.
_STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i if in is it "
    "must my of on or our should that the this to was we what when where which who "
    "why will with you your".split()
)


class InMemoryStore:
    """Reference implementation; also the local-mode backend."""

    def __init__(self):
        self._records: dict[str, ChunkRecord] = {}
        # Term counts per chunk, not a token list: BM25 needs a frequency
        # lookup per query term, and .count() on a list rescans the whole chunk.
        self._tokens: dict[str, Counter[str]] = {}
        self._lengths: dict[str, int] = {}

    def upsert(self, records: list[ChunkRecord]) -> None:
        for rec in records:
            self._records[rec.id] = rec
            tokens = tokenize(rec.content)
            self._tokens[rec.id] = Counter(tokens)
            self._lengths[rec.id] = len(tokens)

    def _corpus_stats(self, ids: list[str], q_terms: set[str]) -> tuple[int, dict[str, int]]:
        """Document frequencies over a caller's *visible* chunks only.

        IDF must not be computed over the whole store. Global document
        frequencies are observable through the returned score: on a multi-term
        query the ratio between two results depends on idf(t1):idf(t2), which
        does not cancel, so a caller could recover the df of a term appearing
        only in documents they cannot see - a term-confirmation oracle over the
        private corpus. Scoping the statistics to the visible set closes that
        channel. The search already scans every record, so this costs nothing
        asymptotically.
        """
        doc_freq = {t: 0 for t in q_terms}
        for rid in ids:
            counts = self._tokens.get(rid)
            if not counts:
                continue
            for term in q_terms:
                if term in counts:
                    doc_freq[term] += 1
        return len(ids), doc_freq

    def _bm25(
        self,
        q_terms: set[str],
        record_id: str,
        n_docs: int,
        doc_freq: dict[str, int],
        avg_len: float,
    ) -> float:
        """Okapi BM25 for one chunk.

        Replaces a raw query-token overlap ratio, which ignored how rare a term
        is, how often it occurs, and how long the chunk is - so a long chunk
        mentioning a common word outranked a short chunk that was actually about
        the query.
        """
        counts = self._tokens.get(record_id)
        if not counts or not q_terms:
            return 0.0

        length = self._lengths[record_id]
        score = 0.0
        for term in q_terms:
            freq = counts.get(term, 0)
            if not freq:
                continue
            df = doc_freq.get(term, 0)
            # Smoothed probabilistic IDF; the 1.0 + inside the log keeps the
            # argument above 1 even when a term appears in every chunk, so this
            # cannot go negative and needs no floor.
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            denom = freq + _BM25_K1 * (
                1 - _BM25_B + _BM25_B * (length / avg_len if avg_len else 1.0)
            )
            score += idf * (freq * (_BM25_K1 + 1)) / denom
        return score

    def hybrid_search(
        self,
        query: str,
        vector: list[float],
        allowed_groups: list[str] | None,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[SearchResult]:
        # NOTE: linear scan; swap for an ANN index if the corpus outgrows a demo.
        # set(): BM25 saturates term frequency on the document side, so summing
        # a repeated query term would reintroduce the linear growth it exists to
        # prevent ("the expense policy on the expense policy" scored 2x).
        q_terms = {t for t in tokenize(query) if t not in _STOPWORDS}

        visible = [
            rec
            for rec in self._records.values()
            if (not category or rec.category == category)
            and is_visible(rec.acl_groups, allowed_groups)
        ]
        # Statistics come from the visible set only - see _corpus_stats.
        n_docs, doc_freq = self._corpus_stats([r.id for r in visible], q_terms)
        avg_len = (
            sum(self._lengths[r.id] for r in visible) / len(visible) if visible else 0.0
        )

        results = []
        for rec in visible:
            bm25 = self._bm25(q_terms, rec.id, n_docs, doc_freq, avg_len)
            # Bounded, monotone, and independent of the other candidates, so the
            # score a caller sees does not depend on their ACL grant.
            lexical = bm25 / (bm25 + _BM25_SATURATION)
            score = _VECTOR_WEIGHT * _cosine(vector, rec.vector) + _KEYWORD_WEIGHT * lexical
            if score > 0:
                results.append(SearchResult(rec, round(score, 4)))

        results.sort(key=lambda r: -r.score)
        return results[:top_k]

    def delete_document(self, doc_id: str) -> int:
        return self._delete(lambda r: r.doc_id == doc_id)

    def delete_category(self, category: str) -> int:
        return self._delete(lambda r: r.category == category)

    def _delete(self, predicate) -> int:
        doomed = [rid for rid, r in self._records.items() if predicate(r)]
        for rid in doomed:
            del self._records[rid]
            # Term counts must go too, or a deleted chunk keeps contributing to
            # the document frequencies computed at search time.
            self._tokens.pop(rid, None)
            self._lengths.pop(rid, None)
        return len(doomed)

    def list_documents(self) -> list[dict]:
        docs: dict[str, dict] = {}
        for rec in self._records.values():
            entry = docs.setdefault(
                rec.doc_id,
                {
                    "doc_id": rec.doc_id,
                    "title": rec.title,
                    "category": rec.category,
                    "chunks": 0,
                    "acl_groups": rec.acl_groups,
                },
            )
            entry["chunks"] += 1
        return list(docs.values())


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class AzureAISearchStore:
    """Azure AI Search adapter (hybrid vector + BM25, ACL via OData filter)."""

    def __init__(self, endpoint: str, api_key: str, index_name: str):
        try:
            from azure.core.credentials import AzureKeyCredential
            from azure.search.documents import SearchClient
        except ImportError as exc:  # pragma: no cover
            raise UpstreamServiceError(
                "azure-search-documents not installed; "
                "pip install -r requirements-azure.txt"
            ) from exc
        self._client = SearchClient(endpoint, index_name, AzureKeyCredential(api_key))

    def upsert(self, records: list[ChunkRecord]) -> None:
        docs = [
            {
                "id": r.id,
                "doc_id": r.doc_id,
                "title": r.title,
                "category": r.category,
                "chunk_index": r.chunk_index,
                "content": r.content,
                "content_vector": r.vector,
                "acl_groups": r.acl_groups,
            }
            for r in records
        ]
        try:
            self._client.merge_or_upload_documents(docs)
        except Exception as exc:
            raise UpstreamServiceError(f"index upsert failed: {exc}") from exc

    def hybrid_search(
        self,
        query: str,
        vector: list[float],
        allowed_groups: list[str] | None,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[SearchResult]:
        from azure.search.documents.models import VectorizedQuery

        filters = []
        if allowed_groups is not None:
            groups = ",".join(_safe_ids([PUBLIC_GROUP, *allowed_groups]))
            filters.append(f"acl_groups/any(g: search.in(g, {_odata_literal(groups)}, ','))")
        if category:
            filters.append(f"category eq {_odata_literal(category)}")
        try:
            pager = self._client.search(
                search_text=query,  # BM25 leg of the hybrid query
                vector_queries=[
                    VectorizedQuery(
                        vector=vector, k_nearest_neighbors=top_k, fields="content_vector"
                    )
                ],
                filter=" and ".join(filters) or None,
                top=top_k,
            )
            return [
                SearchResult(
                    record=ChunkRecord(
                        id=d["id"],
                        doc_id=d["doc_id"],
                        title=d["title"],
                        category=d["category"],
                        chunk_index=d["chunk_index"],
                        content=d["content"],
                        vector=[],  # not returned; saves payload
                        acl_groups=d.get("acl_groups", []),
                    ),
                    score=d["@search.score"],
                )
                for d in pager
            ]
        except Exception as exc:
            raise UpstreamServiceError(f"search query failed: {exc}") from exc

    def delete_document(self, doc_id: str) -> int:
        return self._delete_by_filter(f"doc_id eq {_odata_literal(doc_id)}")

    def delete_category(self, category: str) -> int:
        return self._delete_by_filter(f"category eq {_odata_literal(category)}")

    def _delete_by_filter(self, odata_filter: str) -> int:
        try:
            hits = self._client.search(search_text="*", filter=odata_filter, select="id")
            keys = [{"id": d["id"]} for d in hits]
            if keys:
                self._client.delete_documents(keys)
            return len(keys)
        except Exception as exc:
            raise UpstreamServiceError(f"index delete failed: {exc}") from exc

    def list_documents(self) -> list[dict]:
        # NOTE: production would use a facet query or a documents table in Cosmos DB;
        # a bounded scan keeps this adapter concise.
        try:
            hits = self._client.search(
                search_text="*",
                select="doc_id,title,category,acl_groups",
                top=1000,
            )
        except Exception as exc:
            raise UpstreamServiceError(f"index scan failed: {exc}") from exc
        docs: dict[str, dict] = {}
        for d in hits:
            entry = docs.setdefault(
                d["doc_id"],
                {
                    "doc_id": d["doc_id"],
                    "title": d["title"],
                    "category": d["category"],
                    "chunks": 0,
                    "acl_groups": d.get("acl_groups", []),
                },
            )
            entry["chunks"] += 1
        return list(docs.values())
