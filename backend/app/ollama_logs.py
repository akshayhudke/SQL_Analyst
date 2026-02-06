"""Keep a tiny in-memory log of LLM activity for the UI."""

from collections import deque
from datetime import datetime
from typing import Any, Dict, List

_LOGS: deque[Dict[str, Any]] = deque(maxlen=200)


def log_event(level: str, message: str, meta: Dict[str, Any] | None = None) -> None:
    """Add one log entry to the ring buffer."""
    _LOGS.append(
        {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": level.upper(),
            "message": message,
            "meta": meta or {},
        }
    )


def get_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Return the newest log entries (up to the limit)."""
    items = list(_LOGS)
    if limit <= 0:
        return []
    return items[-limit:]
