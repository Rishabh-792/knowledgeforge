"""Recursive character chunker with overlap. Fully implemented — no cloud calls.

Strategy: split on progressively finer separators (paragraph, line, sentence,
word) until every piece fits `chunk_size`, then greedily merge pieces back up
to `chunk_size`, seeding each new chunk with the tail of the previous one so
context spans chunk boundaries.
"""

from dataclasses import dataclass

SEPARATORS = ["\n\n", "\n", ". ", " "]


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")
    text = text.strip()
    if not text:
        return []
    pieces = _recursive_split(text, chunk_size, SEPARATORS)
    merged = _merge_with_overlap(pieces, chunk_size, overlap)
    return [Chunk(i, t) for i, t in enumerate(merged)]


def _recursive_split(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    if not separators:
        # No separator left: hard-cut (e.g. minified or non-prose content).
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    sep, rest = separators[0], separators[1:]
    parts = text.split(sep)
    if len(parts) == 1:
        return _recursive_split(text, chunk_size, rest)
    out: list[str] = []
    for i, part in enumerate(parts):
        # Re-attach sentence/word separators so text stays readable;
        # paragraph breaks are dropped intentionally.
        piece = part + (sep if sep != "\n\n" and i < len(parts) - 1 else "")
        if len(piece) > chunk_size:
            out.extend(_recursive_split(piece, chunk_size, rest))
        elif piece.strip():
            out.append(piece)
    return out


def _merge_with_overlap(pieces: list[str], chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) + 1 > chunk_size:
            chunks.append(current.strip())
            current = _overlap_tail(current, overlap) + piece
        else:
            current = f"{current} {piece}".strip() if current else piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _overlap_tail(text: str, overlap: int) -> str:
    """Last `overlap` chars of `text`, trimmed to a word boundary."""
    if not overlap:
        return ""
    tail = text[-overlap:]
    cut = tail.find(" ")
    return tail[cut + 1 :] + " " if cut != -1 else ""
