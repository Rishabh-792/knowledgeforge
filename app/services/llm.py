"""LLM implementations behind a common Protocol.

* MockLLM — extractive answerer for credential-free local mode: scores the
  sentences of the supplied SOURCES block against the question by token
  overlap and returns the best ones in document order.
* AzureOpenAIChat — thin wrapper over an Azure OpenAI chat deployment.
"""

import re
from typing import Protocol

from app.core.exceptions import UpstreamServiceError

Message = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": str}

NO_ANSWER = "I could not find an answer to that in the indexed documents."

_STOPWORDS = frozenset(
    "a an and are as at be but by do does for from has have how i in is it of on "
    "or that the this to was we what when where which who why will with you your".split()
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


class LLM(Protocol):
    def complete(self, messages: list[Message], temperature: float = 0.1) -> str: ...


class MockLLM:
    """Deterministic extractive answering — no network, no keys."""

    def complete(self, messages: list[Message], temperature: float = 0.1) -> str:
        question = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        context = "\n".join(m["content"] for m in messages if m["role"] == "system")
        if "SOURCES:" in context:
            context = context.split("SOURCES:", 1)[1]
        q_tokens = _tokens(question)
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+|\n+", context)
            if len(s.strip()) > 20
        ]
        scored = [
            (len(q_tokens & _tokens(s)), i, s) for i, s in enumerate(sentences)
        ]
        best = [t for t in scored if t[0] >= 2] or [t for t in scored if t[0] >= 1]
        if not best:
            return NO_ANSWER
        best.sort(key=lambda t: (-t[0], t[1]))
        picked = sorted(best[:3], key=lambda t: t[1])  # restore document order
        return " ".join(s for _, _, s in picked)


class AzureOpenAIChat:
    """Azure OpenAI chat completion. Requires `openai` (requirements-azure.txt)."""

    def __init__(self, endpoint: str, api_key: str, deployment: str, api_version: str):
        try:
            from openai import AzureOpenAI
        except ImportError as exc:  # pragma: no cover
            raise UpstreamServiceError(
                "openai package not installed; pip install -r requirements-azure.txt"
            ) from exc
        self._client = AzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key, api_version=api_version
        )
        self._deployment = deployment

    def complete(self, messages: list[Message], temperature: float = 0.1) -> str:
        # NOTE: production deployment would add retry/backoff via tenacity here.
        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                temperature=temperature,
            )
        except Exception as exc:
            raise UpstreamServiceError(f"chat completion failed: {exc}") from exc
        return response.choices[0].message.content or ""
