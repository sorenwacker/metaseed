"""Profile version format and content hashing.

A profile spec carries two unrelated version fields, and confusing them is easy:

* ``ProfileSpec.spec_version`` versions the **specification format** -- the YAML
  vocabulary metaseed understands. It changes when metaseed gains a construct.
* ``ProfileSpec.version`` versions the **profile** -- one metadata standard such
  as MIAPPE. It changes when the standard's entities, fields, or constraints
  change. This module governs that field only.

A profile version is ``MAJOR.MINOR``. MAJOR means a dataset that validated under
the previous version may fail under this one; MINOR means every dataset valid
under the previous version is still valid. Whether a given edit forces a MAJOR
bump is decided by :mod:`metaseed.specs.compare`, not here.

The content hash answers a different question. A version number says how a spec
relates to its predecessor; it does not identify a spec. Two files can both
declare ``cinema`` ``1.1`` and hold different content, so the hash gives each
exact document a stable name.

See `docs/api/schema-specs.md#profile-versioning`.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec

PROFILE_VERSION_PATTERN: re.Pattern[str] = re.compile(r"^\d+\.\d+$")
"""The only accepted shape of ``ProfileSpec.version``: ``MAJOR.MINOR``.

There is no patch component. A spec has no implementation that can be fixed
independently of its content: every content change either keeps existing
datasets valid or does not, and that is what the two components record.
"""

HASH_ALGORITHM = "sha256"
"""Digest used by :func:`content_hash`, named in the returned value."""

SHORT_HASH_DIGITS = 12
"""Hex digits kept by :func:`short_hash`. Display only -- compare on the full hash."""


def check_profile_version(value: str) -> str | None:
    """Report why ``value`` is not a valid profile version.

    Args:
        value: The candidate ``ProfileSpec.version``.

    Returns:
        A message naming the offending value and the rule, or None if valid.
    """
    if PROFILE_VERSION_PATTERN.match(value):
        return None
    return (
        f"profile version {value!r} is not MAJOR.MINOR: it must match "
        f"{PROFILE_VERSION_PATTERN.pattern} (for example '1.0' or '2.1'). "
        "MAJOR means datasets valid under the previous version may fail; MINOR "
        "means they stay valid. The specification format version is the "
        "separate 'spec_version' field."
    )


def require_profile_version(value: str) -> str:
    """Return ``value`` if it is a valid profile version.

    Args:
        value: The candidate ``ProfileSpec.version``.

    Returns:
        The unchanged value.

    Raises:
        ValueError: If the value is not ``MAJOR.MINOR``.
    """
    problem = check_profile_version(value)
    if problem is not None:
        raise ValueError(problem)
    return value


def parse_profile_version(value: str) -> tuple[int, int]:
    """Split a profile version into its ``(major, minor)`` integers.

    Args:
        value: A profile version.

    Returns:
        The two components as integers, so versions order numerically
        (``1.10`` is after ``1.9``, not before it).

    Raises:
        ValueError: If the value is not ``MAJOR.MINOR``.
    """
    major, minor = require_profile_version(value).split(".")
    return int(major), int(minor)


def declared_bump(old_version: str, new_version: str) -> str:
    """Classify what a pair of version strings *claims* about compatibility.

    This reads the numbers only. Whether the claim is honest is what
    :func:`metaseed.specs.compare.required_bump` decides from the content.

    Args:
        old_version: The version being superseded.
        new_version: The version superseding it.

    Returns:
        ``"major"``, ``"minor"``, ``"none"`` (identical), or ``"downgrade"``
        (the new version sorts before the old one).

    Raises:
        ValueError: If either value is not ``MAJOR.MINOR``.
    """
    old = parse_profile_version(old_version)
    new = parse_profile_version(new_version)
    if new == old:
        return "none"
    if new < old:
        return "downgrade"
    return "major" if new[0] > old[0] else "minor"


def canonical_json(spec: ProfileSpec) -> str:
    """Serialize a spec to its canonical form, the input to :func:`content_hash`.

    The canonicalization rule, and why each part of it is needed for the hash to
    be stable across a YAML round trip:

    * ``mode="json"`` -- enums and other rich types become JSON scalars, so a
      spec built in memory matches the same spec loaded from a file.
    * ``exclude_none=True`` -- in a profile YAML an omitted optional key and an
      explicit ``null`` state the same thing, so they must not hash differently.
      This is also what ``SpecBuilder.to_yaml`` writes, which is what makes the
      round trip exact rather than approximately equal.
    * Defaults kept -- a field written ``required: false`` and one omitting
      ``required`` both load as ``False`` and so already agree; keeping defaults
      means the hash reflects the loaded spec rather than the authoring style.
    * ``sort_keys=True`` -- mapping key order in the source YAML is not content.
      Reordering ``entities``, or the keys within a field, does not change the
      hash. Sequences (notably ``fields``) keep their order, because field order
      drives form and template layout and is therefore content.

    Args:
        spec: The profile spec to canonicalize.

    Returns:
        A deterministic JSON document.
    """
    return json.dumps(
        spec.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def content_hash(spec: ProfileSpec) -> str:
    """Return the canonical content hash of a spec.

    Args:
        spec: The profile spec to hash.

    Returns:
        ``"sha256:<64 hex digits>"``. Equal hashes mean identical content.
    """
    digest = hashlib.sha256(canonical_json(spec).encode("utf-8")).hexdigest()
    return f"{HASH_ALGORITHM}:{digest}"


def short_hash(spec: ProfileSpec) -> str:
    """Return an abbreviated content hash for display.

    Args:
        spec: The profile spec to hash.

    Returns:
        ``"sha256:<first 12 hex digits>"``. For logs and labels; compare on
        :func:`content_hash`.
    """
    return content_hash(spec)[: len(HASH_ALGORITHM) + 1 + SHORT_HASH_DIGITS]
