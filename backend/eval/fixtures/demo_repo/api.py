"""Minimal chat endpoint used by the demo service."""

from dataclasses import dataclass
from typing import Callable

from auth import validate_token


@dataclass
class ChatRequest:
    repo: str
    question: str
    token: str


def handle_chat(request: ChatRequest, answer: Callable[[str], str]) -> dict:
    """Authenticate the caller, then answer the question."""
    user_id = validate_token(request.token)
    if user_id is None:
        return {"status": 401, "error": "invalid or expired token"}

    return {"status": 200, "user_id": user_id, "answer": answer(request.question)}
