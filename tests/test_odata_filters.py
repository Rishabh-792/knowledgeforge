"""OData filter construction must not be injectable via user-controlled values."""

import pytest

from app.services.vector_store import _odata_literal, _safe_ids


def test_odata_literal_escapes_quotes():
    assert _odata_literal("security") == "'security'"
    # A classic breakout attempt gets neutralised by quote doubling.
    assert (
        _odata_literal("x' or category ne '")
        == "'x'' or category ne '''"
    )


def test_safe_ids_accepts_normal_group_names():
    assert _safe_ids(["public", "engineering", "team-a_1.eu"]) == [
        "public",
        "engineering",
        "team-a_1.eu",
    ]


@pytest.mark.parametrize(
    "bad", ["eng,admin", "a' or 'b", "g)  ", "", "x" * 129]
)
def test_safe_ids_rejects_delimiters_and_syntax(bad):
    with pytest.raises(ValueError):
        _safe_ids([bad])
