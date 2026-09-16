import base64
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from cctv.fetch.image_source import get_image, register_sleep_placeholder_hash
from cctv.fetch.sources import SourceType, classify_source
from cctv.tools.get_image import GET_IMAGE_TOOL, execute_get_image


def _jpeg_bytes(color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    img = Image.new("RGB", (12, 10), color)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _jpeg_base64(color: tuple[int, int, int] = (10, 20, 30)) -> str:
    return base64.b64encode(_jpeg_bytes(color)).decode("ascii")


@pytest.mark.parametrize(
    ("source", "expected_type", "key"),
    [
        ("https://www.youtube.com/watch?v=IDXRscHtp2s", SourceType.YOUTUBE, "url"),
        ("https://youtu.be/IDXRscHtp2s", SourceType.YOUTUBE, "url"),
        ("https://www.youtube.com/live/IDXRscHtp2s", SourceType.YOUTUBE, "url"),
        (
            "https://bezpecnost.praha.eu/Intens.CrisisPortalInfrastructureApp/cameras/101048/image",
            SourceType.PRAGUE_CAMERA,
            "camera_id",
        ),
        ("101048", SourceType.PRAGUE_CAMERA, "camera_id"),
        ("https://example.com/frame.jpg", SourceType.HTTP_IMAGE, "url"),
    ],
)
def test_classify_source(source: str, expected_type: SourceType, key: str) -> None:
    source_type, info = classify_source(source)
    assert source_type == expected_type
    assert key in info


def test_classify_source_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unrecognized"):
        classify_source("not-a-valid-source")


def test_get_image_tool_schema() -> None:
    assert GET_IMAGE_TOOL["function"]["name"] == "get_image"
    assert "source" in GET_IMAGE_TOOL["function"]["parameters"]["properties"]


def test_get_image_prague_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    payload = {"contentBase64": _jpeg_base64((1, 2, 3))}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return payload

    with patch("cctv.fetch.decoder.get_url", return_value=FakeResponse()):
        result = get_image("101048", verbose=False)

    assert result["success"] is True
    assert result["source_type"] == "prague_camera"
    assert Path(result["filepath"]).is_file()
    assert result["camera_id"] == "101048"


def test_get_image_http_raw_image(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    image_bytes = _jpeg_bytes((4, 5, 6))

    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "image/jpeg"}
        content = image_bytes

        @staticmethod
        def json() -> dict:
            raise ValueError("not json")

    with patch("cctv.fetch.image_source.get_url", return_value=FakeResponse()):
        result = get_image("https://example.com/live.jpg", verbose=False)

    assert result["success"] is True
    assert result["source_type"] == "http_image"
    assert Path(result["filepath"]).is_file()


def test_get_image_http_json_base64(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))

    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        text = json.dumps({"contentBase64": _jpeg_base64((7, 8, 9))})

        @staticmethod
        def json() -> dict:
            return {"contentBase64": _jpeg_base64((7, 8, 9))}

    with patch("cctv.fetch.image_source.get_url", return_value=FakeResponse()):
        result = get_image("https://example.com/api/frame", verbose=False)

    assert result["success"] is True
    assert result["source_type"] == "http_image"


def test_likely_unavailable_placeholder(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    placeholder = _jpeg_bytes((200, 200, 200))
    register_sleep_placeholder_hash(hashlib.sha256(placeholder).hexdigest())
    payload = {"contentBase64": base64.b64encode(placeholder).decode("ascii")}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return payload

    with patch("cctv.fetch.decoder.get_url", return_value=FakeResponse()):
        result = get_image("101048", verbose=False)

    assert result["success"] is True
    assert result["likely_unavailable"] is True


def test_execute_get_image_metadata_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    payload = {"contentBase64": _jpeg_base64()}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return payload

    with patch("cctv.fetch.decoder.get_url", return_value=FakeResponse()):
        exec_result = execute_get_image("101048")

    meta = json.loads(exec_result["tool_content"])
    assert meta["success"] is True
    assert "filepath" in meta
    assert exec_result["image_path"]


@patch("cctv.fetch.youtube.requests.get")
@patch("cctv.fetch.youtube.subprocess.run")
@patch("cctv.fetch.youtube.yt_dlp.YoutubeDL")
def test_get_image_youtube_live(
    mock_ytdl_cls: MagicMock,
    mock_subprocess_run: MagicMock,
    mock_requests_get: MagicMock,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))

    ydl = MagicMock()
    ydl.extract_info.return_value = {
        "id": "IDXRscHtp2s",
        "is_live": True,
        "url": "https://stream.example/live.m3u8",
    }
    mock_ytdl_cls.return_value.__enter__.return_value = ydl

    def fake_get(url, headers=None, timeout=None):
        response = MagicMock()
        response.raise_for_status.return_value = None
        if str(url).endswith(".m3u8"):
            response.content = b"#EXTM3U\n#EXTINF:1,\nhttps://stream.example/last.ts\n"
            response.text = response.content.decode()
        else:
            response.content = b"fake-ts-bytes"
            response.text = ""
        return response

    mock_requests_get.side_effect = fake_get

    def _write_jpeg(cmd, **kwargs):
        output = Path(cmd[-1])
        Image.new("RGB", (16, 9), (0, 128, 255)).save(output, format="JPEG")

    mock_subprocess_run.side_effect = _write_jpeg

    result = get_image("https://www.youtube.com/watch?v=IDXRscHtp2s", verbose=False)

    assert result["success"] is True
    assert result["source_type"] == "youtube"
    assert result["video_id"] == "IDXRscHtp2s"
    assert Path(result["filepath"]).is_file()
    fetched_urls = [call.args[0] for call in mock_requests_get.call_args_list]
    assert fetched_urls == [
        "https://stream.example/live.m3u8",
        "https://stream.example/last.ts",
    ]
    ffmpeg_cmd = mock_subprocess_run.call_args[0][0]
    assert ffmpeg_cmd[ffmpeg_cmd.index("-i") + 1].endswith(".ts")
    assert "-an" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-frames:v") + 1] == "1"
    assert str(ffmpeg_cmd[-1]).endswith(".jpg")


