"""PII redaction applied to every document before indexing.

* RegexRedactor — working local implementation covering the classic
  high-signal patterns (emails, phone numbers, national IDs, card numbers).
* AzureLanguageRedactor — Azure AI Language PII detection, production-shaped
  but concise.
"""

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from app.core.exceptions import UpstreamServiceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PIIFinding:
    category: str
    text: str


class PIIRedactor(Protocol):
    def redact(self, text: str) -> tuple[str, list[PIIFinding]]: ...


class RegexRedactor:
    """Deterministic pattern-based redaction; local-mode default."""

    # ponytail: regexes catch the obvious 90%; entity-model redaction is the Azure path.
    PATTERNS: dict[str, re.Pattern] = {
        "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        "phone": re.compile(r"\+?\d[\d\s().-]{8,}\d"),
        "national_id": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "card_number": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    }

    def redact(self, text: str) -> tuple[str, list[PIIFinding]]:
        findings: list[PIIFinding] = []
        for category, pattern in self.PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(PIIFinding(category, match.group()))
            text = pattern.sub(f"[REDACTED:{category}]", text)
        if findings:
            logger.info(
                "pii redacted", extra={"ctx": {"count": len(findings)}}
            )
        return text, findings


class AzureLanguageRedactor:
    """Azure AI Language PII detection (requirements-azure.txt)."""

    def __init__(self, endpoint: str, api_key: str):
        try:
            from azure.ai.textanalytics import TextAnalyticsClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:  # pragma: no cover
            raise UpstreamServiceError(
                "azure-ai-textanalytics not installed; "
                "pip install -r requirements-azure.txt"
            ) from exc
        self._client = TextAnalyticsClient(endpoint, AzureKeyCredential(api_key))

    def redact(self, text: str) -> tuple[str, list[PIIFinding]]:
        # The service caps document size; production would chunk before calling.
        try:
            result = self._client.recognize_pii_entities([text[:5000]])[0]
        except Exception as exc:
            raise UpstreamServiceError(f"pii detection failed: {exc}") from exc
        if result.is_error:
            raise UpstreamServiceError(f"pii detection error: {result.error}")
        findings = [
            PIIFinding(entity.category, entity.text) for entity in result.entities
        ]
        return result.redacted_text, findings
