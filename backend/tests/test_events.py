from __future__ import annotations

import json

from reposage.domain.events import DoneEvent, ErrorEvent, TokenEvent
from reposage.domain.models import Citation, Usage


def test_token_event_serialises_multiline_text_as_one_frame() -> None:
    frame = TokenEvent("hello\nworld").to_sse()

    assert frame.startswith("event: token\ndata: ")
    assert frame.endswith("\n\n")
    body = json.loads(frame.split("data: ", 1)[1])
    assert body["text"] == "hello\nworld"


def test_done_event_carries_usage_and_citations() -> None:
    frame = DoneEvent(
        Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15, cost_usd=0.001, model="m"),
        [Citation("S1", "auth.py", 1, 5, "validate_token")],
    ).to_sse()

    assert frame.startswith("event: done\ndata: ")
    body = json.loads(frame.split("data: ", 1)[1])
    assert body["usage"]["total_tokens"] == 15
    assert body["citations"][0]["path"] == "auth.py"


def test_error_event_has_code() -> None:
    body = json.loads(ErrorEvent("nope", "blocked").to_sse().split("data: ", 1)[1])
    assert body == {"code": "blocked", "message": "nope"}
