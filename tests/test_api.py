import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cctv.api.app import create_app
from cctv.config.agent_yaml import save_agent_config
from cctv.config.effective import UNASSIGNED_SECTOR_ID
from cctv.config.models import AgentConfig, CameraConfig, LocationConfig, SectorConfig, ToolsConfig


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    config_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: config_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    monkeypatch.setattr("cctv.api.chat.load_agent_config", lambda: AgentConfig(
        cameras=[
            CameraConfig(
                id="test_cam",
                name="Test Camera",
                source="101048",
            )
        ],
        tools=ToolsConfig(),
    ))
    return TestClient(create_app())


def test_get_and_put_config(client, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: config_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)

    payload = {
        "locations": [],
        "cameras": [
            {
                "id": "bridge",
                "name": "Bridge",
                "lat": 50.1,
                "lon": 14.4,
                "source": "101200",
                "location_id": None,
                "enabled": True,
            }
        ],
        "tools": {"internet": False, "weather": False, "maps": True},
    }

    put_response = client.put("/api/config", json=payload)
    assert put_response.status_code == 200
    body = put_response.json()
    assert body["cameras"][0]["id"] == "bridge"
    assert body["cameras"][0]["sector_id"] == UNASSIGNED_SECTOR_ID
    assert any(sector["id"] == UNASSIGNED_SECTOR_ID for sector in body["sectors"])
    assert body["tools"]["maps"] is True

    get_response = client.get("/api/config")
    assert get_response.status_code == 200
    assert get_response.json() == body


def test_analyze_camera_endpoint_returns_saved_metadata(client) -> None:
    analyzed = CameraConfig(
        id="test_cam",
        name="Test Camera",
        source="101048",
        analysis={
            "description": "A road carrying vehicles.",
            "scene_tags": ["road"],
            "source_fingerprint": "abc123",
            "analyzed_at": "2026-09-16T12:00:00Z",
        },
    )
    with patch("cctv.api.app.analyze_camera_metadata", return_value=analyzed):
        response = client.post("/api/cameras/test_cam/analyze")
    assert response.status_code == 200
    assert response.json()["analysis"]["scene_tags"] == ["road"]


def test_analyze_camera_endpoint_reports_fetch_failure(client) -> None:
    with patch(
        "cctv.api.app.analyze_camera_metadata",
        side_effect=RuntimeError("Could not fetch camera frame"),
    ):
        response = client.post("/api/cameras/test_cam/analyze")
    assert response.status_code == 502
    assert "Could not fetch" in response.json()["detail"]


def test_conversation_message_flow(client, tmp_path) -> None:
    create_response = client.post("/api/conversations")
    assert create_response.status_code == 200
    conversation = create_response.json()
    assert conversation["messages"] == []
    conversation_id = conversation["id"]

    chat_result = {
        "success": True,
        "analysis": "The street looks calm.",
        "messages": [
            {"role": "user", "content": "How busy is it?"},
            {
                "role": "assistant",
                "content": "The street looks calm.",
            },
        ],
        "image_paths": ["camera_images/test/frame.jpg"],
    }

    with patch("cctv.api.chat.chat_with_tools", return_value=chat_result):
        message_response = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "How busy is it?"},
        )

    assert message_response.status_code == 200
    body = message_response.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"
    assert body["messages"][1]["content"] == "The street looks calm."
    assert body["messages"][1]["imageUrls"] == ["/api/images/camera_images/test/frame.jpg"]

    get_response = client.get(f"/api/conversations/{conversation_id}")
    assert get_response.status_code == 200
    assert get_response.json() == body

    log_path = tmp_path / "logs" / "chat_turns.jsonl"
    assert log_path.is_file()
    entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["conversation_id"] == conversation_id
    assert entry["success"] is True
    assert entry["cameras"] == ["camera_images/test/frame.jpg"]
    assert "duration_ms" in entry


def test_serve_image_under_data_root(client, tmp_path) -> None:
    image_path = tmp_path / "camera_images" / "test" / "frame.jpg"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (4, 4), (0, 255, 0)).save(image_path, format="JPEG")

    ok_response = client.get("/api/images/camera_images/test/frame.jpg")
    assert ok_response.status_code == 200
    assert ok_response.headers["content-type"] == "image/jpeg"

    missing_response = client.get("/api/images/does/not/exist.jpg")
    assert missing_response.status_code == 404

    traversal_response = client.get("/api/images/../agent.yaml")
    assert traversal_response.status_code == 404


