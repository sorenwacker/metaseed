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
        # "dcat" is offered for every profile; "pride" is the profile-specific one.
        assert {a.key for a in exports} == {"pride", "pride-sdrf", "dcat"}
        assert all(a.kind == "export" for a in exports)

        imports = adapters.actions_for_profile("metabolights", kind="import")
        assert [a.key for a in imports] == ["metabolights-import"]
        assert imports[0].surface == "import-menu"

    def test_actions_for_profile_empty_when_extra_missing(self, monkeypatch):
        monkeypatch.setattr(importlib.util, "find_spec", lambda _m: None)
        assert adapters.actions_for_profile("ena") == ()

    def test_a_profile_with_no_adapter_gets_only_the_universal_record(self):
        """darwin-core has no repository adapter of its own, so the DCAT
        catalogue record is the only thing offered — and nothing else leaks in
        from an adapter that does not serve it."""
        keys = {a.key for a in adapters.actions_for_profile("darwin-core")}

        assert keys == {"dcat"}

    def test_find_action_unknown_key_is_none(self):
        assert adapters.find_action("does-not-exist") is None

    def test_applies_to_defaults_to_all_profiles(self):
        action = adapters.Action("export", "x", "X", "m:f")
        assert action.applies_to("anything")
        scoped = adapters.Action("export", "y", "Y", "m:f", profiles=("isa",))
        assert scoped.applies_to("isa")
        assert not scoped.applies_to("ena")


@pytest.mark.parametrize(
    "action",
    [a for adapter in adapters.ADAPTERS for a in adapter.actions],
    ids=lambda a: a.key,
)
def test_every_declared_action_ref_resolves(action) -> None:
    """A typo in ``ref`` is invisible to mypy and ruff, so pin it with a test.

    ``ref`` is an opaque "module:function" string; without this, a stale target
    only surfaces as a 500 the first time a user clicks the control.
    """
    assert callable(action.resolve())


def test_malformed_ref_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="module:function"):
        adapters.Action(kind="export", key="bad", label="Bad", ref="no-colon")


def test_enumerating_the_registry_imports_no_plugin_modules() -> None:
    """Enumeration must stay lazy: listing actions must not import adapters.

    This is the central promise of the declarative model -- a host can list what
    is on offer without paying for (or requiring) every optional extra.
    """
    import sys

    heavy = [m for m in sys.modules if m.startswith("metaseed.ena")]
    for m in heavy:
        del sys.modules[m]

    adapters.actions_for_profile("ena", kind="export")
    adapters.find_action("ena")

    assert not [m for m in sys.modules if m.startswith("metaseed.ena")], (
        "enumerating the registry imported a plugin module"
    )


def test_profiles_tuple_offers_an_action_for_another_profile() -> None:
    """An explicit ``profiles`` must be able to broaden, not only narrow.

    Restricting the search to the adapter whose key equals the profile made this
    field unreachable: it could only ever narrow to nothing.
    """
    action = adapters.Action(
        kind="export",
        key="probe",
        label="Probe",
        ref="metaseed.ena.export:to_ena_xml",
        profiles=("isa",),
    )
    assert action.applies_to("isa", adapter_key="ena") is True
    assert action.applies_to("miappe", adapter_key="ena") is False


def test_action_without_profiles_follows_its_adapter_key() -> None:
    action = adapters.Action(
        kind="export", key="probe2", label="Probe", ref="metaseed.ena.export:to_ena_xml"
    )
    assert action.applies_to("ena", adapter_key="ena") is True
    assert action.applies_to("miappe", adapter_key="ena") is False


def test_a_wildcard_action_applies_to_every_profile() -> None:
    """A record like DCAT describes any dataset, including Spec-Builder
    profiles whose names cannot be listed in the registry."""
    action = adapters.Action(
        "export", "card", "Card", "metaseed.dcat.export:to_dcat", profiles=("*",)
    )

    assert action.applies_to("miappe", adapter_key="dcat")
    assert action.applies_to("a-profile-invented-yesterday", adapter_key="dcat")


def test_the_wildcard_is_not_implemented_as_always_true() -> None:
    """A scoped action must still refuse a profile it does not list, or the
    wildcard would have widened every action in the registry."""
    scoped = adapters.Action(
        "export", "y", "Y", "metaseed.ena.export:to_ena_xml", profiles=("isa",)
    )

    assert scoped.applies_to("isa")
    assert not scoped.applies_to("miappe")
