"""Shared helpers for the repository integration mappers/exporters.

Public because four adapters depend on it. A private module shared across
sibling packages hides a real dependency: nothing signals that changing it
affects ena, pride, brapi and metabolights at once.

The ena/pride/brapi/metabolights adapters each build plain dicts from an external
API and drop empty values so that a field the source omitted is *absent* rather
than present-but-blank. This is the one piece of that logic they genuinely share.
"""

from __future__ import annotations

from typing import Any


def clean(data: dict[str, Any]) -> dict[str, Any]:
    """Drop empty values so a missing field is absent, not blank.

    Removes keys whose value is ``None``, ``""``, ``[]``, or ``{}``. Falsy but
    meaningful values (``0``, ``0.0``, ``False``) are kept.
    """
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def clean_all(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean each dict and drop any that become empty."""
    return [cleaned for row in rows if (cleaned := clean(row))]
