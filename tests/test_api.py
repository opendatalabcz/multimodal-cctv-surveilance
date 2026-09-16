import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cctv.api.app import create_app
from cctv.config.models import AgentConfig, CameraConfig, ToolsConfig


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CCTV_DATA_DIR", str(tmp_path))
    config_path = tmp_path / "agent.yaml"
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: config_path)
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
    monkeypatch.setattr("cctv.config.agent_yaml.agent_config_path", lambda: config_path)

    payload = {
        "cameras": [
            {
                "id": "bridge",
                "name": "Bridge",
                "lat": 50.1,
                "lon": 14.4,
                "source": "101200",
            }
        ],
        "tools": {"internet": False, "google_maps": True},
    }

    put_response = client.put("/api/config", json=payload)
    assert put_response.status_code == 200
    assert put_response.json() == payload

    get_response = client.get("/api/config")
    assert get_response.status_code == 200
    assert get_response.json() == payload


def test_conversation_message_flow(client) -> None:
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
