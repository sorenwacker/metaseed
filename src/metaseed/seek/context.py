"""What a sync accumulates, and what one node placement needs.

Separated from the walk so the per-level placement code and the walk itself can
share these without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.seek.ports import IsaWriter
    from metaseed.specs.schema import ProfileSpec


@dataclass
class SyncResult:
    """Outcome of pushing a dataset to SEEK (node id -> created SEEK id)."""

    investigations: dict[str, str] = dc_field(default_factory=dict)
    studies: dict[str, str] = dc_field(default_factory=dict)
    assays: dict[str, str] = dc_field(default_factory=dict)
    samples: dict[str, str] = dc_field(default_factory=dict)
    data_files: dict[str, str] = dc_field(default_factory=dict)
    skipped: list[tuple[str, str]] = dc_field(default_factory=list)
    errors: list[tuple[str, str]] = dc_field(default_factory=list)
    # Not created: a Sample with no Assay ancestor has no Sample Type to go in,
    # since under ISA-JSON compliance an Assay owns the type its Samples use.
    unlinked: list[tuple[str, str]] = dc_field(default_factory=list)
    # Study id -> the assay stream created for it. Every Assay hangs off one:
    # an assay outside a stream does not render in SEEK's ISA study view.
    assay_streams: dict[str, str] = dc_field(default_factory=dict)
    # Node id -> the SEEK id a previous push had already created. Pushing twice
    # used to make a second copy of everything; these were found and reused
    # instead, and are counted apart from what this push created.
    reused: dict[str, str] = dc_field(default_factory=dict)

    @property
    def synced_count(self) -> int:
        """Total SEEK resources this push touched — created OR reused.

        The per-kind dicts deliberately include reused records (a re-push
        reports the full picture), so this is not a creation count.
        """
        return sum(
            len(d)
            for d in (
                self.investigations,
                self.studies,
                self.assays,
                self.samples,
                self.data_files,
            )
        )

    @property
    def created_count(self) -> int:
        """SEEK resources this push actually created (reused ones excluded)."""
        return max(0, self.synced_count - len(self.reused))


@dataclass
class SyncContext:
    """The shared state a node placement needs, so the walk stays a thin recursion."""

    client: IsaWriter
    project_id: str
    profile: ProfileSpec
    # The Sample-role entities down the material chain, in order: the Source
    # level, the Sample Collection level, then the assay level. Each Sample Type
    # is built from its own entity -- they carry different fields, and using one
    # for all three makes every type demand the others' required attributes.
    chain_entities: list[str]
    isa_tag_ids: Mapping[str, str]
    cv_ids: Mapping[str, str]
    roles: dict[str, str]
    values_by_node: dict[str, Any]
    text_list_fields_by_entity: dict[str, frozenset[str]]
    file_fields_by_entity: dict[str, tuple[str | None, str | None]]
    files_by_study: dict[str, list[tuple[str, str]]]
    # SEEK study id -> the Source Sample Type it owns, the head of the chain.
    study_source_type: dict[str, str]
    # SEEK study id -> the Sample Collection Sample Type it owns. Each Assay
    # under that Study chains its own type to this one.
    study_collection_type: dict[str, str]
    # SEEK study id -> its assay stream, which every Assay hangs off.
    study_stream: dict[str, str]
    # SEEK assay id -> the Sample Type that Assay owns, where its Samples go.
    assay_sample_type: dict[str, str]
    # ISA Template title -> id on the target instance. A Sample Type without a
    # Template cannot be exported as ISA-JSON, so a missing one is an error
    # rather than something to push past.
    template_ids: Mapping[str, str]
    # The SEEK sharing level applied to everything created, or None for SEEK's
    # own default (private to the contributor).
    sharing: str | None
    # entity type -> the fields whose profile ``reference`` names an
    # Assay-role entity. Only these fields may link a material to an Assay;
    # any other value matching an assay identifier is a coincidence.
    assay_reference_fields: dict[str, list[str]]
    # Assay identifier (as written in the dataset) -> its SEEK id, so an
    # AssayMaterial can name the Assay that measured it by reference.
    assay_id_by_identifier: dict[str, str]
    # SEEK assay id -> the protocol name its Samples record. The ISA-JSON
    # exporter refuses a Sample with no protocol ("has no protocol"), so every
    # Sample carries the name of the Assay that produced it.
    assay_protocol: dict[str, str]
    # A Sample Type that exists only to satisfy validation while creating a
    # Study; see ``_placeholder_sample_type_id``.
    placeholder_type_id: str
    result: SyncResult
