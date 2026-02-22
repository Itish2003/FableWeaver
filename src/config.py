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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings():
    return Settings()
