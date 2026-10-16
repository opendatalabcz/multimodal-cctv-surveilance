from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from cctv.config.models import AgentConfig


class ConfigResponse(AgentConfig):
    """GET/PUT /api/config body."""


class ImageAnnotation(BaseModel):
    type: Literal["box", "point", "line", "polygon"]
    points: list[list[int]]
    label: str | None = None


class PresentedImage(BaseModel):
    url: str
    cameraId: str
    annotations: list[ImageAnnotation] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    images: list[PresentedImage] = Field(default_factory=list)
    model: str | None = None


class ConversationResponse(BaseModel):
    id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class PostMessageRequest(BaseModel):
    content: str
