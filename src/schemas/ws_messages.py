"""
WebSocket message validation schemas.

Every inbound WS message must match the ``WsMessage`` envelope.
After the ``action`` field is resolved (including slash-command re-routing),
the ``payload`` dict is validated against the action-specific model via
``validate_ws_payload()``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard limits
# ---------------------------------------------------------------------------
MAX_MESSAGE_BYTES = 65_536  # 64 KB — reject raw text before JSON parsing

# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------
VALID_ACTIONS = frozenset({
    "init", "choice", "rewrite", "research", "enrich",
    "undo", "reset", "bible-diff", "bible-snapshot",
})


class WsMessage(BaseModel):
    """Top-level WebSocket message envelope."""
    action: str = Field(..., description="Action to perform")
    payload: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-action payloads
# ---------------------------------------------------------------------------

class InitPayload(BaseModel):
    universes: List[str] = Field(default_factory=lambda: ["General"], max_length=20)
    timeline_deviation: str = Field(default="", max_length=100_000)
    user_input: str = Field(default="", max_length=100_000)
    genre: str = Field(default="Fantasy", max_length=200)
    theme: str = Field(default="Mystery", max_length=200)


class ChoicePayload(BaseModel):
    choice: str = Field(default="", max_length=100_000)
    question_answers: Dict[str, str] = Field(default_factory=dict)


class RewritePayload(BaseModel):
    instruction: str = Field(default="", max_length=5000)


class ResearchPayload(BaseModel):
    query: str = Field(default="", max_length=2000)
    depth: Literal["quick", "deep"] = "quick"


class EnrichPayload(BaseModel):
    focuses: List[str] = Field(default_factory=lambda: ["all"], max_length=20)


class SnapshotPayload(BaseModel):
    subcommand: Literal["save", "load", "list", "delete"] = "list"
    snapshot_name: Optional[str] = Field(default=None, max_length=200)


# No payload needed for: undo, reset, bible-diff
class EmptyPayload(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------
_ACTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "init": InitPayload,
    "choice": ChoicePayload,
    "rewrite": RewritePayload,
    "research": ResearchPayload,
    "enrich": EnrichPayload,
    "undo": EmptyPayload,
    "reset": EmptyPayload,
    "bible-diff": EmptyPayload,
    "bible-snapshot": SnapshotPayload,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_ws_payload(action: str, raw_payload: dict) -> tuple[bool, dict | str]:
    """
    Validate *raw_payload* against the schema for *action*.

    Returns ``(True, validated_dict)`` on success or
    ``(False, error_message)`` on failure.
    """
    schema = _ACTION_SCHEMAS.get(action)
    if schema is None:
        return False, f"Unknown action: {action}"

    try:
        model = schema(**raw_payload)
        return True, model.model_dump()
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        logger.info("ws_validation_failed | action=%s | errors=%s", action, errors)
        return False, f"Invalid payload for '{action}': {errors}"
