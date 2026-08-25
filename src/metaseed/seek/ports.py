"""The SEEK operations a dataset sync depends on.

:mod:`metaseed.seek.sync` depends on this protocol rather than on
:class:`metaseed.seek.client.SeekClient`, so a test can substitute a double that
the type checker holds to the same surface. The double drifting from the real
client -- a method added on one side and not the other -- then fails type
checking instead of surfacing as an ``AttributeError`` part-way through a walk.

:class:`~metaseed.seek.client.SeekClient` satisfies this structurally; nothing
needs to inherit from it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class Provisioner(Protocol):
    """Creates CVs and Sample Types, and reads back existing ones by title.

    What `execute_provisioning_plan` and `resolve_cv_ids` actually call. Its
    sibling `sync` already depended on `IsaWriter` while provisioning bound to
    the concrete `SeekClient`, so a test or an alternative backend could
    substitute one half of the pipeline but not the other.
    """

    def find_controlled_vocab_id_by_title(self, title: str) -> str | None: ...

    def sample_attribute_type_id(self, title: str) -> str:
        """Resolve a base attribute-type id by title; instance-assigned."""
        ...

    def create_controlled_vocab(
        self,
        *,
        title: str,
        terms: list[dict[str, Any]],
        description: str | None = None,
        source_ontology: str | None = None,
        ols_root_term_uris: str | None = None,
    ) -> str: ...

    def find_sample_type_id_by_title(
        self, title: str, *, project_id: str | None = None
    ) -> str | None: ...

    def create_sample_type(
        self, *, title: str, project_id: str, attributes: list[dict[str, Any]]
    ) -> str: ...


class IsaWriter(Protocol):
    """Creates the ISA resources a compliant sync needs, and reads back their ids."""

    def isa_tag_ids(self) -> dict[str, str]:
        """ISA tag title -> id on this instance."""
        ...

    def create_investigation(
        self,
        *,
        title: str,
        project_id: str,
        description: str | None = None,
        isa_json_compliant: bool = False,
        sharing: str | None = None,
    ) -> str: ...

    def template_ids_by_title(self) -> dict[str, str]:
        """ISA Template title -> id on this instance."""
        ...

    def template_attribute_ids(self, template_id: str) -> dict[str, str]:
        """An installed ISA Template's attribute titles -> ids."""
        ...

    def find_controlled_vocab_id_by_title(self, title: str) -> str | None:
        """The instance's Controlled Vocabulary with this title, if any."""
        ...

    def find_data_file_id_by_title(self, title: str, *, project_id: str) -> str | None:
        """An existing Data File with this title in the project, if any."""
        ...

    def extended_metadata_type_ids(self) -> dict[str, str]:
        """Extended Metadata Type title -> id on this instance (top-level types)."""
        ...

    def extended_metadata_attributes(
        self, type_id: str
    ) -> dict[str, tuple[str | None, str]]:
        """A type's attribute titles -> (nested type id or None, attribute type title)."""
        ...

    def create_isa_study(
        self,
        *,
        title: str,
        investigation_id: str,
        source_title: str,
        source_attributes: Sequence[Mapping[str, Any]],
        collection_title: str,
        collection_attributes: Sequence[Mapping[str, Any]],
        source_template_id: str | None = None,
        collection_template_id: str | None = None,
        sharing: str | None = None,
        extended_metadata: tuple[str, Mapping[str, Any]] | None = None,
    ) -> str: ...

    def create_isa_assay(
        self,
        *,
        title: str,
        study_id: str,
        assay_class_id: int,
        assay_stream_id: str | None = None,
        input_sample_type_id: str | None = None,
        sample_type_title: str | None = None,
        sample_type_attributes: Sequence[Mapping[str, Any]] | None = None,
        sample_type_template_id: str | None = None,
        sharing: str | None = None,
        extended_metadata: tuple[str, Mapping[str, Any]] | None = None,
    ) -> str: ...

    def study_sample_type_ids(self, study_id: str) -> dict[str, str]: ...

    def assay_sample_type_ids(self, assay_id: str) -> dict[str, str]: ...

    def create_sample(
        self,
        *,
        sample_type_id: str,
        project_id: str,
        data: dict[str, Any],
        assay_ids: Sequence[str] | None = None,
        study_id: str | None = None,
    ) -> str: ...

    def create_sample_type(
        self,
        *,
        title: str,
        project_id: str,
        attributes: list[dict[str, Any]],
    ) -> str: ...

    def find_investigation_id_by_title(
        self, title: str, *, project_id: str
    ) -> str | None:
        """An existing Investigation with this title in the project, if any."""
        ...

    def find_study_id_by_title(
        self, title: str, *, investigation_id: str
    ) -> str | None:
        """An existing Study with this title under the investigation, if any."""
        ...

    def find_assay_id_by_title(self, title: str, *, study_id: str) -> str | None:
        """An existing Assay with this title under the study, if any."""
        ...

    def find_sample_id_by_title(self, title: str, *, sample_type_id: str) -> str | None:
        """An existing Sample with this title of the sample type, if any."""
        ...

    def find_sample_type_id_by_title(
        self, title: str, *, project_id: str | None = None
    ) -> str | None: ...

    def sample_attribute_type_id(self, title: str) -> str: ...

    def create_data_file(
        self,
        *,
        title: str,
        project_id: str,
        url: str,
        original_filename: str,
        description: str | None = None,
        assay_ids: list[str | int] | None = None,
    ) -> str: ...
