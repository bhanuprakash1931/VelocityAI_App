import json
from pathlib import Path
from .models import Session
from .config import settings


def _path(sid: str) -> Path:
    d = settings.data_dir / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sid}.json"


def save(s: Session) -> None:
    _path(s.id).write_text(s.model_dump_json(indent=2), encoding="utf-8")


def load(sid: str) -> Session:
    p = _path(sid)
    if not p.exists():
        raise FileNotFoundError(sid)
    return Session.model_validate_json(p.read_text(encoding="utf-8"))


def delete(sid: str) -> None:
    p = _path(sid)
    if p.exists():
        p.unlink()


def list_all() -> list[dict]:
    d = settings.data_dir / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            s = Session.model_validate_json(p.read_text(encoding="utf-8"))
            out.append({"id": s.id, "title": s.title, "created_at": s.created_at,
                        "analysis_done": s.analysis_done, "report_done": s.report_done})
        except Exception:
            pass
    return out