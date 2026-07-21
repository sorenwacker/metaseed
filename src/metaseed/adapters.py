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


ADAPTERS: tuple[AdapterInfo, ...] = (
    AdapterInfo(
        key="ena",
        name="ENA",
        description="Import public metadata for a European Nucleotide Archive accession.",
        direction="import",
        extra="ena",
        requires=("httpx",),
    ),
    AdapterInfo(
        key="pride",
        name="PRIDE",
        description="Import a PRIDE Archive proteomics project; export SDRF / submission.px.",
        direction="import",
        extra="pride",
        requires=("httpx",),
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
