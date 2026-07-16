"""Pydantic request/response models for the public API."""

from pydantic import BaseModel, Field


# --- Ingestion ---------------------------------------------------------------
class IngestTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    category: str = "general"
    acl_groups: list[str] = ["public"]


class IngestResponse(BaseModel):
    doc_id: str
    title: str
    chunks_indexed: int
    pii_redactions: int
    mode: str


# --- Search ------------------------------------------------------------------
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=50)
    category: str | None = None


class SearchHit(BaseModel):
    doc_id: str
    title: str
    category: str
    chunk_index: int
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


# --- Chat --------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    use_agent: bool = False


class Citation(BaseModel):
    ref: int
    doc_id: str
    title: str
    score: float


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation] = []
    agent_steps: list[dict] = []


# --- Admin -------------------------------------------------------------------
class DocumentSummary(BaseModel):
    doc_id: str
    title: str
    category: str
    chunks: int
    acl_groups: list[str]


class DeleteResponse(BaseModel):
    deleted_chunks: int
