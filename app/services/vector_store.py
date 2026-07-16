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
from dataclasses import dataclass, field
from typing import Protocol

from app.core.exceptions import UpstreamServiceError

logger = logging.getLogger(__name__)

PUBLIC_GROUP = "public"
_TOKEN_RE = re.compile(r"[a-z0-9]+")
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
    """Document-level RBAC check. allowed_groups=None means admin (see all)."""
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
        top_k: int = 5,
        allowed_groups: list[str] | None = None,
        category: str | None = None,
    ) -> list[SearchResult]: ...

    def delete_document(self, doc_id: str) -> int: ...

    def delete_category(self, category: str) -> int: ...

    def list_documents(self) -> list[dict]: ...


class InMemoryStore:
    """Reference implementation; also the local-mode backend."""

    def __init__(self):
        self._records: dict[str, ChunkRecord] = {}

    def upsert(self, records: list[ChunkRecord]) -> None:
        for rec in records:
            self._records[rec.id] = rec

    def hybrid_search(
        self,
        query: str,
        vector: list[float],
        top_k: int = 5,
        allowed_groups: list[str] | None = None,
        category: str | None = None,
    ) -> list[SearchResult]:
        # ponytail: linear scan; swap for an ANN index if the corpus outgrows a demo.
        q_tokens = set(_TOKEN_RE.findall(query.lower()))
        results = []
        for rec in self._records.values():
            if category and rec.category != category:
                continue
            if not is_visible(rec.acl_groups, allowed_groups):
                continue
            keyword = (
                len(q_tokens & set(_TOKEN_RE.findall(rec.content.lower())))
                / len(q_tokens)
                if q_tokens
                else 0.0
            )
            score = 0.65 * _cosine(vector, rec.vector) + 0.35 * keyword
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
    dot = sum(x * y for x, y in zip(a, b))
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
        top_k: int = 5,
        allowed_groups: list[str] | None = None,
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
