"""
ResilientGemini — drop-in replacement for ``google.adk.models.google_llm.Gemini``
that uses :class:`ResilientClient` for automatic 429/503 retry and API-key rotation.

Usage in agent factories::

    from src.utils.resilient_gemini import ResilientGemini

    agent = Agent(
        model=ResilientGemini(model="gemini-2.5-flash"),
        ...
    )

This eliminates the need for:
- Global monkey-patching of ``google.genai.Client``
- Setting ``os.environ["GOOGLE_API_KEY"]`` during agent construction
"""
from functools import cached_property

from google.adk.models.google_llm import Gemini
from google.genai import Client, types

from src.utils.resilient_client import ResilientClient


class ResilientGemini(Gemini):
    """Gemini with built-in rate-limit resilience.

    Overrides the ``api_client`` and ``_live_api_client`` cached properties
    so that every LLM call goes through :class:`ResilientClient`, which
    handles 429/503 retries and API-key rotation internally.
    """

    @cached_property
    def api_client(self) -> Client:
        return ResilientClient(
            http_options=types.HttpOptions(
                headers=self._tracking_headers,
                retry_options=self.retry_options,
            ),
        )

    @cached_property
    def _live_api_client(self) -> Client:
        return ResilientClient(
            http_options=types.HttpOptions(
                headers=self._tracking_headers,
                api_version=self._live_api_version,
            ),
        )
