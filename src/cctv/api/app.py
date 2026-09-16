from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from cctv.api.chat import run_chat_turn
from cctv.api.schemas import (
    ConfigResponse,
    ConversationResponse,
    PostMessageRequest,
)
from cctv.api.store import ConversationStore
from cctv.config.agent_yaml import load_agent_config, save_agent_config
from cctv.utils.paths import data_root

logger = logging.getLogger("cctv.api")

store = ConversationStore()


def create_app() -> FastAPI:
    app = FastAPI(title="CCTV Agent API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/config", response_model=ConfigResponse)
    def get_config() -> ConfigResponse:
        return ConfigResponse.model_validate(load_agent_config().model_dump())

    @app.put("/api/config", response_model=ConfigResponse)
    def put_config(body: ConfigResponse) -> ConfigResponse:
        save_agent_config(body)
        return body

    @app.post("/api/conversations", response_model=ConversationResponse)
    def create_conversation() -> ConversationResponse:
        return store.create().to_response()

    @app.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
    def get_conversation(conversation_id: str) -> ConversationResponse:
        conversation = store.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation.to_response()

    @app.post("/api/conversations/{conversation_id}/messages", response_model=ConversationResponse)
    def post_message(conversation_id: str, body: PostMessageRequest) -> ConversationResponse:
        conversation = store.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conversation, result = run_chat_turn(conversation, body.content)
        if not result.get("success"):
            error = result.get("error", "Chat turn failed")
            logger.error("Chat turn failed for %s: %s", conversation_id, error)
            raise HTTPException(status_code=502, detail=error)
        return conversation.to_response()

    @app.get("/api/images/{file_path:path}")
    def get_image(file_path: str) -> FileResponse:
        root = data_root().resolve()
        target = (root / file_path).resolve()
        if root not in target.parents and target != root:
            raise HTTPException(status_code=404, detail="Image not found")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Image not found")
        return FileResponse(Path(target), media_type="image/jpeg")

    return app


app = create_app()
