"""Ground-truth labels for apron states, sampled on a fixed interval."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

STATES = ("parked", "tunnel_attached", "doors_open")
NEAR_BOUNDARY_SECONDS = 20

# CSV columns that bound each state. The end column is exclusive.
_INTERVALS = (
    ("parked", "parked", "left_parking"),
    ("tunnel_attached", "tunnel_attached", "tunnel_detached"),
    ("doors_open", "doors_open", "doors_closed"),
)


@dataclass(frozen=True)
class Sample:
    frame_id: str
    video: str
    timestamp_s: int
    parked: bool
    tunnel_attached: bool
    doors_open: bool
    phase: str
    seconds_to_boundary: float
    near_boundary: bool
    interval_seconds: int

    def truth(self) -> dict[str, bool]:
        return {state: getattr(self, state) for state in STATES}

    def to_dict(self) -> dict:
        return asdict(self)


def parse_clock(value: str) -> float | None:
    """Parse ``H:M:S``. ``end`` means the state lasts until the video ends."""
    text = value.strip()
    if text.lower() == "end":
        return None
    parts = text.split(":")
    if len(parts) != 3:
        raise ValueError(f"Expected H:M:S or 'end', got {value!r}")
    hours, minutes, seconds = (int(part) for part in parts)
    return hours * 3600 + minutes * 60 + seconds


def phase_name(parked: bool, tunnel_attached: bool, doors_open: bool) -> str:
    parts = []
    if parked:
        parts.append("parked")
    if tunnel_attached:
        parts.append("tunnel")
    if doors_open:
        parts.append("doors")
    return "+".join(parts) if parts else "empty"


def sample_times(duration_s: float, interval_seconds: int) -> list[int]:
    """``0, interval, 2*interval, ...`` while the time is inside the video."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    # Stay a second inside the file. The movie header is slightly longer than
    # the last decodable frame, so a sample on that last millisecond fails.
    times = []
    timestamp = 0
    while timestamp + 1 < duration_s:
        times.append(timestamp)
        timestamp += interval_seconds
    return times


def _load_rows(timestamps_path: Path) -> list[dict[str, str]]:
    with timestamps_path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def build_samples(
    timestamps_path: Path,
    durations_s: dict[str, float],
    interval_seconds: int,
) -> list[Sample]:
    samples: list[Sample] = []
    for row in _load_rows(timestamps_path):
        video = row["file_name"].strip()
        if video not in durations_s:
            raise KeyError(f"No duration for {video}")
        duration = durations_s[video]
        bounds: dict[str, tuple[float, float]] = {}
        boundaries: list[float] = []
        for state, start_key, end_key in _INTERVALS:
            start = parse_clock(row[start_key])
            end = parse_clock(row[end_key])
            if start is None:
                raise ValueError(f"{video} {start_key} cannot be 'end'")
            if end is None:
                end = duration
            bounds[state] = (start, end)
            boundaries.append(start)
            if parse_clock(row[end_key]) is not None:
                boundaries.append(end)
        for timestamp in sample_times(duration, interval_seconds):
            labels = {
                state: start <= timestamp < end
                for state, (start, end) in bounds.items()
            }
            distance = min(abs(timestamp - boundary) for boundary in boundaries)
            samples.append(
                Sample(
                    frame_id=f"{video}_{timestamp:06d}",
                    video=video,
                    timestamp_s=timestamp,
                    parked=labels["parked"],
                    tunnel_attached=labels["tunnel_attached"],
                    doors_open=labels["doors_open"],
                    phase=phase_name(
                        labels["parked"],
                        labels["tunnel_attached"],
                        labels["doors_open"],
                    ),
                    seconds_to_boundary=distance,
                    near_boundary=distance <= NEAR_BOUNDARY_SECONDS,
                    interval_seconds=interval_seconds,
                )
            )
    return samples
