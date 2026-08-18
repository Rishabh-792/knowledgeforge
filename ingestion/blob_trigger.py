"""Batch ingestion entry point, shaped like an Azure Functions blob trigger.

Deployed as a Function App, `function.json` binds this to the storage
container configured in AZURE_STORAGE_CONTAINER:

    { "bindings": [{ "type": "blobTrigger", "name": "blob",
                     "path": "incoming-docs/{name}", "direction": "in",
                     "connection": "AZURE_STORAGE_CONNECTION_STRING" }] }

The handler reuses the exact same pipeline stages as the API's /ingest route:
safety gate -> PII redaction -> chunking -> embedding -> index upsert.
"""

import logging
import uuid
from pathlib import Path

from app.api.deps import (
    get_embedder,
    get_pii_redactor,
    get_safety_gate,
    get_vector_store,
)
from app.core.config import get_settings
from app.core.exceptions import KnowledgeForgeError
from app.services.chunking import chunk_text
from app.services.vector_store import ChunkRecord
from ingestion.cracking import extract_text

logger = logging.getLogger(__name__)

# Blobs land under <category>/<filename>; ACLs come from container metadata in
# production. NOTE: a SharePoint connector would feed this same handler via a
# Graph change-notification poller — same cracking + indexing path.


def process_blob(blob_name: str, data: bytes) -> dict:
    settings = get_settings()
    text = extract_text(blob_name, data)
    get_safety_gate().check(text)
    clean, findings = get_pii_redactor().redact(text)
    chunks = chunk_text(clean, settings.chunk_size, settings.chunk_overlap)
    vectors = get_embedder().embed([c.text for c in chunks])

    parts = Path(blob_name)
    category = parts.parent.name or "general"
    doc_id = uuid.uuid4().hex[:12]
    get_vector_store().upsert(
        [
            ChunkRecord(
                id=f"{doc_id}-{c.index}",
                doc_id=doc_id,
                title=parts.name,
                category=category,
                chunk_index=c.index,
                content=c.text,
                vector=v,
                acl_groups=["public"],
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
    )
    summary = {
        "blob": blob_name,
        "doc_id": doc_id,
        "chunks_indexed": len(chunks),
        "pii_redactions": len(findings),
    }
    logger.info("blob ingested", extra={"ctx": summary})
    return summary


def main(blob_name: str, data: bytes) -> None:
    """Azure Functions entry point — log-and-swallow so one bad blob does not
    poison the batch; the platform dead-letters after max retries."""
    try:
        process_blob(blob_name, data)
    except KnowledgeForgeError as exc:
        logger.error(
            "blob ingestion failed",
            extra={"ctx": {"blob": blob_name, "error": exc.detail}},
        )
        raise  # let the Functions runtime retry / dead-letter
