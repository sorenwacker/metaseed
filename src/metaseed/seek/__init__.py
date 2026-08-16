"""FAIRDOM-SEEK adapter — provision a data model and push ISA content into SEEK.

Two phases over the SEEK JSON:API:

- **provision** (:mod:`metaseed.seek.provision`) — project a profile onto SEEK
  Controlled Vocabularies + Sample Types;
- **sync** (:mod:`metaseed.seek.sync`) — push a loaded dataset as Investigations,
  Studies, Assays and Samples;
- **import** (:mod:`metaseed.seek.importer`) — the read direction: reconstruct a
  metaseed dataset from a SEEK Investigation (SEEK -> metaseed).

    >>> from metaseed.seek import SeekClient, client_from_settings
    >>> client = SeekClient("http://localhost:3001", token="...")  # metaseed[seek]

The pure JSON:API payload builders (:mod:`metaseed.seek.payloads`, re-exported
here) import without the ``metaseed[seek]`` extra; ``SeekClient`` needs ``httpx``
and ``to_fair_data_station_rdf`` needs ``rdflib``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.seek.payloads import (
    assay_payload,
    controlled_vocab_payload,
    investigation_payload,
    sample_attribute,
    sample_payload,
    sample_type_payload,
    study_payload,
)
from metaseed.seek.provision import (
    build_provisioning_plan,
    execute_provisioning_plan,
)
from metaseed.seek.sync import sync_dataset_to_seek

if TYPE_CHECKING:
    from metaseed.seek.client import SeekClient, client_from_settings
    from metaseed.seek.fairds import (
        to_fair_data_station_model_rdf,
        to_fair_data_station_rdf,
    )

__all__ = [
    "SeekClient",
    "assay_payload",
    "build_provisioning_plan",
    "client_from_settings",
    "controlled_vocab_payload",
    "execute_provisioning_plan",
    "import_from_seek",
    "investigation_payload",
    "sample_attribute",
    "sample_payload",
    "sample_type_payload",
    "study_payload",
    "sync_dataset_to_seek",
    "to_fair_data_station_model_rdf",
    "to_fair_data_station_rdf",
]


def __getattr__(name: str) -> Any:
    """Lazily expose the httpx/rdflib-backed API so builders import without the extra."""
    if name in ("SeekClient", "client_from_settings"):
        from metaseed.seek import client

        return getattr(client, name)
    if name == "import_from_seek":
        # httpx-backed, like the client below: importing it eagerly made the
        # whole package require the `seek` extra, which is what this lazy
        # accessor exists to avoid.
        from metaseed.seek import importer

        return importer.import_from_seek
    if name in ("to_fair_data_station_rdf", "to_fair_data_station_model_rdf"):
        from metaseed.seek import fairds

        return getattr(fairds, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
