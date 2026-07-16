"""End-to-end pipeline test in local mode: chunk -> embed -> index -> retrieve
-> answer, all with the credential-free implementations."""

from app.services.agent import Agent, calculator
from app.services.chunking import chunk_text
from app.services.embeddings import LocalHashEmbedder
from app.services.llm import NO_ANSWER, MockLLM
from app.services.rag import RagPipeline
from app.services.vector_store import ChunkRecord, InMemoryStore

VPN_DOC = (
    "Remote access requires the corporate VPN client. Employees must connect "
    "to the VPN before opening any internal tool. VPN sessions expire after "
    "twelve hours and require multi-factor authentication to renew."
)
EXPENSE_DOC = (
    "Expense reports are submitted through the finance portal. Receipts are "
    "mandatory for any purchase above twenty-five dollars. Reimbursement "
    "lands within two pay cycles."
)


def _pipeline() -> RagPipeline:
    embedder = LocalHashEmbedder(128)
    store = InMemoryStore()
    for doc_id, title, text in [
        ("vpn", "Remote Access Policy", VPN_DOC),
        ("exp", "Expense Guide", EXPENSE_DOC),
    ]:
        chunks = chunk_text(text, chunk_size=400, overlap=50)
        vectors = embedder.embed([c.text for c in chunks])
        store.upsert(
            [
                ChunkRecord(
                    id=f"{doc_id}-{c.index}",
                    doc_id=doc_id,
                    title=title,
                    category="policy",
                    chunk_index=c.index,
                    content=c.text,
                    vector=v,
                    acl_groups=["public"],
                )
                for c, v in zip(chunks, vectors)
            ]
        )
    return RagPipeline(embedder, store, MockLLM(), top_k=3)


def test_answer_is_grounded_in_right_document():
    result = _pipeline().answer("How long do VPN sessions last?", allowed_groups=[])
    assert "twelve hours" in result.answer
    assert result.citations
    assert result.citations[0]["doc_id"] == "vpn"


def test_unanswerable_question_degrades_gracefully():
    result = _pipeline().answer("zzqx unknowable gibberish", allowed_groups=[])
    assert result.answer in (NO_ANSWER, "No accessible documents matched your question.")


def test_retrieval_ranks_relevant_doc_first():
    hits = _pipeline().retrieve("receipts for expense reimbursement", allowed_groups=[])
    assert hits and hits[0].record.doc_id == "exp"


def test_agent_uses_calculator_for_math():
    pipeline = _pipeline()
    agent = Agent(pipeline, MockLLM(), max_iterations=4)
    result = agent.run("What is 12 * 4 + 1?", allowed_groups=[])
    assert "49" in result.answer
    assert result.steps[0]["tool"] == "calculator"


def test_agent_uses_search_for_knowledge_questions():
    pipeline = _pipeline()
    agent = Agent(pipeline, MockLLM(), max_iterations=4)
    result = agent.run("What does the VPN policy require?", allowed_groups=[])
    assert result.steps[0]["tool"] == "search"
    assert "VPN" in result.answer or "multi-factor" in result.answer


def test_calculator_rejects_code_injection():
    assert "error" in calculator("__import__('os').system('id')")
    assert "error" in calculator("1/0")
    assert calculator("2 ** 10") == "1024"
