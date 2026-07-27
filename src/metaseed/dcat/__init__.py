"""DCAT export adapter for metaseed.

Maps a metaseed dataset onto the DCAT (Data Catalog Vocabulary) model so it can
be published for discovery. This subpackage holds the intermediate model
(:mod:`metaseed.dcat.model`), the resolver that maps a dataset onto it
(:mod:`metaseed.dcat.resolver`), the publication seam a host binds a card to
where it is served (:mod:`metaseed.dcat.publication`), and RDF/JSON-LD/Turtle
serialization (:mod:`metaseed.dcat.serialize`).

Everything exported here is dependency-free. ``serialize`` and ``export`` are
imported lazily, never from this module, so the model stays usable without the
``metaseed[dcat]`` extra.
"""

from metaseed.dcat.model import (
    DcatAgent,
    DcatCatalog,
    DcatChecksum,
    DcatContactPoint,
    DcatDataset,
    DcatDistribution,
)
from metaseed.dcat.publication import (
    PublicationContext,
    build_published_dataset,
    origin_url,
    spdx_license_uri,
)
from metaseed.dcat.resolver import build_dcat_catalog, build_dcat_dataset

__all__ = [
    "DcatAgent",
    "DcatCatalog",
    "DcatChecksum",
    "DcatContactPoint",
    "DcatDataset",
    "DcatDistribution",
    "PublicationContext",
    "build_dcat_catalog",
    "build_dcat_dataset",
    "build_published_dataset",
    "origin_url",
    "spdx_license_uri",
]
