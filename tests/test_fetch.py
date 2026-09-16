import asyncio
import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests
from PIL import Image

from cctv.fetch.decoder import CameraImageFetcher
from cctv.fetch.http import get_url


def _jpeg_base64(color: tuple[int, int, int]) -> str:
    img = Image.new("RGB", (8, 8), color)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_fetch_unique_burst_saves_only_on_hash_change(tmp_path) -> None:
    fetcher = CameraImageFetcher(output_dir=str(tmp_path), verbose=False)
    payloads = [
        {"success": True, "camera_id": "101048", "content_base64": _jpeg_base64((255, 0, 0))},
        {"success": True, "camera_id": "101048", "content_base64": _jpeg_base64((255, 0, 0))},
        {"success": True, "camera_id": "101048", "content_base64": _jpeg_base64((0, 255, 0))},
    ]
    fetcher._fetch_payload_async = AsyncMock(side_effect=payloads)  # type: ignore[method-assign]

    saved = asyncio.run(
        fetcher.fetch_unique_burst(
            "101048",
            n_unique=2,
            interval_s=0.0,
            poll_s=0.0,
            timeout_s=5.0,
            custom_output_dir=str(tmp_path),
        )
    )

    assert len(saved) == 2
    assert all(item["success"] for item in saved)
    assert len(list(tmp_path.glob("camera_101048_*.jpg"))) == 2


def test_fetch_place_snapshot_unknown_place() -> None:
    fetcher = CameraImageFetcher(verbose=False)
    with pytest.raises(KeyError, match="not found"):
        asyncio.run(fetcher.fetch_place_snapshot("unknown_place"))


def test_get_url_retries_without_verify_on_ssl_error() -> None:
    ok = MagicMock()
    ok.status_code = 200

    def fake_get(url, headers=None, timeout=None, verify=True):
        if verify is True:
            raise requests.exceptions.SSLError("self-signed certificate in certificate chain")
        return ok

    with patch("cctv.fetch.http.requests.get", side_effect=fake_get):
        response = get_url("https://bezpecnost.praha.eu/cameras/1/image")

    assert response is ok
