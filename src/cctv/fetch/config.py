from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def load_monitor_config() -> dict[str, Any]:
    """Load ``monitor_config.json`` bundled with the fetch package."""
    path = files("cctv.fetch").joinpath("monitor_config.json")
    return json.loads(path.read_text(encoding="utf-8"))
