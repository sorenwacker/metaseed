"""Registry of metaseed's optional integration adapters ("plugins").

Each adapter is an optional package installed via a pip extra (e.g.
``metaseed[seek]``). There is no runtime discovery — this module is the single
canonical list, so the UI and settings layer can enumerate, describe, and
toggle them. Availability (is the extra installed?) is checked with
``importlib.util.find_spec`` so this module has no heavy imports and no import
side effects.
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, cast


@dataclass(frozen=True)
class ConfigField:
    """A configurable setting for an adapter (e.g. a service URL or API key)."""

    key: str
    """Stable identifier stored in settings (e.g. ``url``, ``api_key``)."""
    label: str
    """Human-readable label shown in the UI."""
    secret: bool = False
    """Whether the value is sensitive (rendered masked, e.g. an API key)."""
    placeholder: str = ""
    """Optional input placeholder."""


ActionKind = Literal["import", "export", "push"]


@dataclass(frozen=True)
class Action:
    """A capability a plugin exposes to a host application.

    An adapter declares its capabilities as actions so a host (the web UI, the
    hub, a CLI) can enumerate, place, and invoke them from data alone.

    ``ref`` is a lazy ``"module:function"`` path resolved only when the action is
    invoked (:meth:`resolve`), so listing the registry never imports a plugin's
    implementation or its optional dependencies — preserving this module's
    no-heavy-imports guarantee.

    ``surface`` names *where* a host should group the action's UI (e.g.
    ``"export-menu"`` vs ``"import-menu"`` vs a dataset toolbar), making placement
    data-driven instead of hard-coded per host. ``kind`` says what the action does
    (``export`` returns ``{filename: text}``; ``import`` builds a dataset; ``push``
    writes to a live service).
    """

    kind: ActionKind
    key: str
    """Stable identifier for the action (e.g. ``ena``, ``pride-sdrf``)."""
    label: str
    """Human-readable label shown on the control."""
    ref: str
    """Lazy target as ``"module:function"`` (e.g. ``metaseed.ena.export:to_ena_xml``)."""
    surface: str = "export-menu"
    """UI surface a host groups this action under."""
    profiles: tuple[str, ...] = ()
    """Profiles the action applies to; empty means the adapter's own ``key``."""
    input_label: str = ""
    """For an ``import`` action, what the single string argument is.

    Import actions share one call shape -- ``fn(value)`` -- but not one meaning:
    ENA/PRIDE/MetaboLights take an accession, BrAPI a server URL. A host renders
    this as the field label so the prompt is honest about which it wants.
    """
    input_placeholder: str = ""
    """Example value for ``input_label`` (e.g. ``PXD000001``)."""

    def __post_init__(self) -> None:
        """Reject a malformed ``ref`` at construction rather than at dispatch.

        Without this a ref missing its ``:`` resolves to ``getattr(mod, "")``,
        surfacing as a 500 the first time a user clicks the control.
        """
        module_name, separator, attribute = self.ref.partition(":")
        if not (module_name and separator and attribute):
            msg = (
                f"Action {self.key!r}: ref must be 'module:function', got {self.ref!r}"
            )
            raise ValueError(msg)

    def resolve(self) -> Callable[..., Any]:
        """Import and return the action's callable (only when invoked).

        Only ever called on registry-owned instances: ``Action`` must not be
        constructed from user input, since ``resolve`` imports by name.
        """
        module_name, _, attribute = self.ref.partition(":")
        return cast(
            "Callable[..., Any]",
            getattr(importlib.import_module(module_name), attribute),
        )

    def applies_to(self, profile: str, *, adapter_key: str | None = None) -> bool:
        """Whether this action is offered for ``profile``.

        An explicit ``profiles`` tuple wins, and ``"*"`` in it means every
        profile — needed by an action like the DCAT card that describes any
        dataset, including Spec-Builder profiles whose names cannot be listed
        here. Otherwise the action is offered for the profile its adapter
        serves, by the convention that an adapter's ``key`` names that profile.
        ``adapter_key`` is omitted only when the caller has already established
        the adapter matches.
        """
        if self.profiles:
            return "*" in self.profiles or profile in self.profiles
        return adapter_key is None or adapter_key == profile


