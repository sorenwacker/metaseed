"""What a repository record says about its terms becomes a resolvable license.

The inputs are the values read from live records on 261128 (see
docs/architecture/integration-adapters.md, "Origin and license").
"""

from __future__ import annotations

import pytest

from metaseed.provenance import EBI_TERMS_OF_USE, normalize_license


@pytest.mark.parametrize(
    ("stated", "stored"),
    [
        ("Creative Commons Public Domain (CC0)", "CC0-1.0"),
        ("https://creativecommons.org/licenses/by/4.0", "CC-BY-4.0"),
        ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
        ("CC-BY-4.0", "CC-BY-4.0"),
        ("cc0-1.0", "CC0-1.0"),
        ("EBI terms of use", EBI_TERMS_OF_USE),
        ("EMBL-EBI Terms of Use", EBI_TERMS_OF_USE),
        ("https://www.ebi.ac.uk/about/terms-of-use/", EBI_TERMS_OF_USE),
        ("https://data.example.org/terms", "https://data.example.org/terms"),
    ],
)
def test_a_known_or_resolvable_statement_is_kept(stated: str, stored: str) -> None:
    assert normalize_license(stated) == stored


@pytest.mark.parametrize(
    "stated", [None, "", "   ", "free for academic use", "see paper"]
)
def test_a_statement_nobody_can_resolve_is_dropped(stated: str | None) -> None:
    assert normalize_license(stated) is None
