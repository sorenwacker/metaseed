"""An ENA import records its origin, under the INSDC policy ENA records carry no license of their own."""

from __future__ import annotations

import datetime as dt

from metaseed.ena import import_accession
from metaseed.provenance import INSDC_POLICY

from .test_import import _mock_client


def test_an_ena_import_records_where_it_came_from() -> None:
    before = dt.datetime.now(dt.UTC)
    origin = import_accession("PRJEB10000", client=_mock_client()).origin

    assert origin is not None
    assert origin.repository == "ENA"
    assert origin.identifier == "PRJEB10000"
    assert origin.record_url == "https://www.ebi.ac.uk/ena/browser/view/PRJEB10000"
    assert origin.license == INSDC_POLICY
    assert origin.retrieved_at >= before
