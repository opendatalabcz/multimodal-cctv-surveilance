from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from cctv.api.schemas import ChatMessage, ConversationResponse
from cctv.config.agent_yaml import load_agent_config
from cctv.config.models import AgentConfig
from cctv.config.prompt import build_welcome_message, build_welcome_suggestions


@dataclass
class Conversation:
    id: str
    messages: list[ChatMessage] = field(default_factory=list)
    azure_messages: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_response(self) -> ConversationResponse:
        return ConversationResponse(
            id=self.id,
            messages=list(self.messages),
            suggestions=list(self.suggestions),
        )

    def has_user_turn(self) -> bool:
        return any(message.role == "user" for message in self.messages)


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def create(self) -> Conversation:
        config = load_agent_config()
        conversation = Conversation(
            id=uuid.uuid4().hex,
            messages=[_welcome_message(config)],
            suggestions=build_welcome_suggestions(config),
        )
        self._conversations[conversation.id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def clear(self) -> None:
        self._conversations.clear()

    def refresh_idle_welcomes(self) -> None:
        config = load_agent_config()
        greeting = _welcome_message(config)
        suggestions = build_welcome_suggestions(config)
        for conversation in self._conversations.values():
            if conversation.has_user_turn():
                continue
            conversation.messages = [greeting]
            conversation.suggestions = list(suggestions)


def _welcome_message(config: AgentConfig) -> ChatMessage:
    return ChatMessage(role="assistant", content=build_welcome_message(config))


def image_urls_for_paths(image_paths: list[str]) -> list[str]:
    from urllib.parse import quote

    urls: list[str] = []
    for path in image_paths:
        encoded = "/".join(quote(part, safe="") for part in path.split("/"))
        urls.append(f"/api/images/{encoded}")
    return urls
