"""Server-Sent Events transport."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from reposage.domain.events import AnswerEvent, ErrorEvent

log = logging.getLogger(__name__)

_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # nginx: do not buffer the stream
}


def sse_response(events: AsyncIterator[AnswerEvent]) -> StreamingResponse:
    async def body() -> AsyncIterator[str]:
        try:
            async for event in events:
                yield event.to_sse()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("chat stream failed")
            yield ErrorEvent("Internal error while answering.", "internal_error").to_sse()

    return StreamingResponse(body(), media_type="text/event-stream", headers=_HEADERS)
