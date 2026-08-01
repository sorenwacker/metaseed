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
        # PRIDE offers one export: the px file and its SDRF are two parts of one
        # submission, so they ship together rather than as rival controls.
        exports = adapters.actions_for_profile("pride", kind="export")
        # One PRIDE export (px + SDRF travel together), plus the DCAT record,
        # which is offered for every profile.
        assert {a.key for a in exports} == {"pride", "dcat"}
        assert all(a.kind == "export" for a in exports)

        imports = adapters.actions_for_profile("metabolights", kind="import")
        assert [a.key for a in imports] == ["metabolights-import"]
        assert imports[0].surface == "import-menu"

    def test_pride_export_resolves_to_the_bundle(self):
        action = adapters.find_action("pride")
        assert action is not None
        from metaseed.pride.export import to_pride_bundle

        assert action.resolve() is to_pride_bundle

    def test_pride_offers_an_accession_importer(self):
        # A host's import-from-source flow finds an importer by surface, so a
        # PRIDE dataset without one cannot be filled from an accession.
        imports = adapters.actions_for_profile("pride", kind="import")
        assert [a.key for a in imports] == ["pride-import"]
        assert imports[0].surface == "import-menu"
        from metaseed.pride import import_accession

        assert imports[0].resolve() is import_accession

    @pytest.mark.parametrize(
        ("profile", "key", "ref"),
        [
            ("ena", "ena-import", "metaseed.ena:import_accession"),
            ("pride", "pride-import", "metaseed.pride:import_accession"),
            (
                "metabolights",
                "metabolights-import",
                "metaseed.metabolights:import_accession",
            ),
            # BrAPI imports a breeding server into the miappe profile, so its
            # action names that profile rather than the adapter's own key.
            ("miappe", "brapi-import", "metaseed.brapi:import_brapi"),
        ],
    )
    def test_every_importer_is_offered_on_the_import_surface(self, profile, key, ref):
        """Each adapter that can import declares it, so hosts need no per-repo
        knowledge to offer the whole set."""
        imports = adapters.actions_for_profile(
            profile, kind="import", surface="import-menu"
        )
        action = next((a for a in imports if a.key == key), None)
        assert action is not None, f"{profile} offers no {key} action"
        assert action.ref == ref
        assert callable(action.resolve())

    def test_import_actions_describe_the_value_they_take(self):
        """Hosts render one text input per importer; the label must say what to
        type, since an accession and a server URL are not interchangeable."""
        for action in (
            adapters.find_action("pride-import"),
            adapters.find_action("brapi-import"),
        ):
            assert action is not None
            assert action.input_label
            assert action.input_placeholder

        assert "URL" in adapters.find_action("brapi-import").input_label
        assert "accession" in adapters.find_action("pride-import").input_label.lower()

    def test_import_action_for_profile_picks_the_import_menu_entry(self):
        """Hosts ask for "the importer for this profile" rather than filtering.

        Three hosts (web UI, MCP, CLI) had to agree on kind *and* surface; one
        of them omitting the surface filter would have offered a non-menu
        import action in a text-input control that cannot drive it.
        """
        action = adapters.import_action_for_profile("pride")
        assert action is not None
        assert action.key == "pride-import"

        from metaseed.pride import import_accession

        assert action.resolve() is import_accession
        assert adapters.import_action_for_profile("darwin-core") is None

    def test_importable_profiles_names_profiles_not_adapter_keys(self):
        """The list is what a host shows after refusing an import, so it must
        name what the user would type as a profile. BrAPI is the case that
        separates the two: its adapter key is ``brapi`` but it imports into
        ``miappe``."""
        importable = adapters.importable_profiles()
        assert {"ena", "pride", "metabolights", "miappe"} <= set(importable)
        assert "brapi" not in importable
        assert "darwin-core" not in importable
        assert list(importable) == sorted(importable)

    def test_importable_profiles_empty_when_extras_missing(self, monkeypatch):
        """An uninstalled extra must drop its profile from the offer, not
        advertise an importer that cannot be resolved."""
        monkeypatch.setattr(importlib.util, "find_spec", lambda _m: None)
        assert adapters.importable_profiles() == ()

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
