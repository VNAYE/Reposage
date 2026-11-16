"""The answering pipeline: guardrail -> retrieve -> prompt -> stream -> verify -> meter."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Sequence

from reposage.config import Settings
from reposage.domain.events import (
    AnswerEvent,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    TokenEvent,
    VerificationEvent,
)
from reposage.domain.interfaces import AnswerService, ChatProvider, Guardrail, Retriever, Verifier
from reposage.domain.models import Citation, ScoredChunk, Usage, VerificationResult
from reposage.generation.prompts import PromptBuilder
from reposage.generation.verifier import citations_in
from reposage.observability.metrics import MetricsRecorder

log = logging.getLogger(__name__)


class ChatService(AnswerService):
    def __init__(
        self,
        settings: Settings,
        guardrails: Sequence[Guardrail],
        retriever: Retriever,
        chat: ChatProvider,
        metrics: MetricsRecorder,
        prompt_builder: PromptBuilder | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        self._settings = settings
        self._guardrails = list(guardrails)
        self._retriever = retriever
        self._chat = chat
        self._metrics = metrics
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._verifier = verifier

    async def ask(self, *, repo: str, question: str) -> AsyncIterator[AnswerEvent]:
        started = time.perf_counter()
        question = (question or "").strip()

        for guardrail in self._guardrails:
            verdict = guardrail.inspect(question)
            if not verdict.allowed:
                await self._metrics.record(
                    Usage(model=self._chat.model),
                    kind="blocked",
                    repo=repo,
                    guardrail=guardrail.name,
                )
                yield ErrorEvent(verdict.reason, "blocked")
                return
            question = verdict.sanitized_text or question

        try:
            sources = await self._retriever.retrieve(
                repo=repo,
                query=question,
                limit=self._settings.retrieval_top_k,
            )
        except Exception as exc:
            log.exception("retrieval failed for %s", repo)
            yield ErrorEvent("Retrieval failed; check that the index is available.", "retrieval_error")
            return

        if not sources:
            yield ErrorEvent(
                f"No indexed sources found for {repo}. Index the repository first.",
                "no_sources",
            )
            return

        yield SourcesEvent(sources)

        answer_parts: list[str] = []
        usage = Usage(model=self._chat.model)
        try:
            async for delta in self._chat.stream(
                system=self._prompt_builder.system,
                prompt=self._prompt_builder.build(question, sources),
            ):
                if delta.text:
                    answer_parts.append(delta.text)
                    yield TokenEvent(delta.text)
                if delta.usage is not None:
                    usage = delta.usage
        except Exception:
            log.exception("chat provider failed for %s", repo)
            yield ErrorEvent("The language model request failed. Try again.", "provider_error")
            return

        answer = "".join(answer_parts).strip()
        if not answer:
            yield ErrorEvent("The model returned an empty answer.", "empty_answer")
            return

        usage.latency_ms = (time.perf_counter() - started) * 1000
        verification_started = time.perf_counter()
        verification = await self._verify(answer, sources, question)
        if verification is not None and verification.usage is not None:
            verification.usage.latency_ms = (time.perf_counter() - verification_started) * 1000
        citations = self._citations(answer, sources)

        await self._metrics.record(
            usage,
            kind="chat",
            repo=repo,
            verified=verification.supported if verification else None,
        )
        if verification is not None and verification.usage is not None:
            await self._metrics.record(
                verification.usage,
                kind="verify",
                repo=repo,
                verified=verification.supported,
            )

        if verification is not None:
            yield VerificationEvent(verification)
        yield DoneEvent(usage, citations)

    async def _verify(
        self,
        answer: str,
        sources: Sequence[ScoredChunk],
        question: str,
    ) -> VerificationResult | None:
        if not self._settings.verify_answers or self._verifier is None:
            return None
        try:
            return await self._verifier.verify(answer=answer, sources=sources, question=question)
        except Exception:
            log.exception("verification failed")
            return VerificationResult(
                supported=True,
                score=0.0,
                verifier="unavailable",
                unsupported_claims=("verification failed",),
            )

    @staticmethod
    def _citations(answer: str, sources: Sequence[ScoredChunk]) -> list[Citation]:
        citations: list[Citation] = []
        for index in citations_in(answer):
            if 1 <= index <= len(sources):
                chunk = sources[index - 1].chunk
                citations.append(
                    Citation(
                        source_id=f"S{index}",
                        path=chunk.path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        symbol=chunk.symbol,
                    )
                )
        return citations
