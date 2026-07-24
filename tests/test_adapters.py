"""Tests for the adapter (plugin) registry."""

from __future__ import annotations

import importlib.util

import pytest

from metaseed import adapters


def test_registry_covers_the_known_adapters():
    keys = {a.key for a in adapters.ADAPTERS}
    assert {"ena", "pride", "brapi", "metabolights", "dcat", "seek"} <= keys


def test_get_adapter_and_is_known():
    assert adapters.is_known("seek")
    assert not adapters.is_known("nope")
    assert adapters.get_adapter("seek").extra == "seek"
    with pytest.raises(KeyError):
        adapters.get_adapter("nope")


def test_is_available_true_when_deps_present():
    # httpx is a dev dependency, so seek's requirement is satisfied here.
    assert adapters.is_available(adapters.get_adapter("seek"))


def test_is_available_false_when_missing(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda _m: None)
    assert not adapters.is_available(adapters.get_adapter("seek"))


def test_is_available_survives_find_spec_raising(monkeypatch):
    def boom(_m: str):
        raise ModuleNotFoundError(_m)

    monkeypatch.setattr(importlib.util, "find_spec", boom)
    assert not adapters.is_available(adapters.get_adapter("dcat"))


class TestActions:
    """The declarative Action model (imports/exports/pushes + UI surfaces)."""

    def test_export_actions_resolve_to_a_callable(self):
        action = adapters.find_action("ena")
        assert action is not None
        assert action.kind == "export"
        assert action.surface == "export-menu"
        # ref is lazy — resolving imports the real exporter only now.
        fn = action.resolve()
        from metaseed.ena.export import to_ena_xml

        assert fn is to_ena_xml

    def test_actions_for_profile_filters_by_kind_and_surface(self):
        exports = adapters.actions_for_profile("pride", kind="export")
        assert {a.key for a in exports} == {"pride", "pride-sdrf"}
        assert all(a.kind == "export" for a in exports)

        imports = adapters.actions_for_profile("metabolights", kind="import")
        assert [a.key for a in imports] == ["metabolights-import"]
        assert imports[0].surface == "import-menu"

    def test_actions_for_profile_empty_when_extra_missing(self, monkeypatch):
        monkeypatch.setattr(importlib.util, "find_spec", lambda _m: None)
        assert adapters.actions_for_profile("ena") == ()

    def test_actions_for_profile_empty_for_unknown_profile(self):
        assert adapters.actions_for_profile("darwin-core") == ()

    def test_find_action_unknown_key_is_none(self):
        assert adapters.find_action("does-not-exist") is None

    def test_applies_to_defaults_to_all_profiles(self):
        action = adapters.Action("export", "x", "X", "m:f")
        assert action.applies_to("anything")
        scoped = adapters.Action("export", "y", "Y", "m:f", profiles=("isa",))
        assert scoped.applies_to("isa")
        assert not scoped.applies_to("ena")
