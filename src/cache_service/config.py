"""Service configuration, read from environment variables (prefix ``CACHE_``)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CACHE_", env_file=".env", extra="ignore")

    # SQLite keeps local runs dependency-free; Docker Compose points this at PostgreSQL.
    database_url: str = "sqlite:///./cache.db"
    # Artificial latency of the transformer, so the benefit of caching is observable.
    transformer_delay_seconds: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
