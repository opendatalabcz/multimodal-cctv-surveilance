"""Shared HTTP helpers for external tool modules."""

from __future__ import annotations

import requests

DEFAULT_TIMEOUT = 10


def get_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, dict | list | None, str | None]:
    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        return True, response.json(), None
    except requests.exceptions.Timeout:
        return False, None, "Request timed out"
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        return False, None, f"HTTP error {status}"
    except requests.exceptions.RequestException as exc:
        return False, None, f"Request failed: {exc}"
    except ValueError:
        return False, None, "Invalid JSON response"
