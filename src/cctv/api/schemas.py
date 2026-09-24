from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from cctv.config.models import AgentConfig, CameraConfig, SectorConfig, ToolsConfig


class ConfigResponse(AgentConfig):
    """GET/PUT /api/config body."""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    imageUrls: list[str] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class PostMessageRequest(BaseModel):
    content: str


__all__ = [
    "AgentConfig",
    "CameraConfig",
    "ChatMessage",
    "ConfigResponse",
    "ConversationResponse",
    "PostMessageRequest",
    "SectorConfig",
    "ToolsConfig",
]
