"""Ingestion endpoints: safety gate -> PII redaction -> chunk -> embed -> index.

Requires the `curator` role. ACL groups supplied at ingest time become the
document-level RBAC boundary enforced by every search.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import (
    get_embedder,
    get_pii_redactor,
    get_safety_gate,
    get_vector_store,
)
from app.core.config import Settings, get_settings
from app.core.security import Principal, require_role
from app.models.schemas import IngestResponse, IngestTextRequest
from app.services.chunking import chunk_text
from app.services.embeddings import Embedder
from app.services.pii import PIIRedactor
from app.services.safety import SafetyGate
from app.services.vector_store import ChunkRecord, VectorStore
from ingestion.cracking import extract_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


def _index_document(
    *,
    title: str,
    content: str,
    category: str,
    acl_groups: list[str],
    settings: Settings,
    safety: SafetyGate,
    redactor: PIIRedactor,
    embedder: Embedder,
    store: VectorStore,
) -> IngestResponse:
    safety.check(content)
    clean, findings = redactor.redact(content)
    chunks = chunk_text(clean, settings.chunk_size, settings.chunk_overlap)
    vectors = embedder.embed([c.text for c in chunks])
    doc_id = uuid.uuid4().hex[:12]
    store.upsert(
        [
            ChunkRecord(
                id=f"{doc_id}-{c.index}",
                doc_id=doc_id,
                title=title,
                category=category,
                chunk_index=c.index,
                content=c.text,
                vector=v,
                acl_groups=acl_groups,
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
    )
    logger.info(
        "document indexed",
        extra={"ctx": {"doc_id": doc_id, "chunks": len(chunks)}},
    )
    return IngestResponse(
        doc_id=doc_id,
        title=title,
        chunks_indexed=len(chunks),
        pii_redactions=len(findings),
        mode=settings.mode,
    )


@router.post("/text", response_model=IngestResponse)
def ingest_text(
    body: IngestTextRequest,
    principal: Principal = Depends(require_role("curator")),
    settings: Settings = Depends(get_settings),
    safety: SafetyGate = Depends(get_safety_gate),
    redactor: PIIRedactor = Depends(get_pii_redactor),
    embedder: Embedder = Depends(get_embedder),
    store: VectorStore = Depends(get_vector_store),
) -> IngestResponse:
    return _index_document(
        title=body.title,
        content=body.content,
        category=body.category,
        acl_groups=body.acl_groups,
        settings=settings,
        safety=safety,
        redactor=redactor,
        embedder=embedder,
        store=store,
    )


@router.post("/file", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    category: str = Form("general"),
    acl_groups: str = Form("public"),  # comma-separated
    principal: Principal = Depends(require_role("curator")),
    settings: Settings = Depends(get_settings),
    safety: SafetyGate = Depends(get_safety_gate),
    redactor: PIIRedactor = Depends(get_pii_redactor),
    embedder: Embedder = Depends(get_embedder),
    store: VectorStore = Depends(get_vector_store),
) -> IngestResponse:
    data = await file.read()
    content = extract_text(file.filename or "upload.txt", data)
    return _index_document(
        title=file.filename or "untitled",
        content=content,
        category=category,
        acl_groups=[g.strip() for g in acl_groups.split(",") if g.strip()],
        settings=settings,
        safety=safety,
        redactor=redactor,
        embedder=embedder,
        store=store,
    )
