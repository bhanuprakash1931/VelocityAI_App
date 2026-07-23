import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    cors_origins: str = "*"
    max_upload_mb: int = 25
    data_dir: Path = Path(__file__).parent.parent / "data"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Runtime overrides (set via /api/config PUT)
_runtime: dict = {}

def get_api_key() -> str:
    return _runtime.get("openai_api_key") or settings.openai_api_key

def get_base_url() -> str:
    return _runtime.get("openai_base_url") or settings.openai_base_url

def get_model() -> str:
    return _runtime.get("openai_model") or settings.openai_model

def set_runtime(key: str, url: str, model: str):
    _runtime["openai_api_key"] = key
    _runtime["openai_base_url"] = url
    _runtime["openai_model"] = model
    # Persist to .env so they survive restarts
    env_path = Path(__file__).parent.parent / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    def _set(lines, k, v):
        for i, l in enumerate(lines):
            if l.startswith(f"{k}="):
                lines[i] = f"{k}={v}"
                return
        lines.append(f"{k}={v}")
    _set(lines, "OPENAI_API_KEY", key)
    _set(lines, "OPENAI_BASE_URL", url)
    _set(lines, "OPENAI_MODEL", model)
    env_path.write_text("\n".join(lines) + "\n")