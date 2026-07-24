"""
common/backend/store.py
────────────────────────
Generic JSON-based session store shared by all Velocity AI applications.

Usage in an app's store.py:

    from common.backend.store import SessionStore
    from .config import settings
    from .models import Session

    _store = SessionStore(
        sessions_dir=settings.data_dir / "sessions",
        model_class=Session,
    )

    # Then expose module-level functions to keep existing import contracts:
    def save(s: Session) -> None:          _store.save(s)
    def load(sid: str) -> Session:         return _store.load(sid)
    def delete(sid: str) -> None:          _store.delete(sid)
    def list_all() -> list[dict]:          return _store.list_all()
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Generic, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class SessionStore(Generic[T]):
    """
    Thread-safe JSON file-based session store.

    Parameters
    ----------
    sessions_dir : Directory where session JSON files are written.
    model_class  : The Pydantic model class used to validate/deserialize files.
    list_fields  : Optional list of field names to include in list_all() output
                   in addition to 'id' and 'title'. E.g. ['versions', 'analysis_done'].
    """

    def __init__(
        self,
        sessions_dir: Path,
        model_class: Type[T],
        list_fields: list[str] | None = None,
    ) -> None:
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._model = model_class
        self._list_fields: list[str] = list_fields or []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Path helper
    # ------------------------------------------------------------------

    def _path(self, sid: str) -> Path:
        return self._dir / f"{sid}.json"

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def save(self, session: T) -> None:
        """Atomically write a session to disk as pretty-printed JSON."""
        with self._lock:
            self._path(session.id).write_text(  # type: ignore[attr-defined]
                session.model_dump_json(indent=2),
                encoding="utf-8",
            )

    def load(self, sid: str) -> T:
        """
        Load and validate a session from disk.

        Raises FileNotFoundError if the session does not exist.
        """
        p = self._path(sid)
        if not p.exists():
            raise FileNotFoundError(sid)
        return self._model.model_validate_json(p.read_text(encoding="utf-8"))

    def delete(self, sid: str) -> None:
        """Delete a session file. No-op if it does not exist."""
        self._path(sid).unlink(missing_ok=True)

    def list_all(self) -> list[dict]:
        """
        Return a lightweight list of all sessions sorted by last-modified time
        (newest first).

        Each dict always contains 'id' and 'title', plus any fields named in
        self._list_fields (e.g. 'versions', 'analysis_done').
        """
        out: list[dict] = []
        for p in sorted(
            self._dir.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        ):
            try:
                s = self._model.model_validate_json(p.read_text(encoding="utf-8"))
                entry: dict[str, Any] = {
                    "id": s.id,           # type: ignore[attr-defined]
                    "title": s.title,     # type: ignore[attr-defined]
                }
                for field in self._list_fields:
                    val = getattr(s, field, None)
                    # For list fields (e.g. versions), expose the count
                    if isinstance(val, list):
                        entry[field] = len(val)
                    else:
                        entry[field] = val
                out.append(entry)
            except Exception:
                pass  # Skip corrupt / incompatible session files
        return out
