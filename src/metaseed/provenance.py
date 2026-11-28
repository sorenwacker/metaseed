"""Where an imported dataset came from, and under which terms.

Nothing in a dataset's entities says that it was imported: a dataset authored
here for submission carries an accession too. An importer therefore records the
origin beside the entities, as :class:`ImportOrigin` on the client it returns,
and a host stores it. See ``docs/architecture/integration-adapters.md``.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

#: The terms of the INSDC databases (ENA, GenBank, DDBJ), whose records name no
#: license of their own.
INSDC_POLICY = "https://www.insdc.org/policy/"

#: The EMBL-EBI terms of use, which PRIDE and MetaboLights records name in words.
EBI_TERMS_OF_USE = "https://www.ebi.ac.uk/about/terms-of-use/"

# Statements of known licenses, compared lowercased with a trailing slash and
# the scheme removed, mapped to their SPDX identifier or terms URL.
_KNOWN: dict[str, str] = {
    "creative commons public domain (cc0)": "CC0-1.0",
    "creativecommons.org/publicdomain/zero/1.0": "CC0-1.0",
    "creativecommons.org/licenses/by/4.0": "CC-BY-4.0",
    "creativecommons.org/licenses/by-sa/4.0": "CC-BY-SA-4.0",
    "creativecommons.org/licenses/by-nc/4.0": "CC-BY-NC-4.0",
    "ebi terms of use": EBI_TERMS_OF_USE,
    "embl-ebi terms of use": EBI_TERMS_OF_USE,
    "www.ebi.ac.uk/about/terms-of-use": EBI_TERMS_OF_USE,
}

# SPDX identifiers a record may state as such, by their lowercased form.
_SPDX = {
    spdx.lower(): spdx
    for spdx in ("CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC-BY-NC-4.0")
}

_SCHEME = re.compile(r"^https?://")


def normalize_license(stated: str | None) -> str | None:
    """The license to store for what a record states about its terms.

    Args:
        stated: The record's license text or URL, as the repository gives it.

    Returns:
        An SPDX identifier for a known license, the EMBL-EBI terms URL under
        either name EMBL-EBI repositories use, any other URL unchanged, or
        ``None`` for text nobody can resolve.
    """
    text = (stated or "").strip()
    if not text:
        return None
    key = _SCHEME.sub("", text.lower()).rstrip("/")
    if key in _KNOWN:
        return _KNOWN[key]
    if key in _SPDX:
        return _SPDX[key]
    if _SCHEME.match(text):
        return text
    return None


@dataclass(frozen=True)
class ImportOrigin:
    """The public record a dataset was imported from."""

    repository: str
    """The repository's name as shown to people, e.g. ``ENA``."""
    identifier: str
    """What was imported: an accession, or a BrAPI address."""
    record_url: str | None
    """A link to the record, or ``None`` where the repository has no page for it."""
    license: str | None
    """An SPDX identifier or terms URL, attached by the importer; ``None`` when
    neither the record nor the repository states terms."""
    retrieved_at: dt.datetime
    """When the record was read, in UTC."""

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable form, for a host to store."""
        return {
            "repository": self.repository,
            "identifier": self.identifier,
            "record_url": self.record_url,
            "license": self.license,
            "retrieved_at": self.retrieved_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportOrigin:
        """Rebuild an origin from :meth:`to_dict`'s output."""
        return cls(
            repository=data["repository"],
            identifier=data["identifier"],
            record_url=data.get("record_url"),
            license=data.get("license"),
            retrieved_at=dt.datetime.fromisoformat(data["retrieved_at"]),
        )


def imported_now(
    repository: str,
    identifier: str,
    *,
    record_url: str | None,
    stated_license: str | None,
    repository_terms: str | None,
) -> ImportOrigin:
    """The origin of a record read just now.

    Args:
        repository: The repository's name as shown to people.
        identifier: What was imported.
        record_url: A link to the record.
        stated_license: What the record says about its terms, if anything.
        repository_terms: The terms the importer declares for every record of
            its repository, used when the record states none it can resolve.
    """
    return ImportOrigin(
        repository=repository,
        identifier=identifier,
        record_url=record_url,
        license=normalize_license(stated_license) or repository_terms,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
