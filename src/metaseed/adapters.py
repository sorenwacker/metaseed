"""Registry of metaseed's optional integration adapters ("plugins").

Each adapter is an optional package installed via a pip extra (e.g.
``metaseed[seek]``). There is no runtime discovery — this module is the single
canonical list, so the UI and settings layer can enumerate, describe, and
toggle them. Availability (is the extra installed?) is checked with
``importlib.util.find_spec`` so this module has no heavy imports and no import
side effects.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass


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


@dataclass(frozen=True)
class ExportFormat:
    """A downloadable file export an adapter can produce from a dataset.

    The callable (``module``.``function``) takes a ``MetaseedClient`` and returns
    ``{filename: text}``. Declared here so the UI derives its export buttons from
    the registry rather than hard-coding a parallel list.
    """

    key: str
    """Stable identifier for the export (e.g. ``ena``, ``pride-sdrf``)."""
    label: str
    """Human-readable label shown on the download button."""
    module: str
    """Import path of the module holding the export function."""
    function: str
    """Name of the ``(client) -> {filename: text}`` export function."""


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
    exports: tuple[ExportFormat, ...] = ()
    """File exports this adapter can produce for its matching profile."""


ADAPTERS: tuple[AdapterInfo, ...] = (
    AdapterInfo(
        key="ena",
        name="ENA",
        description="Import public metadata for a European Nucleotide Archive accession.",
        direction="import",
        extra="ena",
        requires=("httpx",),
        exports=(ExportFormat("ena", "ENA XML", "metaseed.ena.export", "to_ena_xml"),),
    ),
    AdapterInfo(
        key="pride",
        name="PRIDE",
        description="Import a PRIDE Archive proteomics project; export SDRF / submission.px.",
        direction="import",
        extra="pride",
        requires=("httpx",),
        exports=(
            ExportFormat(
                "pride",
                "PRIDE submission",
                "metaseed.pride.export",
                "to_pride_submission",
            ),
            ExportFormat(
                "pride-sdrf", "PRIDE SDRF", "metaseed.pride.export", "to_pride_sdrf"
            ),
        ),
    ),
    AdapterInfo(
        key="brapi",
        name="BrAPI",
        description="Import from a BrAPI v2 plant-breeding server; export BrAPI objects.",
        direction="import",
        extra="brapi",
        requires=("httpx",),
    ),
    AdapterInfo(
        key="metabolights",
        name="MetaboLights",
        description="Import a MetaboLights metabolomics study document.",
        direction="import",
        extra="metabolights",
        requires=("httpx",),
        exports=(
            ExportFormat(
                "metabolights",
                "MetaboLights ISA-Tab",
                "metaseed.metabolights.export",
                "to_metabolights",
            ),
        ),
    ),
    AdapterInfo(
        key="dcat",
        name="DCAT",
        description="Export a dataset as a DCAT catalogue (JSON-LD / Turtle).",
        direction="export",
        extra="dcat",
        requires=("rdflib",),
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


def exports_for_profile(profile: str) -> tuple[ExportFormat, ...]:
    """File exports available for a metaseed profile.

    An adapter's ``key`` matches the profile it exports (``ena`` adapter → ``ena``
    profile), so this returns that adapter's exports when its extra is installed,
    else an empty tuple.
    """
    adapter = _BY_KEY.get(profile)
    if adapter is None or not is_available(adapter):
        return ()
    return adapter.exports


def find_export(key: str) -> ExportFormat | None:
    """Return the :class:`ExportFormat` with ``key`` across all adapters, or None."""
    for adapter in ADAPTERS:
        for export in adapter.exports:
            if export.key == key:
                return export
    return None
