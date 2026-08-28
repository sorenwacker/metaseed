"""The shape every adapter's connection check answers in.

The Plugins page renders one check the same way whatever the adapter, so the
result type lives here rather than in each adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Bound on a probe: a misconfigured host must not stall a settings page.
PROBE_TIMEOUT = 5.0


@dataclass(frozen=True)
class ConnectionCheck:
    """Outcome of one connection check."""

    ok: bool
    message: str
    """One sentence for the user: what the connection reaches, or why it fails."""
    projects: list[tuple[str, str]] = field(default_factory=list)
    """``(id, title)`` of what the credential may write into; empty when the adapter offers no choice, or on failure."""
