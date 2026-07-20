"""Push ISA content into a FAIRDOM-SEEK instance via its JSON:API.

:func:`push_minimal_experiment` creates one complete experiment — an
Investigation with a Study, an Assay, a Sample Type, and a Sample — threading
the ids SEEK returns so the hierarchy links up. It is the smallest end-to-end
proof that a metaseed → SEEK push works, and the seed for the fuller ISA-stream
mapper (see the ``metaseed[seek]`` roadmap in GitHub discussion #26).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.seek.client import SeekClient


@dataclass(frozen=True)
class ExperimentIds:
    """The ids SEEK assigned to each resource of a pushed experiment."""

    project: str
    investigation: str
    study: str
    assay: str
    sample_type: str
    sample: str


def push_minimal_experiment(
    client: SeekClient,
    *,
    project_id: str | None = None,
    title_prefix: str = "metaseed spike",
) -> ExperimentIds:
    """Create a minimal Investigation→Study→Assay + Sample Type + Sample.

    Args:
        client: A configured :class:`~metaseed.seek.client.SeekClient`.
        project_id: Project to attach content to; defaults to the instance's
            first project.
        title_prefix: Prefix for the created resources' titles.

    Returns:
        The ids SEEK assigned to each created resource.
    """
    project = project_id or client.default_project_id()

    investigation = client.create_investigation(
        title=f"{title_prefix} investigation", project_id=project
    )
    study = client.create_study(
        title=f"{title_prefix} study", investigation_id=investigation
    )
    assay = client.create_assay(title=f"{title_prefix} assay", study_id=study)

    string_type = client.sample_attribute_type_id("String")
    from metaseed.seek.payloads import sample_attribute

    sample_type = client.create_sample_type(
        title=f"{title_prefix} sample type",
        project_id=project,
        attributes=[
            sample_attribute(
                title="name", attribute_type_id=string_type, required=True, is_title=True
            )
        ],
    )
    sample = client.create_sample(
        sample_type_id=sample_type,
        project_id=project,
        data={"name": f"{title_prefix} sample 1"},
    )

    return ExperimentIds(
        project=project,
        investigation=investigation,
        study=study,
        assay=assay,
        sample_type=sample_type,
        sample=sample,
    )
