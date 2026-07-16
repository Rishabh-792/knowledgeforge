"""Index management — admin role only."""

from fastapi import APIRouter, Depends

from app.api.deps import get_vector_store
from app.core.exceptions import DocumentNotFoundError
from app.core.security import Principal, require_role
from app.models.schemas import DeleteResponse, DocumentSummary
from app.services.vector_store import VectorStore

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(
    principal: Principal = Depends(require_role("admin")),
    store: VectorStore = Depends(get_vector_store),
) -> list[DocumentSummary]:
    return [DocumentSummary(**doc) for doc in store.list_documents()]


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
def delete_document(
    doc_id: str,
    principal: Principal = Depends(require_role("admin")),
    store: VectorStore = Depends(get_vector_store),
) -> DeleteResponse:
    deleted = store.delete_document(doc_id)
    if not deleted:
        raise DocumentNotFoundError(f"no chunks found for document '{doc_id}'")
    return DeleteResponse(deleted_chunks=deleted)


@router.delete("/categories/{category}", response_model=DeleteResponse)
def delete_category(
    category: str,
    principal: Principal = Depends(require_role("admin")),
    store: VectorStore = Depends(get_vector_store),
) -> DeleteResponse:
    return DeleteResponse(deleted_chunks=store.delete_category(category))
