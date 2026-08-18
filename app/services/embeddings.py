"""Embedder implementations behind a common Protocol.

* LocalHashEmbedder — deterministic, dependency-free signed feature hashing.
  Not semantically smart, but shared vocabulary between query and document
  produces meaningfully higher cosine similarity, which is exactly enough to
  exercise the full retrieval pipeline offline.
* AzureOpenAIEmbedder — thin wrapper over an Azure OpenAI embedding deployment.
"""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from app.core.exceptions import UpstreamServiceError

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class LocalHashEmbedder:
    """Signed feature hashing into a fixed-size, L2-normalised vector."""

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.md5(token.encode()).digest()  # stable across runs
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class AzureOpenAIEmbedder:
    """Azure OpenAI embeddings. Requires the `openai` package (requirements-azure.txt)."""

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
        self.dimensions = 3072  # text-embedding-3-large default

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        # NOTE: production deployment would add retry/backoff via tenacity here.
        try:
            response = self._client.embeddings.create(
                model=self._deployment, input=list(texts)
            )
        except Exception as exc:
            raise UpstreamServiceError(f"embedding request failed: {exc}") from exc
        return [item.embedding for item in response.data]
