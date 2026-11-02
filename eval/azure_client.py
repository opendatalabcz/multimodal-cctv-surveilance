"""Azure vision calls for gpt-4o and the Responses-API deployments."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from eval.cost import cost_usd
from eval.prompt import parse_state_json, prompt_id, repair_prompt

# gpt-4o uses Chat Completions. Luna and Astra use the Responses API.
_TRANSPORT = {
    "gpt-4o": "chat_completions",
    "gpt-5.6-luna": "responses",
    "gpt-6-astra": "responses",
}
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class AzureVisionClient:
    def __init__(
        self,
        project_root: Path,
        cache_dir: Path,
        timeout_s: int = 180,
        *,
        prompt_text: str,
        examples: list[tuple[Path, str]] | None = None,
        few_shot_id: str | None = None,
    ) -> None:
        load_dotenv(project_root / ".env")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        if not api_key or not endpoint:
            raise RuntimeError("AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT are required")
        base = endpoint.rstrip("/")
        if not base.endswith("/openai/v1"):
            base += "/openai/v1"
        self.api_key = api_key
        self.chat_url = f"{base}/chat/completions"
        self.responses_url = f"{base}/responses"
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir
        self.prompt_text = prompt_text
        self.prompt_id = prompt_id(prompt_text)
        self.examples = examples or []
        self.few_shot_id = few_shot_id if self.examples else None
        self.api_calls: dict[str, int] = {}
        self.cache_hits: dict[str, int] = {}
        self.spend_usd: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def predict(self, *, model: str, image_path: Path, frame_id: str, interval_seconds: int, video: str, timestamp_s: int) -> dict:
        if model not in _TRANSPORT:
            raise ValueError(f"Unknown model {model}")
        key = f"{model}:{interval_seconds}:{self.prompt_id}:{frame_id}"
        with self._lock(key):
            cached = self._read_cache(model, interval_seconds, frame_id)
            if cached is not None:
                cached["cache_hit"] = True
                self.cache_hits[model] = self.cache_hits.get(model, 0) + 1
                return cached
            result = self._predict_uncached(model, image_path)
            result.update(
                {
                    "model": model,
                    "frame_id": frame_id,
                    "interval_seconds": interval_seconds,
                    "video": video,
                    "timestamp_s": timestamp_s,
                    "cache_hit": False,
                    "example_images": [path.name for path, _caption in self.examples],
                }
            )
            if result.get("usage"):
                self.api_calls[model] = self.api_calls.get(model, 0) + 1
                priced = cost_usd(model, result["usage"])
                if priced is not None:
                    self.spend_usd[model] = round(self.spend_usd.get(model, 0.0) + priced["total"], 6)
            # Keep transport failures out of the cache so a later run can retry them.
            if result.get("raw_response") or result.get("repair_raw_response"):
                self._write_cache(result)
            return result

    def _predict_uncached(self, model: str, image_path: Path) -> dict:
        try:
            raw, usage, error = self._call(model, image_path, self.prompt_text)
        except Exception as exc:
            return _empty_result(str(exc))
        parsed = parse_state_json(raw) if raw else None
        repair_raw = None
        if parsed is None and error is None:
            try:
                repair_raw, repair_usage, error = self._call(model, image_path, repair_prompt(raw or ""))
            except Exception as exc:
                return _empty_result(str(exc), raw_response=raw, usage=usage)
            if repair_usage:
                usage = _add_usage(usage, repair_usage)
            parsed = parse_state_json(repair_raw) if repair_raw else None
        record = {
            "parse_ok": parsed is not None,
            "parsed": parsed,
            "raw_response": raw,
            "repair_raw_response": repair_raw,
            "usage": usage,
            "error": error,
        }
        return record

    def _call(self, model: str, image_path: Path, prompt: str) -> tuple[str | None, dict, str | None]:
        query_url = _data_url(image_path)
        example_parts = [(_data_url(path), caption) for path, caption in self.examples]
        if _TRANSPORT[model] == "chat_completions":
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": _chat_content(prompt, example_parts, query_url)}],
                "max_completion_tokens": 800,
            }
            url = self.chat_url
        else:
            payload = {
                "model": model,
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": _responses_content(prompt, example_parts, query_url),
                    }
                ],
                "max_output_tokens": 8000,
                "reasoning": {"effort": "medium"},
            }
            url = self.responses_url
        body, error = self._post(url, payload)
        if body is None:
            return None, {}, error
        text = _message_text(body, _TRANSPORT[model])
        return text, body.get("usage") or {}, None if text else "Model returned no text"

    def _post(self, url: str, payload: dict) -> tuple[dict | None, str | None]:
        headers = {"Content-Type": "application/json", "api-key": self.api_key}
        delay = 2.0
        last_error = "request failed"
        for attempt in range(5):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_s)
            except requests.RequestException as exc:
                last_error = str(exc)
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if response.status_code in _RETRY_STATUSES:
                last_error = f"{response.status_code} {(response.text or '')[:300]}"
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if not response.ok:
                return None, f"{response.status_code} {(response.text or '')[:500]}"
            return response.json(), None
        return None, last_error

    def _lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def _cache_file(self, model: str, interval_seconds: int, frame_id: str) -> Path:
        folder = f"interval-{interval_seconds}-{self.prompt_id}"
        if self.few_shot_id:
            folder += f"-fs-{self.few_shot_id}"
        return self.cache_dir / model / folder / f"{frame_id}.json"

    def _read_cache(self, model: str, interval_seconds: int, frame_id: str) -> dict | None:
        path = self._cache_file(model, interval_seconds, frame_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_cache(self, record: dict) -> None:
        path = self._cache_file(record["model"], record["interval_seconds"], record["frame_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
        temporary.replace(path)


def _empty_result(error: str, raw_response: str | None = None, usage: dict | None = None) -> dict:
    return {
        "parse_ok": False,
        "parsed": None,
        "raw_response": raw_response,
        "repair_raw_response": None,
        "usage": usage or {},
        "error": error,
    }


def _data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _chat_content(prompt: str, examples: list[tuple[str, str]], query_url: str) -> list[dict]:
    parts: list[dict] = [{"type": "text", "text": prompt}]
    for data_url, caption in examples:
        parts.append({"type": "text", "text": caption})
        parts.append({"type": "image_url", "image_url": {"url": data_url, "detail": "high"}})
    if examples:
        parts.append({"type": "text", "text": "Judge this frame. Use the examples only as a guide."})
    parts.append({"type": "image_url", "image_url": {"url": query_url, "detail": "high"}})
    return parts


def _responses_content(prompt: str, examples: list[tuple[str, str]], query_url: str) -> list[dict]:
    parts: list[dict] = [{"type": "input_text", "text": prompt}]
    for data_url, caption in examples:
        parts.append({"type": "input_text", "text": caption})
        parts.append({"type": "input_image", "image_url": data_url, "detail": "high"})
    if examples:
        parts.append({"type": "input_text", "text": "Judge this frame. Use the examples only as a guide."})
    parts.append({"type": "input_image", "image_url": query_url, "detail": "high"})
    return parts


def _message_text(body: dict, transport: str) -> str:
    if transport == "chat_completions":
        content = body["choices"][0]["message"].get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
            )
        return ""
    if isinstance(body.get("output_text"), str) and body["output_text"]:
        return body["output_text"]
    chunks: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                chunks.append(part.get("text") or "")
    return "\n".join(chunk for chunk in chunks if chunk)


def _add_usage(first: dict, second: dict) -> dict:
    combined = dict(first)
    for key, value in second.items():
        if isinstance(value, (int, float)) and isinstance(combined.get(key), (int, float)):
            combined[key] = combined[key] + value
        elif key not in combined:
            combined[key] = value
    return combined
