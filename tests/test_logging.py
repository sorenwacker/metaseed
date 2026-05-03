"""Tests for logging configuration.

These tests verify the documented logging behavior.
"""

import io
import logging

from metaseed.logging import configure_logging, get_logger


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def teardown_method(self) -> None:
        """Reset logging after each test."""
        root_logger = logging.getLogger("metaseed")
        root_logger.handlers.clear()
        root_logger.setLevel(logging.WARNING)

    def test_default_level_is_warning(self) -> None:
        """Default log level is WARNING."""
        configure_logging()
        logger = logging.getLogger("metaseed")
        assert logger.level == logging.WARNING

    def test_debug_level(self) -> None:
        """Can set DEBUG level."""
        configure_logging(level="DEBUG")
        logger = logging.getLogger("metaseed")
        assert logger.level == logging.DEBUG

    def test_info_level(self) -> None:
        """Can set INFO level."""
        configure_logging(level="INFO")
        logger = logging.getLogger("metaseed")
        assert logger.level == logging.INFO

    def test_custom_stream(self) -> None:
        """Can set custom output stream."""
        stream = io.StringIO()
        configure_logging(level="INFO", stream=stream)
        logger = logging.getLogger("metaseed.test")
        logger.info("test message")
        output = stream.getvalue()
        assert "test message" in output

    def test_cli_mode_format(self) -> None:
        """CLI mode uses compact format."""
        stream = io.StringIO()
        configure_logging(level="INFO", stream=stream, cli_mode=True)
        logger = logging.getLogger("metaseed.test")
        logger.info("test message")
        output = stream.getvalue()
        assert output.startswith("INFO:")
        assert "test message" in output

    def test_standard_format(self) -> None:
        """Standard mode includes timestamp and module."""
        stream = io.StringIO()
        configure_logging(level="INFO", stream=stream, cli_mode=False)
        logger = logging.getLogger("metaseed.test")
        logger.info("test message")
        output = stream.getvalue()
        assert "metaseed.test" in output
        assert "test message" in output

    def test_integer_level(self) -> None:
        """Can use integer log level."""
        configure_logging(level=logging.DEBUG)
        logger = logging.getLogger("metaseed")
        assert logger.level == logging.DEBUG


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_logger(self) -> None:
        """Returns a logger instance."""
        logger = get_logger("metaseed.test")
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self) -> None:
        """Logger has correct name."""
        logger = get_logger("metaseed.test.module")
        assert logger.name == "metaseed.test.module"


class TestModuleLoggers:
    """Tests that modules use proper logging."""

    def test_comparator_has_logger(self) -> None:
        """Comparator module has logger."""
        from metaseed.specs.merge import comparator

        assert hasattr(comparator, "logger")

    def test_merger_has_logger(self) -> None:
        """Merger module has logger."""
        from metaseed.specs.merge import merger

        assert hasattr(merger, "logger")

    def test_loader_has_logger(self) -> None:
        """Loader module has logger."""
        from metaseed.specs import loader

        assert hasattr(loader, "logger")
