"""DCAT intermediate representation.

Plain models for the DCAT classes a metaseed dataset maps onto. This is the
serializer's input: the RDF/JSON-LD/Turtle binding (#28) consumes these, so no
RDF dependency lives here. Field names follow DCAT/DCAT-AP property names.

See docs/architecture/dcat.md and discussion #25.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

#: The ADMS status vocabulary, the values ``adms:status`` takes, by key.
ADMS_STATUS: dict[str, str] = {
    "completed": "http://purl.org/adms/status/Completed",
    "deprecated": "http://purl.org/adms/status/Deprecated",
    "underDevelopment": "http://purl.org/adms/status/UnderDevelopment",
    "withdrawn": "http://purl.org/adms/status/Withdrawn",
}


class DcatAgent(BaseModel):
    """A `foaf:Agent` (e.g. a `dct:publisher`)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: str | None = None
    uri: str | None = None


class DcatContactPoint(BaseModel):
    """A `dcat:contactPoint` (vCard)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: str | None = None


class DcatChecksum(BaseModel):
    """A `spdx:Checksum` for a distribution (`dcat:Checksum` in DCAT 3)."""

    model_config = ConfigDict(extra="forbid")

    algorithm: str
    value: str


class DcatDistribution(BaseModel):
    """A `dcat:Distribution` — an accessible form of a dataset."""

    model_config = ConfigDict(extra="forbid")

    access_url: str | None = None
    download_url: str | None = None
    media_type: str | None = None
    format: str | None = None
    title: str | None = None
    description: str | None = None
    byte_size: int | None = None
    checksum: DcatChecksum | None = None
    license: str | None = None


class DcatDataset(BaseModel):
    """A `dcat:Dataset`."""

    model_config = ConfigDict(extra="forbid")

    identifier: str | None = None
    title: str | None = None
    description: str | None = None
    issued: str | None = None
    modified: str | None = None
    license: str | None = None
    access_rights: str | None = None
    publisher: DcatAgent | None = None
    contact_point: DcatContactPoint | None = None
    landing_page: str | None = None
    keywords: list[str] = []
    themes: list[str] = []
    related: list[str] = []
    version: str | None = None
    """`dcat:version` — the label of the snapshot this card describes."""
    is_version_of: str | None = None
    """`dct:isVersionOf` — set only when this dataset is a copy of another record."""
    previous_version: str | None = None
    """`dcat:previousVersion` — the landing page of the release before this one."""
    creators: list[DcatAgent] = []
    """`dct:creator` — the people credited for this dataset, in citation order."""
    status: str | None = None
    """`adms:status` — a key of :data:`ADMS_STATUS`."""
    source: list[str] = []
    """Records this dataset was derived from.

    Drives both `dct:source` and `prov:wasDerivedFrom`, which say the same thing
    to different readers. One field rather than two, so they cannot disagree.
    A derivation is not an identity: an imported dataset records the origin here
    and keeps its own `identifier`.
    """
    conforms_to: list[str] = []
    """`dct:conformsTo` — standards the content follows (e.g. MIAPPE, ISA)."""
    distributions: list[DcatDistribution] = []


class DcatCatalog(BaseModel):
    """A `dcat:Catalog` — a curated collection of dataset metadata."""

    model_config = ConfigDict(extra="forbid")

    identifier: str | None = None
    title: str | None = None
    description: str | None = None
    publisher: DcatAgent | None = None
    homepage: str | None = None
    datasets: list[DcatDataset] = []
