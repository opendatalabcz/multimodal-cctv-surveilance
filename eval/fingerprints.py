"""Content fingerprints for reproducible evaluation inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluation_fingerprint(timestamps_path: Path, video_paths: list[Path]) -> tuple[str, dict]:
    sources = {
        "timestamps_csv": {
            "file": timestamps_path.name,
            "sha256": sha256_file(timestamps_path),
        },
        "videos": {
            path.name: sha256_file(path)
            for path in sorted(video_paths)
        },
    }
    fingerprint = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()[:16]
    return fingerprint, sources
