"""Configuration for Metaseed.

This module provides configuration settings using pydantic-settings.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Settings can be configured via environment variables with the
    METASEED_ prefix.

    Attributes:
        default_version: Default MIAPPE version for operations.
        debug: Enable debug mode.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """

    model_config = SettingsConfigDict(
        env_prefix="METASEED_",
        case_sensitive=False,
    )

    default_version: str = "1.2"
    debug: bool = False
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings instance (cached).
    """
    return Settings()
