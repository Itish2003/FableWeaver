"""Legacy logger shim.

Wraps the stdlib logger so that existing ``logger.log(type, msg, meta)``
call-sites keep working while we migrate incrementally to structured logging.
"""

from src.utils.logging_config import get_logger

_logger = get_logger("fable.main")


class _LegacyLoggerShim:
    """Thin shim so existing ``logger.log(type, msg, meta)`` calls keep working
    while we migrate them to stdlib calls incrementally."""
    def log(self, event_type: str, message: str, metadata=None):
        _logger.info(message, extra={"event_type": event_type, "metadata": metadata})


logger = _LegacyLoggerShim()
