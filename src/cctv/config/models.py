from __future__ import annotations

from pydantic import BaseModel, Field


class CameraConfig(BaseModel):
    id: str
    name: str
    lat: float | None = None
    lon: float | None = None
    source: str


class ToolsConfig(BaseModel):
    internet: bool = False
    google_maps: bool = False


class AgentConfig(BaseModel):
    cameras: list[CameraConfig] = Field(default_factory=list)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
