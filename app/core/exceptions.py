"""Domain exceptions. Each carries the HTTP status the API should surface."""


class KnowledgeForgeError(Exception):
    """Base class for all domain errors."""

    status_code = 500

    def __init__(self, detail: str = "internal error"):
        self.detail = detail
        super().__init__(detail)


class DocumentNotFoundError(KnowledgeForgeError):
    status_code = 404


class UnsupportedDocumentError(KnowledgeForgeError):
    status_code = 415


class ContentBlockedError(KnowledgeForgeError):
    """Raised by the content-safety gate when input violates policy."""

    status_code = 422


class UpstreamServiceError(KnowledgeForgeError):
    """An Azure dependency failed or is misconfigured."""

    status_code = 502
