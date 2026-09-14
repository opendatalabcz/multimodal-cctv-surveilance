from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

import aiohttp
import requests
from PIL import Image

from cctv.fetch.config import load_monitor_config
from cctv.utils.paths import place_data_dir


class CameraImageFetcher:
    """Download images from Prague municipal CCTV cameras."""

    def __init__(self, output_dir: str = "camera_images", timeout: int = 30, verbose: bool = True):
        self.base_url = "https://bezpecnost.praha.eu/Intens.CrisisPortalInfrastructureApp/cameras"
        self.output_dir = output_dir
        self.timeout = timeout
        self.verbose = verbose
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        }
        self._session: aiohttp.ClientSession | None = None
        os.makedirs(self.output_dir, exist_ok=True)

    def _print(self, message: str) -> None:
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def _get_camera_url(self, camera_id: str) -> str:
        return f"{self.base_url}/{camera_id}/image"

    def _failure(self, camera_id: str, error: str) -> dict[str, Any]:
        return {"success": False, "camera_id": camera_id, "error": error}

    def _save_frame(self, image_bytes: bytes, camera_id: str, output_dir: str) -> dict[str, Any]:
        img = Image.open(BytesIO(image_bytes))
        now = datetime.now()
        timestamp = f"{now:%Y%m%d_%H%M%S}_{now.microsecond:06d}"
        filename = f"camera_{camera_id}_{timestamp}.jpg"
        filepath = os.path.join(output_dir, filename)
        img.save(filepath)
        return {
            "success": True,
            "camera_id": camera_id,
            "filename": filename,
            "filepath": filepath,
            "dimensions": img.size,
            "size_bytes": len(image_bytes),
        }

    def _parse_time_string(self, time_str: str) -> timedelta:
        if not isinstance(time_str, str):
            raise ValueError("Time string must be a string")
        time_str = time_str.lower().strip()
        if time_str.endswith("s"):
            return timedelta(seconds=int(time_str[:-1]))
        if time_str.endswith("m"):
            return timedelta(minutes=int(time_str[:-1]))
        if time_str.endswith("h"):
            return timedelta(hours=int(time_str[:-1]))
        if time_str.endswith("d"):
            return timedelta(days=int(time_str[:-1]))
        raise ValueError(f"Invalid time format: {time_str}. Use formats like '5m', '2h', '1d'")

    def _normalize_interval(self, interval: str | timedelta | int | float) -> timedelta:
        if isinstance(interval, timedelta):
            return interval
        if isinstance(interval, str):
            return self._parse_time_string(interval)
        if isinstance(interval, (int, float)):
            return timedelta(seconds=interval)
        raise ValueError("Interval must be string, timedelta, or number")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(headers=self.headers, timeout=timeout)
        return self._session

    async def _close_session(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_payload_async(self, camera_id: str) -> dict[str, Any]:
        url = self._get_camera_url(camera_id)
        session = await self._get_session()
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    return self._failure(camera_id, f"HTTP {response.status}")
                data = await response.json()
        except Exception as exc:
            return self._failure(camera_id, str(exc))

        base64_data = data.get("contentBase64")
        if not base64_data:
            return self._failure(camera_id, "No base64 data in response")
        return {"success": True, "camera_id": camera_id, "content_base64": base64_data}

    def fetch_camera_image(
        self,
        camera_id: str,
        save_to_file: bool = True,
        custom_output_dir: str | None = None,
    ) -> dict[str, Any]:
        output_dir = custom_output_dir or self.output_dir
        if save_to_file:
            os.makedirs(output_dir, exist_ok=True)

        url = self._get_camera_url(camera_id)
        self._print(f"Downloading data from camera {camera_id}...")

        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            if response.status_code != 200:
                self._print(f"❌ HTTP Error: {response.status_code}")
                return self._failure(camera_id, f"HTTP {response.status_code}")

            base64_data = response.json().get("contentBase64")
            if not base64_data:
                self._print("⚠️ No base64 data found in response")
                return self._failure(camera_id, "No base64 data in response")

            image_bytes = base64.b64decode(base64_data)
            if not save_to_file:
                img = Image.open(BytesIO(image_bytes))
                return {
                    "success": True,
                    "camera_id": camera_id,
                    "dimensions": img.size,
                    "size_bytes": len(image_bytes),
                }

            result = self._save_frame(image_bytes, camera_id, output_dir)
            self._print(f"✅ Image saved: {result['filename']}")
            return result
        except Exception as exc:
            self._print(f"❌ Error: {exc}")
            return self._failure(camera_id, str(exc))

    async def fetch_camera_image_async(
        self,
        camera_id: str,
        save_to_file: bool = True,
        custom_output_dir: str | None = None,
    ) -> dict[str, Any]:
        output_dir = custom_output_dir or self.output_dir
        if save_to_file:
            os.makedirs(output_dir, exist_ok=True)

        payload = await self._fetch_payload_async(camera_id)
        if not payload.get("success"):
            self._print(f"❌ [ASYNC] {camera_id}: {payload.get('error')}")
            return payload

        image_bytes = base64.b64decode(payload["content_base64"])
        if not save_to_file:
            img = Image.open(BytesIO(image_bytes))
            self._print(f"✅ [ASYNC] {camera_id}: image loaded (not saved)")
            return {
                "success": True,
                "camera_id": camera_id,
                "dimensions": img.size,
                "size_bytes": len(image_bytes),
            }

        result = self._save_frame(image_bytes, camera_id, output_dir)
        self._print(f"✅ [ASYNC] {camera_id}: {result['filename']}")
        return result

    async def fetch_unique_burst(
        self,
        camera_id: str,
        *,
        n_unique: int = 5,
        interval_s: float = 2.0,
        poll_s: float = 0.25,
        timeout_s: float = 60.0,
        custom_output_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        """Poll a camera and save only when the frame hash changes."""
        output_dir = custom_output_dir or self.output_dir
        os.makedirs(output_dir, exist_ok=True)

        last_hash: str | None = None
        saved: list[dict[str, Any]] = []
        started = time.monotonic()
        next_due = started

        while len(saved) < n_unique and time.monotonic() - started < timeout_s:
            now = time.monotonic()
            if now < next_due:
                await asyncio.sleep(min(poll_s, next_due - now))
                continue

            payload = await self._fetch_payload_async(camera_id)
            if not payload.get("success"):
                await asyncio.sleep(poll_s)
                continue

            raw = payload["content_base64"]
            digest = hashlib.sha256(raw.encode("ascii")).hexdigest()
            if digest == last_hash:
                await asyncio.sleep(poll_s)
                continue

            image_bytes = base64.b64decode(raw)
            result = self._save_frame(image_bytes, camera_id, output_dir)
            last_hash = digest
            saved.append(result)
            self._print(
                f"✅ [BURST] {camera_id}: unique {len(saved)}/{n_unique} -> {result['filename']}"
            )
            next_due = time.monotonic() + interval_s

        return saved

    def fetch_unique_burst_sync(
        self,
        camera_id: str,
        *,
        n_unique: int = 5,
        interval_s: float = 2.0,
        poll_s: float = 0.25,
        timeout_s: float = 60.0,
        custom_output_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        return asyncio.run(
            self.fetch_unique_burst(
                camera_id,
                n_unique=n_unique,
                interval_s=interval_s,
                poll_s=poll_s,
                timeout_s=timeout_s,
                custom_output_dir=custom_output_dir,
            )
        )

    async def fetch_place_snapshot(
        self,
        place_id: str,
        *,
        config: dict[str, Any] | None = None,
        custom_output_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all cameras for a place in parallel (same instant)."""
        config = config or load_monitor_config()
        camera_ids = config["cameras"].get(place_id)
        if not camera_ids:
            raise KeyError(f"Place {place_id!r} not found in monitor_config.json")

        output_dir = custom_output_dir or str(place_data_dir(place_id))
        tasks = [self.fetch_camera_image_async(cam_id, True, output_dir) for cam_id in camera_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: list[dict[str, Any]] = []
        for camera_id, result in zip(camera_ids, results):
            if isinstance(result, Exception):
                out.append(self._failure(camera_id, str(result)))
            else:
                out.append(result)
        return out

    def fetch_place_snapshot_sync(
        self,
        place_id: str,
        *,
        config: dict[str, Any] | None = None,
        custom_output_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        return asyncio.run(
            self.fetch_place_snapshot(
                place_id,
                config=config,
                custom_output_dir=custom_output_dir,
            )
        )

    def fetch_multiple_parallel(
        self,
        camera_ids: list[str],
        custom_output_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        return asyncio.run(self.fetch_multiple_async(camera_ids, custom_output_dir))

    async def fetch_multiple_async(
        self,
        camera_ids: list[str],
        custom_output_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        tasks = [self.fetch_camera_image_async(cam_id, True, custom_output_dir) for cam_id in camera_ids]
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time

        normalized: list[dict[str, Any]] = []
        for camera_id, result in zip(camera_ids, results):
            if isinstance(result, Exception):
                normalized.append(self._failure(camera_id, str(result)))
            else:
                normalized.append(result)

        successful = sum(1 for r in normalized if r.get("success"))
        self._print(f"🎯 Parallel: {successful}/{len(camera_ids)} cameras in {duration:.1f}s")
        return normalized

    def monitor_simple(
        self,
        camera_ids: str | list[str],
        interval: str = "10m",
        duration: str = "1h",
        custom_output_dir: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        return asyncio.run(self.monitor_async(camera_ids, interval, duration, custom_output_dir))

    async def monitor_async(
        self,
        camera_ids: str | list[str],
        interval: str,
        duration: str,
        custom_output_dir: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if isinstance(camera_ids, str):
            camera_ids = [camera_ids]

        output_dir = custom_output_dir or self.output_dir
        os.makedirs(output_dir, exist_ok=True)

        interval_td = self._normalize_interval(interval)
        duration_td = self._normalize_interval(duration)
        iterations = int(duration_td.total_seconds() / interval_td.total_seconds())

        self._print(f"🎥 Async monitoring {len(camera_ids)} cameras")
        self._print(f"⏱️ Interval: {interval}, Duration: {duration} ({iterations} iterations)")

        all_results: dict[str, list[dict[str, Any]]] = {cam_id: [] for cam_id in camera_ids}

        for i in range(iterations):
            self._print(f"🔄 Iteration {i+1}/{iterations}")
            tasks = [self.fetch_camera_image_async(cam_id, True, custom_output_dir) for cam_id in camera_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, cam_id in enumerate(camera_ids):
                result = results[j]
                if isinstance(result, Exception):
                    all_results[cam_id].append(self._failure(cam_id, str(result)))
                else:
                    all_results[cam_id].append(result)

            if i < iterations - 1:
                await asyncio.sleep(interval_td.total_seconds())

        self._print("✅ Monitoring completed")
        return all_results

    def fetch_multiple_cameras(
        self,
        camera_ids: list[str],
        custom_output_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        output_dir = custom_output_dir or self.output_dir
        os.makedirs(output_dir, exist_ok=True)

        results: list[dict[str, Any]] = []
        for camera_id in camera_ids:
            self._print(f"📸 Downloading from camera {camera_id}...")
            results.append(self.fetch_camera_image(camera_id, save_to_file=True, custom_output_dir=custom_output_dir))
        return results
