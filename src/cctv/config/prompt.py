from __future__ import annotations

import re
from collections.abc import Iterable

from cctv.config.effective import (
    UNASSIGNED_LOCATION_NAME,
    UNASSIGNED_SECTOR_NAME,
    camera_gps,
    effective_cameras,
    location_for_camera,
    locations_by_id,
    normalize_agent_config,
    sector_for_camera,
)
from cctv.config.models import AgentConfig, CameraConfig, LocationConfig, SectorConfig


def _capability_lines(config: AgentConfig) -> list[str]:
    tools = config.tools
    lines = [
        "Enabled external tools (only call tools that appear in your tool list for this turn):",
        f"- internet search (web_search): {'enabled' if tools.internet else 'disabled'}",
        f"- weather (get_weather): {'enabled' if tools.weather else 'disabled'}",
        f"- map access (search_map, reverse_geocode): {'enabled' if tools.maps else 'disabled'}",
    ]
    if not tools.internet:
        lines.append("Do not claim you searched the web when internet search is disabled.")
    if not tools.weather:
        lines.append(
            "Do not quote measured forecasts or Open-Meteo data when weather is disabled."
        )
    if not tools.maps:
        lines.append("Do not claim map or geocoding lookups when map access is disabled.")
    return lines


def _no_location_sampling_hint(config: AgentConfig) -> str:
    if any(camera.analysis for camera in effective_cameras(config)):
        return (
            "choose cameras whose scene tags and descriptions match the subject of the question. "
            "For cars or traffic, prefer road, intersection, highway, and parking views; do not "
            "sample pedestrian, panorama, or airport views merely for geographic variety. "
            "If no configured view is relevant, say so instead of fetching unrelated cameras. "
            "Use geographic sampling only for genuinely broad comparison questions."
        )
    if config.locations:
        return (
            "do not ask which camera. Sample one camera per configured location "
            "(each location represents one place). "
            "This lets you contrast regions (e.g. Prague vs Japan)."
        )
    return (
        "do not ask which camera. Sample one camera per distinct place: group by rounded GPS "
        "(~0.01°); cameras without GPS each count as their own place. "
        "This lets you contrast regions (e.g. Prague vs Japan)."
    )


_PLACEHOLDER_NAMES = frozenset(
    {UNASSIGNED_SECTOR_NAME.lower(), UNASSIGNED_LOCATION_NAME.lower()}
)

WELCOME_HEADLINE = "**I watch live CCTV cameras and tell you what I see.**"


def _real_names(items: Iterable[SectorConfig | LocationConfig | None]) -> list[str]:
    names: list[str] = []
    for item in items:
        name = (item.name if item else "").strip()
        if not name or name.lower() in _PLACEHOLDER_NAMES or name in names:
            continue
        names.append(name)
    return names


def _joined(names: list[str]) -> str:
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


# Scene tags and analysis descriptions are free text, so each theme is matched by word stems
# (a token counts as a hit when it starts with the stem). Order breaks ties, most specific first.
_TOPIC_STEMS: tuple[tuple[str, frozenset[str]], ...] = (
    ("airport", frozenset({"airport", "aircraft", "airplane", "apron", "runway", "taxiway"})),
    (
        "wildlife",
        frozenset({"wildlife", "animal", "elephant", "waterhole", "watering", "savanna", "desert"}),
    ),
    (
        "traffic",
        frozenset({"traffic", "road", "highway", "motorway", "intersection", "parking", "car"}),
    ),
    ("crowd", frozenset({"pedestrian", "crowd", "square", "promenade", "tourist", "bridge"})),
    (
        "scenery",
        frozenset({"panorama", "waterfront", "river", "beach", "mountain", "harbour", "harbor"}),
    ),
)

_TOPIC_QUESTIONS = {
    "airport": "How busy are the airports in {place}?",
    "wildlife": "Any animals out in {place} right now?",
    "traffic": "What is the traffic like in {place}?",
    "crowd": "How crowded is {place} right now?",
    "scenery": "What does it look like in {place} right now?",
}

_GENERIC_QUESTION = "What can you see in {place} right now?"
_MAX_EXAMPLES = 3


def _places(config: AgentConfig, cameras: list[CameraConfig]) -> dict[str, list[CameraConfig]]:
    """Group cameras under the broadest real name they have: sector, else location."""
    grouped: dict[str, list[CameraConfig]] = {}
    for camera in cameras:
        names = _real_names(
            [sector_for_camera(config, camera), location_for_camera(config, camera)]
        )
        if names:
            grouped.setdefault(names[0], []).append(camera)
    return grouped


def _topic(cameras: Iterable[CameraConfig]) -> str | None:
    """Pick the theme that best describes what these cameras look at."""
    words: list[str] = []
    for camera in cameras:
        if camera.analysis:
            words.extend(camera.analysis.scene_tags)
            words.append(camera.analysis.description)
    tokens = re.findall(r"[a-z]+", " ".join(words).lower())
    if not tokens:
        return None
    scores = {
        topic: sum(any(token.startswith(stem) for stem in stems) for token in tokens)
        for topic, stems in _TOPIC_STEMS
    }
    best = max(scores, key=lambda topic: scores[topic])
    return best if scores[best] else None


