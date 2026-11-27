"""Concurrent execution helpers for evaluation runs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

_T = TypeVar("_T")


def run_models_parallel(
    models: list[str],
    operation: Callable[[str], _T],
    max_concurrent_models: int = 3,
) -> list[tuple[str, _T]]:
    if max_concurrent_models <= 0:
        raise ValueError("max_concurrent_models must be positive")
    if not models:
        return []
    with ThreadPoolExecutor(max_workers=min(len(models), max_concurrent_models)) as executor:
        futures = {executor.submit(operation, model): model for model in models}
        results: dict[str, _T] = {}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [(model, results[model]) for model in models]
