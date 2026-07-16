"""Document cracking: turn an uploaded/blob file into plain text."""

from pathlib import Path

from app.core.exceptions import UnsupportedDocumentError

TEXT_SUFFIXES = {".md", ".txt", ".csv", ".log"}


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return data.decode("utf-8", errors="replace")
    if suffix == ".pdf":
        return _extract_pdf(data)
    if suffix == ".docx":
        return _extract_docx(data)
    raise UnsupportedDocumentError(f"unsupported file type: '{suffix or filename}'")


def _extract_pdf(data: bytes) -> str:
    import io

    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise UnsupportedDocumentError(f"could not parse PDF: {exc}") from exc


def _extract_docx(data: bytes) -> str:
    import io

    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        raise UnsupportedDocumentError(f"could not parse DOCX: {exc}") from exc
