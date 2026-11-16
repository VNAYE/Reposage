"""Text helpers shared by retrieval, fakes and cost estimation."""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SPLIT_RE = re.compile(r"[_\W]+")

STOPWORDS = frozenset(
    "a an and are as at be been but by for from had has have how i if in into is it its "
    "of on or our so than that the their then there these they this to was we were what "
    "when where which who why will with you your".split()
)


def split_identifier(token: str) -> list[str]:
    """``getUserByID`` -> ``get``, ``user``, ``by``, ``id``."""
    spaced = _CAMEL_RE.sub(" ", token.replace("-", "_"))
    return [part for part in _SPLIT_RE.split(spaced.lower()) if len(part) > 1]


def tokenize(text: str) -> list[str]:
    """Lower-cased word tokens, plus the pieces of snake/camel identifiers."""
    tokens: list[str] = []
    for match in _WORD_RE.findall(text):
        lower = match.lower()
        if len(lower) > 1 and lower not in STOPWORDS:
            tokens.append(lower)
        tokens.extend(part for part in split_identifier(match) if part not in STOPWORDS)
    return tokens


def estimate_tokens(text: str) -> int:
    """Rough token count for providers that do not report it (embeddings)."""
    return max(1, len(text) // 4)
