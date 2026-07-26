"""Security regression tests: spec name/version must not escape the specs dir.

``save_spec`` interpolated ``spec.version`` and ``delete_user_spec`` interpolated
``name``/``version`` into filesystem paths without sanitization — a crafted value
(``../../.config/autostart``, an absolute path) escaped the custom-specs directory
(a chosen-directory write, and a destructive ``rmtree`` on delete). The fix routes
both through ``_specs_subpath`` (resolve + containment check).
"""

from __future__ import annotations

import pytest

from metaseed.specs import persistence
from metaseed.specs.loader import SpecLoader


@pytest.fixture
def specs_base(tmp_path, monkeypatch):
    base = tmp_path / "custom_specs"
    base.mkdir()
    monkeypatch.setattr(persistence, "get_custom_specs_dir", lambda: base)
    return base


def _spec():
    spec = SpecLoader(profile="miappe").load_profile(version="1.2", profile="miappe")
    spec.name = "mytestprofile"
    return spec


class TestSaveSpecTraversal:
    def test_relative_traversal_version_blocked(self, specs_base, tmp_path):
        spec = _spec()
        spec.version = "../../outside_evil"
        with pytest.raises(ValueError):
            persistence.save_spec(spec, name="mytestprofile")
        assert not (tmp_path / "outside_evil").exists()

    def test_absolute_version_blocked(self, specs_base, tmp_path):
        spec = _spec()
        # An absolute path outside the specs base must be rejected.
        spec.version = str(tmp_path / "evil_abs")
        with pytest.raises(ValueError):
            persistence.save_spec(spec, name="mytestprofile")

    def test_empty_version_blocked(self, specs_base):
        spec = _spec()
        spec.version = "   "
        with pytest.raises(ValueError):
            persistence.save_spec(spec, name="mytestprofile")

    def test_valid_version_saves_within_base(self, specs_base):
        spec = _spec()
        spec.version = "1.0"
        path = persistence.save_spec(spec, name="mytestprofile")
        assert path.is_relative_to(specs_base)
        assert path.name == "profile.yaml"
        assert path.read_text(encoding="utf-8")


class TestDeleteSpecTraversal:
    def test_version_traversal_does_not_rmtree_outside(
        self, specs_base, tmp_path, monkeypatch
    ):
        # A sibling dir outside the base that must survive.
        victim = tmp_path / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("x")
        # Create the real profile dir so delete reaches the version check.
        spec = _spec()
        spec.version = "1.0"
        persistence.save_spec(spec, name="mytestprofile")
        # Force the user-defined gate so the containment guard is what fires.
        monkeypatch.setattr(
            "metaseed.specs.loader.SpecLoader.is_user_defined", lambda self, name: True
        )
        with pytest.raises(ValueError):
            persistence.delete_user_spec("mytestprofile", "../../victim")
        assert victim.exists() and (victim / "keep.txt").exists()

    def test_name_traversal_does_not_rmtree_outside(
        self, specs_base, tmp_path, monkeypatch
    ):
        victim = tmp_path / "victim2"
        victim.mkdir()
        (victim / "keep.txt").write_text("x")
        monkeypatch.setattr(
            "metaseed.specs.loader.SpecLoader.is_user_defined", lambda self, name: True
        )
        # Name normalization rewrites path separators to '-', so a traversal name
        # cannot resolve outside the base: the delete matches nothing and touches
        # no files (version traversal is still caught by the containment check).
        assert persistence.delete_user_spec("../../victim2") is False
        assert victim.exists() and (victim / "keep.txt").exists()

    def test_valid_delete_roundtrip(self, specs_base, monkeypatch):
        spec = _spec()
        spec.version = "1.0"
        persistence.save_spec(spec, name="mytestprofile")
        monkeypatch.setattr(
            "metaseed.specs.loader.SpecLoader.is_user_defined", lambda self, name: True
        )
        assert persistence.delete_user_spec("mytestprofile", "1.0") is True

    def test_delete_normalizes_name_like_save(self, specs_base, monkeypatch):
        # save_spec stores under a lowercased, sanitized directory; deleting by
        # the original (mixed-case/spaced) name must resolve to the same path
        # rather than silently matching nothing.
        spec = _spec()
        spec.name = "My Spec"
        spec.version = "1.0"
        saved = persistence.save_spec(spec, name="My Spec")
        assert saved.exists()

        monkeypatch.setattr(
            "metaseed.specs.loader.SpecLoader.is_user_defined", lambda self, name: True
        )
        assert persistence.delete_user_spec("My Spec", "1.0") is True
        assert not saved.parent.exists()
