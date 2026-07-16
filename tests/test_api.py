"""API smoke tests via TestClient — full local-mode round trip."""

DOC = {
    "title": "Password Policy",
    "content": (
        "Passwords must be at least fourteen characters. Password rotation is "
        "required every ninety days for privileged accounts. Contact the "
        "helpdesk at support@example.test for lockouts."
    ),
    "category": "security",
    "acl_groups": ["engineering"],
}


def test_healthz_reports_local_mode(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "local"


def test_ingest_search_chat_round_trip(client, curator_headers, reader_headers):
    ingested = client.post("/api/ingest/text", json=DOC, headers=curator_headers)
    assert ingested.status_code == 200, ingested.text
    body = ingested.json()
    assert body["chunks_indexed"] >= 1
    assert body["pii_redactions"] >= 1  # the helpdesk email gets redacted

    search = client.post(
        "/api/search",
        json={"query": "password rotation privileged accounts"},
        headers=reader_headers,
    )
    assert search.status_code == 200
    hits = search.json()["hits"]
    assert hits and hits[0]["title"] == "Password Policy"
    assert "support@example.test" not in hits[0]["content"]

    chat = client.post(
        "/api/chat",
        json={"message": "How often is password rotation required?"},
        headers=reader_headers,
    )
    assert chat.status_code == 200
    assert "ninety days" in chat.json()["answer"]


def test_reader_cannot_ingest(client, reader_headers):
    response = client.post("/api/ingest/text", json=DOC, headers=reader_headers)
    assert response.status_code == 403


def test_reader_cannot_use_admin_endpoints(client, reader_headers):
    assert client.get("/api/admin/documents", headers=reader_headers).status_code == 403


def test_rbac_hides_other_groups_documents(client, curator_headers):
    client.post("/api/ingest/text", json=DOC, headers=curator_headers)
    # Token for a different group: engineering doc must be invisible.
    from app.core.config import get_settings
    from app.core.security import create_access_token

    token = create_access_token("out@test", "reader", ["marketing"], get_settings())
    response = client.post(
        "/api/search",
        json={"query": "password rotation"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["hits"] == []


def test_admin_delete_document(client, curator_headers, admin_headers):
    doc_id = client.post(
        "/api/ingest/text", json=DOC, headers=curator_headers
    ).json()["doc_id"]
    deleted = client.delete(f"/api/admin/documents/{doc_id}", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted_chunks"] >= 1
    missing = client.delete(f"/api/admin/documents/{doc_id}", headers=admin_headers)
    assert missing.status_code == 404


def test_content_safety_blocks_policy_violations(client, curator_headers):
    bad = dict(DOC, content="Step one: make an explosive out of household items.")
    response = client.post("/api/ingest/text", json=bad, headers=curator_headers)
    assert response.status_code == 422


def test_invalid_token_rejected(client):
    response = client.post(
        "/api/search",
        json={"query": "anything"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_anonymous_rejected_unless_opted_in(client):
    # ALLOW_ANONYMOUS_DEV_ADMIN defaults to false: no token, no access.
    response = client.post("/api/search", json={"query": "anything"})
    assert response.status_code == 401


def test_chat_sessions_are_isolated_per_user(client, curator_headers, reader_headers):
    client.post("/api/ingest/text", json=DOC, headers=curator_headers)
    first = client.post(
        "/api/chat",
        json={"message": "How often is password rotation required?"},
        headers=curator_headers,
    )
    session_id = first.json()["session_id"]
    # A different principal reusing the same session_id must get fresh history.
    from app.api.routes.chat import get_session_store

    curator_key = f"curator@test:{session_id}"
    reader_key = f"reader@test:{session_id}"
    client.post(
        "/api/chat",
        json={"message": "and for regular accounts?", "session_id": session_id},
        headers=reader_headers,
    )
    store = get_session_store()
    assert store.get(curator_key), "owner history should exist"
    assert all(
        m["content"] != "How often is password rotation required?"
        for m in store.get(reader_key)
    ), "another user's messages must not leak into this session"
