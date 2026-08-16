"""A spec name must not be able to shape the response header (260816 review).

`export_yaml` built `Content-Disposition: attachment; filename="{name}"` from
the spec's own name, which a user types. A name containing a quote closes the
filename and lets the rest be read as further header content; a name containing
a newline splits the header outright.

The name is the user's to choose, so it is sanitised at the boundary rather
than restricted at the source.
"""

from __future__ import annotations

from metaseed.ui.spec_builder.routes_export import _safe_filename


def test_a_quote_cannot_close_the_filename() -> None:
    assert '"' not in _safe_filename('evil"; drop=1')


def test_a_newline_cannot_split_the_header() -> None:
    cleaned = _safe_filename("evil\r\nX-Injected: yes")

    assert "\n" not in cleaned
    assert "\r" not in cleaned


def test_an_ordinary_name_survives() -> None:
    assert _safe_filename("wheat-drought_2024") == "wheat-drought_2024"


def test_an_empty_name_still_yields_something() -> None:
    assert _safe_filename("") == "profile"
