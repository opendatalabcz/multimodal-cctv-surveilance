"""Concurrent execution helpers for evaluation runs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

_T = TypeVar("_T")


def run_models_parallel(models: list[str], operation: Callable[[str], _T]) -> list[tuple[str, _T]]:
    if not models:
        return []
    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {executor.submit(operation, model): model for model in models}
        results: dict[str, _T] = {}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [(model, results[model]) for model in models]