@patch("cctv.fetch.youtube.requests.get")
@patch("cctv.fetch.youtube.subprocess.run")
@patch("cctv.fetch.youtube.yt_dlp.YoutubeDL")
def test_get_image_youtube_picks_720p_video_only(
    mock_ytdl_cls: MagicMock,
    mock_subprocess_run: MagicMock,
    mock_requests_get: MagicMock,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    ydl = MagicMock()
    ydl.extract_info.return_value = {
        "id": "IDXRscHtp2s",
        "is_live": True,
        "formats": [
            {
                "url": "https://stream.example/audio.m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "height": None,
            },
            {
                "url": "https://stream.example/1080.m3u8",
                "vcodec": "avc1",
                "acodec": "none",
                "height": 1080,
            },
            {
                "url": "https://stream.example/720.m3u8",
                "vcodec": "avc1",
                "acodec": "none",
                "height": 720,
            },
            {
                "url": "https://stream.example/storyboard.mhtml",
                "vcodec": "jpeg",
                "acodec": "none",
                "protocol": "mhtml",
                "height": 90,
            },
        ],
    }
    mock_ytdl_cls.return_value.__enter__.return_value = ydl

    def fake_get(url, headers=None, timeout=None):
        response = MagicMock()
        response.raise_for_status.return_value = None
        if str(url).endswith(".m3u8"):
            response.content = b"#EXTM3U\nhttps://stream.example/edge.ts\n"
        else:
            response.content = b"fake-ts-bytes"
        return response

    mock_requests_get.side_effect = fake_get

    def _write_jpeg(cmd, **kwargs):
        output = Path(cmd[-1])
        Image.new("RGB", (16, 9), (0, 128, 255)).save(output, format="JPEG")

    mock_subprocess_run.side_effect = _write_jpeg

    result = get_image("https://www.youtube.com/watch?v=IDXRscHtp2s", verbose=False)

    assert result["success"] is True
    fetched_urls = [call.args[0] for call in mock_requests_get.call_args_list]
    assert fetched_urls[0] == "https://stream.example/720.m3u8"
    assert fetched_urls[1] == "https://stream.example/edge.ts"
    ffmpeg_cmd = mock_subprocess_run.call_args[0][0]
    assert ffmpeg_cmd[ffmpeg_cmd.index("-i") + 1].endswith(".ts")
    assert "-an" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-frames:v") + 1] == "1"
    assert str(ffmpeg_cmd[-1]).endswith(".jpg")
    ydl_opts = mock_ytdl_cls.call_args[0][0]
    assert "format" not in ydl_opts


@patch("cctv.fetch.youtube.yt_dlp.YoutubeDL")
def test_get_image_youtube_not_live(mock_ytdl_cls: MagicMock, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    ydl = MagicMock()
    ydl.extract_info.return_value = {"id": "abc123", "is_live": False, "url": "https://x"}
    mock_ytdl_cls.return_value.__enter__.return_value = ydl

    result = get_image("https://www.youtube.com/watch?v=abc123", verbose=False)

    assert result["success"] is False
    assert "not a live stream" in result["error"]


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_YOUTUBE") != "1",
    reason="Set RUN_LIVE_YOUTUBE=1 to run live YouTube frame capture",
)
def test_get_image_youtube_live_integration(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    result = get_image("https://www.youtube.com/watch?v=IDXRscHtp2s", verbose=False)
    assert result["success"] is True
    assert Path(result["filepath"]).is_file()
