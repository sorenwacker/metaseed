"""Tests for metaseed.core.context."""

import pytest

from metaseed.core.context import ProfileContext


class TestProfileContext:
    """Test ProfileContext dataclass."""

    def test_basic_creation(self):
        """ProfileContext can be created with profile and version."""
        ctx = ProfileContext(profile="miappe", version="1.2")
        assert ctx.profile == "miappe"
        assert ctx.version == "1.2"

    def test_cache_key_format(self):
        """cache_key returns profile:version format."""
        ctx = ProfileContext(profile="isa", version="1.0")
        assert ctx.cache_key == "isa:1.0"

    def test_cache_key_is_cached(self):
        """cache_key property is cached."""
        ctx = ProfileContext(profile="darwin-core", version="1.0")
        key1 = ctx.cache_key
        key2 = ctx.cache_key
        assert key1 is key2

    def test_immutability(self):
        """ProfileContext is immutable (frozen)."""
        ctx = ProfileContext(profile="miappe", version="1.1")
        with pytest.raises(AttributeError):
            ctx.profile = "isa"

    def test_equality(self):
        """Two ProfileContext with same values are equal."""
        ctx1 = ProfileContext(profile="miappe", version="1.2")
        ctx2 = ProfileContext(profile="miappe", version="1.2")
        assert ctx1 == ctx2

    def test_hashable(self):
        """ProfileContext is hashable (can be used in sets/dicts)."""
        ctx = ProfileContext(profile="isa", version="1.0")
        ctx_set = {ctx}
        assert ctx in ctx_set

    def test_different_versions_not_equal(self):
        """Different versions create different contexts."""
        ctx1 = ProfileContext(profile="miappe", version="1.1")
        ctx2 = ProfileContext(profile="miappe", version="1.2")
        assert ctx1 != ctx2
        assert ctx1.cache_key != ctx2.cache_key
