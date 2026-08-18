"""BM25 ranking, and the two properties that make it safe under RBAC.

The scoring logic is the one place where a retrieval bug and a security bug
look identical, so the invariants are pinned rather than assumed.
"""

from __future__ import annotations

import pytest

from app.services.embeddings import LocalHashEmbedder
from app.services.vector_store import ChunkRecord, InMemoryStore

EMBEDDER = LocalHashEmbedder(256)


def _store(*docs: tuple[str, str, list[str]]) -> InMemoryStore:
    store = InMemoryStore()
    store.upsert(
        [
            ChunkRecord(
                id=name,
                doc_id=name,
                title=name,
                category="handbook",
                chunk_index=0,
                content=content,
                vector=EMBEDDER.embed([content])[0],
                acl_groups=groups,
            )
            for name, content, groups in docs
        ]
    )
    return store


def _scores(store: InMemoryStore, query: str, groups: list[str] | None) -> dict[str, float]:
    vector = EMBEDDER.embed([query])[0]
    return {
        r.record.title: r.score
        for r in store.hybrid_search(query, vector, groups, top_k=10)
    }


def test_invisible_documents_cannot_influence_a_callers_scores():
    """The no-leak invariant: a restricted document must be *inert* for a
    reader who cannot see it.

    Note this is deliberately not "every caller gets the same score". Because
    IDF is scoped to the visible corpus, an admin and a reader legitimately
    score the same chunk differently - they are ranking over different
    corpora. What must never happen is a document the caller cannot see
    changing what they do see, which is what this asserts by comparing a
    reader against a store where the restricted document does not exist.

    Regression: the lexical leg was once normalised by the best BM25 among the
    visible candidates, and IDF was computed over the whole store; both let
    hidden content move a reader's scores. That score is returned by
    /api/search and in every RAG citation.
    """
    query = "vpn session timeout"
    visible_docs = (
        ("visible", "vpn timeout guidance for staff", ["public"]),
        ("filler", "cafeteria lunch menu noon salad", ["public"]),
    )
    with_secret = _store(
        ("restricted", "vpn session timeout expires after twelve hours of vpn use", ["secret"]),
        *visible_docs,
    )
    without_secret = _store(*visible_docs)

    reader_with = _scores(with_secret, query, ["public"])
    reader_without = _scores(without_secret, query, ["public"])

    assert "restricted" not in reader_with
    assert reader_with == reader_without

    # And the admin does see it, so the fixture is actually exercising the path.
    assert "restricted" in _scores(with_secret, query, None)


def test_ranking_of_visible_documents_is_unaffected_by_invisible_ones():
    store = _store(
        ("secret_strong", "alpha alpha alpha alpha beta", ["secret"]),
        ("pub_a", "alpha beta gamma", ["public"]),
        ("pub_b", "beta gamma delta", ["public"]),
    )
    admin = _scores(store, "alpha beta", None)
    reader = _scores(store, "alpha beta", ["public"])

    admin_order = [t for t in sorted(admin, key=lambda k: -admin[k]) if t.startswith("pub_")]
    reader_order = sorted(reader, key=lambda k: -reader[k])
    assert admin_order == reader_order


def test_idf_is_scoped_to_the_visible_corpus():
    """Document frequencies must not be computed over the whole store.

    Global df is observable through the returned score, which would let a
    caller confirm that a term occurs in documents they cannot see.
    """
    query_terms = {"zephyr"}
    store = _store(
        ("hidden1", "zephyr zephyr project notes", ["secret"]),
        ("hidden2", "zephyr rollout plan", ["secret"]),
        ("visible", "zephyr mentioned once here", ["public"]),
    )

    all_ids = [r.id for r in store._records.values()]
    visible_ids = ["visible"]

    n_all, df_all = store._corpus_stats(all_ids, query_terms)
    n_vis, df_vis = store._corpus_stats(visible_ids, query_terms)

    assert (n_all, df_all["zephyr"]) == (3, 3)
    assert (n_vis, df_vis["zephyr"]) == (1, 1)


def test_repeated_query_terms_do_not_change_the_ranking():
    """Regression: iterating a query *list* summed a repeated term linearly,
    reintroducing exactly the growth BM25's saturation exists to prevent, so
    "the expense policy on the expense policy" scored 2x.

    `hybrid_search` now dedupes at the boundary and `_bm25` takes a set, so the
    duplication is structurally impossible rather than merely handled. What is
    still worth asserting is the user-visible property: repeating a word must
    not reorder results. Scores are not compared because the two queries are
    different strings and therefore embed differently.
    """
    store = _store(
        ("policy", "expense policy per diem limits", ["public"]),
        ("other", "incident severity escalation ladder", ["public"]),
        ("filler", "cafeteria lunch menu noon", ["public"]),
    )
    plain = list(_scores(store, "expense policy", ["public"]))
    repeated = list(_scores(store, "expense policy expense policy", ["public"]))
    assert plain == repeated
    assert plain[0] == "policy"


def test_rare_term_outranks_a_common_one():
    """The defect that motivated BM25: raw overlap ignored term rarity."""
    common = [(f"common{i}", "quarterly report meeting notes agenda", ["public"]) for i in range(8)]
    store = _store(*common, ("rare", "quarterly report defenestration clause", ["public"]))
    scores = _scores(store, "defenestration report", ["public"])
    assert max(scores, key=scores.get) == "rare"


def test_longer_chunk_with_the_same_hit_scores_lower():
    """Length normalisation: b=0.75 should penalise padding."""
    filler = " ".join(f"word{i}" for i in range(200))
    store = _store(
        ("short", "password rotation ninety days", ["public"]),
        ("long", f"password rotation ninety days {filler}", ["public"]),
    )
    scores = _scores(store, "password rotation", ["public"])
    assert scores["short"] > scores["long"]


def test_delete_removes_term_counts():
    store = _store(
        ("keep", "alpha beta", ["public"]),
        ("drop", "alpha gamma", ["public"]),
    )
    assert store._corpus_stats(["keep", "drop"], {"alpha"})[1]["alpha"] == 2

    assert store.delete_document("drop") == 1
    remaining = [r.id for r in store._records.values()]
    assert store._corpus_stats(remaining, {"alpha"})[1]["alpha"] == 1
    assert "drop" not in store._tokens
    assert "drop" not in store._lengths


@pytest.mark.parametrize("groups", [None, ["public"], ["engineering"]])
def test_scores_stay_within_bounds(groups):
    store = _store(
        ("a", "password rotation policy ninety days", ["public"]),
        ("b", "incident severity escalation ladder", ["engineering"]),
    )
    for score in _scores(store, "password policy", groups).values():
        # 0.35*cos + 0.65*saturation, both bounded by 1.
        assert 0.0 < score <= 1.0
