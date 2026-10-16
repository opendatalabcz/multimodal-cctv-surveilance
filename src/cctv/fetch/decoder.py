from __future__ import annotations

import base64
import os
from datetime import datetime
from io import BytesIO
from typing import Any

from PIL import Image

from cctv.fetch.http import get_url


class CameraImageFetcher:
    """Download one still from a Prague municipal CCTV camera."""

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
        img.load()
        now = datetime.now()
        timestamp = f"{now:%Y%m%d_%H%M%S}_{now.microsecond:06d}"
        filename = f"camera_{camera_id}_{timestamp}.jpg"
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, filename)
        if (img.format or "").upper() in {"JPEG", "JPG", "MPO"}:
            with open(filepath, "wb") as handle:
                handle.write(image_bytes)
        else:
            img.convert("RGB").save(filepath, format="JPEG", quality=95, subsampling=0)
        return {
            "success": True,
            "camera_id": camera_id,
            "filename": filename,
            "filepath": filepath,
            "dimensions": img.size,
            "size_bytes": os.path.getsize(filepath),
        }

    def fetch_camera_image(
        self,
        camera_id: str,
        custom_output_dir: str | None = None,
    ) -> dict[str, Any]:
        output_dir = custom_output_dir or self.output_dir
        os.makedirs(output_dir, exist_ok=True)

        url = self._get_camera_url(camera_id)
        self._print(f"Downloading data from camera {camera_id}...")

        try:
            response = get_url(url, headers=self.headers, timeout=self.timeout)
            if response.status_code != 200:
                self._print(f"❌ HTTP Error: {response.status_code}")
                return self._failure(camera_id, f"HTTP {response.status_code}")

            base64_data = response.json().get("contentBase64")
            if not base64_data:
                self._print("⚠️ No base64 data found in response")
                return self._failure(camera_id, "No base64 data in response")

            image_bytes = base64.b64decode(base64_data)
            result = self._save_frame(image_bytes, camera_id, output_dir)
            self._print(f"✅ Image saved: {result['filename']}")
            return result
        except Exception as exc:
            self._print(f"❌ Error: {exc}")
            return self._failure(camera_id, str(exc))
