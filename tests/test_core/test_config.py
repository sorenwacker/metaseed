"""Tests for metaseed.core.config."""

import os
from unittest.mock import patch

from metaseed.core.config import Settings, get_settings


class TestSettings:
    """Test Settings class."""

    def test_default_values(self):
        """Settings have expected default values."""
        settings = Settings()
        assert settings.default_version == "1.1"
        assert settings.debug is False
        assert settings.log_level == "INFO"

    def test_env_prefix(self):
        """Settings respect METASEED_ environment prefix."""
        with patch.dict(os.environ, {"METASEED_DEBUG": "true"}):
            settings = Settings()
            assert settings.debug is True

    def test_env_version_override(self):
        """Default version can be overridden via environment."""
        with patch.dict(os.environ, {"METASEED_DEFAULT_VERSION": "1.2"}):
            settings = Settings()
            assert settings.default_version == "1.2"

    def test_env_log_level_override(self):
        """Log level can be overridden via environment."""
        with patch.dict(os.environ, {"METASEED_LOG_LEVEL": "DEBUG"}):
            settings = Settings()
            assert settings.log_level == "DEBUG"

    def test_case_insensitive_env_vars(self):
        """Environment variables are case insensitive."""
        with patch.dict(os.environ, {"metaseed_debug": "true"}):
            settings = Settings()
            assert settings.debug is True


class TestGetSettings:
    """Test get_settings function."""

    def test_returns_settings_instance(self):
        """get_settings returns a Settings instance."""
        get_settings.cache_clear()
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_returns_cached_instance(self):
        """get_settings returns the same cached instance."""
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
