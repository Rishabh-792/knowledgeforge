"""Content-safety gate run on inbound documents and chat messages.

* KeywordGate — working local implementation with a small phrase blocklist.
* AzureContentSafetyGate — Azure AI Content Safety text analysis with
  per-category severity thresholds; production-shaped but concise.

Both raise ContentBlockedError so callers have a single failure mode.
"""

import logging
from typing import Protocol

from app.core.exceptions import ContentBlockedError, UpstreamServiceError

logger = logging.getLogger(__name__)


class SafetyGate(Protocol):
    def check(self, text: str) -> None: ...


class KeywordGate:
    """Phrase blocklist; local-mode default.

    NOTE: naive substring matching — the Azure gate is the real classifier,
    this exists so the pipeline stage is exercised offline.
    """

    BLOCKED_PHRASES = (
        "how to build a weapon",
        "make an explosive",
        "synthesize a nerve agent",
        "instructions for self-harm",
    )

    def check(self, text: str) -> None:
        lowered = text.lower()
        for phrase in self.BLOCKED_PHRASES:
            if phrase in lowered:
                logger.warning(
                    "content blocked", extra={"ctx": {"phrase": phrase}}
                )
                raise ContentBlockedError(
                    "content violates the acceptable-use policy"
                )


class AzureContentSafetyGate:
    """Azure AI Content Safety (requirements-azure.txt)."""

    SEVERITY_THRESHOLD = 2  # block medium and above on any category

    def __init__(self, endpoint: str, api_key: str):
        try:
            from azure.ai.contentsafety import ContentSafetyClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:  # pragma: no cover
            raise UpstreamServiceError(
                "azure-ai-contentsafety not installed; "
                "pip install -r requirements-azure.txt"
            ) from exc
        self._client = ContentSafetyClient(endpoint, AzureKeyCredential(api_key))

    def check(self, text: str) -> None:
        from azure.ai.contentsafety.models import AnalyzeTextOptions

        try:
            analysis = self._client.analyze_text(AnalyzeTextOptions(text=text[:10000]))
        except Exception as exc:
            raise UpstreamServiceError(f"content safety call failed: {exc}") from exc
        for item in analysis.categories_analysis:
            if (item.severity or 0) >= self.SEVERITY_THRESHOLD:
                logger.warning(
                    "content blocked",
                    extra={"ctx": {"category": str(item.category)}},
                )
                raise ContentBlockedError(
                    f"content blocked: {item.category} severity {item.severity}"
                )
