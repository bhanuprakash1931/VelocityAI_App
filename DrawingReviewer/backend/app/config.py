"""
DrawingReviewer/backend/app/config.py
───────────────────────────────────────
Thin wrapper around the shared common.backend.config module.
All logic lives in common/backend/config.py.
"""
import sys
from pathlib import Path

# ── Ensure repo root is on sys.path so `common` package is importable ─────
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from common.backend.config import make_runtime_helpers  # noqa: E402

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

(
    settings,
    get_api_key,
    get_base_url,
    get_model,
    set_runtime,
    get_runtime_snapshot,
    persist_runtime_to_env,
) = make_runtime_helpers(
    env_file=_ENV_FILE,
    default_model="gpt-4o",
)
