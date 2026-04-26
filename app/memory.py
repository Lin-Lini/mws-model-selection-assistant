from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock

from app.models import CatalogSnapshot, Scenario


@dataclass(slots=True)
class SessionState:
    scenario: Scenario = field(default_factory=Scenario)
    catalog: CatalogSnapshot | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionState] = {}
        self._lock = Lock()

    def get(self, session_id: str) -> SessionState | None:
        with self._lock:
            self._cleanup_locked()
            state = self._sessions.get(session_id)
            if state is not None:
                state.updated_at = datetime.now(timezone.utc)
            return state

    def get_or_create(self, session_id: str) -> SessionState:
        with self._lock:
            self._cleanup_locked()
            state = self._sessions.get(session_id)
            if state is None:
                state = SessionState()
                self._sessions[session_id] = state
            state.updated_at = datetime.now(timezone.utc)
            return state

    def _cleanup_locked(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            key
            for key, value in self._sessions.items()
            if now - value.updated_at > timedelta(seconds=self.ttl_seconds)
        ]
        for key in expired:
            self._sessions.pop(key, None)
