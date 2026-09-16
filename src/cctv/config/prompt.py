from __future__ import annotations

from cctv.config.effective import (
    camera_gps,
    effective_cameras,
    location_for_camera,
    locations_by_id,
    sector_for_camera,
)
from cctv.config.models import AgentConfig


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
                lines.append(f"  - {camera.name} [id={camera.id}]{gps}")
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
            "Do not mention the cite block in the visible answer.",
        ]
    )
    return "\n".join(lines)
