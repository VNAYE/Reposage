from __future__ import annotations

from collections.abc import Sequence

from reposage.domain.interfaces import Verifier
from reposage.domain.models import Chunk, ScoredChunk, VerificationResult
from reposage.generation.verifier import (
    CitationVerifier,
    CompositeVerifier,
    LlmGroundednessVerifier,
    citations_in,
)
from reposage.providers.fakes import FakeChatProvider


def _sources(count: int) -> list[ScoredChunk]:
    return [
        ScoredChunk(
            chunk=Chunk(
                id=f"chunk-{index}",
                repo="owner/repo",
                path=f"file_{index}.py",
                start_line=1,
                end_line=5,
                language="python",
                symbol="example",
                content="def example(): pass",
            )
        )
        for index in range(1, count + 1)
    ]


def test_citations_in_preserves_order_and_deduplicates() -> None:
    assert citations_in("See [S2], [S1] and [S2] again.") == [2, 1]


async def test_citation_verifier_accepts_existing_sources() -> None:
    result = await CitationVerifier().verify(answer="See [S1] and [S2].", sources=_sources(2))
    assert result.supported
    assert result.score == 1.0
    assert result.cited_sources == ("S1", "S2")


async def test_citation_verifier_rejects_unknown_source() -> None:
    result = await CitationVerifier().verify(answer="See [S9].", sources=_sources(2))
    assert not result.supported
    assert "S9" in result.unsupported_claims[0]


async def test_citation_verifier_rejects_answer_without_citations() -> None:
    result = await CitationVerifier().verify(answer="Trust me.", sources=_sources(2))
    assert not result.supported
    assert result.score == 0.0


async def test_citation_verifier_accepts_honest_refusal() -> None:
    result = await CitationVerifier().verify(
        answer="I could not find this in the indexed sources.", sources=_sources(2)
    )
    assert result.supported
    assert result.score == 1.0


async def test_llm_verifier_returns_provider_usage() -> None:
    result = await LlmGroundednessVerifier(FakeChatProvider()).verify(
        answer="See [S1].", sources=_sources(1), question="What does this do?"
    )
    assert result.supported
    assert result.usage is not None
    assert result.usage.total_tokens > 0


class _StubVerifier(Verifier):
    name = "stub"

    def __init__(self, supported: bool) -> None:
        self._supported = supported

    async def verify(
        self,
        *,
        answer: str,
        sources: Sequence[ScoredChunk],
        question: str = "",
    ) -> VerificationResult:
        return VerificationResult(
            supported=self._supported,
            score=1.0 if self._supported else 0.0,
            verifier=self.name,
            unsupported_claims=() if self._supported else ("made up",),
        )


async def test_composite_verifier_requires_every_check_to_pass() -> None:
    result = await CompositeVerifier([_StubVerifier(True), _StubVerifier(False)]).verify(
        answer="x", sources=_sources(1)
    )
    assert not result.supported
    assert result.unsupported_claims == ("made up",)
    assert result.score == 0.0
