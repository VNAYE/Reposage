"""Streaming events emitted by the chat pipeline, each serialising itself as SSE."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from .models import Citation, ScoredChunk, Usage, VerificationResult


class AnswerEvent(ABC):
    type: ClassVar[str] = "event"

    @abstractmethod
    def payload(self) -> dict[str, Any]:
        """JSON-serialisable body of the event."""

    def to_sse(self) -> str:
        return f"event: {self.type}\ndata: {json.dumps(self.payload(), ensure_ascii=False)}\n\n"


class SourcesEvent(AnswerEvent):
    type = "sources"

    def __init__(self, sources: list[ScoredChunk]) -> None:
        self.sources = sources

    def payload(self) -> dict[str, Any]:
        return {"sources": [source.to_dict() for source in self.sources]}


class TokenEvent(AnswerEvent):
    type = "token"

    def __init__(self, text: str) -> None:
        self.text = text

    def payload(self) -> dict[str, Any]:
        return {"text": self.text}


class VerificationEvent(AnswerEvent):
    type = "verification"

    def __init__(self, result: VerificationResult) -> None:
        self.result = result

    def payload(self) -> dict[str, Any]:
        return {"verification": self.result.to_dict()}


class DoneEvent(AnswerEvent):
    type = "done"

    def __init__(self, usage: Usage, citations: list[Citation]) -> None:
        self.usage = usage
        self.citations = citations

    def payload(self) -> dict[str, Any]:
        return {
            "usage": self.usage.to_dict(),
            "citations": [citation.to_dict() for citation in self.citations],
        }


class ErrorEvent(AnswerEvent):
    type = "error"

    def __init__(self, message: str, code: str = "error") -> None:
        self.message = message
        self.code = code

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}