@dataclass(frozen=True)
class AdapterInfo:
    """Static description of an optional integration adapter."""

    key: str
    """Stable identifier, matching the package name and pip extra (e.g. ``seek``)."""
    name: str
    """Human-readable name."""
    description: str
    """One-line summary of what the adapter does."""
    direction: str
    """``import`` (fetch into metaseed), ``export`` (emit a file), or ``push``
    (write to a live service)."""
    extra: str
    """The pip extra that installs it (``pip install 'metaseed[<extra>]'``)."""
    requires: tuple[str, ...]
    """Third-party modules whose presence means the extra is installed."""
    config_fields: tuple[ConfigField, ...] = ()
    """Per-instance configuration this adapter accepts (URLs, keys)."""
    action_path: str | None = None
    """UI path to the adapter's action page, if it has one (e.g. ``/seek``)."""
    actions: tuple[Action, ...] = field(default_factory=tuple)
    """Capabilities (imports/exports/pushes) this adapter exposes to hosts."""


ADAPTERS: tuple[AdapterInfo, ...] = (
    AdapterInfo(
        key="ena",
        name="ENA",
        description="Import public metadata for a European Nucleotide Archive accession.",
        direction="import",
        extra="ena",
        requires=("httpx",),
        actions=(
            Action("export", "ena", "ENA XML", "metaseed.ena.export:to_ena_xml"),
            Action(
                "import",
                "ena-import",
                "Import ENA accession",
                "metaseed.ena:import_accession",
                surface="import-menu",
                input_label="ENA accession",
                input_placeholder="PRJEB1234",
            ),
        ),
    ),
    AdapterInfo(
        key="pride",
        name="PRIDE",
        description="Import a PRIDE Archive proteomics project; export submission.px + SDRF.",
        direction="import",
        extra="pride",
        requires=("httpx",),
        actions=(
            # One export, not two: the px file and its SDRF table are parts of a
            # single ProteomeXchange submission, so they travel together.
            Action(
                "export",
                "pride",
                "PRIDE submission",
                "metaseed.pride.export:to_pride_bundle",
            ),
            Action(
                "import",
                "pride-import",
                "Import PRIDE project",
                "metaseed.pride:import_accession",
                surface="import-menu",
                input_label="ProteomeXchange accession",
                input_placeholder="PXD000001",
            ),
        ),
    ),
    AdapterInfo(
        key="brapi",
        name="BrAPI",
        # Import only, by design: BrAPI servers are read sources here, and
        # writing back would need per-server credentials and write endpoints
        # most deployments do not expose. ``to_brapi`` stays available as a
        # library call but declares no export action, so no host offers one.
        description="Import a BrAPI v2 plant-breeding server's studies into the miappe profile.",
        direction="import",
        extra="brapi",
        requires=("httpx",),
        actions=(
            Action(
                "import",
                "brapi-import",
                "Import BrAPI server",
                "metaseed.brapi:import_brapi",
                surface="import-menu",
                # BrAPI reads a breeding server into the miappe profile, so the
                # adapter-key-names-the-profile convention does not apply.
                profiles=("miappe",),
                input_label="BrAPI v2 server URL",
                input_placeholder="https://test-server.brapi.org/brapi/v2",
            ),
        ),
    ),
    AdapterInfo(
        key="metabolights",
        name="MetaboLights",
        description="Import a MetaboLights metabolomics study document.",
        direction="import",
        extra="metabolights",
        requires=("httpx",),
        actions=(
            Action(
                "export",
                "metabolights",
                "MetaboLights ISA-Tab",
                "metaseed.metabolights.export:to_metabolights",
            ),
            Action(
                "import",
                "metabolights-import",
                "Import MetaboLights study",
                "metaseed.metabolights:import_accession",
                surface="import-menu",
                input_label="MetaboLights study accession",
                input_placeholder="MTBLS1",
            ),
        ),
    ),
    AdapterInfo(
        key="dcat",
        name="DCAT",
        description="Export a dataset's catalogue record as DCAT (JSON-LD / Turtle).",
        direction="export",
        extra="dcat",
        requires=("rdflib",),
        actions=(
            Action(
                "export",
                "dcat",
                "DCAT record (JSON-LD + Turtle)",
                "metaseed.dcat.export:to_dcat",
                # Every profile: a catalogue record describes any dataset, and
                # the adapter key names a vocabulary rather than a profile, so
                # the usual key-names-the-profile convention offers it to none.
                profiles=("*",),
            ),
        ),
    ),
    AdapterInfo(
        key="seek",
        name="FAIRDOM-SEEK",
        description="Export a dataset as SEEK-importable ISA RDF; push ISA content over the API.",
        direction="export",
        extra="seek",
        # httpx for the JSON:API client, rdflib for the ISA RDF export.
        requires=("httpx", "rdflib"),
        config_fields=(
            ConfigField("url", "SEEK URL", placeholder="http://localhost:3001"),
            ConfigField("api_key", "API key", secret=True),
        ),
        action_path="/seek",
    ),
)