def test_put_config_rejects_sector_deletion_with_cameras(client, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "agent.yaml"
    overlay_path = tmp_path / "agent.local.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: config_path)
    monkeypatch.setattr("cctv.config.agent_yaml.agent_overlay_path", lambda: overlay_path)
    save_agent_config(
        AgentConfig(
            sectors=[
                SectorConfig(id="prague", name="Prague"),
                SectorConfig(id="airport", name="Airport"),
            ],
            locations=[
                LocationConfig(id="bridge", name="Bridge", sector_id="prague"),
                LocationConfig(id="gate", name="Gate", sector_id="airport"),
            ],
            cameras=[
                CameraConfig(
                    id="bridge",
                    name="Bridge",
                    source="101200",
                    sector_id="prague",
                    location_id="bridge",
                ),
                CameraConfig(
                    id="gate",
                    name="Gate",
                    source="101048",
                    sector_id="airport",
                    location_id="gate",
                ),
            ],
        ),
        config_path,
    )

    response = client.put(
        "/api/config",
        json={
            "sectors": [{"id": "airport", "name": "Airport", "enabled": True}],
            "locations": [
                {"id": "bridge", "name": "Bridge", "sector_id": "prague", "enabled": True, "lat": None, "lon": None},
                {"id": "gate", "name": "Gate", "sector_id": "airport", "enabled": True, "lat": None, "lon": None},
            ],
            "cameras": [
                {
                    "id": "bridge",
                    "name": "Bridge",
                    "lat": None,
                    "lon": None,
                    "source": "101200",
                    "sector_id": "prague",
                    "location_id": "bridge",
                    "enabled": True,
                },
                {
                    "id": "gate",
                    "name": "Gate",
                    "lat": None,
                    "lon": None,
                    "source": "101048",
                    "sector_id": "airport",
                    "location_id": "gate",
                    "enabled": True,
                },
            ],
            "tools": {"internet": False, "weather": False, "maps": False},
        },
    )
    assert response.status_code == 400
    assert "Cannot remove sector" in response.json()["detail"]


def test_post_message_chat_failure(client) -> None:
    create_response = client.post("/api/conversations")
    conversation_id = create_response.json()["id"]

    with patch(
        "cctv.api.chat.chat_with_tools",
        return_value={"success": False, "error": "Azure OpenAI configuration missing"},
    ):
        response = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "hello"},
        )

    assert response.status_code == 502
    assert "configuration missing" in response.json()["detail"]

    transcript = client.get(f"/api/conversations/{conversation_id}").json()
    assert transcript["messages"] == []


def _sse_events(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def test_message_stream_emits_status_then_done(client) -> None:
    conversation_id = client.post("/api/conversations").json()["id"]

    def fake_chat(*args, on_progress=None, **kwargs):
        if on_progress:
            on_progress({"type": "status", "stage": "fetching", "detail": "Fetching 2 cameras…"})
            on_progress(
                {"type": "status", "stage": "analyzing", "detail": "Analyzing 2 camera frames…"}
            )
        return {
            "success": True,
            "analysis": "The street looks calm.",
            "messages": [
                {"role": "user", "content": "How busy is it?"},
                {"role": "assistant", "content": "The street looks calm."},
            ],
            "image_paths": ["camera_images/test/frame.jpg"],
        }

    with patch("cctv.api.chat.chat_with_tools", side_effect=fake_chat):
        with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/messages/stream",
            json={"content": "How busy is it?"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            body = "".join(response.iter_text())

    events = _sse_events(body)
    assert [event["type"] for event in events] == ["status", "status", "done"]
    assert events[0]["detail"] == "Fetching 2 cameras…"
    assert events[1]["stage"] == "analyzing"
    done = events[-1]
    assert done["conversation"]["id"] == conversation_id
    assert done["conversation"]["messages"][-1]["content"] == "The street looks calm."
    assert done["conversation"]["messages"][-1]["imageUrls"] == [
        "/api/images/camera_images/test/frame.jpg"
    ]


def test_message_stream_emits_error(client) -> None:
    conversation_id = client.post("/api/conversations").json()["id"]

    with patch(
        "cctv.api.chat.chat_with_tools",
        return_value={"success": False, "error": "Azure OpenAI configuration missing"},
    ):
        with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/messages/stream",
            json={"content": "hello"},
        ) as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

    events = _sse_events(body)
    assert events[-1]["type"] == "error"
    assert "configuration missing" in events[-1]["detail"]
    transcript = client.get(f"/api/conversations/{conversation_id}").json()
    assert transcript["messages"] == []


def test_message_stream_unknown_conversation(client) -> None:
    response = client.post(
        "/api/conversations/missing/messages/stream",
        json={"content": "hello"},
    )
    assert response.status_code == 404
