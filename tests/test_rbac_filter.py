from app.services.embeddings import LocalHashEmbedder
from app.services.vector_store import ChunkRecord, InMemoryStore, is_visible

EMBEDDER = LocalHashEmbedder(64)


def _record(rid: str, content: str, groups: list[str]) -> ChunkRecord:
    return ChunkRecord(
        id=rid,
        doc_id=f"doc-{rid}",
        title=rid,
        category="policy",
        chunk_index=0,
        content=content,
        vector=EMBEDDER.embed([content])[0],
        acl_groups=groups,
    )


def _store() -> InMemoryStore:
    store = InMemoryStore()
    store.upsert(
        [
            _record("eng", "engineering deploy pipeline password rotation", ["engineering"]),
            _record("hr", "salary bands and compensation review process", ["hr"]),
            _record("pub", "office wifi guest network access", ["public"]),
        ]
    )
    return store


def _search(store: InMemoryStore, query: str, groups: list[str] | None):
    vector = EMBEDDER.embed([query])[0]
    return store.hybrid_search(query, vector, top_k=10, allowed_groups=groups)


def test_is_visible_matrix():
    assert is_visible(["public"], ["anything"])
    assert is_visible(["engineering"], ["engineering", "hr"])
    assert not is_visible(["hr"], ["engineering"])
    assert is_visible(["hr"], None)  # admin bypass


def test_reader_cannot_see_other_groups_documents():
    hits = _search(_store(), "compensation salary review", ["engineering"])
    assert all(h.record.doc_id != "doc-hr" for h in hits)


def test_reader_sees_own_group_and_public():
    hits = _search(_store(), "deploy pipeline wifi access", ["engineering"])
    doc_ids = {h.record.doc_id for h in hits}
    assert "doc-eng" in doc_ids
    assert "doc-pub" in doc_ids
    assert "doc-hr" not in doc_ids


def test_admin_bypass_sees_everything():
    hits = _search(_store(), "salary compensation", None)
    assert any(h.record.doc_id == "doc-hr" for h in hits)


def test_category_filter():
    store = _store()
    vector = EMBEDDER.embed(["wifi"])[0]
    hits = store.hybrid_search("wifi", vector, allowed_groups=None, category="nonexistent")
    assert hits == []
