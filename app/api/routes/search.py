"""Hybrid search endpoint. Results are filtered by the caller's ACL groups —
the RBAC boundary lives in the store query, not in post-processing."""

from fastapi import APIRouter, Depends

from app.api.deps import get_rag
from app.core.security import Principal, require_role
from app.models.schemas import SearchHit, SearchRequest, SearchResponse
from app.services.rag import RagPipeline

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
def search(
    body: SearchRequest,
    principal: Principal = Depends(require_role("reader")),
    rag: RagPipeline = Depends(get_rag),
) -> SearchResponse:
    results = rag.retrieve(
        body.query,
        allowed_groups=principal.acl_groups,
        category=body.category,
        top_k=body.top_k,
    )
    return SearchResponse(
        query=body.query,
        hits=[
            SearchHit(
                doc_id=r.record.doc_id,
                title=r.record.title,
                category=r.record.category,
                chunk_index=r.record.chunk_index,
                content=r.record.content,
                score=r.score,
            )
            for r in results
        ],
    )
