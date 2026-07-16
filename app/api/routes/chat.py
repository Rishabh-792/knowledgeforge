"""RAG chat with session history.

Sessions live behind SessionStore so the in-memory default can be swapped for
a Cosmos DB or Redis implementation without touching the route.
"""

import uuid
from collections import defaultdict
from functools import lru_cache
from typing import Protocol

from fastapi import APIRouter, Depends

from app.api.deps import get_agent, get_rag, get_safety_gate
from app.core.security import Principal, require_role
from app.models.schemas import ChatRequest, ChatResponse, Citation
from app.services.agent import Agent
from app.services.llm import Message
from app.services.rag import RagPipeline
from app.services.safety import SafetyGate

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_HISTORY_MESSAGES = 10


class SessionStore(Protocol):
    def get(self, session_id: str) -> list[Message]: ...

    def append(self, session_id: str, role: str, content: str) -> None: ...


class InMemorySessionStore:
    """Per-process session history.

    NOTE: production deployment swaps this for Cosmos DB or Redis so history
    survives restarts and scale-out; the Protocol above is the contract.
    """

    def __init__(self):
        self._sessions: dict[str, list[Message]] = defaultdict(list)

    def get(self, session_id: str) -> list[Message]:
        return self._sessions[session_id][-MAX_HISTORY_MESSAGES:]

    def append(self, session_id: str, role: str, content: str) -> None:
        self._sessions[session_id].append({"role": role, "content": content})


@lru_cache
def get_session_store() -> SessionStore:
    return InMemorySessionStore()


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    principal: Principal = Depends(require_role("reader")),
    rag: RagPipeline = Depends(get_rag),
    agent: Agent = Depends(get_agent),
    safety: SafetyGate = Depends(get_safety_gate),
    sessions: SessionStore = Depends(get_session_store),
) -> ChatResponse:
    safety.check(body.message)
    session_id = body.session_id or uuid.uuid4().hex[:12]
    history = sessions.get(session_id)

    if body.use_agent:
        result = agent.run(body.message, principal.acl_groups)
        answer, citations, steps = result.answer, [], result.steps
    else:
        rag_answer = rag.answer(body.message, principal.acl_groups, history)
        answer = rag_answer.answer
        citations = [Citation(**c) for c in rag_answer.citations]
        steps = []

    sessions.append(session_id, "user", body.message)
    sessions.append(session_id, "assistant", answer)
    return ChatResponse(
        session_id=session_id, answer=answer, citations=citations, agent_steps=steps
    )
