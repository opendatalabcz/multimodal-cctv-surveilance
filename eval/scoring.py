"""Accuracy, precision, recall, F1, and flicker for stand-state predictions."""

from __future__ import annotations

from collections import defaultdict

from eval.labels import STATES, Sample

Row = dict


def prediction_row(sample: Sample, record: dict | None) -> Row:
    parsed = record.get("parsed") if record and record.get("parse_ok") else None
    return {
        "frame_id": sample.frame_id,
        "video": sample.video,
        "timestamp_s": sample.timestamp_s,
        "near_boundary": sample.near_boundary,
        "phase": sample.phase,
        "truth": sample.truth(),
        "pred": {state: parsed[state] for state in STATES} if parsed else None,
        "parse_ok": parsed is not None,
        "description": parsed.get("description") if parsed else None,
        "error": None if record is None else record.get("error"),
    }


def summarize(rows: list[Row], *, interval_seconds: int, model: str) -> dict:
    return {
        "model": model,
        "interval_seconds": interval_seconds,
        "n_frames": len(rows),
        "overall": _block(rows),
        "by_video": {video: _block(group) for video, group in _by_video(rows).items()},
        "near_boundary": _block([row for row in rows if row["near_boundary"]]),
        "near_boundary_by_video": {
            video: _block([row for row in group if row["near_boundary"]])
            for video, group in _by_video(rows).items()
        },
        "flicker": flicker(rows),
        "flicker_by_video": {video: flicker(group) for video, group in _by_video(rows).items()},
    }


def _by_video(rows: list[Row]) -> dict[str, list[Row]]:
    grouped: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        grouped[row["video"]].append(row)
    return dict(grouped)


def _block(rows: list[Row]) -> dict:
    return {
        "n": len(rows),
        "parse_failures": sum(1 for row in rows if not row["parse_ok"]),
        "exact_match": _rate(
            sum(
                1
                for row in rows
                if row["parse_ok"] and all(row["pred"][state] == row["truth"][state] for state in STATES)
            ),
            len(rows),
        ),
        "states": {state: _state_metrics(rows, state) for state in STATES},
    }


def _state_metrics(rows: list[Row], state: str) -> dict:
    positive = sum(1 for row in rows if row["truth"][state])
    negative = len(rows) - positive
    correct = sum(1 for row in rows if row["parse_ok"] and row["pred"][state] == row["truth"][state])
    true_positive = false_positive = false_negative = true_negative = 0
    for row in rows:
        if not row["parse_ok"]:
            continue
        predicted = row["pred"][state]
        actual = row["truth"][state]
        if predicted and actual:
            true_positive += 1
        elif predicted and not actual:
            false_positive += 1
        elif not predicted and actual:
            false_negative += 1
        else:
            true_negative += 1
    precision = _rate(true_positive, true_positive + false_positive)
    recall = _rate(true_positive, true_positive + false_negative)
    return {
        "accuracy": _rate(correct, len(rows)),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "positive": positive,
        "negative": negative,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
    }


def flicker(rows: list[Row]) -> dict:
    """Count prediction changes between adjacent samples whose ground truth did not change."""
    summary = {
        "pairs": 0,
        "stable_pairs": 0,
        "prediction_flips": 0,
        "unparsed_pairs": 0,
        "by_state": {state: {"stable_pairs": 0, "flips": 0} for state in STATES},
    }
    grouped: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        grouped[row["video"]].append(row)
    for items in grouped.values():
        items.sort(key=lambda row: row["timestamp_s"])
        for left, right in zip(items, items[1:]):
            summary["pairs"] += 1
            if not left["parse_ok"] or not right["parse_ok"]:
                summary["unparsed_pairs"] += 1
                continue
            if all(left["truth"][state] == right["truth"][state] for state in STATES):
                summary["stable_pairs"] += 1
                if any(left["pred"][state] != right["pred"][state] for state in STATES):
                    summary["prediction_flips"] += 1
            for state in STATES:
                if left["truth"][state] != right["truth"][state]:
                    continue
                summary["by_state"][state]["stable_pairs"] += 1
                if left["pred"][state] != right["pred"][state]:
                    summary["by_state"][state]["flips"] += 1
    return summary


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)
