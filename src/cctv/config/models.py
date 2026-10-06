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


class ModelReasoning(BaseModel):
    """Values the chat header may select for one model control.

    For reasoning, ``default`` means omit ``reasoning_effort`` on Chat
    Completions. An empty ``choices`` list means the control is disabled.
    ``locked`` keeps the control on ``default`` and disables it. Verbosity
    reuses this shape; its default is ``medium``, which omits the API field.
    """

    choices: list[str] = Field(default_factory=list)
    default: str = "default"
    locked: bool = False


class ModelOption(BaseModel):
    """One deployment the chat UI can select.

    ``provider`` is ``azure`` for every shipped option. A later open-source
    model would use another provider and its own client; the chat loop rejects
    unknown providers instead of calling Azure.

    ``transport`` is ``chat_completions`` or ``responses``. GPT-6 Astra tool
    calls require the Responses API.
    """

    id: str
    label: str
    provider: str = "azure"
    transport: Literal["chat_completions", "responses"] = "chat_completions"
    reasoning: ModelReasoning = Field(default_factory=ModelReasoning)
    verbosity: ModelReasoning = Field(
        default_factory=lambda: ModelReasoning(choices=[], default="medium", locked=True)
    )


DEFAULT_MODEL_ID = "gpt-5.6-luna"
DEFAULT_REASONING = "default"
DEFAULT_VERBOSITY = "medium"


def default_model_catalog() -> list[ModelOption]:
    return [
        ModelOption(
            id="gpt-5.6-luna",
            label="GPT-5.6 Luna",
            provider="azure",
            transport="chat_completions",
            reasoning=ModelReasoning(
                choices=["default", "low", "medium", "high"],
                default="default",
                locked=False,
            ),
            verbosity=ModelReasoning(
                choices=["low", "medium", "high"],
                default="medium",
                locked=False,
            ),
        ),
        ModelOption(
            id="gpt-4o",
            label="GPT-4o",
            provider="azure",
            transport="chat_completions",
            reasoning=ModelReasoning(choices=[], default="default", locked=True),
            verbosity=ModelReasoning(choices=[], default="medium", locked=True),
        ),
        ModelOption(
            id="gpt-6-astra",
            label="GPT-6 Astra",
            provider="azure",
            transport="responses",
            reasoning=ModelReasoning(
                choices=["low", "medium", "high", "xhigh", "max"],
                default="medium",
                locked=False,
            ),
            verbosity=ModelReasoning(
                choices=["low", "medium", "high"],
                default="medium",
                locked=False,
            ),
        ),
    ]


def model_by_id(models: list[ModelOption], model_id: str) -> ModelOption | None:
    return next((item for item in models if item.id == model_id), None)


def clamp_control(control: ModelReasoning | None, requested: str | None, fallback: str) -> str:
    """Return a value this control accepts, or its catalog default."""
    if control is None:
        return requested or fallback
    if not control.choices:
        return control.default
    if requested in control.choices:
        return requested
    return control.default


def clamp_reasoning(option: ModelOption | None, requested: str | None) -> str:
    """Return an effort this model accepts, or its catalog default."""
    if option is None:
        return clamp_control(None, requested, DEFAULT_REASONING)
    return clamp_control(option.reasoning, requested, DEFAULT_REASONING)


def clamp_verbosity(option: ModelOption | None, requested: str | None) -> str:
    """Return a verbosity this model accepts, or its catalog default."""
    if option is None:
        return clamp_control(None, requested, DEFAULT_VERBOSITY)
    return clamp_control(option.verbosity, requested, DEFAULT_VERBOSITY)


def migrate_setting_maps(data: object) -> object:
    """Turn a legacy scalar reasoning or verbosity value into a per-model map."""
    if not isinstance(data, dict):
        return data
    migrated = dict(data)
    for field in ("reasoning", "verbosity"):
        if field not in migrated:
            continue
        value = migrated[field]
        if value is None:
            migrated[field] = {}
        elif isinstance(value, str):
            model = migrated.get("model") or DEFAULT_MODEL_ID
            migrated[field] = {str(model): value}
    return migrated


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
    reasoning: dict[str, str] = Field(default_factory=dict)
    verbosity: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _migrate_setting_maps(cls, data: object) -> object:
        return migrate_setting_maps(data)


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
    reasoning: dict[str, str] = Field(default_factory=dict)
    verbosity: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _migrate_setting_maps(cls, data: object) -> object:
        return migrate_setting_maps(data)