def build_welcome_suggestions(config: AgentConfig) -> list[str]:
    """Opening questions to offer the user, drawn from what the cameras actually watch."""
    cameras = effective_cameras(config)
    if not cameras:
        return []
    grouped = _places(normalize_agent_config(config), cameras)
    if not grouped:
        return ["What can the cameras see right now?"]
    questions = []
    for place, place_cameras in list(grouped.items())[:_MAX_EXAMPLES]:
        topic = _topic(place_cameras)
        template = _TOPIC_QUESTIONS.get(topic or "", _GENERIC_QUESTION)
        questions.append(template.format(place=place))
    if len(questions) < _MAX_EXAMPLES:
        questions.append("Which cameras can you see?")
    return questions


def build_welcome_message(config: AgentConfig) -> str:
    """Short pitch. The example questions ride alongside as suggestions, not as text."""
    cameras = effective_cameras(config)
    if not cameras:
        return (
            f"{WELCOME_HEADLINE}\n\n"
            "No cameras are enabled yet. Add one in the Config panel (a source URL is enough), "
            "then ask me what it looks like out there."
        )

    normalized = normalize_agent_config(config)
    sectors = _real_names(sector_for_camera(normalized, camera) for camera in cameras)

    noun = "camera" if len(cameras) == 1 else "cameras"
    scope = f"{len(cameras)} {noun}"
    if sectors:
        scope += f" across {_joined(sectors)}"

    return f"{WELCOME_HEADLINE}\n\n{scope}. Pick a question below, or ask your own."


def build_system_prompt(config: AgentConfig) -> str:
    lines = [
        "You are a CCTV surveillance assistant.",
        "Always prefer live camera evidence before external data.",
        "",
        "Camera routing:",
        "- When the user names a place that matches one or more effectively enabled cameras "
        "(by name or GPS area), fetch those cameras in one get_camera_image call "
        "(cameras: [id, ...]) — not a single random sample, and not one tool call per camera.",
        f"- When the question has no location (e.g. 'what is the weather like today?'), "
        f"{_no_location_sampling_hint(config)}",
        "- Prefer staying near a soft cap of about 10 images per turn. "
        "If a place-wide question legitimately needs more (e.g. 12 Prague cameras), "
        "fetch them rather than refusing — but avoid flooding unrelated cameras.",
        "- If the user names a place with no matching configured camera, tell them to add it "
        "in the Config panel (name, optional GPS, source URL). "
        "If map or weather toggles are on, you may use those tools for context instead.",
        "- Disabled sectors, locations, or cameras are hidden from list_cameras and cannot be fetched.",
        "",
        "Weather and traffic:",
        "- Describe visible conditions from camera frames first.",
        "- Use get_weather only when the Weather toggle is on. "
        "Clearly label measured/forecast data as distinct from what the camera shows.",
        "- Do not use web_search as a weather API.",
        "- For traffic beyond what images show, describe only visible traffic; "
        "optionally use web_search when Internet search is on.",
        "",
        "Tool usage:",
        "Fetch live frames with one get_camera_image call. Pass cameras: [id or name, ...].",
        "Call list_cameras if you are unsure which cameras are configured.",
        "",
        "Configured cameras (effectively enabled):",
    ]
    active = effective_cameras(config)
    if active:
        location_map = locations_by_id(config.locations)
        by_location: dict[str, list] = {}
        for camera in active:
            location = location_for_camera(config, camera)
            key = location.id if location else camera.id
            by_location.setdefault(key, []).append(camera)
        for location_id, cameras in by_location.items():
            location = location_map.get(location_id.lower())
            location_label = location.name if location else location_id
            sector = sector_for_camera(config, cameras[0])
            sector_label = f", sector={sector.name}" if sector else ""
            lines.append(f"- {location_label}{sector_label}:")
            for camera in cameras:
                lat, lon = camera_gps(config, camera)
                gps = f" (lat={lat}, lon={lon})" if lat is not None and lon is not None else ""
                metadata = ""
                if camera.analysis:
                    tags = ", ".join(camera.analysis.scene_tags) or "none"
                    metadata = (
                        f" [scene_tags={tags}; description={camera.analysis.description}]"
                    )
                lines.append(f"  - {camera.name} [id={camera.id}]{gps}{metadata}")
    else:
        lines.append("- (none effectively enabled)")

    lines.append("")
    lines.extend(_capability_lines(config))
    lines.extend(
        [
            "",
            "When describing a scene, call get_camera_image with the relevant cameras, "
            "look at the returned frames, then answer in markdown.",
            "Cite every camera you discuss (and only those) in a final fenced block "
            "using configured camera ids, for example:",
            "```cite",
            "charles_bridge",
            "hybernska",
            "```",
            "Use an empty ```cite``` block if you discuss no frames. "
            "The user only sees the images you cite, not every frame you fetched. "
            "Do not mention the cite block in the visible answer. "
            "Do not use sep, ..sep, or any other fence language for citations.",
            "",
            "After the cite block, end with a followup block of two or three short questions "
            "the user could ask next, one per line, for example:",
            "```followup",
            "Has the traffic cleared on Barrandovský most?",
            "What is the weather like at Charles Bridge?",
            "```",
            "Write them in the user's voice, keep each under 80 characters, and only suggest "
            "questions your configured cameras can actually answer. "
            "Do not repeat a question the user already asked. "
            "Do not mention the followup block in the visible answer.",
        ]
    )
    return "\n".join(lines)
