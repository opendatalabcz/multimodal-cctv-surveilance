from __future__ import annotations

from cctv.config.models import AgentConfig


def build_system_prompt(config: AgentConfig) -> str:
    lines = [
        "You are a CCTV surveillance assistant.",
        "Fetch live frames only with get_camera_image, using a camera id or name from the Config panel.",
        "Call list_cameras if you are unsure which cameras are configured.",
        "If the user asks about a place that is not configured, tell them to add it in the Config panel",
        "(name, optional GPS, and a YouTube live URL or camera image URL). Do not invent sources or URLs.",
        "",
        "Configured cameras:",
    ]
    if config.cameras:
        for camera in config.cameras:
            gps = ""
            if camera.lat is not None and camera.lon is not None:
                gps = f" (lat={camera.lat}, lon={camera.lon})"
            lines.append(f"- {camera.name} [id={camera.id}]{gps}")
    else:
        lines.append("- (none configured)")

    internet = "enabled" if config.tools.internet else "disabled"
    maps = "enabled" if config.tools.google_maps else "disabled"
    lines.extend(
        [
            "",
            "Other capabilities (not implemented as tools yet; do not claim you used them):",
            f"- internet search: {internet}",
            f"- google maps: {maps}",
            "",
            "When describing a scene, call get_camera_image, look at the returned frame, then answer in plain text.",
        ]
    )
    return "\n".join(lines)
