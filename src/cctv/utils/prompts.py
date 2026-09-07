from __future__ import annotations

from importlib.resources import files

import yaml


def load_place_prompt(place_id: str) -> str:
    """Assemble the analysis prompt from the shared template, type filler, and place filler."""
    prompts = files("cctv.prompts")
    template = prompts.joinpath("template.md").read_text(encoding="utf-8")
    place = yaml.safe_load(prompts.joinpath("fillers", "places", f"{place_id}.yaml").read_text(encoding="utf-8"))
    type_id = place["type"]
    type_fillers = yaml.safe_load(
        prompts.joinpath("fillers", "types", f"{type_id}.yaml").read_text(encoding="utf-8")
    )
    fillers = {**type_fillers, **place}
    fillers.setdefault("place_context", "")
    fillers.setdefault("extra_notes", "")
    return template.format(**fillers)
