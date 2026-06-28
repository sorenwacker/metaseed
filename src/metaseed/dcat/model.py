"""DCAT intermediate representation.

Plain models for the DCAT classes a metaseed dataset maps onto. This is the
serializer's input: the RDF/JSON-LD/Turtle binding (#28) consumes these, so no
RDF dependency lives here. Field names follow DCAT/DCAT-AP property names.

See docs/architecture/dcat.md and discussion #25.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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
