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
    preview_path: str | None = None


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


class ModelOption(BaseModel):
    """One deployment the chat UI can select.

    ``provider`` is ``azure`` for every shipped option. A later open-source
    model would use another provider and its own client; the chat loop rejects
    unknown providers instead of calling Azure.
    """

    id: str
    label: str
    provider: str = "azure"


DEFAULT_MODEL_ID = "gpt-5.6-luna"


def default_model_catalog() -> list[ModelOption]:
    return [
        ModelOption(id="gpt-5.6-luna", label="GPT-5.6 Luna", provider="azure"),
        ModelOption(id="gpt-4o", label="GPT-4o", provider="azure"),
        ModelOption(id="gpt-6-astra", label="GPT-6 Astra", provider="azure"),
    ]


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
    models: list[ModelOption] = Field(default_factory=default_model_catalog)
    model: str = DEFAULT_MODEL_ID


class AgentOverlay(BaseModel):
    """Local deltas on top of the committed catalog."""

    sectors: list[SectorConfig] = Field(default_factory=list)
    remove_sector_ids: list[str] = Field(default_factory=list)
    locations: list[LocationConfig] = Field(default_factory=list)
    remove_location_ids: list[str] = Field(default_factory=list)
    cameras: list[CameraConfig] = Field(default_factory=list)
    remove_camera_ids: list[str] = Field(default_factory=list)
    tools: ToolsConfig | None = None
    model: str | None = None
