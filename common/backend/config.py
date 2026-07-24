"""
common/backend/config.py
────────────────────────
Shared configuration module for all Velocity AI applications.

Usage in each app (e.g. RequirementsGenerator/backend/app/config.py):

    from common.backend.config import make_settings, make_runtime_helpers

    settings, get_api_key, get_base_url, get_model, set_runtime, \
        get_runtime_snapshot, persist_runtime_to_env = make_runtime_helpers(
            env_file=Path(__file__).resolve().parents[1] / ".env",
            default_model="gpt-4.1-mini",
        )
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Base Settings class — apps subclass or use make_settings() directly
# ---------------------------------------------------------------------------

class BaseAppSettings(BaseSettings):
    """Shared settings fields present in every Velocity AI application."""

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    cors_origins: str = "*"
    max_upload_mb: int = 25
    data_dir: Path = Path("data")

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )


def make_settings(
    env_file: Path,
    default_model: str = "gpt-4.1-mini",
    data_dir: Path | None = None,
    **extra_defaults,
) -> BaseAppSettings:
    """
    Factory that creates a fully-configured Settings instance for an app.

    Parameters
    ----------
    env_file      : Absolute path to the app's .env file.
    default_model : Default LLM model name for this app.
    data_dir      : Override for the data directory (default: <env_file parent>/data).
    extra_defaults: Any additional field overrides.
    """

    _data_dir = data_dir or (env_file.parent / "data")

    class _Settings(BaseAppSettings):
        openai_model: str = default_model
        data_dir: Path = _data_dir

        model_config = SettingsConfigDict(
            env_file=str(env_file),
            env_file_encoding="utf-8",
            extra="ignore",
        )

    instance = _Settings(**extra_defaults)
    # Ensure data directories exist on startup
    instance.data_dir.mkdir(parents=True, exist_ok=True)
    (instance.data_dir / "uploads").mkdir(exist_ok=True)
    (instance.data_dir / "sessions").mkdir(exist_ok=True)
    return instance


# ---------------------------------------------------------------------------
# Runtime override helpers
# ---------------------------------------------------------------------------

def make_runtime_helpers(
    env_file: Path,
    default_model: str = "gpt-4.1-mini",
    data_dir: Path | None = None,
):
    """
    Returns (settings, get_api_key, get_base_url, get_model,
              set_runtime, get_runtime_snapshot, persist_runtime_to_env).

    This is the primary entry-point for apps.  Example app config.py:

        from pathlib import Path
        from common.backend.config import make_runtime_helpers

        _ENV = Path(__file__).resolve().parents[1] / ".env"
        (
            settings,
            get_api_key, get_base_url, get_model,
            set_runtime, get_runtime_snapshot, persist_runtime_to_env,
        ) = make_runtime_helpers(env_file=_ENV, default_model="gpt-4.1-mini")
    """

    settings = make_settings(env_file=env_file, default_model=default_model, data_dir=data_dir)

    _runtime: dict = {}

    # -- Readers ---------------------------------------------------------------

    def get_api_key() -> str:
        return _runtime.get("openai_api_key", settings.openai_api_key)

    def get_base_url() -> str:
        return _runtime.get("openai_base_url", settings.openai_base_url)

    def get_model() -> str:
        return _runtime.get("openai_model", settings.openai_model)

    # -- Writer ----------------------------------------------------------------

    def set_runtime(key: str, base_url: str, model: str) -> None:
        """Apply in-process runtime overrides (lost on process restart)."""
        _runtime["openai_api_key"] = key.strip()
        _runtime["openai_base_url"] = base_url.strip().rstrip("/")
        _runtime["openai_model"] = model.strip()

    # -- Snapshot --------------------------------------------------------------

    def get_runtime_snapshot() -> dict:
        """Return a dict of all currently active settings values."""
        return {
            "openai_api_key": get_api_key(),
            "openai_base_url": get_base_url(),
            "openai_model": get_model(),
        }

    # -- Persist ---------------------------------------------------------------

    def persist_runtime_to_env() -> None:
        """
        Write the current runtime overrides back to the .env file so they
        survive a server restart.  Called automatically by PUT /api/config.
        """
        snap = get_runtime_snapshot()
        lines: list[str] = []
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()

        def _upsert(k: str, v: str) -> None:
            pattern = re.compile(rf"^{re.escape(k)}\s*=", re.IGNORECASE)
            for i, line in enumerate(lines):
                if pattern.match(line):
                    lines[i] = f"{k}={v}"
                    return
            lines.append(f"{k}={v}")

        _upsert("OPENAI_API_KEY", snap["openai_api_key"])
        _upsert("OPENAI_BASE_URL", snap["openai_base_url"])
        _upsert("OPENAI_MODEL", snap["openai_model"])
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return (
        settings,
        get_api_key,
        get_base_url,
        get_model,
        set_runtime,
        get_runtime_snapshot,
        persist_runtime_to_env,
    )