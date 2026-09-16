from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from cctv.api.schemas import ChatMessage, ConversationResponse


@dataclass
class Conversation:
    id: str
    messages: list[ChatMessage] = field(default_factory=list)
    azure_messages: list[dict[str, Any]] = field(default_factory=list)

    def to_response(self) -> ConversationResponse:
        return ConversationResponse(id=self.id, messages=list(self.messages))


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def create(self) -> Conversation:
        conversation_id = uuid.uuid4().hex
        conversation = Conversation(id=conversation_id)
        self._conversations[conversation_id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)


def image_urls_for_paths(image_paths: list[str]) -> list[str]:
    from urllib.parse import quote

    urls: list[str] = []
    for path in image_paths:
        encoded = "/".join(quote(part, safe="") for part in path.split("/"))
        urls.append(f"/api/images/{encoded}")
    return urls
