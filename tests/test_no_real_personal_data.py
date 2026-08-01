"""Gate on the "no real personal data in examples or fixtures" rule.

CLAUDE.md requires that fixtures and shipped example data carry synthetic
identities only. That was prose, enforced by review, and review missed a set of
recorded ISA-Tab fixtures that kept their submitters' telephone numbers and
street addresses long after their names had been replaced.

Two categories are checked here because both are decidable from the file alone:
a contact email outside the reserved example domains, and a non-empty telephone
number. Names, affiliations and ORCIDs are deliberately not checked — a gate
cannot tell an invented person from a real one, so those stay a review concern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# The data a reader could mistake for a real record: recorded API responses and
# the example datasets that ship inside the package.
DATA_ROOTS = (
    REPO_ROOT / "tests",
    REPO_ROOT / "src" / "metaseed" / "examples",
)

# RFC 2606 reserves these for documentation; nothing routes to them.
RESERVED_EMAIL_DOMAINS = ("example.org", "example.com", "example.net")

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# ISA-Tab ``Person Phone``/``Person Fax`` columns and the JSON/YAML equivalents.
# Only a value that follows the key on the same line is considered, so an
# accession or a checksum elsewhere in the file cannot look like a number.
_PHONE = re.compile(
    r"""(?ix)
    (?:person[ _]?)?(?:phone|fax|telephone)   # the key
    (?:"|')?\s*[:\t]\s*                       # separator (JSON/YAML colon or ISA-Tab tab)
    (?:"|')?
    (?P<value>[0-9][0-9()\-.\s+]{5,})         # a number-shaped value
    """
)


def _data_files() -> list[Path]:
    """Every fixture and shipped example file worth scanning."""
    suffixes = {".json", ".yaml", ".yml", ".txt", ".tsv", ".csv", ".xml"}
    files = []
    for root in DATA_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if "fixtures" in path.parts or root.name == "examples":
                files.append(path)
    return sorted(files)


DATA_FILES = _data_files()


def test_the_scan_covers_something() -> None:
    """A gate over an empty file list would pass regardless of the contents."""
    assert len(DATA_FILES) > 5, f"expected fixture data to scan, found {DATA_FILES}"


@pytest.mark.parametrize(
    "path", DATA_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_contact_emails_use_a_reserved_domain(path: Path) -> None:
    """A recorded record must not redistribute its submitters' email addresses.

    Importing a public record does not license republishing the people in it;
    de-identify on the way into the repository.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    offenders = [
        address
        for address in _EMAIL.findall(text)
        if not address.lower().endswith(RESERVED_EMAIL_DOMAINS)
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} carries non-synthetic email(s): "
        f"{sorted(set(offenders))}. Use an @example.org address."
    )


@pytest.mark.parametrize(
    "path", DATA_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_telephone_numbers(path: Path) -> None:
    """Contact numbers are personal data and are never needed by a test.

    Nothing in the suite asserts on a phone number, so the correct synthetic
    value is an empty one.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    offenders = [match.group("value").strip() for match in _PHONE.finditer(text)]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} carries telephone number(s): "
        f"{sorted(set(offenders))}. Leave the field empty."
    )
