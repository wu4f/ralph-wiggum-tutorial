"""Short-lived storage for repository analysis snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4


JSONDict = dict[str, Any]


@dataclass(frozen=True)
class AnalysisSnapshot:
    """Server-side snapshot used for learner-safe payloads and scoring."""

    analysis_id: str
    learner_payload: JSONDict
    answer_keys: JSONDict
    created_at: datetime
    expires_at: datetime


class AnalysisStore:
    """In-memory snapshot store with TTL-based eviction."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._snapshots: dict[str, AnalysisSnapshot] = {}
        self._lock = Lock()

    def save(self, learner_payload: JSONDict, answer_keys: JSONDict) -> AnalysisSnapshot:
        """Persist a new snapshot and return the stored record."""
        now = datetime.now(UTC)
        snapshot = AnalysisSnapshot(
            analysis_id=uuid4().hex,
            learner_payload=learner_payload,
            answer_keys=answer_keys,
            created_at=now,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        with self._lock:
            self._cleanup_locked(now)
            self._snapshots[snapshot.analysis_id] = snapshot
        return snapshot

    def get(self, analysis_id: str) -> AnalysisSnapshot | None:
        """Return a snapshot if it exists and has not expired."""
        now = datetime.now(UTC)
        with self._lock:
            self._cleanup_locked(now)
            return self._snapshots.get(analysis_id)

    def _cleanup_locked(self, now: datetime) -> None:
        expired_ids = [
            analysis_id
            for analysis_id, snapshot in self._snapshots.items()
            if snapshot.expires_at <= now
        ]
        for analysis_id in expired_ids:
            del self._snapshots[analysis_id]
