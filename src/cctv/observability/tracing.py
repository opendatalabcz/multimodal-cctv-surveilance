"""Langfuse client and observation helpers.

Tracing is off unless ``LANGFUSE_ENABLED`` is set and both API keys are present.
SDK failures are logged and never raised to the chat loop. Payloads are sanitized
before they reach the SDK, because Langfuse extracts base64 media before its
own masking hook runs.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from cctv.observability.sanitize import sanitize_for_export
from cctv.utils.paths import data_root

logger = logging.getLogger("cctv.observability")

_LOOKUP_TOOLS = frozenset({"list_cameras", "web_search", "search_map", "reverse_geocode"})

_TRUE = frozenset({"1", "true", "yes", "on"})
_CLIENT: Any = None
_CLIENT_FAILED = False
_MISSING_KEYS_WARNED = False


class Observation:
    """SDK span, or a no-op when tracing is disabled or the SDK failed."""

    def __init__(self, inner: Any | None) -> None:
        self._inner = inner

    def update(
        self,
        *,
        input: Any = None,
        output: Any = None,
        metadata: Any = None,
        usage_details: dict[str, int] | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        if self._inner is None:
            return
        payload: dict[str, Any] = {}
        if input is not None:
            payload["input"] = sanitize_for_export(input, include_images=False)
        if output is not None:
            payload["output"] = sanitize_for_export(output, include_images=False)
        if metadata is not None:
            payload["metadata"] = sanitize_for_export(metadata, include_images=False)
        if usage_details:
            payload["usage_details"] = usage_details
        if level:
            payload["level"] = level
        if status_message:
            payload["status_message"] = str(status_message)[:1500]
        if not payload:
            return
        try:
            self._inner.update(**payload)
        except Exception:
            logger.exception("Langfuse update failed")


def tracing_enabled() -> bool:
    """True when tracing is explicitly enabled and both Langfuse keys are set."""
    load_dotenv()
    if not _flag("LANGFUSE_ENABLED"):
        return False
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return True
    global _MISSING_KEYS_WARNED
    if not _MISSING_KEYS_WARNED:
        _MISSING_KEYS_WARNED = True
        logger.warning("Langfuse is enabled but API keys are missing; tracing is off")
    return False


def capture_images_enabled() -> bool:
    """True when traces may include CCTV frame bytes."""
    load_dotenv()
    return _flag("LANGFUSE_CAPTURE_IMAGES")


def flush_traces() -> None:
    """Export queued spans. Failures are logged and ignored."""
    try:
        client = _get_client()
        if client is not None:
            client.flush()
    except Exception:
        logger.exception("Langfuse flush failed")


@contextmanager
def start_turn(
    *,
    turn_id: str,
    session_id: str,
    user_input: str,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Observation]:
    """Root agent observation for one user message. ``turn_id`` is the Langfuse trace id."""

    def factory(client: Any) -> Any:
        return client.start_as_current_observation(
            as_type="agent",
            name="answer-chat",
            trace_context={"trace_id": turn_id},
            input=sanitize_for_export(user_input, include_images=False),
            metadata=sanitize_for_export(metadata or {}, include_images=False),
        )

    with _observation(factory) as observation:
        if not tracing_enabled():
            yield observation
            return
        with _attributes(session_id=session_id, trace_name="answer-chat", tags=["chat"]):
            yield observation


@contextmanager
def start_generation(
    *,
    name: str,
    model: str | None,
    input: Any,
    model_parameters: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    include_images: bool = False,
    tags: list[str] | None = None,
) -> Iterator[Observation]:
    """One Azure request. Image bytes are included only when requested."""
    parameters = _scalar_parameters(model_parameters)

    def factory(client: Any) -> Any:
        kwargs: dict[str, Any] = {
            "as_type": "generation",
            "name": name,
            "input": _export_input(input, include_images=include_images),
            "metadata": sanitize_for_export(metadata or {}, include_images=False),
        }
        if model:
            kwargs["model"] = model
        if parameters:
            kwargs["model_parameters"] = parameters
        return client.start_as_current_observation(**kwargs)

    with _observation(factory) as observation:
        if tags and tracing_enabled():
            with _attributes(tags=tags, trace_name=name):
                yield observation
        else:
            yield observation


@contextmanager
def start_tool(*, name: str, arguments: Any) -> Iterator[Observation]:
    """One tool or lookup nested under the active chat agent."""
    observation_type = "retriever" if name in _LOOKUP_TOOLS else "tool"

    def factory(client: Any) -> Any:
        return client.start_as_current_observation(
            as_type=observation_type,
            name=name or "tool",
            input=sanitize_for_export(arguments, include_images=False),
            metadata={"tool": name or "tool"},
        )

    with _observation(factory) as observation:
        yield observation


def exported_image(
    path: str,
    *,
    camera_id: str | None = None,
    camera_name: str | None = None,
) -> dict[str, Any]:
    """Camera-frame metadata, plus image bytes when capture is enabled."""
    record: dict[str, Any] = {
        "path": path,
        "camera_id": camera_id,
        "camera_name": camera_name,
    }
    file_path = _resolve_image(path)
    if file_path is None:
        record["missing"] = True
        return record
    record["bytes"] = file_path.stat().st_size
    try:
        from PIL import Image

        with Image.open(file_path) as image:
            record["width"], record["height"] = image.size
    except Exception:
        logger.debug("Could not read image dimensions for %s", path, exc_info=True)
    if capture_images_enabled():
        try:
            from langfuse.media import LangfuseMedia

            record["media"] = LangfuseMedia(
                content_bytes=file_path.read_bytes(),
                content_type="image/jpeg",
            )
        except Exception:
            logger.exception("Could not attach frame %s to Langfuse", path)
    return record


def _export_input(value: Any, *, include_images: bool) -> Any:
    if not include_images:
        return sanitize_for_export(value, include_images=False)
    preserved = sanitize_for_export(value, include_images=True)
    try:
        return _attach_media(preserved)
    except Exception:
        logger.exception("Could not attach inline images; exporting metadata only")
        return sanitize_for_export(value, include_images=False)


def _attach_media(value: Any) -> Any:
    from langfuse.media import LangfuseMedia

    if isinstance(value, dict):
        image = value.get("image_url")
        data_url = _data_url(image if isinstance(image, str) else None)
        if value.get("type") == "input_image" and data_url:
            return {
                "type": "input_image",
                "image": LangfuseMedia(base64_data_uri=data_url),
            }
        if isinstance(image, dict):
            nested = _data_url(image.get("url") if isinstance(image.get("url"), str) else None)
            if nested:
                media = {"type": "image_url", "image": LangfuseMedia(base64_data_uri=nested)}
                detail = image.get("detail")
                if isinstance(detail, str):
                    media["detail"] = detail
                return media
        return {key: _attach_media(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_attach_media(item) for item in value]
    if isinstance(value, str):
        data_url = _data_url(value)
        if data_url:
            return LangfuseMedia(base64_data_uri=data_url)
    return value


def _data_url(value: str | None) -> str | None:
    if isinstance(value, str) and value.lower().startswith("data:") and ";base64," in value.lower():
        return value
    return None


@contextmanager
def _observation(factory: Callable[[Any], Any]) -> Iterator[Observation]:
    client = _get_client()
    if client is None:
        yield Observation(None)
        return
    try:
        context = factory(client)
        span = context.__enter__()
    except Exception:
        logger.exception("Langfuse observation failed to start")
        yield Observation(None)
        return
    observation = Observation(span)
    try:
        yield observation
    except Exception as exc:
        observation.update(level="ERROR", status_message=str(exc))
        _close(context, exc)
        raise
    else:
        _close(context, None)


def _close(context: Any, exc: BaseException | None) -> None:
    try:
        if exc is None:
            context.__exit__(None, None, None)
        else:
            context.__exit__(type(exc), exc, exc.__traceback__)
    except Exception:
        logger.exception("Langfuse observation failed to close")


@contextmanager
def _attributes(
    *,
    session_id: str | None = None,
    trace_name: str | None = None,
    tags: list[str] | None = None,
) -> Iterator[None]:
    context = None
    try:
        from langfuse import propagate_attributes

        context = propagate_attributes(
            session_id=session_id,
            trace_name=trace_name,
            tags=tags,
        )
        context.__enter__()
    except Exception:
        logger.exception("Langfuse session propagation failed")
        context = None
    try:
        yield
    finally:
        if context is not None:
            try:
                context.__exit__(*sys.exc_info())
            except Exception:
                logger.exception("Langfuse session propagation failed to close")


def _get_client() -> Any | None:
    global _CLIENT, _CLIENT_FAILED
    if not tracing_enabled():
        return None
    if _CLIENT is not None:
        return _CLIENT
    if _CLIENT_FAILED:
        return None
    try:
        from langfuse import Langfuse

        _CLIENT = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            base_url=os.getenv("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com",
            environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT") or "development",
            tracing_enabled=True,
        )
    except Exception:
        _CLIENT_FAILED = True
        logger.exception("Langfuse client failed to start; tracing is off")
        return None
    return _CLIENT


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE


def _scalar_parameters(values: dict[str, Any] | None) -> dict[str, Any] | None:
    if not values:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, (str, int, float, bool)):
            cleaned[str(key)] = value
    return cleaned or None


def _resolve_image(path: str) -> Path | None:
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    rooted = data_root() / path
    if rooted.is_file():
        return rooted
    return None
