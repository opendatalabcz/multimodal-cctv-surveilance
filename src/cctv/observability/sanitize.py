"""Copy trace payloads and remove secrets, encrypted reasoning, and image bytes."""

from __future__ import annotations

import base64
import re
from typing import Any

_SECRET_KEYS = frozenset(
    {
        "api-key",
        "api_key",
        "apikey",
        "authorization",
        "secret",
        "secret_key",
        "password",
        "access_token",
    }
)
_DROP_KEYS = _SECRET_KEYS | {"encrypted_content"}
_ENCRYPTED_REASONING = "reasoning.encrypted_content"
_DATA_URL = re.compile(r"^data:([^;,]+);base64,", re.IGNORECASE)


def sanitize_for_export(value: Any, *, include_images: bool = False) -> Any:
    """Return a JSON-like copy safe to hand to Langfuse.

    ``include_images`` keeps raw ``data:`` URLs so the caller can turn them into
    media. Chat generations pass ``False`` and attach each frame once elsewhere.
    """
    return _walk(value, include_images=include_images)


def _walk(value: Any, *, include_images: bool) -> Any:
    if isinstance(value, dict):
        image = _image_part(value)
        if image is not None:
            data_url, detail = image
            if include_images:
                return value
            return _image_metadata(data_url, detail=detail)
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            if str(key).casefold() in _DROP_KEYS:
                continue
            cleaned[key] = _walk(item, include_images=include_images)
        return cleaned
    if isinstance(value, list):
        walked = [_walk(item, include_images=include_images) for item in value]
        return [item for item in walked if item != _ENCRYPTED_REASONING]
    if isinstance(value, str):
        if value == _ENCRYPTED_REASONING:
            return value
        if _DATA_URL.match(value) and not include_images:
            return _image_metadata(value, detail=None)
        return value
    return value


def _image_part(value: dict[Any, Any]) -> tuple[str, str | None] | None:
    part_type = value.get("type")
    if part_type == "image_url":
        image = value.get("image_url")
        url = image.get("url") if isinstance(image, dict) else None
        if isinstance(image, dict) and isinstance(url, str) and _DATA_URL.match(url):
            detail = image.get("detail")
            return image["url"], detail if isinstance(detail, str) else None
        if isinstance(image, str) and _DATA_URL.match(image):
            return image, None
    if part_type == "input_image":
        url = value.get("image_url")
        if isinstance(url, str) and _DATA_URL.match(url):
            return url, None
    return None


def _image_metadata(data_url: str, *, detail: str | None) -> dict[str, Any]:
    header, _, encoded = data_url.partition(",")
    media_type = "application/octet-stream"
    if header.lower().startswith("data:"):
        parsed = header[5:].split(";", 1)[0].strip()
        if parsed:
            media_type = parsed
    try:
        byte_length = len(base64.b64decode(encoded, validate=False))
    except Exception:
        byte_length = len(encoded)
    metadata: dict[str, Any] = {
        "type": "image",
        "omitted": True,
        "media_type": media_type,
        "byte_length": byte_length,
    }
    if detail:
        metadata["detail"] = detail
    return metadata
