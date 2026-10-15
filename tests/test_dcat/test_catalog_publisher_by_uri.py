"""A catalog publisher identified only by URI or email is serialized.

The dataset path accepted a publisher with a name, URI or email; the catalog
path still required a name, so the same publisher appeared on a dataset and
vanished from its catalog.
"""

from __future__ import annotations

import pytest
from rdflib import URIRef
from rdflib.namespace import DCTERMS

from metaseed.dcat.model import DcatAgent, DcatCatalog
from metaseed.dcat.serialize import to_graph


@pytest.mark.parametrize(
    "agent",
    [DcatAgent(uri="https://example.org/org"), DcatAgent(email="data@example.org")],
)
def test_a_catalog_publisher_without_a_name_is_kept(agent: DcatAgent) -> None:
    graph = to_graph(
        DcatCatalog(identifier="https://example.org/catalog", publisher=agent)
    )

    assert list(graph.objects(URIRef("https://example.org/catalog"), DCTERMS.publisher))
