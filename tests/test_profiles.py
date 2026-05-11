"""Tests for the ProfileFactory class."""

from unittest.mock import patch

import pytest

from metaseed.facade import ProfileFacade
from metaseed.profiles import ProfileFactory


class TestProfileFactoryBasic:
    """Basic tests for ProfileFactory functionality."""

    @pytest.fixture
    def factory(self) -> ProfileFactory:
        """Create ProfileFactory instance."""
        return ProfileFactory()

    def test_list_profiles_returns_list(self, factory: ProfileFactory) -> None:
        """list_profiles returns a list of strings."""
        profiles = factory.list_profiles()
        assert isinstance(profiles, list)
        assert all(isinstance(p, str) for p in profiles)

    def test_list_profiles_includes_miappe(self, factory: ProfileFactory) -> None:
        """list_profiles includes miappe profile."""
        profiles = factory.list_profiles()
        assert "miappe" in profiles

    def test_list_profiles_includes_isa(self, factory: ProfileFactory) -> None:
        """list_profiles includes isa profile."""
        profiles = factory.list_profiles()
        assert "isa" in profiles

    def test_list_profiles_is_sorted(self, factory: ProfileFactory) -> None:
        """list_profiles returns sorted list."""
        profiles = factory.list_profiles()
        assert profiles == sorted(profiles)


class TestProfileFactoryVersions:
    """Tests for ProfileFactory version methods."""

    @pytest.fixture
    def factory(self) -> ProfileFactory:
        """Create ProfileFactory instance."""
        return ProfileFactory()

    def test_list_versions_miappe(self, factory: ProfileFactory) -> None:
        """list_versions returns versions for miappe profile."""
        versions = factory.list_versions("miappe")
        assert isinstance(versions, list)
        assert len(versions) > 0
        assert "1.1" in versions

    def test_list_versions_isa(self, factory: ProfileFactory) -> None:
        """list_versions returns versions for isa profile."""
        versions = factory.list_versions("isa")
        assert isinstance(versions, list)
        assert len(versions) > 0
        assert "1.0" in versions

    def test_list_versions_is_sorted(self, factory: ProfileFactory) -> None:
        """list_versions returns sorted list."""
        versions = factory.list_versions("miappe")
        assert versions == sorted(versions)

    def test_get_latest_version_miappe(self, factory: ProfileFactory) -> None:
        """get_latest_version returns latest miappe version."""
        latest = factory.get_latest_version("miappe")
        assert latest is not None
        assert latest == factory.list_versions("miappe")[-1]


class TestProfileFactoryInfo:
    """Tests for ProfileFactory get_profile_info method."""

    @pytest.fixture
    def factory(self) -> ProfileFactory:
        """Create ProfileFactory instance."""
        return ProfileFactory()

    def test_get_profile_info_returns_list(self, factory: ProfileFactory) -> None:
        """get_profile_info returns list of dicts."""
        info = factory.get_profile_info()
        assert isinstance(info, list)
        assert len(info) > 0

    def test_get_profile_info_has_required_keys(self, factory: ProfileFactory) -> None:
        """Each profile info dict has required keys."""
        info = factory.get_profile_info()
        for profile_info in info:
            assert "name" in profile_info
            assert "versions" in profile_info
            assert "latest" in profile_info

    def test_get_profile_info_includes_all_profiles(self, factory: ProfileFactory) -> None:
        """get_profile_info includes all profiles from list_profiles."""
        info = factory.get_profile_info()
        profile_names = {p["name"] for p in info}
        expected_profiles = set(factory.list_profiles())
        assert profile_names == expected_profiles


class TestProfileFactoryCreate:
    """Tests for ProfileFactory create method."""

    @pytest.fixture
    def factory(self) -> ProfileFactory:
        """Create ProfileFactory instance."""
        return ProfileFactory()

    def test_create_miappe_returns_facade(self, factory: ProfileFactory) -> None:
        """create returns ProfileFacade for miappe."""
        facade = factory.create("miappe")
        assert isinstance(facade, ProfileFacade)
        assert facade.profile == "miappe"

    def test_create_isa_returns_facade(self, factory: ProfileFactory) -> None:
        """create returns ProfileFacade for isa."""
        facade = factory.create("isa")
        assert isinstance(facade, ProfileFacade)
        assert facade.profile == "isa"

    def test_create_with_version(self, factory: ProfileFactory) -> None:
        """create with explicit version works."""
        facade = factory.create("miappe", "1.1")
        assert facade.version == "1.1"

    def test_create_uses_latest_version_by_default(self, factory: ProfileFactory) -> None:
        """create uses latest version when version not specified."""
        facade = factory.create("miappe")
        expected_latest = factory.get_latest_version("miappe")
        assert facade.version == expected_latest

    def test_create_unknown_profile_raises(self, factory: ProfileFactory) -> None:
        """create raises ValueError for unknown profile."""
        with pytest.raises(ValueError, match="Profile not found"):
            factory.create("nonexistent-profile")


class TestProfileFactoryDefault:
    """Tests for ProfileFactory get_default_profile method."""

    @pytest.fixture
    def factory(self) -> ProfileFactory:
        """Create ProfileFactory instance."""
        return ProfileFactory()

    def test_get_default_profile_returns_string(self, factory: ProfileFactory) -> None:
        """get_default_profile returns a string."""
        default = factory.get_default_profile()
        assert isinstance(default, str)

    def test_get_default_profile_is_valid(self, factory: ProfileFactory) -> None:
        """get_default_profile returns a valid profile name."""
        default = factory.get_default_profile()
        assert default in factory.list_profiles()

    def test_get_default_profile_prefers_miappe(self, factory: ProfileFactory) -> None:
        """get_default_profile returns miappe when available."""
        default = factory.get_default_profile()
        assert default == "miappe"


class TestProfileFactoryEdgeCases:
    """Tests for ProfileFactory edge cases using mocking."""

    def test_get_default_profile_no_profiles_raises(self) -> None:
        """get_default_profile raises ValueError when no profiles available."""
        factory = ProfileFactory()
        with patch.object(factory, "list_profiles", return_value=[]):
            with pytest.raises(ValueError, match="No profiles available"):
                factory.get_default_profile()

    def test_get_default_profile_without_miappe(self) -> None:
        """get_default_profile returns first profile when miappe not available."""
        factory = ProfileFactory()
        with patch.object(factory, "list_profiles", return_value=["alpha", "beta"]):
            default = factory.get_default_profile()
            assert default == "alpha"

    def test_create_no_versions_raises(self) -> None:
        """create raises ValueError when profile has no versions."""
        factory = ProfileFactory()
        with patch.object(factory, "list_profiles", return_value=["test-profile"]):
            with patch.object(factory, "get_latest_version", return_value=None):
                with pytest.raises(ValueError, match="No versions found"):
                    factory.create("test-profile")
