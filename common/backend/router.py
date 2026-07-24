"""
common/backend/router.py
──────────────────────────
Shared FastAPI route factories for the endpoints that are identical across
all Velocity AI applications:

  - config_router()   : GET /api/config  +  PUT /api/config
  - health_router()   : GET /api/health
  - sessions_router() : GET/POST/GET/{sid}/DELETE/{sid} /api/sessions

Usage in an app's main.py:

    from common.backend.router import config_router, health_router, sessions_router
    from .config import settings, get_api_key, get_base_url, get_model, set_runtime
    from .models import Session, LlmConfigRequest
    from . import store

    app = FastAPI(title="My App")

    app.include_router(config_router(
        get_api_key=get_api_key,
        get_base_url=get_base_url,
        get_model=get_model,
        set_runtime=set_runtime,
        settings=settings,
    ))

    app.include_router(health_router(
        get_api_key=get_api_key,
        get_base_url=get_base_url,
        get_model=get_model,
        settings=settings,
    ))

    app.include_router(sessions_router(
        store=store,
        session_factory=lambda: Session(title="New session"),
    ))
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from uuid import uuid4

from common.backend.llm_service import probe_llm
from common.backend.models import LlmConfigRequest


# ---------------------------------------------------------------------------
# /api/config  (GET + PUT)
# ---------------------------------------------------------------------------

def config_router(
    get_api_key: Callable[[], str],
    get_base_url: Callable[[], str],
    get_model: Callable[[], str],
    set_runtime: Callable[[str, str, str], None],
    settings: Any,
    prefix: str = "",
) -> APIRouter:
    """
    Returns an APIRouter with:
      GET  /api/config  — return masked current config.
      PUT  /api/config  — update runtime config and probe LLM connectivity.
    """
    router = APIRouter(prefix=prefix)

    @router.get("/api/config")
    def get_config():
        key = get_api_key()
        masked = (
            "*" * 8 + key[-4:]
            if len(key) > 8
            else "*" * len(key) if key else ""
        )
        return {
            "openai_api_key": masked,
            "openai_base_url": get_base_url(),
            "openai_model": get_model(),
            "has_key": bool(key),
            "source": (
                "runtime"
                if key and key != settings.openai_api_key
                else ("env" if settings.openai_api_key else "none")
            ),
        }

    @router.put("/api/config")
    async def put_config(req: LlmConfigRequest):
        # "__keep__" sentinel means: don't replace the existing key
        key = (
            get_api_key()
            if req.openai_api_key.strip() == "__keep__"
            else req.openai_api_key
        )
        set_runtime(key, req.openai_base_url, req.openai_model)

        llm_mode, llm_error = await probe_llm(
            get_api_key=get_api_key,
            get_base_url=get_base_url,
            get_model=get_model,
        )
        return {"success": True, "llm_mode": llm_mode, "llm_error": llm_error}

    return router


# ---------------------------------------------------------------------------
# /api/health  (GET)
# ---------------------------------------------------------------------------

def health_router(
    get_api_key: Callable[[], str],
    get_base_url: Callable[[], str],
    get_model: Callable[[], str],
    settings: Any,
    prefix: str = "",
) -> APIRouter:
    """
    Returns an APIRouter with:
      GET /api/health — liveness + LLM connectivity check.
    """
    router = APIRouter(prefix=prefix)

    @router.get("/api/health")
    async def health():
        llm_mode, llm_error = await probe_llm(
            get_api_key=get_api_key,
            get_base_url=get_base_url,
            get_model=get_model,
        )
        return {
            "status": "healthy",
            "llm_mode": llm_mode,
            "llm_url": get_base_url(),
            "llm_model": get_model(),
            "llm_error": llm_error,
        }

    return router


# ---------------------------------------------------------------------------
# /api/sessions  (CRUD)
# ---------------------------------------------------------------------------

def sessions_router(
    store: Any,
    session_factory: Callable[[], Any],
    prefix: str = "",
) -> APIRouter:
    """
    Returns an APIRouter with:
      GET    /api/sessions          — list all sessions.
      POST   /api/sessions          — create a new session.
      GET    /api/sessions/{sid}    — retrieve a session by ID.
      DELETE /api/sessions/{sid}    — delete a session.

    Parameters
    ----------
    store           : The app's store module (must expose save/load/delete/list_all).
    session_factory : Zero-argument callable that returns a new Session instance.
    """
    router = APIRouter(prefix=prefix)

    @router.get("/api/sessions")
    def list_sessions():
        return store.list_all()

    @router.post("/api/sessions")
    def create_session():
        s = session_factory()
        store.save(s)
        return s

    @router.get("/api/sessions/{sid}")
    def get_session(sid: str):
        try:
            return store.load(sid)
        except FileNotFoundError:
            raise HTTPException(404, "Session not found")

    @router.delete("/api/sessions/{sid}")
    def delete_session(sid: str):
        store.delete(sid)
        return {"success": True}

    return router


# ---------------------------------------------------------------------------
# /api/download  (GET) — generic file download used by DrawingReviewer
# ---------------------------------------------------------------------------

def download_router(prefix: str = "") -> APIRouter:
    """
    Returns an APIRouter with:
      GET /api/download?path=<absolute_path> — serve any file for download.

    Used by DrawingReviewer to serve generated Word / PDF / Excel artifacts.
    """
    router = APIRouter(prefix=prefix)

    @router.get("/api/download")
    def download(path: str):
        p = Path(path)
        if not p.exists():
            raise HTTPException(404, "File not found")
        return FileResponse(
            path=str(p),
            filename=p.name,
            media_type="application/octet-stream",
        )

    return router
