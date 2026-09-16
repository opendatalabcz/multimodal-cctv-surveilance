from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


SceneTag = Literal[
    "road",
    "intersection",
    "highway",
    "parking",
    "bridge",
    "pedestrian",
    "public-square",
    "airport",
    "rail",
    "waterfront",
    "panorama",
    "indoor",
]


class CameraAnalysis(BaseModel):
    description: str = Field(max_length=240)
    scene_tags: list[SceneTag] = Field(default_factory=list, max_length=6)
    source_fingerprint: str
    analyzed_at: datetime


class SectorConfig(BaseModel):
    id: str
    name: str
    enabled: bool = True


class LocationConfig(BaseModel):
    id: str
    name: str
    sector_id: str | None = None
    enabled: bool = True
    lat: float | None = None
    lon: float | None = None


class CameraConfig(BaseModel):
    id: str
    name: str
    lat: float | None = None
    lon: float | None = None
    source: str
    sector_id: str | None = None
    location_id: str | None = None
    enabled: bool = True
    analysis: CameraAnalysis | None = None


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
    sectors: list[SectorConfig] = Field(default_factory=list)
    locations: list[LocationConfig] = Field(default_factory=list)
    cameras: list[CameraConfig] = Field(default_factory=list)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)


class AgentOverlay(BaseModel):
    """Local deltas on top of the committed catalog."""

    sectors: list[SectorConfig] = Field(default_factory=list)
    remove_sector_ids: list[str] = Field(default_factory=list)
    locations: list[LocationConfig] = Field(default_factory=list)
    remove_location_ids: list[str] = Field(default_factory=list)
    cameras: list[CameraConfig] = Field(default_factory=list)
    remove_camera_ids: list[str] = Field(default_factory=list)
    tools: ToolsConfig | None = None
