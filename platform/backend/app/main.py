import logging
import asyncio
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import (
    settings,
    get_api_key, get_base_url, get_model,
    set_runtime, get_runtime_snapshot, persist_runtime_to_env,
)
from .registry import get_apps
from . import process_manager

_log = logging.getLogger("platform")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start all app backends on platform startup; stop them on shutdown."""
    _log.info("Platform starting — launching all app backends...")
    await process_manager.start_all()
    _log.info("All app backends launched.")
    yield
    _log.info("Platform shutting down — stopping all app backends...")
    process_manager.stop_all()


app = FastAPI(title="Velocity Platform API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins="*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class LlmConfigRequest(BaseModel):
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    push_to_apps: bool = True  # whether to forward config to all app backends


# ---------------------------------------------------------------------------
# Platform health
# ---------------------------------------------------------------------------

@app.get("/api/platform/health")
async def platform_health():
    """Platform-level health: checks its own LLM probe and lists apps."""
    llm_mode = "demo"
    llm_error = None
    key = get_api_key()
    if key:
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.post(
                    get_base_url().rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={"model": get_model(), "temperature": 0, "max_tokens": 1,
                          "messages": [{"role": "user", "content": "hi"}]},
                )
                llm_mode = "configured" if r.status_code in (200, 400, 422, 500, 503) else "error"
                if r.status_code not in (200, 400, 422, 500, 503):
                    llm_error = f"HTTP {r.status_code}"
        except httpx.ConnectError as e:
            llm_mode = "unreachable"
            llm_error = str(e)
        except httpx.TimeoutException:
            llm_mode = "unreachable"
            llm_error = "Timeout"
        except Exception as e:
            llm_mode = "error"
            llm_error = str(e)
    return {
        "status": "healthy",
        "llm_mode": llm_mode,
        "llm_url": get_base_url(),
        "llm_model": get_model(),
        "llm_error": llm_error,
    }


# ---------------------------------------------------------------------------
# App registry
# ---------------------------------------------------------------------------

@app.get("/api/platform/apps")
def list_apps():
    """Return all registered apps with their URLs and metadata."""
    return {"apps": get_apps()}


# ---------------------------------------------------------------------------
# Per-app health proxy
# ---------------------------------------------------------------------------

async def _probe_app(backend_url: str, app_id: str) -> dict:
    """Probe a single app backend's /api/health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get(backend_url.rstrip("/") + "/api/health")
            if r.status_code == 200:
                data = r.json()
                return {
                    "id": app_id,
                    "reachable": True,
                    "llm_mode": data.get("llm_mode", "unknown"),
                    "status": data.get("status", "unknown"),
                }
            return {"id": app_id, "reachable": False, "error": f"HTTP {r.status_code}"}
    except httpx.ConnectError:
        return {"id": app_id, "reachable": False, "error": "Connection refused"}
    except httpx.TimeoutException:
        return {"id": app_id, "reachable": False, "error": "Timeout"}
    except Exception as e:
        return {"id": app_id, "reachable": False, "error": str(e)}


@app.get("/api/platform/apps/health")
async def apps_health():
    """Probe all app backends concurrently and return their health."""
    apps = get_apps()
    tasks = [_probe_app(a["backend_url"], a["id"]) for a in apps]
    results = await asyncio.gather(*tasks)
    return {"apps": list(results)}


@app.get("/api/platform/apps/{app_id}/health")
async def app_health(app_id: str):
    """Probe a single app backend."""
    apps = {a["id"]: a for a in get_apps()}
    if app_id not in apps:
        raise HTTPException(404, f"App '{app_id}' not found in registry")
    return await _probe_app(apps[app_id]["backend_url"], app_id)


# ---------------------------------------------------------------------------
# Platform LLM config  — read / write / push to apps
# ---------------------------------------------------------------------------

@app.get("/api/platform/config")
def get_config():
    key = get_api_key()
    return {
        "openai_api_key": ("*" * 8 + key[-4:]) if len(key) > 8 else ("*" * len(key) if key else ""),
        "openai_base_url": get_base_url(),
        "openai_model": get_model(),
        "has_key": bool(key),
        "source": "runtime" if key and key != settings.openai_api_key
                  else ("env" if settings.openai_api_key else "none"),
    }


