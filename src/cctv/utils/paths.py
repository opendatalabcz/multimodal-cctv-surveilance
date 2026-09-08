"""Filesystem locations for the data this project reads and writes.

Everything is anchored to the project root, i.e. the nearest directory above
this file that holds ``pyproject.toml``. Set ``CCTV_DATA_DIR`` to keep captured
frames and logs somewhere else, such as an external drive.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_MARKER = "pyproject.toml"
IMAGES_DIRNAME = "camera_images"


@cache
def project_root() -> Path:
    """Nearest ancestor of this file that contains ``pyproject.toml``."""
    module_path = Path(__file__).resolve()
    for directory in module_path.parents:
        if (directory / PROJECT_MARKER).is_file():
            return directory
    raise FileNotFoundError(
        f"No {PROJECT_MARKER} above {module_path}. Install the package from a "
        f"source checkout, or set CCTV_DATA_DIR to choose where data lives."
    )


def data_root() -> Path:
    """Root for generated data: ``CCTV_DATA_DIR`` if set, else the project root."""
    load_dotenv()
    override = os.getenv("CCTV_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return project_root()


def images_dir() -> Path:
    return data_root() / IMAGES_DIRNAME


def place_data_dir(place_id: str) -> Path:
    return images_dir() / place_id


def logs_dir() -> Path:
    return data_root() / "logs"


def experiments_dir(place_id: str | None = None) -> Path:
    """JSON analysis outputs: ``experiments/`` or ``experiments/<place>/``."""
    root = data_root() / "experiments"
    return root / place_id if place_id else root
