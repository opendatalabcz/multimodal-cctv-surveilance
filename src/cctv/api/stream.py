from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Iterator
from typing import Any

from fastapi.responses import StreamingResponse

from cctv.api.chat import run_chat_turn
from cctv.api.store import Conversation

logger = logging.getLogger("cctv.api")
_SENTINEL = object()


def _sse_line(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def iter_chat_turn_sse(conversation: Conversation, content: str) -> Iterator[str]:
    events: queue.Queue[object] = queue.Queue()

    def on_progress(event: dict[str, Any]) -> None:
        events.put(event)

    def worker() -> None:
        try:
            updated, result = run_chat_turn(conversation, content, on_progress=on_progress)
            if not result.get("success"):
                error = result.get("error", "Chat turn failed")
                logger.error("Chat turn failed for %s: %s", conversation.id, error)
                events.put({"type": "error", "detail": error})
            else:
                events.put(
                    {
                        "type": "done",
                        "conversation": updated.to_response().model_dump(mode="json"),
                    }
                )
        except Exception as exc:
            logger.exception("Chat stream failed for %s", conversation.id)
            events.put({"type": "error", "detail": str(exc)})
        finally:
            events.put(_SENTINEL)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = events.get()
        if item is _SENTINEL:
            break
        if isinstance(item, dict):
            yield _sse_line(item)


def chat_turn_stream_response(conversation: Conversation, content: str) -> StreamingResponse:
    return StreamingResponse(
        iter_chat_turn_sse(conversation, content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
