"""WebSocket action dispatch table and result type."""

from __future__ import annotations

import dataclasses
from typing import Callable, Awaitable

from src.ws.context import WsSessionContext


@dataclasses.dataclass
class ActionResult:
    """Returned by each action handler.

    If ``needs_runner`` is True, the main loop calls ``run_pipeline(ctx)``
    after the handler returns.  Otherwise the handler handled everything
    inline (sent ``turn_complete``, etc.) and the loop continues.
    """
    needs_runner: bool = False


# Type alias for action handler signatures
ActionHandler = Callable[[WsSessionContext, dict], Awaitable[ActionResult]]


def get_action_dispatch() -> dict[str, ActionHandler]:
    """Build and return the action → handler dispatch table.

    Imports are deferred to avoid circular-import issues and to keep this
    module lightweight at import time.
    """
    from src.ws.actions.init import handle_init
    from src.ws.actions.choice import handle_choice
    from src.ws.actions.rewrite import handle_rewrite
    from src.ws.actions.research import handle_research
    from src.ws.actions.enrich import handle_enrich
    from src.ws.actions.undo import handle_undo
    from src.ws.actions.reset import handle_reset
    from src.ws.actions.bible_diff import handle_bible_diff
    from src.ws.actions.bible_snapshot import handle_bible_snapshot

    return {
        "init": handle_init,
        "choice": handle_choice,
        "rewrite": handle_rewrite,
        "research": handle_research,
        "enrich": handle_enrich,
        "undo": handle_undo,
        "reset": handle_reset,
        "bible-diff": handle_bible_diff,
        "bible-snapshot": handle_bible_snapshot,
    }
