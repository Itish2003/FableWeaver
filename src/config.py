from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "FableWeaver"
    # Default to a local postgres database if not set in env
    database_url: str = "postgresql+asyncpg://localhost/fable"

    # Model configuration - can be overridden via environment variables
    model_storyteller: str = "gemini-2.5-flash"  # Main storytelling model
    model_archivist: str = "gemini-2.5-flash"    # World Bible state updates
    model_research: str = "gemini-2.5-flash"     # Research/Lore agents

    # Resilient client retry settings
    resilient_max_retries: int = 10
    resilient_base_delay: int = 2  # seconds, used with exponential backoff

    # API key cooldown after exhaustion
    key_cooldown_seconds: int = 60

    # Storyteller chapter length guidance
    chapter_min_words: int = 6000
    chapter_max_words: int = 8000

    # Max output tokens for the Storyteller LLM call (Gemini 2.5 Flash supports up to 65536).
    # Default 8192 is too low for 6000-8000 word chapters + JSON metadata.
    storyteller_max_output_tokens: int = 16384

    # Pipeline timeout in seconds (default 5 minutes)
    pipeline_timeout_seconds: int = 300

    # Heartbeat interval during generation (seconds)
    heartbeat_interval_seconds: int = 15

    # ADK session ID prefix for story sessions
    session_id_prefix: str = "session"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings():
    return Settings()

def make_session_id(story_id: str) -> str:
    """Build the ADK session ID for a given story."""
    settings = get_settings()
    return f"{settings.session_id_prefix}_{story_id}"
