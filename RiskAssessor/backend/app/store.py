"""
RiskAssessor/backend/app/store.py
──────────────────────────────────
Thin wrapper around the shared common.backend.store.SessionStore.
All generic logic lives in common/backend/store.py.
"""
from common.backend.store import SessionStore
from .config import settings
from .models import Session

_store = SessionStore(
    sessions_dir=settings.data_dir / "sessions",
    model_class=Session,
    list_fields=["versions"],
)


def save(s: Session) -> None:
    _store.save(s)


def load(sid: str) -> Session:
    return _store.load(sid)


def delete(sid: str) -> None:
    _store.delete(sid)


def list_all() -> list[dict]:
    return _store.list_all()