_BY_KEY: dict[str, AdapterInfo] = {a.key: a for a in ADAPTERS}


def get_adapter(key: str) -> AdapterInfo:
    """Return the adapter with ``key`` or raise ``KeyError``."""
    return _BY_KEY[key]


def is_known(key: str) -> bool:
    """Return whether ``key`` names a registered adapter."""
    return key in _BY_KEY


def _module_present(module: str) -> bool:
    # find_spec raises (not returns None) for a dotted path whose parent package
    # is missing, so guard it — keeps `requires` free to list submodules later.
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def is_available(info: AdapterInfo) -> bool:
    """Return whether the adapter's pip extra is installed (deps importable)."""
    return all(_module_present(module) for module in info.requires)


def actions_for_profile(
    profile: str,
    *,
    kind: ActionKind | None = None,
    surface: str | None = None,
) -> tuple[Action, ...]:
    """Actions a host should offer for ``profile``, from installed adapters.

    Every installed adapter is consulted, and each action decides for itself via
    ``applies_to``: an action with an explicit ``profiles`` tuple is offered for
    those profiles, otherwise it falls back to the convention that an adapter's
    ``key`` names the profile it serves (``ena`` adapter → ``ena`` profile).
    Scanning all adapters is what makes ``profiles`` meaningful — restricting the
    search to ``_BY_KEY[profile]`` would mean an action could only ever narrow to
    nothing, never be offered for another profile. Optionally filter by ``kind``
    (import/export/push) and ``surface`` so a host can populate one UI area.
    """
    return tuple(
        action
        for adapter in ADAPTERS
        if is_available(adapter)
        for action in adapter.actions
        if action.applies_to(profile, adapter_key=adapter.key)
        and (kind is None or action.kind == kind)
        and (surface is None or action.surface == surface)
    )


def import_action_for_profile(profile: str) -> Action | None:
    """The importer a host should offer for ``profile``, or None.

    Every host that offers "fill this dataset from an archive" needs the same
    lookup — an ``import`` action on the ``import-menu`` surface — and each one
    filtering for itself is how the web UI and an agent tool come to disagree
    about what is on offer.

    Args:
        profile: Profile name the dataset uses (e.g. ``"pride"``).

    Returns:
        The action to run, or None when the profile has no installed importer.
    """
    return next(
        iter(actions_for_profile(profile, kind="import", surface="import-menu")),
        None,
    )


def importable_profiles() -> tuple[str, ...]:
    """Profiles an installed adapter can import into, sorted.

    Names profiles rather than adapter keys, because that is what a caller was
    asked for and what it would retry with: BrAPI's adapter key is ``brapi`` but
    it imports into ``miappe``.

    Returns:
        Sorted, de-duplicated profile names.
    """
    profiles: set[str] = set()
    for adapter in ADAPTERS:
        if not is_available(adapter):
            continue
        for action in adapter.actions:
            if action.kind != "import" or action.surface != "import-menu":
                continue
            profiles.update(action.profiles or (adapter.key,))
    return tuple(sorted(profiles))


def find_action(key: str) -> Action | None:
    """Return the :class:`Action` with ``key`` across all adapters, or None."""
    for adapter in ADAPTERS:
        for action in adapter.actions:
            if action.key == key:
                return action
    return None
