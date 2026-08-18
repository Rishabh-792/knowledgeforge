"""Shared tokenizer.

The embedder and the BM25 scorer must split text identically. When they were
separate copies of the same regex, any drift between them would have degraded
retrieval silently, with no test failing.
"""

import re

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())
