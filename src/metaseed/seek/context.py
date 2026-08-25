"""What a sync accumulates, and what one node placement needs.

Separated from the walk so the per-level placement code and the walk itself can
share these without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

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
    # Attribute-level omissions on a record that WAS pushed: a field the
    # Extended Metadata Type has no attribute for, or an attribute that holds
    # a SEEK record reference no value can fill. Distinct from ``skipped``,
    # which names whole entities that did not reach SEEK.
    notes: list[tuple[str, str]] = dc_field(default_factory=list)
    # Samples the ISA tree cannot reach. An assay material naming no existing
    # Assay has no Sample Type to go in and is not created; a Sample stored in a
    # Study-owned type whose chain never reaches an Assay link IS created, but
    # nothing walking down from the Investigation finds it.
    unlinked: list[tuple[str, str]] = dc_field(default_factory=list)
    # Study id -> the assay stream created for it. Every Assay hangs off one:
    # an assay outside a stream does not render in SEEK's ISA study view.
    assay_streams: dict[str, str] = dc_field(default_factory=dict)
    # The Study-owned Sample Type ids this push created (Source and Sample
    # Collection, per new Study). SEEK does not delete them with their Study —
    # they stay behind as orphans — so a caller cleaning up needs their ids.
    sample_types: list[str] = dc_field(default_factory=list)
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
    # SEEK study ids whose stream already carries a template-bound chain. A
    # stream is a line, so the next chain in that Study gets its own.
    study_stream_taken: set[str]
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
    # Called after every node is placed with (placed, total), so a caller can
    # show progress on a push that takes minutes. None when nobody listens.
    on_progress: Callable[[int, int], None] | None = None
    total_nodes: int = 0
    placed_nodes: int = 0
    # Node ids of Samples pushed with an Assay association. The post-walk
    # reachability check treats a material chain as reachable once any node in
    # it carries one, because SEEK derives Study and Investigation from it.
    assay_linked_nodes: set[str] = dc_field(default_factory=set)
    # SEEK Sample Type id -> the attribute a Sample's title is read from. The
    # input link into a type is keyed ``Input (<predecessor's title attribute>)``,
    # SEEK's own naming, so a successor needs to know this about its predecessor.
    title_attribute_by_type: dict[str, str] = dc_field(default_factory=dict)
    # SEEK Sample Type id -> the type it takes its inputs from.
    linked_type_of: dict[str, str] = dc_field(default_factory=dict)
    # (Sample Type id, title) -> the SEEK sample placed there, so a profile
    # that names its predecessor through an ``Input`` field can resolve it.
    sample_by_type_and_title: dict[tuple[str, str], str] = dc_field(
        default_factory=dict
    )
    # Extended Metadata Type title -> id on the target, read once when any
    # entity declares one, and each consulted type's attributes (title -> the
    # nested type id it links to, or None), fetched on first use.
    extended_metadata_type_ids: dict[str, str] = dc_field(default_factory=dict)
    extended_metadata_attribute_cache: dict[str, dict[str, tuple[str | None, str]]] = (
        dc_field(default_factory=dict)
    )
    # File URL -> the remote DataFile registered for it, so one file named by
    # several records is registered once.
    data_file_by_url: dict[str, str] = dc_field(default_factory=dict)
    # ISA Template id -> attribute title -> id, fetched once per template.
    template_attribute_cache: dict[str, dict[str, str]] = dc_field(default_factory=dict)
    # SEEK sample id -> node ids of the samples placed with it as their input.
    # The reachability report follows these as well as the tree, because a
    # referenced chain links siblings the tree does not.
    successor_nodes: dict[str, list[str]] = dc_field(default_factory=dict)
    # SEEK assay id -> {entity name: (SEEK assay id, Sample Type id)} for a
    # profile Assay that became several chained SEEK Assays, one per
    # assay-level entity under it. Keyed by the first assay's id, which is what
    # the walk threads down.
    assay_entity_types: dict[str, dict[str, tuple[str, str]]] = dc_field(
        default_factory=dict
    )
