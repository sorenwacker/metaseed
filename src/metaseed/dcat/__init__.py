"""DCAT export adapter for metaseed.

Maps a metaseed dataset onto the DCAT (Data Catalog Vocabulary) model so it can
be published for discovery. This subpackage holds the intermediate model
(:mod:`metaseed.dcat.model`), the resolver that maps a dataset onto it
(:mod:`metaseed.dcat.resolver`), and RDF/JSON-LD/Turtle serialization
(:mod:`metaseed.dcat.serialize`).
"""

from metaseed.dcat.model import (
    DcatAgent,
    DcatCatalog,
    DcatChecksum,
    DcatContactPoint,
    DcatDataset,
    DcatDistribution,
)
from metaseed.dcat.resolver import build_dcat_catalog, build_dcat_dataset

__all__ = [
    "DcatAgent",
    "DcatCatalog",
    "DcatChecksum",
    "DcatContactPoint",
    "DcatDataset",
    "DcatDistribution",
    "build_dcat_catalog",
    "build_dcat_dataset",
]
