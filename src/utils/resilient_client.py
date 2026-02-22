import asyncio
import logging
import time

from google.genai import Client as GenAIClient

from src.utils.auth import get_api_key, mark_key_exhausted
from src.config import get_settings

logger = logging.getLogger("fable.resilient_client")

class ResilientClient(GenAIClient):
    """
    A subclass of google.genai.Client that intercepts 429 errors
    and automatically rotates the API key.
    """
    def __init__(self, api_key=None, http_options=None, **kwargs):
        # Store initial key to track it
        self._current_key = api_key or get_api_key()
        super().__init__(api_key=self._current_key, http_options=http_options, **kwargs)
        
        # Internal state
        self._kwargs = kwargs
        self._http_options = http_options
        self._active_client = GenAIClient(api_key=self._current_key, http_options=http_options, **kwargs)
        
        # Proxies
        self._aio_proxy = AioProxy(self)

    @property
    def aio(self):
        return self._aio_proxy

    def rotate(self):
        # Mark the current key as exhausted before getting a new one
        mark_key_exhausted(self._current_key)
        
        logger.info("Rotating API key. Old key: %s...", self._current_key[:8])
        self._current_key = get_api_key()
        self._active_client = GenAIClient(api_key=self._current_key, http_options=self._http_options, **self._kwargs)

class AioProxy:
    def __init__(self, parent: ResilientClient):
        self._parent = parent
        self._models_proxy = ModelsProxy(parent)
        self._live_proxy = LiveProxy(parent)

    @property
    def models(self):
        return self._models_proxy
        
    @property
    def live(self):
        return self._live_proxy

class ModelsProxy:
    def __init__(self, parent: ResilientClient):
        self._parent = parent

    def __getattr__(self, name):
        # We intercept method access to wrap them with retry logic
        # But we need to know valid methods.
        # Default to checking active client.
        real_method = getattr(self._parent._active_client.aio.models, name)
        
        if callable(real_method):
            return self._create_wrapper(name)
        return real_method

    def _sanitize_request_arguments(self, kwargs):
        """
        Strips invalid or empty parts from 'contents' to prevent 400 INVALID_ARGUMENT errors.
        Specifically handles the 'required oneof field data must have one initialized field' error.
        """
        contents = kwargs.get("contents")
        if not contents:
            return kwargs

        # Skip sanitization if contents is a raw string (SDK handles it internally)
        if isinstance(contents, str):
            return kwargs

        new_contents = []
        # Fields that constitute valid data in a Part
        DATA_FIELDS = [
            'text', 'inline_data', 'function_call', 'function_response', 
            'file_data', 'executable_code', 'code_execution_result'
        ]

        total_parts_before = 0
        total_parts_after = 0

        for content in contents:
            is_dict = isinstance(content, dict)
            parts = content.get("parts", []) if is_dict else getattr(content, "parts", [])
            total_parts_before += len(parts)
            
            new_parts = []
            for part in parts:
                is_part_dict = isinstance(part, dict)
                # Check if ANY valid data field is present and non-empty
                has_data = False
                for field in DATA_FIELDS:
                    val = part.get(field) if is_part_dict else getattr(part, field, None)
                    if val is not None:
                        # Special handling for text: must be non-empty string
                        if field == 'text':
                            if isinstance(val, str) and val.strip():
                                has_data = True
                                break
                        else:
                            # For other fields, presence is usually enough, 
                            # but we could be more strict if needed.
                            has_data = True
                            break
                
                if has_data:
                    new_parts.append(part)
            
            total_parts_after += len(new_parts)
            if new_parts:
                if is_dict:
                    content["parts"] = new_parts
                else:
                    content.parts = new_parts
                new_contents.append(content)
            # If a Content has NO parts, we discard it entirely 
            # (Gemini doesn't allow empty contents in history)

        if total_parts_before != total_parts_after:
            logger.debug("Sanitization: stripped %d empty parts (%d -> %d)", total_parts_before - total_parts_after, total_parts_before, total_parts_after)
        
        kwargs["contents"] = new_contents
        return kwargs

    def _create_wrapper(self, method_name):
        async def wrapper(*args, **kwargs):
            # Sanitize history for generation methods
            if method_name in ["generate_content", "generate_content_stream"]:
                kwargs = self._sanitize_request_arguments(kwargs)
                
            settings = get_settings()
            retries = settings.resilient_max_retries
            base_delay = settings.resilient_base_delay
            for attempt in range(retries):
                try:
                    # Always get the FRESH method from active client
                    current_client = self._parent._active_client
                    method = getattr(current_client.aio.models, method_name)
                    return await method(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).upper()
                    # Retry on rate limits (429) OR server overload (503)
                    is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
                    is_server_overload = "503" in error_str or "UNAVAILABLE" in error_str

                    if is_rate_limit or is_server_overload:
                        delay = base_delay * (2 ** attempt)
                        error_type = "429 Rate Limit" if is_rate_limit else "503 Server Overload"
                        logger.warning("%s for %s. Attempt %d/%d. Backoff: %ds", error_type, method_name, attempt + 1, retries, delay)
                        if is_rate_limit:
                            self._parent.rotate()  # Only rotate keys on rate limit, not overload
                        await asyncio.sleep(delay)
                        continue
                    raise e
            raise Exception("ResilientClient: Exhausted all retries.")
        return wrapper

class LiveProxy:
    def __init__(self, parent: ResilientClient):
        self._parent = parent
    
    def __getattr__(self, name):
        # Same logic for live (e.g. connect)
        real_method = getattr(self._parent._active_client.aio.live, name)
        if callable(real_method):
            return self._create_wrapper(name)
        return real_method

    def _create_wrapper(self, method_name):
        # Note: live.connect is an async context manager usually? 
        # "async with client.aio.live.connect..."
        # Wrappers for async context managers are tricky.
        # But ADK might just await it?
        # Check usage in google_llm.py: "async with ...connect() as session"
        # So we need to return an AsyncContextManager that handles retries inside __aenter__?
        # Retrying a connection is doable.
        
        from contextlib import asynccontextmanager
        
        @asynccontextmanager
        async def wrapper(*args, **kwargs):
             # We can try to connect. If fails 429, rotate and try again.
            settings = get_settings()
            retries = settings.resilient_max_retries
            for attempt in range(retries):
                try:
                    current_client = self._parent._active_client
                    method = getattr(current_client.aio.live, method_name)
                    async with method(*args, **kwargs) as session:
                        yield session
                    return # Exit after yield handled
                except Exception as e:
                    error_str = str(e).upper()
                    # Retry on rate limits (429) OR server overload (503)
                    is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
                    is_server_overload = "503" in error_str or "UNAVAILABLE" in error_str

                    if is_rate_limit or is_server_overload:
                        error_type = "429 Rate Limit" if is_rate_limit else "503 Server Overload"
                        logger.warning("%s - Retry %d/%d for Live Connect", error_type, attempt + 1, retries)
                        if is_rate_limit:
                            self._parent.rotate()
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise e
            raise Exception("ResilientClient: Live Connect exhausted.")
            
        return wrapper
