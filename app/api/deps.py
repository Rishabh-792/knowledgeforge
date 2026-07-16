"""Dependency wiring. Each provider inspects settings.mode once and returns a
process-wide singleton, so routes only ever depend on the Protocols."""

from functools import lru_cache

from app.core.config import get_settings
from app.services.agent import Agent
from app.services.embeddings import AzureOpenAIEmbedder, Embedder, LocalHashEmbedder
from app.services.llm import LLM, AzureOpenAIChat, MockLLM
from app.services.pii import AzureLanguageRedactor, PIIRedactor, RegexRedactor
from app.services.rag import RagPipeline
from app.services.safety import AzureContentSafetyGate, KeywordGate, SafetyGate
from app.services.vector_store import AzureAISearchStore, InMemoryStore, VectorStore


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.mode == "azure":
        return AzureOpenAIEmbedder(
            s.azure_openai_endpoint,
            s.azure_openai_api_key,
            s.azure_openai_embedding_deployment,
            s.azure_openai_api_version,
        )
    return LocalHashEmbedder(s.embedding_dimensions)


@lru_cache
def get_vector_store() -> VectorStore:
    s = get_settings()
    if s.mode == "azure":
        return AzureAISearchStore(
            s.azure_search_endpoint, s.azure_search_api_key, s.azure_search_index
        )
    return InMemoryStore()


@lru_cache
def get_llm() -> LLM:
    s = get_settings()
    if s.mode == "azure":
        return AzureOpenAIChat(
            s.azure_openai_endpoint,
            s.azure_openai_api_key,
            s.azure_openai_chat_deployment,
            s.azure_openai_api_version,
        )
    return MockLLM()


@lru_cache
def get_rag() -> RagPipeline:
    s = get_settings()
    return RagPipeline(get_embedder(), get_vector_store(), get_llm(), s.retrieval_top_k)


@lru_cache
def get_agent() -> Agent:
    return Agent(get_rag(), get_llm(), get_settings().agent_max_iterations)


@lru_cache
def get_pii_redactor() -> PIIRedactor:
    s = get_settings()
    if s.azure_language_endpoint and s.azure_language_api_key:
        return AzureLanguageRedactor(s.azure_language_endpoint, s.azure_language_api_key)
    return RegexRedactor()


@lru_cache
def get_safety_gate() -> SafetyGate:
    s = get_settings()
    if s.azure_content_safety_endpoint and s.azure_content_safety_api_key:
        return AzureContentSafetyGate(
            s.azure_content_safety_endpoint, s.azure_content_safety_api_key
        )
    return KeywordGate()


def reset_singletons() -> None:
    """Test hook: drop all cached providers (e.g. to get a fresh store)."""
    for provider in (
        get_embedder,
        get_vector_store,
        get_llm,
        get_rag,
        get_agent,
        get_pii_redactor,
        get_safety_gate,
    ):
        provider.cache_clear()
