from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Platform-level .env lives at platform/backend/.env
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    # Shared LLM config — written here and can be pushed to app backends
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"

    # Platform server
    cors_origins: str = "*"
    platform_port: int = 7000

    # App backend URLs (used for health checks and config push)
    req_gen_backend_url: str = "http://localhost:8000"
    risk_assessor_backend_url: str = "http://localhost:8001"

    # App frontend URLs (used for launch links)
    req_gen_frontend_url: str = "http://localhost:5173"
    risk_assessor_frontend_url: str = "http://localhost:5174"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# ---------------------------------------------------------------------------
# Runtime overrides (in-process, survive until restart)
# ---------------------------------------------------------------------------
_runtime: dict = {}


def get_api_key() -> str:
    return _runtime.get("openai_api_key", settings.openai_api_key)


def get_base_url() -> str:
    return _runtime.get("openai_base_url", settings.openai_base_url)


def get_model() -> str:
    return _runtime.get("openai_model", settings.openai_model)


def set_runtime(key: str, base_url: str, model: str) -> None:
    _runtime["openai_api_key"] = key.strip()
    _runtime["openai_base_url"] = base_url.strip().rstrip("/")
    _runtime["openai_model"] = model.strip()


def get_runtime_snapshot() -> dict:
    return {
        "openai_api_key": get_api_key(),
        "openai_base_url": get_base_url(),
        "openai_model": get_model(),
    }


def persist_runtime_to_env() -> None:
    """Write current runtime overrides back to platform .env so they survive restart."""
    import re

    snap = get_runtime_snapshot()
    lines: list[str] = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text(encoding="utf-8").splitlines()

    def _upsert(key: str, value: str) -> None:
        pattern = re.compile(rf"^{re.escape(key)}\s*=", re.IGNORECASE)
        for i, line in enumerate(lines):
            if pattern.match(line):
                lines[i] = f"{key}={value}"
                return
        lines.append(f"{key}={value}")

    _upsert("OPENAI_API_KEY", snap["openai_api_key"])
    _upsert("OPENAI_BASE_URL", snap["openai_base_url"])
    _upsert("OPENAI_MODEL", snap["openai_model"])
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")