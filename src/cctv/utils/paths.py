from pathlib import Path

import cctv


def repo_root() -> Path:
    """Repository root (parent of ``src/``) when the package is installed editable."""
    return Path(cctv.__file__).resolve().parents[2]


def place_data_dir(place_id: str) -> Path:
    return repo_root() / "data" / place_id
