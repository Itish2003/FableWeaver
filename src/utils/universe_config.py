"""
Universe configuration loader.

Loads universe-specific settings (wiki hints, leakage terms) from
src/data/universe_config.json at import time. Results are cached so
the file is read only once per process.

Adding a new universe requires only editing the JSON file — no code changes.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "universe_config.json"


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    """Read and parse the JSON config once; cache the result."""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(
            "universe_config.json not found at %s; using empty config", _CONFIG_PATH
        )
        return {"universes": {}}
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse universe_config.json: %s", exc)
        return {"universes": {}}


def get_universe_config() -> dict:
    """Return the full parsed config dict."""
    return _load_raw()


def get_all_leakage_terms() -> Dict[str, List[str]]:
    """
    Return a mapping of {category_key: [terms]} for every universe that has
    leakage terms defined.  Empty-term universes are omitted.
    """
    universes = _load_raw().get("universes", {})
    return {
        key: cfg["leakage_terms"]
        for key, cfg in universes.items()
        if cfg.get("leakage_terms")
    }


def get_source_text_hints(universe_name: str) -> Optional[dict]:
    """
    Return the ``source_text_hints`` dict for *universe_name*, or ``None``
    if the universe has no source text configuration.
    """
    universes = _load_raw().get("universes", {})
    name_lower = universe_name.lower()
    for cfg in universes.values():
        for display in cfg.get("display_names", []):
            if display.lower() in name_lower or name_lower in display.lower():
                return cfg.get("source_text_hints")
    return None


def get_wiki_hint(universe_name: str) -> Optional[str]:
    """
    Return the ``site:`` search hint for *universe_name*, or ``None`` if
    the universe is unknown or has no hint configured.

    Matching is case-insensitive against each universe's ``display_names``
    list.
    """
    universes = _load_raw().get("universes", {})
    name_lower = universe_name.lower()
    for cfg in universes.values():
        for display in cfg.get("display_names", []):
            if display.lower() in name_lower or name_lower in display.lower():
                url = cfg.get("wiki_url")
                return url  # may be None if not configured
    return None
