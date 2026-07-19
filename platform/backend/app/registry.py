"""Static app registry — defines all apps available on the platform.

Each entry describes an application card shown on the platform landing page.
To add a new app: add one entry to APPS and one entry to APP_PROCESS_CONFIG.
"""
from .config import settings

# ---------------------------------------------------------------------------
# Process launch config — used by process_manager.py to start app backends
# ---------------------------------------------------------------------------
# backend_dir : path relative to the monorepo root
# module      : uvicorn app module string (e.g. "app.main:app")
# port        : port the backend will listen on
APP_PROCESS_CONFIG: list[dict] = [
    {
        "id": "requirements-generator",
        "backend_dir": "RequirementsGenerator/backend",
        "module": "app.main:app",
        "port": 8000,
        "frontend_dir": "RequirementsGenerator/frontend",
        "frontend_port": 5173,
        # VITE_API_URL: empty means use Vite proxy (proxies /api → localhost:8000)
        "frontend_env": {},
    },
    {
        "id": "risk-assessor",
        "backend_dir": "RiskAssessor/backend",
        "module": "app.main:app",
        "port": 8001,
        "frontend_dir": "RiskAssessor/frontend",
        "frontend_port": 5174,
        # VITE_API_URL bypasses Vite proxy → hits RiskAssessor backend on 8001 directly
        "frontend_env": {"VITE_API_URL": "http://localhost:8001"},
    },
]

# ---------------------------------------------------------------------------
# UI card registry — used by the platform frontend
# ---------------------------------------------------------------------------
APPS: list[dict] = [
    {
        "id": "requirements-generator",
        "name": "Requirements Generator",
        "tagline": "AI-powered requirements engineering",
        "description": (
            "Transform stakeholder needs into structured, traceable requirement "
            "specifications. Supports custom Excel templates, DFMEA/FMEA tables, "
            "version history, XLSX export, and a Mermaid traceability diagram."
        ),
        "icon": "📋",
        "color": "#0070ad",
        "frontend_url_key": "req_gen_frontend_url",
        "backend_url_key": "req_gen_backend_url",
        "tags": ["Requirements", "DFMEA", "FMEA", "Excel", "AI"],
        "status": "live",
    },
    {
        "id": "risk-assessor",
        "name": "Risk Assessor",
        "tagline": "AI-powered risk register generation",
        "description": (
            "Generate comprehensive risk registers from project context. Covers "
            "Strategic, Operational, Financial, Compliance, Safety, Security, "
            "Technology and more. Includes a Likelihood × Impact heatmap, "
            "category breakdown, action panel, and XLSX export."
        ),
        "icon": "🛡️",
        "color": "#c0392b",
        "frontend_url_key": "risk_assessor_frontend_url",
        "backend_url_key": "risk_assessor_backend_url",
        "tags": ["Risk", "FMEA", "Heatmap", "Excel", "AI"],
        "status": "live",
    },
]


def get_apps() -> list[dict]:
    """Return the registry with runtime URLs resolved from settings."""
    result = []
    for app in APPS:
        entry = dict(app)
        entry["frontend_url"] = getattr(settings, app["frontend_url_key"], "")
        entry["backend_url"] = getattr(settings, app["backend_url_key"], "")
        # Remove the key references — they are internal implementation details
        entry.pop("frontend_url_key", None)
        entry.pop("backend_url_key", None)
        result.append(entry)
    return result