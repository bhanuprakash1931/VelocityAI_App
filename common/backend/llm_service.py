"""
common/backend/llm_service.py
──────────────────────────────
Shared LLM service layer for all Velocity AI applications.

Provides:
  - _parse_json()        : Strip markdown fences and parse first JSON object.
  - llm_json()           : POST to /chat/completions and return parsed JSON.
  - llm_vision_json()    : Multimodal (vision) variant — accepts base64 images.
  - llm_chat_completion(): Raw string response (for chat endpoints).
  - probe_llm()          : Lightweight connectivity test used by /api/config PUT
                           and /api/health.

Usage in an app's services.py:

    from common.backend.llm_service import llm_json, llm_chat_completion
    from .config import get_api_key, get_base_url, get_model

    result = await llm_json(
        system="You are a requirements engineer …",
        user=json.dumps(payload),
        get_api_key=get_api_key,
        get_base_url=get_base_url,
        get_model=get_model,
    )
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

import httpx

_log = logging.getLogger("common.llm_service")


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict | None:
    """Strip markdown fences and parse the first JSON object found in text."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    a = text.find("{")
    b = text.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        return json.loads(text[a : b + 1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core LLM call — returns parsed JSON dict or None on any failure
# ---------------------------------------------------------------------------

async def llm_json(
    system: str,
    user: str,
    get_api_key: Callable[[], str],
    get_base_url: Callable[[], str],
    get_model: Callable[[], str],
    timeout: int = 120,
    temperature: float = 0.2,
) -> dict | None:
    """
    Call the configured LLM /chat/completions endpoint with a system + user
    message pair and return the response parsed as a JSON dict.

    Returns None on any failure (no key, connection error, timeout, HTTP
    error, or unparseable response) — callers should fall back to demo data.
    """
    api_key = get_api_key()
    if not api_key:
        _log.debug("llm_json: no API key configured — skipping")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": get_model(),
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                get_base_url().rstrip("/") + "/chat/completions",
                headers=headers,
                json=payload,
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"]
            result = _parse_json(raw)
            if result is None:
                _log.warning("llm_json: response was not valid JSON — raw[:200]: %s", raw[:200])
            return result
    except httpx.ConnectError:
        _log.warning("llm_json: cannot connect to %s", get_base_url())
        return None
    except httpx.TimeoutException:
        _log.warning("llm_json: timed out after %ds", timeout)
        return None
    except httpx.HTTPStatusError as e:
        _log.warning(
            "llm_json: HTTP %s — %s",
            e.response.status_code,
            e.response.text[:200],
        )
        return None
    except Exception:
        _log.exception("llm_json: unexpected error")
        return None


# ---------------------------------------------------------------------------
# Vision (multimodal) variant — accepts base64 images alongside a text prompt
# ---------------------------------------------------------------------------

async def llm_vision_json(
    prompt: str,
    images_b64: list[dict],
    get_api_key: Callable[[], str],
    get_base_url: Callable[[], str],
    get_model: Callable[[], str],
    timeout: int = 180,
    max_tokens: int = 8192,
) -> dict | None:
    """
    Call the LLM with vision (multimodal) content and return parsed JSON.

    Each element of images_b64 should be a dict with keys:
        b64       : base64-encoded image string (or a data-URI).
        mime_type : MIME type string, e.g. "image/jpeg" (default).

    Returns None on any failure.
    """
    api_key = get_api_key()
    if not api_key:
        _log.debug("llm_vision_json: no API key configured — skipping")
        return None

    content: list[dict] = [{"type": "text", "text": prompt}]
    for img in images_b64:
        b64 = img.get("b64", "")
        mime = img.get("mime_type", "image/jpeg")
        if not b64:
            continue
        url = b64 if b64.startswith("data:image") else f"data:{mime};base64,{b64}"
        content.append({"type": "image_url", "image_url": {"url": url}})

    payload = {
        "model": get_model(),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                get_base_url().rstrip("/") + "/chat/completions",
                headers=headers,
                json=payload,
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"]
            result = _parse_json(raw)
            if result is None:
                _log.warning(
                    "llm_vision_json: response was not valid JSON — raw[:200]: %s", raw[:200]
                )
            return result
    except httpx.ConnectError:
        _log.warning("llm_vision_json: cannot connect to %s", get_base_url())
        return None
    except httpx.TimeoutException:
        _log.warning("llm_vision_json: timed out after %ds", timeout)
        return None
    except httpx.HTTPStatusError as e:
        _log.warning(
            "llm_vision_json: HTTP %s — %s",
            e.response.status_code,
            e.response.text[:200],
        )
        return None
    except Exception:
        _log.exception("llm_vision_json: unexpected error")
        return None


# ---------------------------------------------------------------------------
# Raw string chat completion — used by chat / Q&A endpoints
# ---------------------------------------------------------------------------

async def llm_chat_completion(
    system: str,
    user: str,
    get_api_key: Callable[[], str],
    get_base_url: Callable[[], str],
    get_model: Callable[[], str],
    timeout: int = 60,
    max_tokens: int = 1024,
    no_key_message: str = "Chat requires an API key. Configure one via the ⚙ settings panel.",
) -> str:
    """
    Call the LLM and return the raw assistant text content as a string.

    Unlike llm_json(), this does NOT attempt JSON parsing — it returns the
    assistant message as plain text for display in chat UIs.

    Returns a user-friendly error string on any failure.
    """
    api_key = get_api_key()
    if not api_key:
        return no_key_message

    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                get_base_url().rstrip("/") + "/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": get_model(),
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except httpx.ConnectError:
        return f"Cannot connect to LLM at {get_base_url()}. Check your API base URL."
    except httpx.TimeoutException:
        return "LLM request timed out. Try again."
    except httpx.HTTPStatusError as e:
        return f"LLM returned HTTP {e.response.status_code}. Check API key and endpoint."
    except Exception as e:
        return f"Chat error: {e}"


# ---------------------------------------------------------------------------
# Connectivity probe — used by /api/config PUT and /api/health
# ---------------------------------------------------------------------------

async def probe_llm(
    get_api_key: Callable[[], str],
    get_base_url: Callable[[], str],
    get_model: Callable[[], str],
    timeout: int = 8,
) -> tuple[str, str | None]:
    """
    Send a minimal test request to the LLM endpoint.

    Returns
    -------
    (llm_mode, llm_error) where llm_mode is one of:
        "demo"        — no API key configured.
        "configured"  — key present and endpoint responded 200 or 400.
        "unreachable" — key present but cannot connect or timed out.
        "error"       — key present but unexpected HTTP status or exception.
    """
    api_key = get_api_key()
    if not api_key:
        return "demo", None

    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                get_base_url().rstrip("/") + "/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": get_model(),
                    "temperature": 0,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            if r.status_code in (200, 400):
                return "configured", None
            return "error", f"HTTP {r.status_code}"
    except httpx.ConnectError as e:
        return "unreachable", f"Cannot reach {get_base_url()}: {e}"
    except httpx.TimeoutException:
        return "unreachable", "Connection timed out"
    except Exception as e:
        return "error", str(e)
