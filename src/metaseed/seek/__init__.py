"""FAIRDOM-SEEK adapter — push ISA content into a SEEK instance.

Creates the ISA hierarchy (Investigation → Study → Assay) plus Sample Types and
Samples in a `FAIRDOM-SEEK <https://seek4science.org/>`_ instance through its
JSON:API.

    >>> from metaseed.seek import SeekClient, push_minimal_experiment
    >>> client = SeekClient("http://localhost:3001", auth=("admin", "..."))  # metaseed[seek]
    >>> ids = push_minimal_experiment(client)

The pure JSON:API payload builders (:mod:`metaseed.seek.payloads`, re-exported
here) import without the ``metaseed[seek]`` extra; ``SeekClient`` and
``push_minimal_experiment`` need ``httpx``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.seek.payloads import (
    assay_payload,
    investigation_payload,
    sample_attribute,
    sample_payload,
    sample_type_payload,
    study_payload,
)

if TYPE_CHECKING:
    from metaseed.seek.client import SeekClient
    from metaseed.seek.export import ExperimentIds, push_minimal_experiment

__all__ = [
    "ExperimentIds",
    "SeekClient",
    "assay_payload",
    "investigation_payload",
    "push_minimal_experiment",
    "sample_attribute",
    "sample_payload",
    "sample_type_payload",
    "study_payload",
]


def __getattr__(name: str) -> Any:
    """Lazily expose the httpx-backed API so builders import without the extra."""
    if name == "SeekClient":
        from metaseed.seek.client import SeekClient

        return SeekClient
    if name in ("push_minimal_experiment", "ExperimentIds"):
        from metaseed.seek import export

        return getattr(export, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
