"""Tests for metaseed.core.exceptions."""

import pytest

from metaseed.core.exceptions import (
    MiappeError,
    ModelError,
    SpecError,
    StorageIOError,
    ValidationFailedError,
)


class TestExceptionHierarchy:
    """Test exception class hierarchy."""

    def test_miappe_error_is_base_exception(self):
        """MiappeError inherits from Exception."""
        assert issubclass(MiappeError, Exception)

    def test_spec_error_inherits_from_miappe_error(self):
        """SpecError inherits from MiappeError."""
        assert issubclass(SpecError, MiappeError)

    def test_model_error_inherits_from_miappe_error(self):
        """ModelError inherits from MiappeError."""
        assert issubclass(ModelError, MiappeError)

    def test_validation_failed_error_inherits_from_miappe_error(self):
        """ValidationFailedError inherits from MiappeError."""
        assert issubclass(ValidationFailedError, MiappeError)

    def test_storage_io_error_inherits_from_miappe_error(self):
        """StorageIOError inherits from MiappeError."""
        assert issubclass(StorageIOError, MiappeError)


class TestExceptionUsage:
    """Test exception instantiation and catching."""

    def test_can_raise_and_catch_miappe_error(self):
        """MiappeError can be raised and caught."""
        with pytest.raises(MiappeError, match="test message"):
            raise MiappeError("test message")

    def test_can_catch_spec_error_as_miappe_error(self):
        """SpecError can be caught as MiappeError."""
        with pytest.raises(MiappeError):
            raise SpecError("spec problem")

    def test_can_catch_model_error_as_miappe_error(self):
        """ModelError can be caught as MiappeError."""
        with pytest.raises(MiappeError):
            raise ModelError("model problem")

    def test_can_catch_validation_error_as_miappe_error(self):
        """ValidationFailedError can be caught as MiappeError."""
        with pytest.raises(MiappeError):
            raise ValidationFailedError("validation problem")

    def test_can_catch_storage_error_as_miappe_error(self):
        """StorageIOError can be caught as MiappeError."""
        with pytest.raises(MiappeError):
            raise StorageIOError("storage problem")

    def test_exception_message_preserved(self):
        """Exception message is preserved."""
        msg = "detailed error message"
        error = SpecError(msg)
        assert str(error) == msg
