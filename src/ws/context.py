"""Per-connection shared state for WebSocket action handlers."""

from __future__ import annotations

import dataclasses
from typing import Any

from fastapi import WebSocket


@dataclasses.dataclass
class WsSessionContext:
    """Bundles all per-connection state that action handlers need.

    Created once per WebSocket connection in ``handler.py`` and passed to
    every action handler + the runner.
    """
    websocket: WebSocket
    story_id: str
    user_id: str
    agent_session_id: str
    session_service: Any            # DatabaseSessionService
    memory_service: Any             # InMemoryMemoryService
    artifact_service: Any           # InMemoryArtifactService
    active_agent: Any = None        # set by init/choice/rewrite handlers
    input_text: str = ""            # set by init/choice/rewrite handlers
    bible_snapshot_content: dict | None = None  # set by choice/rewrite handlers
    action: str = ""                # current action name
