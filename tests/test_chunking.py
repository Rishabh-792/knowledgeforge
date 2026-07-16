import pytest

from app.services.chunking import chunk_text

PARAGRAPH = (
    "Access reviews run every quarter. Managers confirm that direct reports "
    "still need each entitlement. Unconfirmed access is revoked automatically "
    "after fourteen days. Exceptions require a written risk acceptance."
)
LONG_TEXT = "\n\n".join(PARAGRAPH for _ in range(10))


def test_empty_input_yields_no_chunks():
    assert chunk_text("   \n  ") == []


def test_short_text_is_single_chunk():
    chunks = chunk_text("Just one small paragraph.", chunk_size=800)
    assert len(chunks) == 1
    assert chunks[0].index == 0


def test_chunks_respect_size_limit():
    chunks = chunk_text(LONG_TEXT, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)


def test_consecutive_chunks_share_overlap_words():
    chunks = chunk_text(LONG_TEXT, chunk_size=300, overlap=80)
    tail_words = chunks[0].text[-80:].split()
    head = chunks[1].text[:160]
    assert any(word in head for word in tail_words)


def test_indexes_are_sequential():
    chunks = chunk_text(LONG_TEXT, chunk_size=300, overlap=50)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_hard_cut_handles_text_without_separators():
    blob = "x" * 1000
    chunks = chunk_text(blob, chunk_size=300, overlap=0)
    assert all(len(c.text) <= 300 for c in chunks)
    assert sum(len(c.text) for c in chunks) == 1000


@pytest.mark.parametrize("size,overlap", [(0, 0), (100, 100), (100, -1)])
def test_invalid_parameters_raise(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=size, overlap=overlap)
