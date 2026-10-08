"""A BrAPI address must be the server's base URL, and one that is not is refused.

Reported: a trial's own address was entered,
``.../brapi/v2/trials/<trialDbId>``. The importer appended ``/studies`` to it,
the server ignored the trial and answered with every study it holds (2763 on
FAIDARE), and the import paged through them and then asked for each study's
observation units, for hours. A single trial cannot be imported yet, so the
address is refused before anything is fetched, with what to enter instead.
"""

from __future__ import annotations

import pytest

from metaseed.brapi import import_brapi

SERVER = "https://server.example.org/brapi/v2"


class _NeverAsked:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the server was asked for {name}")


@pytest.mark.parametrize(
    "address",
    [
        f"{SERVER}/trials/dXJuOnRyaWFsLzQy%3D",
        f"{SERVER}/trials/42/",
        f"{SERVER}/studies/7",
        f"{SERVER}/studies",
    ],
)
def test_an_address_below_the_base_url_is_refused_before_any_request(
    address: str,
) -> None:
    with pytest.raises(ValueError, match=r"base URL.*/brapi/v2") as refused:
        import_brapi(address, client=_NeverAsked())  # type: ignore[arg-type]

    assert SERVER in str(refused.value), (
        "the message names the address to enter instead"
    )


def test_the_base_url_is_accepted() -> None:
    class _Empty:
        def studies(self) -> list:
            return []

        def germplasm(self) -> list:
            return []

    client = import_brapi(SERVER + "/", client=_Empty())  # type: ignore[arg-type]

    assert client.profile == "miappe"
