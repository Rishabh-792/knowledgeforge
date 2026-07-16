"""Application settings via pydantic-settings.

MODE is not a switch you set — it is derived from credential presence:
if the four Azure OpenAI + Azure AI Search values are populated the app
runs in "azure" mode, otherwise it runs fully local with mock backends.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_name: str = "KnowledgeForge"
    log_level: str = "INFO"
    jwt_secret: str = "dev-only-secret-change-me-please-0123456789"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60

    # Retrieval tuning
    chunk_size: int = 800
    chunk_overlap: int = 150
    embedding_dimensions: int = 256
    retrieval_top_k: int = 5
    agent_max_iterations: int = 4

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-06-01"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"

    # Azure AI Search
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index: str = "knowledgeforge-chunks"

    # Azure AI Language (PII)
    azure_language_endpoint: str = ""
    azure_language_api_key: str = ""

    # Azure AI Content Safety
    azure_content_safety_endpoint: str = ""
    azure_content_safety_api_key: str = ""

    # Azure Blob Storage (batch ingestion)
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "incoming-docs"

    @property
    def mode(self) -> str:
        """"azure" when core AI credentials are present, else "local"."""
        azure_ready = all(
            [
                self.azure_openai_endpoint,
                self.azure_openai_api_key,
                self.azure_search_endpoint,
                self.azure_search_api_key,
            ]
        )
        return "azure" if azure_ready else "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
