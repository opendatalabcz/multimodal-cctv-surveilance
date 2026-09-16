from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class CameraConfig(BaseModel):
    id: str
    name: str
    lat: float | None = None
    lon: float | None = None
    source: str


class ToolsConfig(BaseModel):
    internet: bool = False
    weather: bool = False
    maps: bool = False

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_google_maps(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "google_maps" in data:
            if "maps" not in data:
                data["maps"] = data["google_maps"]
            data.pop("google_maps", None)
        return data


class AgentConfig(BaseModel):
    cameras: list[CameraConfig] = Field(default_factory=list)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)


class AgentOverlay(BaseModel):
    """Local deltas on top of the committed catalog."""

    cameras: list[CameraConfig] = Field(default_factory=list)
    remove_camera_ids: list[str] = Field(default_factory=list)
    tools: ToolsConfig | None = None
