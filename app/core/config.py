"""Application settings via pydantic-settings.

MODE is not a switch you set — it is derived from credential presence:
if the four Azure OpenAI + Azure AI Search values are populated the app
runs in "azure" mode, otherwise it runs fully local with mock backends.
"""

import secrets
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Retained only so the production validator can still recognise and reject the
# value that used to ship as the default. Nothing signs with it any more.
_DEV_JWT_SECRET = "dev-only-secret-change-me-please-0123456789"


def _ephemeral_jwt_secret() -> str:
    """A fresh signing key per process when none is configured.

    The previous default was a constant published in this repository, so anyone
    who stood the demo up on a reachable host had forgeable auth: mint
    {"role": "admin"} and RBAC returns everything. Tokens now stop working
    across restarts, which is the correct trade for a demo.
    """
    return secrets.token_urlsafe(32)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_name: str = "KnowledgeForge"
    log_level: str = "INFO"
    jwt_secret: str = Field(default_factory=_ephemeral_jwt_secret)
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60
    # Opt-in ONLY: lets tokenless requests act as a dev admin for the local
    # quickstart. Refused outright in azure mode (see validator below).
    allow_anonymous_dev_admin: bool = False

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

    @model_validator(mode="after")
    def _fill_blank_jwt_secret(self) -> "Settings":
        """Treat a blank JWT_SECRET as unset.

        .env.example ships `JWT_SECRET=` so no constant key is published. A
        copied .env therefore supplies an empty string, which *overrides* the
        random default rather than triggering it — the app would sign every
        token with "". Blank means "generate one".
        """
        if not self.jwt_secret.strip():
            self.jwt_secret = _ephemeral_jwt_secret()
        return self

    @model_validator(mode="after")
    def _enforce_production_auth(self) -> "Settings":
        """Fail fast instead of running azure mode with dev-grade auth."""
        if self.mode == "azure":
            if self.jwt_secret == _DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be set to a strong value (>= 32 chars) "
                    "when Azure credentials are configured"
                )
            if self.allow_anonymous_dev_admin:
                raise ValueError(
                    "ALLOW_ANONYMOUS_DEV_ADMIN must be false "
                    "when Azure credentials are configured"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
