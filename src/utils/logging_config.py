"""
Structured JSON logging configuration for FableWeaver.

Replaces the hand-rolled ``FileLogger`` with Python's stdlib ``logging``
module.  All log records are emitted as single-line JSON objects to both
``server.log`` and stderr.

Usage::

    from src.utils.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("chapter generated", extra={"story_id": sid, "chapter": 5})

For WebSocket handlers that need story-scoped context on every message::

    from src.utils.logging_config import get_logger, StoryAdapter

    raw = get_logger("fable.ws")
    logger = StoryAdapter(raw, story_id="abc-123")
    logger.info("turn started")        # automatically includes story_id
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, MutableMapping


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Emits each record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge extra fields (story_id, event_type, etc.)
        for key in ("story_id", "event_type", "agent", "action",
                     "duration_ms", "trace_id", "metadata"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


# ---------------------------------------------------------------------------
# StoryAdapter — attaches story_id to every log call
# ---------------------------------------------------------------------------

class StoryAdapter(logging.LoggerAdapter):
    """Logger adapter that injects ``story_id`` into every record."""

    def __init__(self, logger: logging.Logger, story_id: str):
        super().__init__(logger, {"story_id": story_id})

    def process(
        self,
        msg: str,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[str, MutableMapping[str, Any]]:
        extra = kwargs.setdefault("extra", {})
        extra.update(self.extra)
        return msg, kwargs


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_CONFIGURED = False


def setup_logging(log_file: str = "server.log", level: int = logging.INFO) -> None:
    """Configure the root ``fable`` logger with JSON handlers.

    Safe to call multiple times — only the first call has effect.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    root = logging.getLogger("fable")
    root.setLevel(level)
    root.propagate = False

    formatter = JSONFormatter()

    # File handler — append to server.log (same location as old FileLogger)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Stderr handler — for docker / systemd journal visibility
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(formatter)
    sh.setLevel(logging.WARNING)
    root.addHandler(sh)


def get_logger(name: str = "fable") -> logging.Logger:
    """Return a child logger under the ``fable`` namespace.

    Automatically calls :func:`setup_logging` on first use.
    """
    setup_logging()
    if name.startswith("fable"):
        return logging.getLogger(name)
    return logging.getLogger(f"fable.{name}")
