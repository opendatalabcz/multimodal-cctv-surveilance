from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("cctv.api.app:app", host="0.0.0.0", port=8000, reload=True)