async def _push_config_to_app(backend_url: str, app_id: str, key: str, base_url: str, model: str) -> dict:
    """Forward LLM config to a single app backend via its PUT /api/config."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.put(
                backend_url.rstrip("/") + "/api/config",
                json={
                    "openai_api_key": key,
                    "openai_base_url": base_url,
                    "openai_model": model,
                },
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "id": app_id,
                    "pushed": True,
                    "llm_mode": data.get("llm_mode", "unknown"),
                    "llm_error": data.get("llm_error"),
                }
            return {"id": app_id, "pushed": False, "error": f"HTTP {r.status_code}"}
    except httpx.ConnectError:
        return {"id": app_id, "pushed": False, "error": "Connection refused — app backend not running"}
    except httpx.TimeoutException:
        return {"id": app_id, "pushed": False, "error": "Timeout"}
    except Exception as e:
        return {"id": app_id, "pushed": False, "error": str(e)}


@app.put("/api/platform/config")
async def put_config(req: LlmConfigRequest):
    """Save platform LLM config and optionally push it to all app backends."""
    # Resolve sentinel
    key = get_api_key() if req.openai_api_key.strip() == "__keep__" else req.openai_api_key
    set_runtime(key, req.openai_base_url, req.openai_model)
    persist_runtime_to_env()

    # Platform-level LLM probe
    llm_mode = "demo"
    llm_error = None
    if key:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.post(
                    get_base_url().rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={"model": get_model(), "temperature": 0, "max_tokens": 1,
                          "messages": [{"role": "user", "content": "hi"}]},
                )
                llm_mode = "configured" if r.status_code in (200, 400, 422, 500, 503) else "error"
                if r.status_code not in (200, 400, 422, 500, 503):
                    llm_error = f"HTTP {r.status_code}"
        except httpx.ConnectError as e:
            llm_mode = "unreachable"
            llm_error = f"Cannot reach {get_base_url()}: {e}"
        except httpx.TimeoutException:
            llm_mode = "unreachable"
            llm_error = "Connection timed out"
        except Exception as e:
            llm_mode = "error"
            llm_error = str(e)

    # Push to all app backends concurrently if requested
    push_results: list[dict] = []
    if req.push_to_apps:
        apps = get_apps()
        tasks = [
            _push_config_to_app(
                a["backend_url"], a["id"],
                key, get_base_url(), get_model(),
            )
            for a in apps
        ]
        push_results = list(await asyncio.gather(*tasks))
        for res in push_results:
            if not res.get("pushed"):
                _log.warning("Config push failed for %s: %s", res["id"], res.get("error"))

    return {
        "success": True,
        "llm_mode": llm_mode,
        "llm_error": llm_error,
        "push_results": push_results,
    }


@app.post("/api/platform/config/push")
async def push_config_to_apps():
    """Push the current platform config to all app backends (without changing the key)."""
    key = get_api_key()
    base_url = get_base_url()
    model = get_model()
    apps = get_apps()
    tasks = [
        _push_config_to_app(a["backend_url"], a["id"], key, base_url, model)
        for a in apps
    ]
    results = list(await asyncio.gather(*tasks))
    return {"success": True, "push_results": results}


# ---------------------------------------------------------------------------
# Process management endpoints
# ---------------------------------------------------------------------------

@app.get("/api/platform/processes")
def get_processes():
    """Return the live status of all managed app backend processes."""
    return {"processes": process_manager.get_status()}


@app.post("/api/platform/processes/{app_id}/restart")
async def restart_process(app_id: str):
    """Stop and restart a specific app backend + frontend process."""
    proc = process_manager.get_process(app_id)
    if proc is None:
        raise HTTPException(404, f"No managed process found for app '{app_id}'")
    front = process_manager.get_frontend(app_id)
    _log.info("Manual restart requested for %s", app_id)
    if front:
        front.stop()
    proc.stop()
    await asyncio.sleep(1)
    proc.stopped = False
    proc.restarts = 0
    ok = proc.start()
    if ok:
        from .process_manager import _monitor
        proc._monitor_task = asyncio.create_task(_monitor(proc))
        await asyncio.sleep(3)
        if front:
            front.stopped = False
            front.start()
    return {"success": ok, "process": proc.info()}


@app.post("/api/platform/processes/{app_id}/stop")
def stop_process(app_id: str):
    """Stop a specific app backend + frontend process."""
    proc = process_manager.get_process(app_id)
    if proc is None:
        raise HTTPException(404, f"No managed process found for app '{app_id}'")
    front = process_manager.get_frontend(app_id)
    if front:
        front.stop()
    proc.stop()
    return {"success": True, "process": proc.info()}


@app.post("/api/platform/processes/{app_id}/start")
async def start_process(app_id: str):
    """Start a specific app backend + frontend process (if not already running)."""
    proc = process_manager.get_process(app_id)
    if proc is None:
        raise HTTPException(404, f"No managed process found for app '{app_id}'")
    front = process_manager.get_frontend(app_id)
    if proc.is_running:
        return {"success": True, "process": proc.info(), "note": "already running"}
    proc.stopped = False
    proc.restarts = 0
    ok = proc.start()
    if ok:
        from .process_manager import _monitor
        proc._monitor_task = asyncio.create_task(_monitor(proc))
        await asyncio.sleep(3)
        if front and not front.is_running:
            front.stopped = False
            front.start()
    return {"success": ok, "process": proc.info()}
